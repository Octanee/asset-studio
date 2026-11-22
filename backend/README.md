# Asset Studio backend

A FastAPI modular monolith (see `docs/04-Architecture/System-Architecture.md`).

```powershell
uv sync
uv run uvicorn asset_studio.main:app --reload
uv run pytest
uv run ruff check . ; uv run ruff format --check . ; uv run mypy ; uv run lint-imports
```
