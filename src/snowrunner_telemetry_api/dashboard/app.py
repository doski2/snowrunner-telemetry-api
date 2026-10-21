"""GUI tkinter — panel en vivo: velocidad, gas, combustible, terreno y estado de grabación."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Any

from ..context import ContextTags
from ..physics import LiveMetrics
from .advice import EfficiencyTable, IdealThrottleTable
from .agent_source import AgentLoopSource, AgentSampleError
from .poll import ApiSampleError, fetch_api_sample, parse_speed_kmh, resolve_source
from ..autorecord import PlayRecorder
from ..coverage import CoverageTracker
from .terrain import compare_terrain
from .view import build_view

BIG = ("Segoe UI", 28, "bold")
MID = ("Segoe UI", 18, "bold")
SMALL = ("Segoe UI", 10)
MUTED = "#666"


class SpeedDashboard:
    def __init__(
        self,
        base_url: str,
        interval_ms: int,
        *,
        source: str = "auto",
        compare_csv: bool = False,
        record_label: str | None = "dash",
        full_rows: bool = False,
        cap_seconds: float = 0.0,
    ) -> None:
        self.base_url = base_url
        self.interval_ms = interval_ms
        self.source_mode = resolve_source(source, base_url)
        self.compare_csv = compare_csv
        self._ideal_table = IdealThrottleTable()
        self._eff_table = EfficiencyTable()
        self._context = ContextTags()
        self._coverage = CoverageTracker()
        self._recorder = (
            PlayRecorder(
                context=self._context,
                interval_ms=min(interval_ms, 100),
                label=record_label,
                slim=not full_rows,
                coverage=self._coverage,
                cap_seconds=cap_seconds,
            )
            if record_label
            else None
        )

        self._agent: AgentLoopSource | None = None
        self._compare_agent: AgentLoopSource | None = None
        if self.source_mode == "agent" or compare_csv:
            # con el agente como fuente se graba cada muestra suya, no solo las que pinta la ventana
            on_sample = self._recorder.handle if self._recorder and self.source_mode == "agent" else None
            self._agent = AgentLoopSource(interval_ms, on_sample)
            self._agent.start()
        if compare_csv and self.source_mode != "agent":
            self._compare_agent = AgentLoopSource(interval_ms)
            self._compare_agent.start()

        self.running = True
        self.vmax = 0.0
        self._live = LiveMetrics()
        self._last_seq: object = None
        self._last_metrics: dict = {}

        self.root = tk.Tk()
        self.root.title("SnowRunner — Telemetría")
        self.root.geometry("860x480")
        self.root.minsize(800, 440)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(0, self._tick)

    # ---------------------------------------------------------------- UI

    def _card(self, title: str, row: int, column: int) -> ttk.LabelFrame:
        card = ttk.LabelFrame(self.grid, text=title, padding=(12, 6, 12, 10))
        card.grid(row=row, column=column, sticky="nsew", padx=5, pady=5)
        return card

    def _value(self, parent: tk.Misc, var: tk.StringVar, font: tuple, **kw: Any) -> ttk.Label:
        label = ttk.Label(parent, textvariable=var, font=font, **kw)
        label.pack(anchor=tk.W)
        return label

    def _note(self, parent: tk.Misc, var: tk.StringVar, wrap: int = 230) -> None:
        ttk.Label(
            parent, textvariable=var, font=SMALL, foreground=MUTED, wraplength=wrap, justify=tk.LEFT
        ).pack(anchor=tk.W, pady=(2, 0))

    def _bar(self, parent: tk.Misc) -> ttk.Progressbar:
        bar = ttk.Progressbar(parent, mode="determinate", maximum=100, length=200)
        bar.pack(anchor=tk.W, fill=tk.X, pady=(6, 0))
        return bar

    def _build_ui(self) -> None:
        self.grid = ttk.Frame(self.root, padding=(8, 8, 8, 0))
        self.grid.pack(fill=tk.BOTH, expand=True)
        for col in range(3):
            self.grid.columnconfigure(col, weight=1, uniform="cards")
        for row in range(3):
            self.grid.rowconfigure(row, weight=1)

        # Fila 1: lo que se conduce
        card = self._card("Velocidad", 0, 0)
        self.speed_var = tk.StringVar(value="—")
        row = ttk.Frame(card)
        row.pack(anchor=tk.W)
        ttk.Label(row, textvariable=self.speed_var, font=BIG).pack(side=tk.LEFT)
        ttk.Label(row, text=" km/h", font=SMALL, foreground=MUTED).pack(side=tk.LEFT, anchor=tk.S, pady=6)
        self.vmax_var = tk.StringVar(value="máx 0.0 km/h")
        self._note(card, self.vmax_var)

        card = self._card("Gas", 0, 1)
        self.gas_var = tk.StringVar(value="—")
        self._value(card, self.gas_var, BIG, foreground="#6a3d9a")
        self.gas_bar = self._bar(card)
        self.gas_advice_var = tk.StringVar(value="")
        self._note(card, self.gas_advice_var)
        self.gas_eff_var = tk.StringVar(value="")
        self._note(card, self.gas_eff_var)

        card = self._card("Combustible", 0, 2)
        self.fuel_var = tk.StringVar(value="—")
        self._value(card, self.fuel_var, MID, foreground="#c45c00")
        self.fuel_bar = self._bar(card)

        # Fila 2: contexto
        card = self._card("Terreno", 1, 0)
        self.terrain_var = tk.StringVar(value="—")
        self._value(card, self.terrain_var, MID, foreground="#2d6a4f")
        self.terrain_detail_var = tk.StringVar(value="")
        self._note(card, self.terrain_detail_var)

        card = self._card("Camión", 1, 1)
        self.vehicle_var = tk.StringVar(value="—")
        self._value(card, self.vehicle_var, ("Segoe UI", 12, "bold"))
        self.source_var = tk.StringVar(value="")
        self._note(card, self.source_var)
        self.ctx_var = tk.StringVar(value="")
        self._note(card, self.ctx_var)

        card = self._card("Grabación", 1, 2)
        self.rec_var = tk.StringVar(value="No se graba")
        self._value(card, self.rec_var, ("Segoe UI", 12, "bold"))
        self.rec_detail_var = tk.StringVar(value="" if self._recorder is None else "esperando camión…")
        self._note(card, self.rec_detail_var)
        self.cov_var = tk.StringVar(value="")
        self._note(card, self.cov_var)
        if self._recorder is not None:
            self.rec_var.set("● REC  0 filas")

        # Fila 3: física derivada
        card = self._card("Inclinación", 2, 0)
        self.tilt_var = tk.StringVar(value="—")
        self._value(card, self.tilt_var, MID, foreground="#1f5f8b")
        self.tilt_detail_var = tk.StringVar(value="")
        self._note(card, self.tilt_detail_var)

        card = self._card("Aceleración neta", 2, 1)
        self.accel_var = tk.StringVar(value="—")
        self._value(card, self.accel_var, MID, foreground="#a02c5d")
        self.accel_detail_var = tk.StringVar(value="")
        self._note(card, self.accel_detail_var)

        card = self._card("Consumo", 2, 2)
        self.cons_var = tk.StringVar(value="—")
        self._value(card, self.cons_var, MID, foreground="#c45c00")
        self.cons_detail_var = tk.StringVar(value="")
        self._note(card, self.cons_detail_var)

        # Barra inferior
        self.compare_var = tk.StringVar(value="")
        if self.compare_csv:
            ttk.Label(
                self.root, textvariable=self.compare_var, font=("Segoe UI", 9), wraplength=780
            ).pack(anchor=tk.W, padx=14)
            self.compare_var.set("Modo comparar: agente vs CSV (necesita run_api.bat + grabar_ce.py)")

        footer = ttk.Frame(self.root, padding=(12, 4, 12, 10))
        footer.pack(fill=tk.X)
        self.pause_btn = ttk.Button(footer, text="Pausar", command=self._toggle_pause)
        self.pause_btn.pack(side=tk.LEFT)
        ttk.Button(footer, text="Reiniciar máx", command=self._reset_vmax).pack(side=tk.LEFT, padx=(8, 0))
        self.status_var = tk.StringVar(
            value="Leyendo agente C# (SnowRunner en mapa)"
            if self.source_mode == "agent"
            else f"Poll API {self.base_url}/v1/sample"
        )
        ttk.Label(footer, textvariable=self.status_var, foreground=MUTED).pack(side=tk.RIGHT)

    # ----------------------------------------------------------- acciones

    def _toggle_pause(self) -> None:
        self.running = not self.running
        self.pause_btn.configure(text="Reanudar" if not self.running else "Pausar")
        self.status_var.set("Pausado" if not self.running else "Reanudado")

    def _reset_vmax(self) -> None:
        self.vmax = 0.0
        self.vmax_var.set("máx 0.0 km/h")

    def _on_close(self) -> None:
        for agent in (self._agent, self._compare_agent):
            if agent is not None:
                agent.stop()
        if self._recorder is not None:
            self._recorder.close()
        self.root.destroy()

    # ------------------------------------------------------------- bucle

    def _tick(self) -> None:
        if self.running:
            self._poll()
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

        ctx = self._context.current()
        if self._recorder is not None:
            if self.source_mode != "agent":
                self._recorder.handle(sample)  # fuente API: se graba al ritmo de la ventana
            n = self._recorder.rows
            self.rec_var.set(f"● REC  {n} fila{'' if n == 1 else 's'}")
            path = self._recorder.path
            self.rec_detail_var.set(path.name if path else "esperando camión…")
            self.cov_var.set(
                self._coverage.hint(
                    str(sample.get("vehicle_id") or ""), str(sample.get("terrain_kind") or "sin_dato"), ctx
                )
            )

        seq = sample.get("sample_seq")
        if seq is None or seq != self._last_seq:  # una muestra repetida no debe recalcular nada
            ts = sample.get("ts_ms")
            now = float(ts) / 1000.0 if isinstance(ts, (int, float)) else time.monotonic()
            self._last_metrics = self._live.update(sample, now)
            self._last_seq = seq
        view = build_view(sample, speed, self._ideal_table, self._last_metrics, self._eff_table, ctx)
        self.vmax = max(self.vmax, speed)
        self.speed_var.set(view.speed_text)
        self.vmax_var.set(f"máx {self.vmax:.1f} km/h")
        self.gas_var.set(view.gas_text)
        self.gas_bar["value"] = view.gas_pct or 0
        self.gas_advice_var.set(view.gas_advice)
        self.gas_eff_var.set(view.efficiency_advice)
        self.ctx_var.set(", ".join(f"{k}={v}" for k, v in ctx.items()) if ctx else "sin etiquetas (set_context.py)")
        self.fuel_var.set(view.fuel_text)
        self.fuel_bar["value"] = view.fuel_pct or 0
        self.terrain_var.set(view.terrain_title)
        self.terrain_detail_var.set(view.terrain_detail)
        self.vehicle_var.set(view.vehicle)
        self.source_var.set(f"fuente: {view.source}")
        self.tilt_var.set(view.tilt_text)
        self.tilt_detail_var.set(view.tilt_detail)
        self.accel_var.set(view.accel_text)
        self.accel_detail_var.set(view.accel_detail)
        self.cons_var.set(view.consumption_text)
        self.cons_detail_var.set(view.consumption_detail)

        if self.compare_csv:
            self._update_compare(sample)

        self.status_var.set(
            f"OK · {self.source_mode} · {self.interval_ms} ms" + (f" · seq {seq}" if seq else "")
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

    def run(self) -> None:
        self.root.mainloop()
