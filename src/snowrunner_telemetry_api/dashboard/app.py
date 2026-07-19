"""GUI tkinter + matplotlib — velocidad y combustible en tiempo real."""

from __future__ import annotations

import math
import time
import tkinter as tk
from collections import deque
from tkinter import ttk
from typing import Any

from .agent_source import AgentLoopSource, AgentSampleError
from .metrics import CHART_METRIC_LABELS, CHART_METRICS, normalize_chart_metric
from .poll import ApiSampleError, fetch_api_sample, parse_optional_float, parse_speed_kmh, resolve_source
from .terrain import compare_terrain


class SpeedDashboard:
    def __init__(
        self,
        base_url: str,
        interval_ms: int,
        history_len: int,
        *,
        source: str = "auto",
        chart_metric: str = "speed_kmh",
        compare_csv: bool = False,
    ) -> None:
        try:
            from . import chart_backend
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                'Falta matplotlib. Instala: pip install -e ".[dashboard]"'
            ) from exc

        self._Figure = chart_backend.Figure
        self._FigureCanvasTkAgg = chart_backend.FigureCanvasTkAgg
        self.base_url = base_url
        self.interval_ms = interval_ms
        self.source_mode = resolve_source(source, base_url)
        self.compare_csv = compare_csv
        self.chart_metric = normalize_chart_metric(chart_metric)
        self._agent: AgentLoopSource | None = None
        self._compare_agent: AgentLoopSource | None = None
        if self.source_mode == "agent" or compare_csv:
            self._agent = AgentLoopSource(interval_ms)
            self._agent.start()
        if compare_csv and self.source_mode != "agent":
            self._compare_agent = AgentLoopSource(interval_ms)
            self._compare_agent.start()

        self.times: deque[float] = deque(maxlen=history_len)
        self.speeds: deque[float] = deque(maxlen=history_len)
        self.fuels: deque[float | None] = deque(maxlen=history_len)
        self.started = time.monotonic()
        self.running = True
        self.show_history = True

        self.root = tk.Tk()
        self.root.title("SnowRunner — Telemetría")
        self.root.geometry("900x560")
        self.root.minsize(720, 320)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(0, self._tick)

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=(12, 10))
        header.pack(fill=tk.X)
        self._header = header

        values = ttk.Frame(header)
        values.pack(fill=tk.X)

        speed_col = ttk.Frame(values)
        speed_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(speed_col, text="Velocidad", font=("Segoe UI", 11)).pack(anchor=tk.W)
        self.speed_var = tk.StringVar(value="— km/h")
        ttk.Label(
            speed_col,
            textvariable=self.speed_var,
            font=("Segoe UI", 26, "bold"),
        ).pack(anchor=tk.W, pady=(2, 0))

        fuel_col = ttk.Frame(values)
        fuel_col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(24, 0))
        ttk.Label(fuel_col, text="Combustible", font=("Segoe UI", 11)).pack(anchor=tk.W)
        self.fuel_var = tk.StringVar(value="— %")
        ttk.Label(
            fuel_col,
            textvariable=self.fuel_var,
            font=("Segoe UI", 26, "bold"),
            foreground="#c45c00",
        ).pack(anchor=tk.W, pady=(2, 0))

        terrain_col = ttk.Frame(values)
        terrain_col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(24, 0))
        ttk.Label(terrain_col, text="Terreno", font=("Segoe UI", 11)).pack(anchor=tk.W)
        self.terrain_var = tk.StringVar(value="—")
        ttk.Label(
            terrain_col,
            textvariable=self.terrain_var,
            font=("Segoe UI", 18, "bold"),
            foreground="#2d6a4f",
        ).pack(anchor=tk.W, pady=(2, 0))
        self.terrain_detail_var = tk.StringVar(value="")
        ttk.Label(
            terrain_col,
            textvariable=self.terrain_detail_var,
            font=("Segoe UI", 10),
            foreground="#555",
        ).pack(anchor=tk.W)

        meta = ttk.Frame(header)
        meta.pack(fill=tk.X, pady=(8, 0))
        self.vehicle_var = tk.StringVar(value="vehicle_id: —")
        self.source_var = tk.StringVar(value="fuente: —")
        self.compare_var = tk.StringVar(value="")
        ttk.Label(meta, textvariable=self.vehicle_var).pack(side=tk.LEFT)
        ttk.Label(meta, textvariable=self.source_var).pack(side=tk.LEFT, padx=(16, 0))

        compare_row = ttk.Frame(header)
        compare_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(
            compare_row,
            textvariable=self.compare_var,
            font=("Segoe UI", 9),
            foreground="#444",
            wraplength=860,
        ).pack(anchor=tk.W)

        self.status_var = tk.StringVar(value="Conectando…")
        ttk.Label(header, textvariable=self.status_var, foreground="#555").pack(
            anchor=tk.W, pady=(6, 0)
        )

        self.chart_frame = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        self.chart_frame.pack(fill=tk.BOTH, expand=True)

        self.figure = self._Figure(figsize=(7.8, 3.8), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("Histórico")
        self.ax.set_xlabel("Tiempo (s)")
        self.ax.grid(True, alpha=0.35)
        (self.speed_line,) = self.ax.plot(
            [], [], color="#1f77b4", linewidth=2, marker="o", markersize=3, label="speed_kmh"
        )

        self.ax_fuel = self.ax.twinx()
        (self.fuel_line,) = self.ax_fuel.plot(
            [], [], color="#c45c00", linewidth=2, marker="o", markersize=3, label="fuel_pct"
        )
        self.figure.tight_layout()

        self.canvas = self._FigureCanvasTkAgg(self.figure, master=self.chart_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        footer = ttk.Frame(self.root, padding=(12, 0, 12, 10))
        footer.pack(fill=tk.X)

        self.pause_btn = ttk.Button(footer, text="Pausar", command=self._toggle_pause)
        self.pause_btn.pack(side=tk.LEFT)

        ttk.Button(footer, text="Limpiar", command=self._clear_history).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.history_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            footer,
            text="Histórico",
            variable=self.history_var,
            command=self._toggle_history,
        ).pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(footer, text="Gráfico:").pack(side=tk.LEFT, padx=(12, 0))
        self.chart_metric_var = tk.StringVar(value=CHART_METRIC_LABELS[self.chart_metric])
        self.metric_combo = ttk.Combobox(
            footer,
            textvariable=self.chart_metric_var,
            values=[CHART_METRIC_LABELS[key] for key in CHART_METRICS],
            width=14,
            state="readonly",
        )
        self.metric_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.metric_combo.bind("<<ComboboxSelected>>", self._on_chart_metric_changed)

        footer_label: str = (
            f"Fuente: {self.source_mode}"
            if self.source_mode == "agent"
            else f"API: {self.base_url}"
        )
        ttk.Label(footer, text=footer_label).pack(side=tk.RIGHT)

        self.status_var.set(
            "Leyendo agente C# (SnowRunner en mapa)"
            if self.source_mode == "agent"
            else f"Poll API {self.base_url}/v1/sample"
        )
        if self.compare_csv:
            self.compare_var.set(
                "Modo comparar: agente vs CSV (necesita run_api.bat + grabar_ce.py activo)"
            )

    def _on_chart_metric_changed(self, _event: object | None = None) -> None:
        self.chart_metric = normalize_chart_metric(self.chart_metric_var.get())
        if self.show_history:
            self._refresh_chart()

    def _toggle_history(self) -> None:
        self.show_history = self.history_var.get()
        self.metric_combo.configure(state="readonly" if self.show_history else "disabled")
        if self.show_history:
            self.chart_frame.pack(fill=tk.BOTH, expand=True, after=self._header)
            self._refresh_chart()
        else:
            self.chart_frame.pack_forget()

    def _toggle_pause(self) -> None:
        self.running = not self.running
        self.pause_btn.configure(text="Reanudar" if not self.running else "Pausar")
        self.status_var.set("Pausado" if not self.running else "Reanudado")

    def _clear_history(self) -> None:
        self.times.clear()
        self.speeds.clear()
        self.fuels.clear()
        self.started = time.monotonic()
        if self.show_history:
            self._refresh_chart()

    def _on_close(self) -> None:
        if self._agent is not None:
            self._agent.stop()
        if self._compare_agent is not None:
            self._compare_agent.stop()
        self.root.destroy()

    def _tick(self) -> None:
        if self.running:
            self._poll()
        if self.show_history:
            self._refresh_chart()
        self.root.after(self.interval_ms, self._tick)

    def _read_sample(self) -> dict[str, Any]:
        if self.source_mode == "agent":
            assert self._agent is not None
            return self._agent.latest()
        return fetch_api_sample(self.base_url)

    def _poll(self) -> None:
        try:
            sample = self._read_sample()
            speed = parse_speed_kmh(sample)
        except (AgentSampleError, ApiSampleError) as exc:
            self.status_var.set(str(exc))
            return
        except (TypeError, ValueError):
            self.status_var.set("Respuesta sin speed_kmh válido")
            return

        fuel = parse_optional_float(sample, "fuel_pct")
        fuel_liters = parse_optional_float(sample, "fuel_liters")
        self.times.append(time.monotonic() - self.started)
        self.speeds.append(speed)
        self.fuels.append(fuel)

        self.speed_var.set(f"{speed:.2f} km/h")
        if fuel is not None and fuel_liters is not None:
            self.fuel_var.set(f"{fuel:.1f} % ({fuel_liters:.1f} L)")
        elif fuel is not None:
            self.fuel_var.set(f"{fuel:.1f} %")
        else:
            self.fuel_var.set("— %")

        terrain_kind = str(sample.get("terrain_kind") or "").strip()
        mud_label = str(sample.get("mud_grade_label") or "").strip()
        wheel_grip = parse_optional_float(sample, "wheel_grip")
        contact_avg = parse_optional_float(sample, "contact_avg")
        wheel_count = sample.get("wheel_count")
        if terrain_kind:
            title = terrain_kind.upper()
            if mud_label and mud_label != terrain_kind:
                title = f"{title} ({mud_label.replace('_', ' ')})"
            self.terrain_var.set(title)
            detail_parts: list[str] = []
            surface_avg = parse_optional_float(sample, "surface_avg")
            if wheel_grip is not None:
                detail_parts.append(f"grip {wheel_grip:.2f}")
            if surface_avg is not None:
                detail_parts.append(f"surface {surface_avg:.2f}")
            elif contact_avg is not None:
                detail_parts.append(f"contact {contact_avg:.2f}")
            if wheel_count not in (None, "", 0):
                detail_parts.append(f"{wheel_count} ruedas")
            self.terrain_detail_var.set(" · ".join(detail_parts))
        else:
            self.terrain_var.set("—")
            self.terrain_detail_var.set("sin terrain_kind (¿juego abierto?)")

        if self.compare_csv:
            self._update_compare(sample)

        vehicle_id = str(sample.get("vehicle_id") or "—")
        fuel_source = str(sample.get("fuel_source") or "")
        sample_seq = sample.get("sample_seq")
        if self.source_mode == "agent":
            data_source = fuel_source or str(sample.get("throttle_input_src") or "agent")
        else:
            data_source = str(sample.get("source") or sample.get("schema_version") or "—")
        self.vehicle_var.set(f"vehicle_id: {vehicle_id}")
        self.source_var.set(f"fuente: {data_source}")

        fuel_pts = sum(1 for value in self.fuels if value is not None)
        fuel_note = f" · fuel {fuel_pts} pts" if fuel_pts else " · sin fuel_pct"
        seq_note = f" · seq {sample_seq}" if sample_seq else ""
        self.status_var.set(
            f"OK — {len(self.speeds)} pts{fuel_note}{seq_note} · {self.source_mode} · {self.interval_ms} ms"
        )

    def _update_compare(self, primary_sample: dict[str, Any]) -> None:
        try:
            api_sample = fetch_api_sample(self.base_url)
        except ApiSampleError as exc:
            self.compare_var.set(f"Comparar CSV: {exc}")
            return

        agent_sample = primary_sample
        if self.source_mode != "agent":
            if self._compare_agent is None:
                self.compare_var.set("Comparar: sin agente C#")
                return
            try:
                agent_sample = self._compare_agent.latest()
            except AgentSampleError as exc:
                self.compare_var.set(f"Comparar agente: {exc}")
                return

        self.compare_var.set(compare_terrain(agent_sample, api_sample))

    def _series_xy(
        self, values: deque[float] | deque[float | None]
    ) -> tuple[list[float], list[float]]:
        if not self.times:
            return [], []
        t0 = self.times[0]
        xs: list[float] = []
        ys: list[float] = []
        for t, value in zip(self.times, values, strict=False):
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            xs.append(t - t0)
            ys.append(float(value))
        return xs, ys

    def _set_xlim(self, xs: list[float]) -> None:
        if not xs:
            return
        span = max(xs[-1] - xs[0], 1.0) if len(xs) > 1 else max(xs[-1], 1.0)
        self.ax.set_xlim(xs[0], xs[0] + span)

    def _set_ylim(self, axis: Any, ys: list[float], *, floor_zero: bool = True) -> None:
        if not ys:
            return
        ymin, ymax = min(ys), max(ys)
        pad = 5.0 if ymax <= 5.0 else max(2.0, ymax * 0.1)
        if ymin == ymax:
            lo = max(0.0, ymin - pad) if floor_zero else ymin - pad
            axis.set_ylim(lo, ymax + pad)
        else:
            lo = max(0.0, ymin - pad * 0.2) if floor_zero else ymin - pad * 0.2
            axis.set_ylim(lo, ymax + pad * 0.2)

    def _refresh_chart(self) -> None:
        metric = self.chart_metric
        show_speed = metric in ("speed_kmh", "both")
        show_fuel = metric in ("fuel_pct", "both")

        speed_xs, speed_ys = self._series_xy(self.speeds)
        fuel_xs, fuel_ys = self._series_xy(self.fuels)

        self.speed_line.set_data(speed_xs, speed_ys)
        self.fuel_line.set_data(fuel_xs, fuel_ys)
        self.speed_line.set_visible(show_speed and bool(speed_ys))
        self.fuel_line.set_visible(show_fuel and bool(fuel_ys))

        if show_speed and show_fuel:
            self.ax.set_ylabel("km/h", color="#1f77b4")
            self.ax.tick_params(axis="y", labelcolor="#1f77b4", labelleft=True)
            self.ax_fuel.set_ylabel("fuel_pct", color="#c45c00")
            self.ax_fuel.tick_params(axis="y", labelcolor="#c45c00", labelright=True)
            self.ax_fuel.set_visible(True)
            if speed_ys:
                self._set_ylim(self.ax, speed_ys)
            if fuel_ys:
                fmin, fmax = min(fuel_ys), max(fuel_ys)
                if fmin == fmax:
                    self.ax_fuel.set_ylim(max(0.0, fmin - 5.0), min(100.0, fmax + 5.0))
                else:
                    self.ax_fuel.set_ylim(max(0.0, fmin - 3.0), min(100.0, fmax + 3.0))
            else:
                self.ax_fuel.set_ylim(0, 100)
            title = "Histórico — velocidad + combustible"
            xlim_xs = speed_xs or fuel_xs
        elif show_fuel:
            self.ax.set_ylabel("fuel_pct", color="#c45c00")
            self.ax.tick_params(axis="y", labelcolor="#c45c00", labelleft=True)
            self.ax_fuel.set_visible(False)
            if fuel_ys:
                fmin, fmax = min(fuel_ys), max(fuel_ys)
                if fmin == fmax:
                    self.ax.set_ylim(max(0.0, fmin - 5.0), min(100.0, fmax + 5.0))
                else:
                    self.ax.set_ylim(max(0.0, fmin - 3.0), min(100.0, fmax + 3.0))
            title = "Histórico — combustible" if fuel_ys else "Histórico — sin datos fuel_pct"
            xlim_xs = fuel_xs
        else:
            self.ax.set_ylabel("km/h", color="#1f77b4")
            self.ax.tick_params(axis="y", labelcolor="#1f77b4", labelleft=True)
            self.ax_fuel.set_visible(False)
            if speed_ys:
                self._set_ylim(self.ax, speed_ys)
            title = "Histórico — velocidad"
            xlim_xs = speed_xs

        self.ax.set_title(title)
        self._set_xlim(xlim_xs)
        self.canvas.draw_idle()

    def run(self) -> None:
        self.root.mainloop()
