"""Structured logging (see Infrastructure: Observability)."""

import logging

import structlog

_SENSITIVE = ("token", "secret", "password", "authorization", "cookie")


def _redact(
    _logger: object, _method: str, event_dict: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    for key in list(event_dict):
        if any(word in key.lower() for word in _SENSITIVE):
            event_dict[key] = "[redacted]"
    return event_dict


def configure_logging(level: str = "INFO", as_json: bool = True) -> None:
    logging.basicConfig(level=level, format="%(message)s")
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer() if as_json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )
