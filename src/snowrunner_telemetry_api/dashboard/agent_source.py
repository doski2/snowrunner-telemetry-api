"""Lectura continua de muestras JSON desde el agente C# (--loop)."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from collections.abc import Callable
from typing import Any

# El agente siempre muestrea rápido: la ventana solo decide cada cuánto repinta.
AGENT_MAX_INTERVAL_MS = 100


class AgentSampleError(Exception):
    """Sin muestra del agente aún o proceso caído."""


def try_parse_json_buffer(lines: list[str]) -> dict[str, Any] | None:
    if not lines:
        return None
    try:
        payload = json.loads("\n".join(lines))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def is_agent_status_line(text: str) -> bool:
    return text.startswith("[") or "SnowRunner" in text or "offsets" in text


class AgentLoopSource:
    def __init__(
        self,
        interval_ms: int = 500,
        on_sample: Callable[[dict[str, Any]], object] | None = None,
    ) -> None:
        self.interval_ms = interval_ms
        self._on_sample = on_sample  # se llama por cada muestra, desde el hilo lector
        self._lock = threading.Lock()
        self._latest: dict[str, Any] | None = None
        self._error = "Iniciando agente…"
        self._proc: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[3]

    @staticmethod
    def _build_dir() -> Path:
        return AgentLoopSource._repo_root() / ".agent-build"

    def start(self) -> None:
        if self._proc is not None:
            return

        agent_dir = self._repo_root() / "agent"
        project = agent_dir / "SnowrunnerTelemetryAgent.csproj"
        build_dir = self._build_dir()
        build_dir.mkdir(parents=True, exist_ok=True)

        build = subprocess.run(
            [
                "dotnet",
                "build",
                str(project),
                "-c",
                "Debug",
                "-o",
                str(build_dir),
                "-v",
                "q",
            ],
            cwd=agent_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if build.returncode != 0:
            self._error = build.stderr.strip() or build.stdout.strip() or "Fallo al compilar agente"
            return

        dll = build_dir / "snowrunner-telemetry-agent.dll"
        if not dll.exists():
            self._error = f"No se encontró {dll}"
            return

        self._proc = subprocess.Popen(
            [
                "dotnet",
                "exec",
                str(dll),
                "--",
                "--loop",
                f"--interval={min(self.interval_ms, AGENT_MAX_INTERVAL_MS)}",
                "--memory-only",
            ],
            cwd=agent_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._thread.start()

    def _publish(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._latest = payload
            self._error = ""
        if self._on_sample is not None:
            try:
                self._on_sample(payload)
            except Exception:  # noqa: BLE001 - un fallo al grabar no debe parar la lectura
                pass

    def _read_stdout(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None

        buffer: list[str] = []
        for line in self._proc.stdout:
            stripped = line.strip()
            if buffer:
                buffer.append(line.rstrip("\n\r"))
                payload = try_parse_json_buffer(buffer)
                if payload is not None:
                    self._publish(payload)
                    buffer = []
                elif len(buffer) > 120:
                    buffer = []
                continue

            if stripped.startswith("{"):
                payload = try_parse_json_buffer([stripped])
                if payload is not None:
                    self._publish(payload)
                    continue

                buffer = [line.rstrip("\n\r")]
                continue

            if stripped and is_agent_status_line(stripped):
                with self._lock:
                    if self._latest is None:
                        self._error = stripped

        code = self._proc.wait()
        with self._lock:
            if self._latest is None:
                self._error = self._error or f"Agente terminado (código {code})"
            elif code != 0:
                self._error = f"Agente salió con código {code}"

    def latest(self) -> dict[str, Any]:
        with self._lock:
            if self._latest is not None:
                return dict(self._latest)
            if self._proc is not None and self._proc.poll() is not None:
                raise AgentSampleError(self._error or "Agente no disponible")
            raise AgentSampleError(self._error or "Esperando primera muestra del agente…")

    def stop(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
