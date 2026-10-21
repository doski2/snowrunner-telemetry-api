"""Grabador automático para juego normal: `python -m snowrunner_telemetry_api.autorecord`.

Lanza el agente, espera a que haya juego y camión, y graba un NDJSON por camión en
data/sessions/play_<vehicle_id>_<fecha>.ndjson. Adelgaza los ratos parado y sobrevive a
cerrar el juego o salir al menú (reintenta). Parar con Ctrl+C.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .dashboard.recorder import SessionRecorder

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "agent" / "SnowrunnerTelemetryAgent.csproj"
IDLE_KMH = 0.3
IDLE_GAS = 0.02
STATS_EVERY_S = 60.0
RETRY_S = 5.0


GAME_DIR = Path(
    os.environ.get(
        "SNOWRUNNER_GAME_DIR",
        r"C:\Program Files (x86)\Steam\steamapps\common\SnowRunner",
    )
)
OFFSETS_PATH = ROOT / "agent" / "data" / "offsets_referencia.json"


def _file_info(path: Path, *, digest: bool = False) -> dict[str, Any]:
    try:
        st = path.stat()
    except OSError:
        return {"found": False}
    info: dict[str, Any] = {
        "found": True,
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }
    if digest:
        h = hashlib.sha1()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        info["sha1"] = h.hexdigest()
    return info


def session_meta(interval_ms: int) -> dict[str, Any]:
    """Qué juego, qué pak (vanilla o mod) y qué offsets produjeron la sesión."""
    try:
        offsets = json.loads(OFFSETS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        offsets = {}
    return {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "interval_ms": interval_ms,
        "game_exe": _file_info(GAME_DIR / "Sources" / "Bin" / "SnowRunner.exe"),
        "initial_pak": _file_info(GAME_DIR / "preload" / "paks" / "client" / "initial.pak", digest=True),
        "offsets_game_version": offsets.get("game_version", ""),
        "offsets_source": offsets.get("source", ""),
    }


class IdleThinner:
    """Descarta muestras de reposo salvo una cada `keep_s` segundos."""

    def __init__(self, keep_s: float = 2.0) -> None:
        self.keep_s = keep_s
        self._last_kept = float("-inf")

    def keep(self, sample: dict[str, Any], now: float) -> bool:
        speed = float(sample.get("speed_kmh") or 0.0)
        gas = float(sample.get("throttle_game") or 0.0)
        if speed >= IDLE_KMH or gas >= IDLE_GAS:
            return True
        if now - self._last_kept >= self.keep_s:
            self._last_kept = now
            return True
        return False


class PlayRecorder:
    """Un fichero por camión: al cambiar de vehicle_id cierra el anterior y abre otro."""

    def __init__(
        self, directory: Path | None = None, keep_idle_s: float = 2.0, interval_ms: int = 100
    ) -> None:
        self.directory = directory
        self.interval_ms = interval_ms
        self._meta: dict[str, Any] | None = None
        self._thin = IdleThinner(keep_idle_s)
        self._rec: SessionRecorder | None = None
        self._vehicle = ""
        self.rows = 0

    def handle(self, sample: dict[str, Any], now: float | None = None) -> bool:
        vehicle = str(sample.get("vehicle_id") or "")
        if not vehicle:
            return False
        if vehicle != self._vehicle:
            self.close()
            if self._meta is None:  # el hash del pak se calcula una vez por arranque
                self._meta = session_meta(self.interval_ms)
            self._rec = SessionRecorder(f"play_{vehicle}", self.directory, self._meta)
            self._vehicle = vehicle
            print(f"[autorecord] {vehicle} -> {self._rec.path}", flush=True)
        if not self._thin.keep(sample, time.monotonic() if now is None else now):
            return False
        assert self._rec is not None
        wrote = self._rec.write(sample)
        self.rows += int(wrote)
        return wrote

    def close(self) -> None:
        if self._rec is not None:
            self._rec.close()
            self._rec = None
        self._vehicle = ""


def _run_agent_once(recorder: PlayRecorder, interval_ms: int) -> int:
    cmd = [
        "dotnet", "run", "--project", str(PROJECT), "-v", "q", "--",
        "--loop", f"--interval={interval_ms}", "--memory-only",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8"
    )
    last_stats = time.monotonic()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                recorder.handle(json.loads(line))
            except json.JSONDecodeError:
                continue
            if time.monotonic() - last_stats >= STATS_EVERY_S:
                last_stats = time.monotonic()
                print(f"[autorecord] {recorder.rows} filas grabadas", flush=True)
    finally:
        proc.terminate()
    return proc.wait()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=int, default=100, help="ms entre muestras (mín. 50)")
    ap.add_argument("--dir", type=Path, default=None, help="carpeta de salida")
    args = ap.parse_args(argv)
    if args.interval < 50:
        print("intervalo mínimo 50 ms")
        return 2

    recorder = PlayRecorder(args.dir, interval_ms=args.interval)
    announced_at = -1
    print("[autorecord] grabando; Ctrl+C para parar.", flush=True)
    try:
        while True:
            code = _run_agent_once(recorder, args.interval)
            recorder.close()
            if announced_at != recorder.rows:  # un solo aviso por cada corte
                print(f"[autorecord] esperando juego/camión (agente salió con {code})…", flush=True)
                announced_at = recorder.rows
            time.sleep(RETRY_S)
    except KeyboardInterrupt:
        recorder.close()
        print(f"\n[autorecord] parado. {recorder.rows} filas grabadas.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
