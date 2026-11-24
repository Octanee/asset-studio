"""Built-in ComfyUI workflows (FR-030-FR-033), from the graph the WP-01 spike ran on the GPU.

One base (text-to-image or image-to-image) plus optional pose control (OpenPose ControlNet),
reference conditioning (IP-Adapter), a separate VAE and up to two LoRAs (WP-13). Each
combination is a versioned template with its own id, e.g. ``txt2img+pose+lora`` v1. The
domain fills named inputs; node ids stay here (ADR-006).
"""

from dataclasses import dataclass
from functools import cache
from typing import Any

from asset_studio.modules.providers.workflows import InputSpec, InputType, WorkflowTemplate

VERSION = 1
MAX_LORAS = 2
SAMPLERS = ("euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_sde", "ddim", "uni_pc")
SCHEDULERS = ("normal", "karras", "exponential", "sgm_uniform", "simple")


@dataclass(frozen=True)
class Features:
    img2img: bool = False
    pose: bool = False
    reference: bool = False
    vae: bool = False
    loras: int = 0  # LoRAs chained after the checkpoint (FR-075)

    @property
    def id(self) -> str:
        parts = ["img2img" if self.img2img else "txt2img"]
        parts += [name for name in ("pose", "reference", "vae") if getattr(self, name)]
        if self.loras:
            parts.append("lora" if self.loras == 1 else f"lora{self.loras}")
        return "+".join(parts)

    def required_kinds(self) -> tuple[str, ...]:
        kinds = ["checkpoint"]
        if self.pose:
            kinds.append("controlnet")
        if self.reference:
            kinds += ["ip_adapter", "clip_vision"]
        if self.vae:
            kinds.append("vae")
        kinds += ["lora"] * self.loras
        return tuple(kinds)


def _s(*targets: tuple[str, str], required: bool = True, default: Any = None) -> InputSpec:
    return InputSpec("string", targets, required=required, default=default)


def _n(
    kind: InputType, *targets: tuple[str, str], lo: float, hi: float, default: Any = None
) -> InputSpec:
    return InputSpec(
        kind, targets, required=default is None, default=default, minimum=lo, maximum=hi
    )


@cache
def template(f: Features) -> WorkflowTemplate:
    vae_ref: list[Any] = ["2", 0] if f.vae else ["1", 2]
    # Each LoRA changes the model and the text encoder; later nodes take the last one's.
    model_ref: list[Any] = ["1", 0]
    clip_ref: list[Any] = ["1", 1]
    loras: dict[str, dict[str, Any]] = {}
    for n in range(1, f.loras + 1):
        node = str(39 + n)
        loras[node] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": model_ref,
                "clip": clip_ref,
                "lora_name": "",
                "strength_model": 1.0,
                "strength_clip": 1.0,
            },
        }
        model_ref, clip_ref = [node, 0], [node, 1]
    g: dict[str, dict[str, Any]] = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ""}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": clip_ref}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": clip_ref}},
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 0,
                "steps": 30,
                "cfg": 6.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": model_ref,
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": vae_ref}},
        "8": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "asset_studio", "images": ["7", 0]},
        },
    }
    inputs: dict[str, InputSpec] = {
        "checkpoint": _s(("1", "ckpt_name")),
        "prompt": _s(("3", "text")),
        "negative": _s(("4", "text"), required=False, default=""),
        "seed": _n("integer", ("6", "seed"), lo=0, hi=2**53 - 1),
        "steps": _n("integer", ("6", "steps"), lo=1, hi=150),
        "cfg": _n("number", ("6", "cfg"), lo=1, hi=30),
        "sampler": _s(("6", "sampler_name")),
        "scheduler": _s(("6", "scheduler")),
        "prefix": _s(("8", "filename_prefix"), required=False, default="asset_studio"),
    }
    for n, node in enumerate(loras, start=1):
        g[node] = loras[node]
        inputs[f"lora_{n}"] = _s((node, "lora_name"))
        inputs[f"lora_{n}_strength"] = _n(
            "number", (node, "strength_model"), (node, "strength_clip"), lo=0, hi=2
        )
    if f.vae:
        g["2"] = {"class_type": "VAELoader", "inputs": {"vae_name": ""}}
        inputs["vae"] = _s(("2", "vae_name"))
    if f.img2img:
        g["30"] = {"class_type": "LoadImage", "inputs": {"image": ""}}
        g["32"] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["30", 0],
                "upscale_method": "lanczos",
                "width": 1024,
                "height": 1024,
                "crop": "center",
            },
        }
        g["31"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["32", 0], "vae": vae_ref}}
        g["6"]["inputs"]["latent_image"] = ["31", 0]
        inputs["init_image"] = _s(("30", "image"))
        inputs["width"] = _n("integer", ("32", "width"), lo=256, hi=2048)
        inputs["height"] = _n("integer", ("32", "height"), lo=256, hi=2048)
        inputs["denoise"] = _n("number", ("6", "denoise"), lo=0.05, hi=1)
    else:
        g["5"] = {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
        }
        inputs["width"] = _n("integer", ("5", "width"), lo=256, hi=2048)
        inputs["height"] = _n("integer", ("5", "height"), lo=256, hi=2048)
    if f.pose:
        g["10"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": ""}}
        g["11"] = {"class_type": "LoadImage", "inputs": {"image": ""}}
        g["12"] = {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["3", 0],
                "negative": ["4", 0],
                "control_net": ["10", 0],
                "image": ["11", 0],
                "strength": 1.0,
                "start_percent": 0.0,
                "end_percent": 1.0,
            },
        }
        g["6"]["inputs"]["positive"] = ["12", 0]
        g["6"]["inputs"]["negative"] = ["12", 1]
        inputs["controlnet"] = _s(("10", "control_net_name"))
        inputs["pose_image"] = _s(("11", "image"))
        inputs["pose_strength"] = _n("number", ("12", "strength"), lo=0, hi=2)
        inputs["pose_end"] = _n("number", ("12", "end_percent"), lo=0.05, hi=1)
    if f.reference:
        g["20"] = {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": ""}}
        g["21"] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": ""}}
        g["22"] = {"class_type": "LoadImage", "inputs": {"image": ""}}
        g["23"] = {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model": model_ref,
                "ipadapter": ["20", 0],
                "image": ["22", 0],
                "clip_vision": ["21", 0],
                "weight": 0.6,
                "weight_type": "linear",
                "combine_embeds": "concat",
                "start_at": 0.0,
                "end_at": 1.0,
                "embeds_scaling": "V only",
            },
        }
        g["6"]["inputs"]["model"] = ["23", 0]
        inputs["ip_adapter"] = _s(("20", "ipadapter_file"))
        inputs["clip_vision"] = _s(("21", "clip_name"))
        inputs["reference_image"] = _s(("22", "image"))
        inputs["reference_weight"] = _n("number", ("23", "weight"), lo=0, hi=2)
        inputs["reference_end"] = _n("number", ("23", "end_at"), lo=0.05, hi=1)
    return WorkflowTemplate(id=f.id, version=VERSION, graph=g, inputs=inputs)


ALL = tuple(
    Features(img2img=a, pose=b, reference=c, vae=d, loras=n)
    for a in (False, True)
    for b in (False, True)
    for c in (False, True)
    for d in (False, True)
    for n in range(MAX_LORAS + 1)
)


BACKGROUND_VERSION = 1


@cache
def remove_background() -> WorkflowTemplate:
    """BiRefNet through ComfyUI's native nodes (ADR-010): the foreground mask as an image.
    The cut-out is made from the original and this mask outside the engine."""
    g: dict[str, dict[str, Any]] = {
        "1": {"class_type": "LoadImage", "inputs": {"image": ""}},
        "2": {"class_type": "LoadBackgroundRemovalModel", "inputs": {"bg_removal_name": ""}},
        "3": {
            "class_type": "RemoveBackground",
            "inputs": {"bg_removal_model": ["2", 0], "image": ["1", 0]},
        },
        "4": {"class_type": "MaskToImage", "inputs": {"mask": ["3", 0]}},
        "5": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "asset_studio", "images": ["4", 0]},
        },
    }
    return WorkflowTemplate(
        id="remove_background",
        version=BACKGROUND_VERSION,
        graph=g,
        inputs={
            "image": _s(("1", "image")),
            "model": _s(("2", "bg_removal_name")),
            "prefix": _s(("5", "filename_prefix"), required=False, default="asset_studio"),
        },
    )
