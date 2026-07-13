"""Utilidades de entorno Windows (Fase 1)."""

from __future__ import annotations

import subprocess


def snowrunner_running() -> bool:
    if not _is_windows():
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq SnowRunner.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return "SnowRunner.exe" in (result.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return False


def snowrunner_pid() -> int | None:
    if not _is_windows():
        return None
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq SnowRunner.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in (result.stdout or "").splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 2 and parts[0].lower() == "snowrunner.exe":
                return int(parts[1])
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return None


def _is_windows() -> bool:
    import sys

    return sys.platform == "win32"
