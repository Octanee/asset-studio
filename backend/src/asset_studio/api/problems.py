"""RFC 9457 problem+json responses."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from asset_studio.errors import DomainError

PROBLEM = "application/problem+json"


def problem_response(
    status: int, code: str, detail: str, extra: dict[str, Any] | None = None
) -> JSONResponse:
    body = {
        "type": f"urn:asset-studio:problem:{code}",
        "title": code,
        "status": status,
        "code": code,
        "detail": detail,
        **(extra or {}),
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def install(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return problem_response(exc.status, exc.code, exc.detail, exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return problem_response(
            422, "REQUEST_INVALID", "The request is not valid.", {"errors": errors}
        )
