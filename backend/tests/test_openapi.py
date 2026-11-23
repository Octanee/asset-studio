"""The committed OpenAPI document matches the code (the frontend client is generated from it)."""

from pathlib import Path

from asset_studio.openapi import render

COMMITTED = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "openapi.json"


def test_frontend_openapi_document_is_current() -> None:
    assert COMMITTED.read_text(encoding="utf-8") == render(), (
        "Regenerate: cd backend && uv run python -m asset_studio.openapi "
        "../frontend/src/api/openapi.json && cd ../frontend && pnpm gen:api"
    )
