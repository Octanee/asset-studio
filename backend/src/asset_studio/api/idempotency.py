"""``Idempotency-Key`` for POSTs that create jobs or publications (API-Architecture).

Without a key a request runs as usual, except for MCP, which must send one: an agent may
retry a call whose answer it never saw. With a key, the first answer is stored and returned
again for every repeat of the same request.
"""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from asset_studio.api.security import CurrentActor
from asset_studio.db import get_session
from asset_studio.errors import DomainError
from asset_studio.modules.system import idempotency


class Idempotent:
    def __init__(self, request: Request, actor: str, db: Session, key: str | None) -> None:
        self.request, self.actor, self.db, self.key = request, actor, db, key

    def run(
        self,
        model: type[BaseModel],
        status_code: int,
        payload: Any,
        work: Callable[[], Any],
    ) -> Any:
        if not self.key:
            if self.actor == "mcp":
                raise DomainError(
                    428,
                    "IDEMPOTENCY_KEY_REQUIRED",
                    "Claude must send an Idempotency-Key with this request.",
                )
            return work()
        body = payload.model_dump_json() if isinstance(payload, BaseModel) else repr(payload)
        claim = idempotency.claim(
            self.db,
            self.actor,
            self.key,
            idempotency.fingerprint(self.request.method, self.request.url.path, body),
        )
        if claim.replay is not None:
            status, content = claim.replay
            return JSONResponse(content, status_code=status, headers={"Idempotent-Replay": "true"})
        data = model.model_validate(work()).model_dump(mode="json")
        idempotency.store(self.db, claim, status_code, data)
        return data


def _idempotent(
    request: Request,
    actor: CurrentActor,
    db: Annotated[Session, Depends(get_session)],
    key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=200)] = None,
) -> Idempotent:
    return Idempotent(request, actor, db, key)


Idem = Annotated[Idempotent, Depends(_idempotent)]
