"""Backend matplotlib — requiere pip install -e \".[dashboard]\"."""

from __future__ import annotations

import matplotlib

matplotlib.use("TkAgg")

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

__all__ = ["Figure", "FigureCanvasTkAgg"]
