"""Programmatic SVG (WP-14): deterministic templates (FR-045), sanitising and optimising
(FR-046, NFR-011), rasterising for thumbnails, validation and export (FR-047), the API, the
CPU job and Claude's tools (UC-014)."""

import io
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from asset_studio.errors import DomainError
from asset_studio.modules.assets import service as assets
from asset_studio.modules.assets.models import AssetVersion
from asset_studio.modules.processing import service as processing
from asset_studio.modules.publishing import service as publishing
from asset_studio.modules.storage.local import LocalStorage
from asset_studio.modules.svg import service as svg
from asset_studio.modules.svg.raster import render
from asset_studio.modules.svg.sanitize import SvgError, clean
from asset_studio.modules.svg.templates import TEMPLATES, get_template, normalise
from tests.conftest import MCP, ORIGIN, project_config
from tests.test_jobs import _runner
from tests.test_publishing import (  # noqa: F401 - the exports fixture is used by name
    _plan,
    _publish,
    _setup,
    exports,
)
from tests.test_publishing import _run as _run_exports
from tests.test_publishing import _version as _raster_version

HOSTILE = (
    b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
    b'viewBox="0 0 10 10" onload="alert(1)"><script>alert(1)</script><style>*{}</style>'
    b'<image href="http://example.invalid/x.png"/><a xlink:href="javascript:x()"><rect/></a>'
    b'<rect width="10" height="10" fill="url(http://example.invalid/#a)" style="fill:red"/>'
    b"<foreignObject><div/></foreignObject><!-- note --><svg viewBox='0 0 1 1'/>"
    b'<g><circle cx="1.23456" cy="-0.0001" r="2" stroke-width="0.50"/></g><g/></svg>'
)


@pytest.fixture(autouse=True)
def _storage(storage: LocalStorage, monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (svg, processing, publishing):
        monkeypatch.setattr(module, "get_storage", lambda: storage)


def _project(client: TestClient) -> str:
    r = client.post("/api/v1/projects", json=project_config(), headers=ORIGIN)
    return str(r.json()["id"])


def _style(client: TestClient, pid: str, palette: list[str]) -> str:
    r = client.post(
        f"/api/v1/projects/{pid}/styles",
        json={"name": "Flat", "attributes": {"palette": palette}},
        headers=ORIGIN,
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _run(connection: Connection) -> None:
    runner = _runner(connection, {**svg.HANDLERS, **processing.HANDLERS})
    while runner.tick():
        pass


def _create(client: TestClient, pid: str, headers: dict[str, str] = ORIGIN, **kw: Any) -> Any:
    body = {
        "project_id": pid,
        "template_id": "icon-line",
        "params": {"glyph": "heart", "stroke_width": 2.5},
        "asset": {"category": "core", "name": "Heart icon"},
        **kw,
    }
    return client.post("/api/v1/svg", json=body, headers=headers)


# --- templates (FR-045) -----------------------------------------------------------------------


def test_fr045_every_template_is_deterministic_and_clean() -> None:
    for template in TEMPLATES.values():
        params = normalise(template, {})
        first, second = template.draw(params), template.draw(dict(params))
        assert first == second
        cleaned = clean(first)
        # Template output is already in the canonical form: cleaning changes nothing.
        assert cleaned.svg == first and cleaned.removed_elements == cleaned.removed_attributes == 0


def test_fr045_parameters_are_checked_and_normalised() -> None:
    icon = get_template("icon-line")
    assert normalise(icon, {"color": "#ABCDEF", "stroke_width": 2})["color"] == "#abcdef"
    assert normalise(icon, {"stroke_width": 2}) == normalise(icon, {"stroke_width": 2.0})
    for bad, code in (
        ({"size": 3}, "SVG_PARAM_UNKNOWN"),
        ({"stroke_width": 9}, "SVG_PARAM_INVALID"),
        ({"stroke_width": True}, "SVG_PARAM_INVALID"),
        ({"color": "red"}, "SVG_PARAM_INVALID"),
        ({"glyph": "skull"}, "SVG_PARAM_INVALID"),
    ):
        with pytest.raises(DomainError) as err:
            normalise(icon, bad)
        assert err.value.code == code
    with pytest.raises(DomainError) as err:
        get_template("nope")
    assert err.value.code == "SVG_TEMPLATE_NOT_FOUND"


def test_fr045_dot_pattern_tiles_without_a_seam() -> None:
    dots = get_template("pattern-dots")
    for spacing in (3, 5, 7, 8):
        c = clean(dots.draw(normalise(dots, {"spacing": spacing})))
        assert c.width == c.height and (c.width / spacing).is_integer()


# --- sanitising and optimising (FR-046, NFR-011) -----------------------------------------------


def test_fr046_hostile_content_is_removed() -> None:
    c = clean(HOSTILE)
    for word in ("script", "style", "onload", "href", "image", "foreignObject", "invalid", "note"):
        assert word not in c.svg
    assert c.svg == (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<rect width="10" height="10"/><g><circle cx="1.235" cy="0" r="2" stroke-width="0.5"/>'
        "</g></svg>"
    )
    # script, style, image, a (with its rect), foreignObject (with its div), nested svg
    assert c.removed_elements == 8
    assert c.removed_attributes == 3  # onload, the external fill, style
    assert c.bytes_out < c.bytes_in


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (
            b'<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>',
            "SVG_DOCTYPE",
        ),
        (b"<svg", "SVG_INVALID"),
        (b"<html/>", "SVG_INVALID"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"/>', "SVG_VIEWBOX"),
        (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 5"/>', "SVG_VIEWBOX"),
        (b"\xff\xfe", "SVG_INVALID"),
        (b" " * (600 * 1024), "SVG_TOO_LARGE"),
    ],
)
def test_nfr011_unusable_svg_is_refused(data: bytes, code: str) -> None:
    with pytest.raises(SvgError) as err:
        clean(data)
    assert err.value.code == code


def test_fr047_render_fits_the_box_and_keeps_the_aspect_ratio() -> None:
    wide = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 24">'
        '<rect width="48" height="24"/></svg>'
    )
    image = Image.open(io.BytesIO(render(wide, 100, 100)))
    assert image.format == "PNG" and image.size == (100, 50)
    with pytest.raises(SvgError):
        render(wide, 0, 100)


# --- API ---------------------------------------------------------------------------------------


def test_uc014_templates_and_preview(client: TestClient) -> None:
    pid = _project(client)
    listed = client.get("/api/v1/svg/templates").json()
    assert {t["id"] for t in listed} == set(TEMPLATES)
    icon = next(t for t in listed if t["id"] == "icon-line")
    assert {p["name"]: p["kind"] for p in icon["params"]} == {
        "glyph": "glyph",
        "color": "color",
        "stroke_width": "number",
    }
    body = {"project_id": pid, "template_id": "badge-circle", "params": {"glyph": "star"}}
    first = client.post("/api/v1/svg:preview", json=body, headers=ORIGIN).json()
    second = client.post("/api/v1/svg:preview", json=body, headers=ORIGIN).json()
    assert first["ready"] and first["svg"].startswith("<svg") and first["width"] == 24
    assert (first["sha256"], first["params_hash"]) == (second["sha256"], second["params_hash"])
    assert first["params"]["glyph_color"] == "#ffffff"  # defaults are filled in
    changed = client.post(
        "/api/v1/svg:preview", json={**body, "params": {"glyph": "heart"}}, headers=ORIGIN
    ).json()
    assert changed["sha256"] != first["sha256"]


def test_uc014_colours_must_come_from_the_style_palette(client: TestClient) -> None:
    pid = _project(client)
    style = _style(client, pid, ["#2BB3A3", "#1f2a44"])
    body = {"project_id": pid, "template_id": "badge-circle", "style_id": style}
    ok = client.post("/api/v1/svg:preview", json=body, headers=ORIGIN).json()
    # Teal is in the palette and white is a neutral every palette allows.
    assert ok["ready"] and ok["palette"] == ["#1f2a44", "#2bb3a3"]
    off = client.post(
        "/api/v1/svg:preview", json={**body, "params": {"color": "#ff0000"}}, headers=ORIGIN
    ).json()
    assert not off["ready"]
    assert [(p["code"], p["param"]) for p in off["problems"]] == [("PALETTE_MISMATCH", "color")]
    r = _create(client, pid, style_id=style, params={"color": "#ff0000"})
    assert r.status_code == 422 and r.json()["code"] == "SVG_NOT_READY"


def test_uc014_a_queued_svg_becomes_a_version_for_review(
    client: TestClient, connection: Connection, db: Session
) -> None:
    pid = _project(client)
    r = _create(client, pid)
    assert r.status_code == 202, r.text
    queued = r.json()
    assert queued["job"]["kind"] == "svg" and queued["job"]["lane"] == "cpu"
    _run(connection)
    versions = client.get(f"/api/v1/assets/{queued['asset_id']}/versions").json()
    assert len(versions) == 1
    v = db.get(AssetVersion, uuid.UUID(versions[0]["id"]))
    assert v is not None
    db.refresh(v)
    assert v.mime == "image/svg+xml" and v.state == "awaiting_review"
    meta = v.generation_metadata
    assert meta["template"] == {"id": "icon-line", "version": 1}
    assert meta["params"] == {"glyph": "heart", "color": "#1f2a44", "stroke_width": 2.5}
    assert meta["engine"]["name"] == "svg" and len(meta["params_hash"]) == 16
    # The stored file is exactly the preview (FR-045).
    preview = client.post(
        "/api/v1/svg:preview",
        json={"project_id": pid, "template_id": "icon-line", "params": meta["params"]},
        headers=ORIGIN,
    ).json()
    assert v.sha256 == preview["sha256"]
    out = v.processing["output"]
    assert out["mime"] == "image/svg+xml" and out["ext"] == "svg"
    thumb = client.get(f"/api/v1/versions/{v.id}/file", params={"size": "thumb"})
    assert thumb.status_code == 200 and Image.open(io.BytesIO(thumb.content)).format == "WEBP"
    original = client.get(f"/api/v1/versions/{v.id}/file")
    assert original.headers["content-type"].startswith("image/svg+xml")
    assert "sandbox" in original.headers["content-security-policy"]
    results = client.get(f"/api/v1/versions/{v.id}/validation").json()["results"]
    report = {x["rule"]: x for x in results}
    assert report["integrity"]["status"] == "passed"
    assert report["format"]["status"] == "skipped"
    assert report["format"]["details"]["reason"] == "vector"
    assert report["dimensions"]["status"] == "passed"


def test_uc014_claude_creates_svg_once_per_request_id(client: TestClient) -> None:
    pid = _project(client)
    headers = MCP | {"Idempotency-Key": "svg-request-1"}
    first = _create(client, pid, headers=headers)
    again = _create(client, pid, headers=headers)
    assert first.status_code == again.status_code == 202, first.text
    assert first.json()["job"]["id"] == again.json()["job"]["id"]
    target = _create(client, pid, headers=MCP | {"Idempotency-Key": "svg-request-2"}, asset={})
    assert target.status_code == 422 and target.json()["code"] == "SVG_TARGET_REQUIRED"


def test_new_version_of_an_existing_asset(client: TestClient, connection: Connection) -> None:
    pid = _project(client)
    asset_id = _create(client, pid).json()["asset_id"]
    r = _create(client, pid, asset={"asset_id": asset_id}, params={"glyph": "star"})
    assert r.status_code == 202 and r.json()["asset_id"] == asset_id
    _run(connection)
    numbers = [v["number"] for v in client.get(f"/api/v1/assets/{asset_id}/versions").json()]
    assert sorted(numbers) == [1, 2]


# --- export (FR-047) ---------------------------------------------------------------------------


def _approved_svg(client: TestClient, connection: Connection, db: Session, pid: str) -> str:
    asset_id = _create(client, pid).json()["asset_id"]
    _run(connection)
    vid = client.get(f"/api/v1/assets/{asset_id}/versions").json()[0]["id"]
    assets.transition(db, uuid.UUID(vid), "approve", "user")
    db.flush()
    return str(vid)


def test_fr047_export_renders_svg_to_raster_and_copies_it_as_svg(
    client: TestClient, connection: Connection, db: Session, exports: Path
) -> None:
    pid = _project(client)
    vid = _approved_svg(client, connection, db, pid)
    png_preset, target = _setup(client, uuid.UUID(pid))
    plan = _plan(client, uuid.UUID(pid), png_preset, target, version_ids=[vid]).json()
    assert _publish(client, plan).status_code == 202
    _run_exports(connection)
    png = next(exports.rglob("*.png"))
    assert Image.open(png).size == (64, 64)

    r = client.post(
        f"/api/v1/projects/{pid}/presets",
        json={"name": "Vector", "definition": {"format": "svg", "naming": "{asset}-vector"}},
        headers=ORIGIN,
    )
    assert r.status_code == 201, r.text
    plan = _plan(client, uuid.UUID(pid), r.json()["id"], target, version_ids=[vid]).json()
    assert _publish(client, plan).status_code == 202
    _run_exports(connection)
    vector = next(exports.rglob("*.svg")).read_text(encoding="utf-8")
    assert vector.startswith('<svg xmlns="http://www.w3.org/2000/svg"') and "script" not in vector


def test_fr047_a_raster_version_is_not_exported_as_svg(
    client: TestClient, db: Session, storage: LocalStorage, exports: Path
) -> None:
    pid = _project(client)
    v = _raster_version(db, storage, uuid.UUID(pid), "Squat")
    db.flush()
    r = client.post(
        f"/api/v1/projects/{pid}/presets",
        json={"name": "Vector", "definition": {"format": "svg"}},
        headers=ORIGIN,
    )
    _, target = _setup(client, uuid.UUID(pid))
    plan = _plan(client, uuid.UUID(pid), r.json()["id"], target, version_ids=[str(v.id)])
    assert plan.status_code == 409
    assert plan.json()["skipped"][0]["reason"] == "NOT_VECTOR"


def test_svg_versions_are_not_training_images(
    client: TestClient, connection: Connection, db: Session
) -> None:
    pid = _project(client)
    vid = _approved_svg(client, connection, db, pid)
    ds = client.post(
        f"/api/v1/projects/{pid}/datasets",
        json={"name": "Icons", "trigger_word": "exz_icon"},
        headers=ORIGIN,
    )
    assert ds.status_code == 201, ds.text
    r = client.post(
        f"/api/v1/datasets/{ds.json()['id']}/items:versions",
        json={"version_ids": [vid]},
        headers=ORIGIN,
    )
    assert r.status_code == 422 and r.json()["code"] == "VERSION_NOT_RASTER"
