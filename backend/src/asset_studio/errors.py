"""Domain errors, rendered as RFC 9457 problem+json by the API layer."""

from typing import Any


class DomainError(Exception):
    def __init__(self, status: int, code: str, detail: str, extra: dict[str, Any] | None = None):
        super().__init__(detail)
        self.status, self.code, self.detail, self.extra = status, code, detail, extra or {}
