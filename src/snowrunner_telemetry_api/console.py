"""Utilidades de consola compartidas por los scripts."""

from __future__ import annotations

import sys


def use_utf8_output() -> None:
    """Fuerza UTF-8 en stdout: las consolas cp1252 de Windows no imprimen →, ●, —…"""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")
