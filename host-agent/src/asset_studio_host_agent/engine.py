"""Supervises the native ComfyUI process (ADR-005).

The command is fixed: the portable build's embedded Python runs ``ComfyUI/main.py`` on
loopback with pinned arguments. Requests choose only start, stop or restart; they never
pass paths or arguments, and nothing runs through a shell.
"""

import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any


class EngineError(Exception):
    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


@dataclass(frozen=True)
class EngineConfig:
    comfyui_dir: str = ""
    python: str = ""  # default: <comfyui_dir>/python_embeded/python.exe (portable build)
    port: int = 8188
    log_dir: str = "./logs"

    @property
    def configured(self) -> bool:
        return bool(self.comfyui_dir)

    def python_path(self) -> Path:
        if self.python:
            return Path(self.python)
        return Path(self.comfyui_dir) / "python_embeded" / "python.exe"

    def main_path(self) -> Path:
        return Path(self.comfyui_dir) / "ComfyUI" / "main.py"

    def command(self) -> list[str]:
        return [
            str(self.python_path()),
            "-s",
            str(self.main_path()),
            "--windows-standalone-build",
            "--listen",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--disable-auto-launch",
        ]


Spawn = Callable[..., Any]


class EngineSupervisor:
    def __init__(self, config: EngineConfig, *, spawn: Spawn = subprocess.Popen) -> None:
        self.config = config
        self._spawn = spawn
        self._proc: Any = None
        self._log: IO[bytes] | None = None
        self._started_at: str | None = None
        self._lock = threading.Lock()

    def _running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status()

    def _status(self) -> dict[str, Any]:
        running = self._running()
        return {
            "configured": self.config.configured,
            "running": running,
            "pid": self._proc.pid if running else None,
            "exit_code": None if self._proc is None or running else self._proc.poll(),
            "started_at": self._started_at if running else None,
            "port": self.config.port,
        }

    def start(self) -> dict[str, Any]:
        with self._lock:
            if not self.config.configured:
                raise EngineError(409, "ENGINE_NOT_CONFIGURED", "No ComfyUI folder is configured.")
            if not (self.config.python_path().is_file() and self.config.main_path().is_file()):
                raise EngineError(
                    409,
                    "ENGINE_NOT_INSTALLED",
                    "ComfyUI is not installed in the configured folder.",
                )
            if self._running():
                return self._status()
            log_dir = Path(self.config.log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            self._close_log()
            self._log = (log_dir / "comfyui.log").open("ab")
            env = {**os.environ, "PYTHONUTF8": "1"}  # prototype S-3: UTF-8 console on Windows
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            self._proc = self._spawn(
                self.config.command(),
                cwd=self.config.comfyui_dir,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=flags,
            )
            self._started_at = datetime.now(UTC).isoformat()
            return self._status()

    def stop(self, timeout: float = 20.0) -> dict[str, Any]:
        with self._lock:
            if self._running():
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait(timeout=timeout)
            self._close_log()
            return self._status()

    def restart(self) -> dict[str, Any]:
        self.stop()
        time.sleep(0.5)  # let the port close before binding again
        return self.start()

    def _close_log(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None
