"""Provider layer: workflow templates, the fake and ComfyUI adapters, the engine gate and
the generation driver (ADR-006, FR-043, RULE-013, NFR-008)."""

import json
import struct
import zlib
from typing import Any

import httpx
import pytest
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.errors import DomainError
from asset_studio.modules.jobs import service as jobs
from asset_studio.modules.jobs.runner import JobContext, Runner
from asset_studio.modules.providers.base import GenerationRequest, ProviderError
from asset_studio.modules.providers.comfyui import ComfyUIProvider
from asset_studio.modules.providers.engine import EngineMonitor, run_generation
from asset_studio.modules.providers.fake import FakeProvider
from asset_studio.modules.providers.hostagent import HostAgentClient
from asset_studio.modules.providers.workflows import InputSpec, WorkflowTemplate
from tests.conftest import bound_sessions
from tests.test_jobs import InlineExecutor

GRAPH = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 0, "steps": 20, "model": ["4", 0]}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["4", 1]}},
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 512, "height": 512, "batch_size": 1},
    },
}
T2I = WorkflowTemplate(
    id="t2i-basic",
    version=1,
    graph=GRAPH,
    inputs={
        "prompt": InputSpec("string", (("6", "text"),)),
        "seed": InputSpec("integer", (("3", "seed"),), default=0, minimum=0),
        "steps": InputSpec("integer", (("3", "steps"),), required=False, minimum=1, maximum=150),
        "width": InputSpec("integer", (("5", "width"),), default=64, minimum=16, maximum=2048),
        "height": InputSpec("integer", (("5", "height"),), default=32, minimum=16, maximum=2048),
    },
)


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


# --- workflow templates -------------------------------------------------------------------


def test_render_places_inputs_without_touching_the_template() -> None:
    graph = T2I.render({"prompt": "a squat", "seed": 7})
    assert graph["6"]["inputs"]["text"] == "a squat"
    assert graph["3"]["inputs"]["seed"] == 7
    assert graph["3"]["inputs"]["steps"] == 20  # optional and not given: graph value kept
    assert GRAPH["6"]["inputs"]["text"] == ""


@pytest.mark.parametrize(
    ("values", "bad"),
    [
        ({}, "prompt"),
        ({"prompt": "x", "nodes": 1}, "nodes"),
        ({"prompt": "x", "seed": "7"}, "seed"),
        ({"prompt": "x", "seed": True}, "seed"),
        ({"prompt": "x", "steps": 500}, "steps"),
    ],
)
def test_render_rejects_bad_inputs(values: dict[str, Any], bad: str) -> None:
    with pytest.raises(DomainError) as err:
        T2I.render(values)
    assert err.value.code == "WORKFLOW_INPUT_INVALID"
    assert err.value.extra["inputs"] == [bad]


def test_template_targets_must_exist() -> None:
    with pytest.raises(ValueError, match="targets missing"):
        WorkflowTemplate("x", 1, GRAPH, {"cfg": InputSpec("number", (("3", "cfg"),))})


# --- fake provider ------------------------------------------------------------------------


class Sink:
    def __init__(self, cancel_after: int | None = None) -> None:
        self.reports: list[dict[str, Any]] = []
        self.checks = 0
        self.cancel_after = cancel_after

    def progress(self, **data: Any) -> None:
        self.reports.append(data)

    def check(self) -> None:
        self.checks += 1
        if self.cancel_after is not None and self.checks > self.cancel_after:
            raise RuntimeError("cancelled by the user")


def test_fr030_fake_generation_end_to_end() -> None:
    provider = FakeProvider(steps=2)
    request = GenerationRequest(T2I, {"prompt": "push-up", "seed": 3, "width": 40})
    sink = Sink()
    files = run_generation(provider, request, sink, sleep=lambda _: None)
    assert [f.mime for f in files] == ["image/png"]
    assert _png_size(files[0].data) == (40, 32)
    assert [r["step"] for r in sink.reports] == [1, 2]


def test_fake_output_is_deterministic_per_seed() -> None:
    def image(seed: int) -> bytes:
        files = run_generation(
            FakeProvider(steps=0),
            GenerationRequest(T2I, {"prompt": "x", "seed": seed}),
            Sink(),
            sleep=lambda _: None,
        )
        return files[0].data

    assert image(1) == image(1)
    assert image(1) != image(2)
    assert zlib.decompress(image(1)[41:-12])  # IDAT holds valid deflate data


def test_engine_failure_becomes_a_stable_error() -> None:
    provider = FakeProvider(steps=1, fail_with="CUDA out of memory")
    with pytest.raises(ProviderError) as err:
        run_generation(
            provider, GenerationRequest(T2I, {"prompt": "x"}), Sink(), sleep=lambda _: None
        )
    assert (err.value.code, err.value.detail) == ("GENERATION_FAILED", "CUDA out of memory")


def test_cancelling_the_job_cancels_the_engine_job() -> None:
    provider = FakeProvider(steps=10)
    with pytest.raises(RuntimeError):
        run_generation(
            provider,
            GenerationRequest(T2I, {"prompt": "x"}),
            Sink(cancel_after=2),
            sleep=lambda _: None,
        )
    (ref,) = provider._jobs
    assert provider.progress(ref).error == "cancelled"


# --- engine gate (RULE-013) ---------------------------------------------------------------


def test_gate_reports_unavailable_engine_and_caches_health() -> None:
    now = [0.0]
    provider = FakeProvider(available=False)
    monitor = EngineMonitor(provider, ttl=5, clock=lambda: now[0])
    assert monitor.gate() == "ENGINE_UNAVAILABLE"
    provider.available = True
    assert monitor.gate() == "ENGINE_UNAVAILABLE"  # cached
    now[0] = 6
    assert monitor.gate() is None


def test_rule013_gpu_jobs_wait_while_the_engine_is_down(
    connection: Connection, db: Session
) -> None:
    gpu = jobs.enqueue(db, "generate", {}, actor="user")
    cpu = jobs.enqueue(db, "process", {}, actor="user")
    db.commit()
    provider = FakeProvider(available=False)
    monitor = EngineMonitor(provider, ttl=0)
    ran: list[str] = []

    def handle(ctx: JobContext) -> None:
        ran.append(ctx.kind)

    runner = Runner(
        bound_sessions(connection),
        "w",
        {"generate": handle, "process": handle},
        gates={"gpu": monitor.gate},
        executor=InlineExecutor(),
    )
    runner.tick()
    held = jobs.get_job(db, gpu.id)
    assert (held.state, held.wait_reason) == ("queued", "ENGINE_UNAVAILABLE")
    assert jobs.get_job(db, cpu.id).state == "completed"

    provider.available = True  # the user starts the engine
    runner.tick()
    assert jobs.get_job(db, gpu.id).state == "completed"
    assert ran == ["process", "generate"]


# --- ComfyUI adapter ----------------------------------------------------------------------


class FakeComfy:
    """Just enough of ComfyUI's HTTP API for the adapter."""

    def __init__(self) -> None:
        self.prompts: list[dict[str, Any]] = []
        self.history: dict[str, Any] = {}
        self.running: list[str] = []
        self.pending: list[str] = []
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        self.calls.append((request.method, path, body))
        if path == "/system_stats":
            return httpx.Response(
                200,
                json={
                    "system": {"comfyui_version": "0.46.0", "os": "nt"},
                    "devices": [
                        {
                            "name": "cuda:0 NVIDIA GeForce RTX",
                            "vram_total": 6 * 2**30,
                            "vram_free": 5 * 2**30,
                        }
                    ],
                },
            )
        if path == "/prompt":
            if body["prompt"]["6"]["inputs"]["text"] == "broken":
                return httpx.Response(
                    400,
                    json={
                        "error": {"message": "Prompt outputs failed validation"},
                        "node_errors": {"6": {}},
                    },
                )
            self.prompts.append(body)
            self.pending.append("p1")
            return httpx.Response(200, json={"prompt_id": "p1", "number": 1, "node_errors": {}})
        if path.startswith("/history/"):
            ref = path.rsplit("/", 1)[1]
            return httpx.Response(200, json={ref: self.history[ref]} if ref in self.history else {})
        if path == "/queue" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "queue_running": [[0, r, {}, {}, []] for r in self.running],
                    "queue_pending": [[1, r, {}, {}, []] for r in self.pending],
                },
            )
        if path == "/view":
            return httpx.Response(
                200, content=b"\x89PNG-data", headers={"content-type": "image/png"}
            )
        return httpx.Response(200, json={})


def _comfy(fake: FakeComfy) -> ComfyUIProvider:
    client = httpx.Client(base_url="http://comfy", transport=httpx.MockTransport(fake))
    return ComfyUIProvider("http://comfy", client=client)


def test_comfyui_health_reports_version_and_vram() -> None:
    health = _comfy(FakeComfy()).health()
    assert (health.available, health.version) == (True, "0.46.0")
    assert health.devices[0].vram_total_mb == 6144
    assert health.devices[0].vram_free_mb == 5120


def test_comfyui_down_is_engine_unavailable() -> None:
    def refuse(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = httpx.Client(base_url="http://comfy", transport=httpx.MockTransport(refuse))
    provider = ComfyUIProvider("http://comfy", client=client)
    health = provider.health()
    assert (health.available, health.reason) == (False, "ENGINE_UNAVAILABLE")
    with pytest.raises(ProviderError) as err:
        provider.submit(GenerationRequest(T2I, {"prompt": "x"}))
    assert (err.value.code, err.value.status) == ("ENGINE_UNAVAILABLE", 503)


def test_comfyui_submit_progress_and_collect() -> None:
    fake = FakeComfy()
    provider = _comfy(fake)
    ref = provider.submit(GenerationRequest(T2I, {"prompt": "lunge", "seed": 11}))
    sent = fake.prompts[0]
    assert sent["client_id"] == provider.client_id
    assert sent["prompt"]["6"]["inputs"]["text"] == "lunge"
    assert sent["prompt"]["3"]["inputs"]["seed"] == 11

    assert provider.progress(ref).state == "queued"
    fake.pending, fake.running = [], [ref]
    assert provider.progress(ref).state == "running"
    fake.running = []
    fake.history[ref] = {
        "status": {"status_str": "success", "completed": True, "messages": []},
        "outputs": {
            "9": {
                "images": [
                    {"filename": "as_00001_.png", "subfolder": "", "type": "output"},
                    {"filename": "preview.png", "subfolder": "", "type": "temp"},
                ]
            }
        },
    }
    assert provider.progress(ref).state == "completed"
    files = provider.collect(ref)
    assert [(f.filename, f.mime) for f in files] == [("as_00001_.png", "image/png")]


def test_comfyui_rejection_and_execution_errors() -> None:
    fake = FakeComfy()
    provider = _comfy(fake)
    with pytest.raises(ProviderError) as err:
        provider.submit(GenerationRequest(T2I, {"prompt": "broken"}))
    assert err.value.code == "ENGINE_REJECTED"
    assert err.value.extra["nodes"] == ["6"]

    fake.history["p9"] = {
        "status": {
            "status_str": "error",
            "messages": [["execution_error", {"exception_message": "Allocation on device"}]],
        },
        "outputs": {},
    }
    assert provider.progress("p9").error == "Allocation on device"
    assert provider.progress("gone").state == "failed"  # unknown after an engine restart


def test_comfyui_cancel_deletes_pending_or_interrupts_running() -> None:
    fake = FakeComfy()
    provider = _comfy(fake)
    fake.pending = ["a"]
    provider.cancel("a")
    fake.pending, fake.running = [], ["b"]
    provider.cancel("b")
    posts = [(path, body) for method, path, body in fake.calls if method == "POST"]
    assert posts == [("/queue", {"delete": ["a"]}), ("/interrupt", {"prompt_id": "b"})]


def test_comfyui_free_vram() -> None:
    fake = FakeComfy()
    _comfy(fake).free_vram()
    assert ("POST", "/free", {"unload_models": True, "free_memory": True}) in fake.calls


# --- host agent client --------------------------------------------------------------------


def _agent(handler: Any, token: str = "agent-token") -> HostAgentClient:  # noqa: S107
    client = httpx.Client(base_url="http://agent", transport=httpx.MockTransport(handler))
    return HostAgentClient("http://agent", token, client=client)


def test_host_agent_sends_the_token_and_maps_errors() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        if request.url.path == "/engine:start":
            return httpx.Response(
                409,
                json={"detail": {"code": "ENGINE_NOT_CONFIGURED", "detail": "No ComfyUI folder."}},
            )
        return httpx.Response(401)

    agent = _agent(handler)
    with pytest.raises(DomainError) as err:
        agent.engine_action("start")
    assert (err.value.status, err.value.code) == (409, "ENGINE_NOT_CONFIGURED")
    with pytest.raises(DomainError) as err:
        agent.gpu()
    assert err.value.code == "HOST_AGENT_REJECTED"
    assert seen == ["Bearer agent-token", "Bearer agent-token"]


def test_host_agent_not_configured_or_down() -> None:
    with pytest.raises(DomainError) as err:
        _agent(lambda _: httpx.Response(200, json={}), token="").engine()
    assert err.value.code == "HOST_AGENT_NOT_CONFIGURED"

    def down(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(DomainError) as err:
        _agent(down).engine()
    assert (err.value.status, err.value.code) == (503, "HOST_AGENT_UNAVAILABLE")
