"""Worker process entry point. The persistent job queue arrives in WP-04."""

import signal
import time
from types import FrameType

import structlog

from asset_studio.config import get_settings
from asset_studio.logging import configure_logging

_running = True


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global _running
    _running = False


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = structlog.get_logger("worker")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker.started")
    while _running:
        log.debug("worker.heartbeat")
        time.sleep(5)
    log.info("worker.stopped")


if __name__ == "__main__":
    main()
