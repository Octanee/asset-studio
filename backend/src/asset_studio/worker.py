"""Worker process entry point: runs the persistent job queue (ADR-004, WP-04).

Modules that own work register job handlers in ``HANDLERS`` (generation in WP-08,
processing in WP-09, ...). A NOTIFY on enqueue wakes the worker; it also polls.
"""

import os
import signal
import socket
import time
import uuid
from types import FrameType

import psycopg
import structlog

from asset_studio.config import get_settings
from asset_studio.db import get_engine, get_sessionmaker
from asset_studio.logging import configure_logging
from asset_studio.models import load_all
from asset_studio.modules.generation.service import handle_generate
from asset_studio.modules.jobs.runner import Handler, Runner
from asset_studio.modules.jobs.service import NOTIFY_CHANNEL
from asset_studio.modules.models.service import handle_download, handle_verify_model
from asset_studio.modules.poses.detection import load_default_detector, set_detector
from asset_studio.modules.poses.service import handle_detect_pose
from asset_studio.modules.providers.engine import get_engine_monitor

HANDLERS: dict[str, Handler] = {
    "detect_pose": handle_detect_pose,
    "generate": handle_generate,
    "download": handle_download,
    "verify_model": handle_verify_model,
}
POLL_SECONDS = 2.0


class _Stop:
    requested = False


def _stop(_signum: int, _frame: FrameType | None) -> None:
    _Stop.requested = True


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = structlog.get_logger("worker")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    load_all()  # every table, so foreign keys to other modules resolve
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    # GPU jobs wait in the queue, with the reason shown, while the engine is down (RULE-013).
    engine = get_engine_monitor()
    # Pose detection runs when the DWPose models are installed (ADR-009).
    detector = load_default_detector()
    set_detector(detector)
    log.info("worker.pose_detector", detector=detector.name if detector else None)
    runner = Runner(get_sessionmaker(), worker_id, HANDLERS, gates={"gpu": engine.gate})
    # The API applies migrations on start; wait for them instead of crashing.
    while not _Stop.requested:
        try:
            runner.start()
            break
        except Exception as exc:
            log.warning("worker.waiting_for_database", error=type(exc).__name__)
            time.sleep(POLL_SECONDS)
    dsn = get_engine().url.set(drivername="postgresql").render_as_string(hide_password=False)
    log.info("worker.started", worker_id=worker_id, kinds=sorted(HANDLERS))
    with psycopg.connect(dsn, autocommit=True) as listen:
        listen.execute(f"LISTEN {NOTIFY_CHANNEL}")
        while not _Stop.requested:
            try:
                runner.tick()
            except Exception:  # keep the worker alive; the next tick retries
                log.exception("worker.tick_failed")
            for _ in listen.notifies(timeout=POLL_SECONDS, stop_after=1):
                pass
    runner.stop()
    log.info("worker.stopped", worker_id=worker_id)


if __name__ == "__main__":
    main()
