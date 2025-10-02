"""
Ventana Auto – refactor táctil + scroll + validación y ejecución completas.

- Layout 1024×530: barra izquierda fija + panel derecho con controles, monitor y tabla.
- Entradas numéricas normalizadas (enteros y decimales) con `TecladoNumerico`.
- Tabla scrolleable 8 columnas × múltiples filas (categorías definidas en ROWS).
- Acciones: Validar, Iniciar, Pausar, Reanudar, Detener, Guardar/Cargar preset.
- Persistencia de BYPASS desde `valv_pos.csv` para información (no obligatorio para ejecutar).
- Mensajería de ejecución (resumen):
    • MFC flujo (PWM):           $;1;{mfc};1;{pwm};!
    • Válvula 1 pos A/B:         $;3;1;1;{1|2};!
    • Válvula 2 pos A/B:         $;3;2;1;{1|2};!
    • Solenoide (auto presión):  $;3;5;0;{p10};!
    • Peristáltica 1 ON/OFF:     $;3;6;1;{1|2};!
    • Peristáltica 2 ON/OFF:     $;3;7;1;{1|2};!

Notas:
- Este archivo implementa una ejecución por etapas simples (hasta 8 columnas). Cada etapa puede definir:
  tiempos de etapa, válvulas conmutadas por tA/tB, presión objetivo, estado de peristálticas,
  gas y flujo por cada MFC, setpoints de hornos (se exponen pero no se envían aquí; integrar si se requiere).
"""

from __future__ import annotations

import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico

# -----------------------------
# Helpers comunes
# -----------------------------

def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def mmss(seg):
    seg = max(0, int(seg))
    m, s = divmod(seg, 60)
    return f"{m:02d}:{s:02d}"


def flujo_a_pwm(flujo_ml_min: float, maximo: int) -> int:
    maximo = max(1, int(maximo))
    f = clamp(float(flujo_ml_min), 0.0, float(maximo))
    pwm = round((f / float(maximo)) * 255.0)
    return int(clamp(pwm, 0, 255))


# -----------------------------
# Límites MFC (por gas)
# -----------------------------

GASES = ("O2", "N2", "H2", "CO2", "CO", "Aire")

MFC_DEFAULTS = {
    1: ("O2",  {"O2": 10000, "N2": 10000, "H2": 10100, "CO2":  7370, "CO": 10000, "Aire": 10060}),
    2: ("CO2", {"O2":  9920, "N2": 10000, "H2": 10100, "CO2": 10000, "CO": 10000, "Aire": 10060}),
    3: ("N2",  {"O2":  9920, "N2": 10000, "H2": 10100, "CO2":  7370, "CO": 10000, "Aire": 10060}),
    4: ("H2",  {"O2":  9920, "N2": 10000, "H2": 10000, "CO2":  7370, "CO": 10000, "Aire": 10060}),
}

MAX_SP = 600
MAX_PRES = 20.0


class VentanaAuto(tk.Frame):
    """Secuenciador automático por etapas (hasta 8 columnas)."""

    ROWS = [
        ("Etapa", "label"),                    # fila 0 (cabeceras 1..8 en columnas)
        ("Tiempo de etapa (min)", "int"),     # fila 1
        ("", "spacer"),                      # 2
        ("Válvulas - Posición inicial", "combo_pos"),   # 3
        ("Válvulas - Tiempo en A (min)", "int"),        # 4
        ("Válvulas - Tiempo en B (min)", "int"),        # 5
        ("Presión de proceso (bar)", "decimal1"),       # 6
        ("", "spacer"),                      # 7
        ("Peristáltica 1", "combo_onoff"),              # 8
        ("Peristáltica 2", "combo_onoff"),              # 9
        ("", "spacer"),                      # 10
        ("MFC1 - Gas", "combo_gas"),                     # 11
        ("MFC1 - Flujo (mL/min)", "flow_mfc1"),          # 12
        ("MFC2 - Gas", "combo_gas"),                     # 13
        ("MFC2 - Flujo (mL/min)", "flow_mfc2"),          # 14
        ("MFC3 - Gas", "combo_gas"),                     # 15
        ("MFC3 - Flujo (mL/min)", "flow_mfc3"),          # 16
        ("MFC4 - Gas", "combo_gas"),                     # 17
        ("MFC4 - Flujo (mL/min)", "flow_mfc4"),          # 18
        ("", "spacer"),                      # 19
        ("Setpoint Horno 1 (°C)", "sp_temp"),            # 20 (no se envía en esta versión)
        ("Setpoint Horno 2 (°C)", "sp_temp"),            # 21 (no se envía en esta versión)
    ]

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Estado de ejecución
        self._run_active = False
        self._paused = False
        self._tick_id: str | None = None

        # Progreso/temporizadores
        self._active_cols: list[int] = []
        self._col_ptr = -1
        self._stage_remaining = 0  # seg restantes en etapa
        self._seg_remaining = 0    # seg restantes para cambio de posición válvula
        self._seg_pos = "A"        # posición actual válvula
        self._seg_tA = 0           # duración A (seg)
        self._seg_tB = 0           # duración B (seg)

        # Info BYPASS (si existe en CSV). No es condicionante aquí.
        self._bypass = self._leer_bypass()

        # Celdas de la grilla: por columna 1..8 un dict de widgets
        self.cells: dict[int, dict[str, tk.Widget]] = {c: {} for c in range(1, 9)}

        # Construcción UI
        self._build_ui()

    # ------------------------------------------------------------------
    # Construcción de UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=120)
        barra.grid(row=0, column=0, sticky="ns")
        barra.grid_propagate(False)

        main = ttk.Frame(self)
        main.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        main.grid_rowconfigure(3, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self._build_controls(main)
        self._build_monitor(main)
        self._build_grid(main)

    def _build_controls(self, parent):
        wrap = ttk.Frame(parent)
        wrap.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        for i in range(0, 7):
            wrap.grid_columnconfigure(i, weight=0)
        wrap.grid_columnconfigure(7, weight=1)

        ttk.Button(wrap, text="Validar", command=self._cmd_validar).grid(row=0, column=0, padx=4, pady=2)
        ttk.Button(wrap, text="Iniciar", command=self._cmd_iniciar).grid(row=0, column=1, padx=4, pady=2)
        self.btn_pausar = ttk.Button(wrap, text="Pausar", command=self._cmd_pausar, state="disabled")
        self.btn_pausar.grid(row=0, column=2, padx=4, pady=2)
        self.btn_reanudar = ttk.Button(wrap, text="Reanudar", command=self._cmd_reanudar, state="disabled")
        self.btn_reanudar.grid(row=0, column=3, padx=4, pady=2)
        ttk.Button(wrap, text="Detener", command=self._cmd_detener).grid(row=0, column=4, padx=4, pady=2)
        ttk.Button(wrap, text="Guardar preset", command=self._cmd_guardar_preset).grid(row=0, column=5, padx=8, pady=2)
        ttk.Button(wrap, text="Cargar preset", command=self._cmd_cargar_preset).grid(row=0, column=6, padx=4, pady=2)

    def _build_monitor(self, parent):
        box = ttk.LabelFrame(parent, text="Monitor")
        box.grid(row=2, column=0, sticky="ew", pady=(2, 6))
        for i in range(0, 10):
            box.grid_columnconfigure(i, weight=0)

        self.var_mon_etapa = tk.StringVar(value="-")
        self.var_mon_pos = tk.StringVar(value="-")
        self.var_mon_rest_etapa = tk.StringVar(value="-")
        self.var_mon_rest_seg = tk.StringVar(value="-")
        self.var_mon_pres = tk.StringVar(value="-")

        ttk.Label(box, text="Etapa:").grid(row=0, column=0, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_etapa).grid(row=0, column=1, padx=2, pady=4, sticky="w")
        ttk.Label(box, text="Posición válvulas:").grid(row=0, column=2, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_pos).grid(row=0, column=3, padx=2, pady=4, sticky="w")
        ttk.Label(box, text="Restante etapa:").grid(row=0, column=4, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_rest_etapa).grid(row=0, column=5, padx=2, pady=4, sticky="w")
        ttk.Label(box, text="Cambio válvulas en:").grid(row=0, column=6, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_rest_seg).grid(row=0, column=7, padx=2, pady=4, sticky="w")
        ttk.Label(box, text="Presión etapa (bar):").grid(row=0, column=8, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_pres).grid(row=0, column=9, padx=2, pady=4, sticky="w")

    def _build_grid(self, parent):
        holder = ttk.Frame(parent)
        holder.grid(row=3, column=0, sticky="nsew")
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(holder, highlightthickness=0)
        vsb = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        hsb = ttk.Scrollbar(holder, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.grid_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        label_padx = (6, 4)
        label_pady = (4, 2)
        cell_pad = dict(padx=3, pady=2)

        # Columna 0 (nombres de filas)
        for r, (text, kind) in enumerate(self.ROWS):
            lbl = ttk.Label(self.grid_frame, text=text, anchor="e", justify="right")
            lbl.grid(row=r, column=0, sticky="e", padx=label_padx, pady=label_pady)

        # Columnas 1..8 (etapas)
        for c in range(1, 9):
            head = ttk.Label(self.grid_frame, text=str(c), anchor="center")
            head.grid(row=0, column=c, sticky="nsew", **cell_pad)

            ent_t_etapa = self._make_entry_int(self.grid_frame, default="0")
            ent_t_etapa.grid(row=1, column=c, sticky="w", **cell_pad)

            cmb_pos = ttk.Combobox(self.grid_frame, values=("A", "B"), state="readonly", width=5)
            cmb_pos.set("A")
            cmb_pos.grid(row=3, column=c, sticky="w", **cell_pad)

            ent_ta = self._make_entry_int(self.grid_frame, default="0")
            ent_ta.grid(row=4, column=c, sticky="w", **cell_pad)

            ent_tb = self._make_entry_int(self.grid_frame, default="0")
            ent_tb.grid(row=5, column=c, sticky="w", **cell_pad)

            ent_pres = self._make_entry_dec(self.grid_frame, default="0.0", max_dec=1, cap_max=MAX_PRES)
            ent_pres.grid(row=6, column=c, sticky="w", **cell_pad)

            cmb_p1 = ttk.Combobox(self.grid_frame, values=("OFF", "ON"), state="readonly", width=6)
            cmb_p1.set("OFF")
            cmb_p1.grid(row=8, column=c, sticky="w", **cell_pad)

            cmb_p2 = ttk.Combobox(self.grid_frame, values=("OFF", "ON"), state="readonly", width=6)
            cmb_p2.set("OFF")
            cmb_p2.grid(row=9, column=c, sticky="w", **cell_pad)

            def make_gas_flow(row_gas, row_flow, mfc_id):
                gas_default = MFC_DEFAULTS[mfc_id][0]
                cmb = ttk.Combobox(self.grid_frame, values=GASES, state="readonly", width=8)
                cmb.set(gas_default)
                cmb.grid(row=row_gas, column=c, sticky="w", **cell_pad)
                ent = self._make_entry_int(self.grid_frame, default="0")
                ent.grid(row=row_flow, column=c, sticky="w", **cell_pad)
                self._attach_flow_logic(ent, mfc_id, cmb)
                return cmb, ent

            cmb_m1, ent_m1 = make_gas_flow(11, 12, 1)
            cmb_m2, ent_m2 = make_gas_flow(13, 14, 2)
            cmb_m3, ent_m3 = make_gas_flow(15, 16, 3)
            cmb_m4, ent_m4 = make_gas_flow(17, 18, 4)

            ent_t1 = self._make_entry_int(self.grid_frame, default="0", cap_max=MAX_SP)
            ent_t1.grid(row=20, column=c, sticky="w", **cell_pad)

            ent_t2 = self._make_entry_int(self.grid_frame, default="0", cap_max=MAX_SP)
            ent_t2.grid(row=21, column=c, sticky="w", **cell_pad)

            self.cells[c] = {
                "t_etapa": ent_t_etapa,
                "pos_ini": cmb_pos,
                "t_a": ent_ta,
                "t_b": ent_tb,
                "pres": ent_pres,
                "p1": cmb_p1,
                "p2": cmb_p2,
                "m1_gas": cmb_m1, "m1_f": ent_m1,
                "m2_gas": cmb_m2, "m2_f": ent_m2,
                "m3_gas": cmb_m3, "m3_f": ent_m3,
                "m4_gas": cmb_m4, "m4_f": ent_m4,
                "t1": ent_t1, "t2": ent_t2,
            }
        self._enable_touch_scroll()

    # ------------------------------------------------------------------
    # Validación y preset (guardar/cargar)
    # ------------------------------------------------------------------
    def _cmd_validar(self) -> None:
        errores = []
        etapas_activas = []
        for c in range(1, 9):
            v_t = self._read_int(self.cells[c]["t_etapa"], 0)
            if v_t <= 0:
                continue
            etapas_activas.append(c)
            # Validaciones simples
            v_ta = self._read_int(self.cells[c]["t_a"], 0)
            v_tb = self._read_int(self.cells[c]["t_b"], 0)
            v_pres = self._read_float(self.cells[c]["pres"], 0.0)
            if v_t < 0:
                errores.append(f"Col {c}: Tiempo de etapa inválido")
            if v_ta < 0 or v_tb < 0:
                errores.append(f"Col {c}: Tiempos A/B inválidos")
            if not (0.0 <= v_pres <= MAX_PRES):
                errores.append(f"Col {c}: Presión fuera de rango (0..{MAX_PRES} bar)")
            for mfc_id in (1, 2, 3, 4):
                gas = self.cells[c][f"m{mfc_id}_gas"].get()
                if gas not in GASES:
                    errores.append(f"Col {c}: Gas MFC{mfc_id} inválido")
                maxv = self._max_mfc(mfc_id, gas)
                try:
                    f = float((self.cells[c][f"m{mfc_id}_f"].get() or "0").strip())
                except Exception:
                    f = -1
                if f < 0 or f > maxv:
                    errores.append(f"Col {c}: Flujo MFC{mfc_id} fuera de 0..{maxv}")

        if not etapas_activas:
            messagebox.showwarning("Validación", "No hay etapas activas (columna con tiempo > 0)")
            return

        if errores:
            msg = "".join(errores[:20])
            if len(errores) > 20:
                msg += f"... y {len(errores)-20} más"
            messagebox.showerror("Errores de validación", msg)
        else:
            messagebox.showinfo("Validación", f"Validación completa. Etapas activas: {etapas_activas}")

    def _cmd_guardar_preset(self) -> None:
        path = filedialog.asksaveasfilename(title="Guardar preset", defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                # Encabezado: nombre de fila + valores col 1..8
                for r, (text, kind) in enumerate(self.ROWS):
                    row = [text]
                    if kind == "label":
                        row.extend([str(c) for c in range(1, 9)])
                    else:
                        for c in range(1, 9):
                            row.append(self._cell_value_str(r, c))
                    w.writerow(row)
            messagebox.showinfo("Preset", "Preset guardado correctamente.")
        except Exception as e:
            messagebox.showerror("Preset", f"No se pudo guardar el preset: {e}")

    def _cmd_cargar_preset(self) -> None:
        path = filedialog.askopenfilename(title="Cargar preset", defaultextension=".csv",
                                          filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8") as f:
                rd = csv.reader(f)
                rows = list(rd)
            # Mapear por texto de fila
            mapa = {row[0]: row[1:] for row in rows if row}
            for r, (text, kind) in enumerate(self.ROWS):
                vals = mapa.get(text)
                if not vals:
                    continue
                for c in range(1, 9):
                    val = vals[c-1] if c-1 < len(vals) else ""
                    self._apply_cell_value(r, c, val)
            messagebox.showinfo("Preset", "Preset cargado.")
        except Exception as e:
            messagebox.showerror("Preset", f"No se pudo cargar el preset: {e}")

    # ------------------------------------------------------------------
    # Ejecución: iniciar/pausar/reanudar/detener
    # ------------------------------------------------------------------
    def _cmd_iniciar(self) -> None:
        if self._run_active:
            messagebox.showwarning("Auto", "La ejecución ya está en curso.")
            return
        # Preparar lista de columnas activas
        self._active_cols = [c for c in range(1, 9) if self._read_int(self.cells[c]["t_etapa"], 0) > 0]
        if not self._active_cols:
            messagebox.showwarning("Auto", "No hay etapas activas (tiempo > 0).")
            return
        self._col_ptr = -1
        self._run_active = True
        self._paused = False
        self.btn_pausar.configure(state="normal")
        self.btn_reanudar.configure(state="disabled")
        self._next_stage()

    def _cmd_pausar(self) -> None:
        if not self._run_active or self._paused:
            return
        self._paused = True
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None
        self.btn_pausar.configure(state="disabled")
        self.btn_reanudar.configure(state="normal")

    def _cmd_reanudar(self) -> None:
        if not self._run_active or not self._paused:
            return
        self._paused = False
        self.btn_pausar.configure(state="normal")
        self.btn_reanudar.configure(state="disabled")
        self._schedule_tick()

    def _cmd_detener(self) -> None:
        self._stop_all()
        messagebox.showinfo("Auto", "Ejecución detenida.")

    def _stop_all(self) -> None:
        self._run_active = False
        self._paused = False
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None
        self.btn_pausar.configure(state="disabled")
        self.btn_reanudar.configure(state="disabled")
        # Limpieza de monitor
        self.var_mon_etapa.set("-")
        self.var_mon_pos.set("-")
        self.var_mon_rest_etapa.set("-")
        self.var_mon_rest_seg.set("-")
        self.var_mon_pres.set("-")

    # ------------------------------------------------------------------
    # Avance de etapas y temporización
    # ------------------------------------------------------------------
    def _next_stage(self) -> None:
        """Avanza a la siguiente etapa activa; si no hay más, detiene."""
        self._col_ptr += 1
        if self._col_ptr >= len(self._active_cols):
            self._stop_all()
            messagebox.showinfo("Auto", "Secuencia completada.")
            return
        col = self._active_cols[self._col_ptr]
        # Leer parámetros de la etapa
        t_min = self._read_int(self.cells[col]["t_etapa"], 0)
        self._stage_remaining = max(1, int(t_min) * 60)
        pos_ini = (self.cells[col]["pos_ini"].get() or "A").strip().upper()
        self._seg_pos = "A" if pos_ini != "B" else "B"
        self._seg_tA = max(0, int(self._read_int(self.cells[col]["t_a"], 0) * 60))
        self._seg_tB = max(0, int(self._read_int(self.cells[col]["t_b"], 0) * 60))
        self._seg_remaining = self._seg_tA if self._seg_pos == "A" else self._seg_tB

        # Envíos al inicio de etapa
        self._enviar_valvulas_pos(self._seg_pos)
        pres = self._read_float(self.cells[col]["pres"], 0.0)
        self._enviar_presion_auto(pres)
        p1 = self.cells[col]["p1"].get() == "ON"
        p2 = self.cells[col]["p2"].get() == "ON"
        self._enviar_peristalticas(p1, p2)
        self._enviar_mfcs(col)

        # Monitor
        self.var_mon_etapa.set(str(col))
        self.var_mon_pos.set(self._seg_pos)
        self.var_mon_rest_etapa.set(mmss(self._stage_remaining))
        self.var_mon_rest_seg.set(mmss(self._seg_remaining) if self._seg_remaining > 0 else "-")
        self.var_mon_pres.set(f"{pres:.1f}")

        # Programar ticks
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        if self._run_active and not self._paused:
            self._tick_id = self.after(1000, self._tick)

    def _tick(self) -> None:
        if not self._run_active or self._paused:
            return
        # Contadores
        self._stage_remaining -= 1
        if self._stage_remaining <= 0:
            self._next_stage()
            return

        if self._seg_tA > 0 or self._seg_tB > 0:
            self._seg_remaining -= 1
            if self._seg_remaining <= 0:
                # Conmutar posición
                self._seg_pos = "B" if self._seg_pos == "A" else "A"
                self._enviar_valvulas_pos(self._seg_pos)
                self._seg_remaining = self._seg_tA if self._seg_pos == "A" else self._seg_tB

        # Actualizar monitor
        self.var_mon_pos.set(self._seg_pos)
        self.var_mon_rest_etapa.set(mmss(self._stage_remaining))
        self.var_mon_rest_seg.set(mmss(self._seg_remaining) if self._seg_remaining > 0 else "-")

        # Siguiente tick
        self._schedule_tick()

    # ------------------------------------------------------------------
    # Envíos (Arduino)
    # ------------------------------------------------------------------
    def _send(self, msg: str) -> None:
        print("[TX AUTO]", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            try:
                self.controlador.enviar_a_arduino(msg)
            except Exception:
                pass

    def _enviar_valvulas_pos(self, pos: str) -> None:
        code = "1" if (pos or "A").upper() == "A" else "2"
        self._send(f"$;3;1;1;{code};!")  # V1
        self._send(f"$;3;2;1;{code};!")  # V2

    def _enviar_presion_auto(self, pres_bar: float) -> None:
        p = clamp(float(pres_bar), 0.0, MAX_PRES)
        p10 = int(round(p * 10))
        self._send(f"$;3;5;0;{p10};!")

    def _enviar_peristalticas(self, p1_on: bool, p2_on: bool) -> None:
        self._send(f"$;3;6;1;{'1' if p1_on else '2'};!")
        self._send(f"$;3;7;1;{'1' if p2_on else '2'};!")

    def _enviar_mfcs(self, col: int) -> None:
        for mfc_id in (1, 2, 3, 4):
            gas = self.cells[col][f"m{mfc_id}_gas"].get()
            maxv = self._max_mfc(mfc_id, gas)
            try:
                flujo = float((self.cells[col][f"m{mfc_id}_f"].get() or "0").strip())
            except Exception:
                flujo = 0.0
            flujo = clamp(flujo, 0.0, float(maxv))
            pwm = flujo_a_pwm(flujo, maxv)
            self._send(f"$;1;{mfc_id};1;{pwm};!")

    # ------------------------------------------------------------------
    # Lectura/normalización de celdas
    # ------------------------------------------------------------------
    def _cell_value_str(self, r: int, c: int) -> str:
        kind = self.ROWS[r][1]
        if kind in ("label", "spacer"):
            return ""
        w = self.cells[c].get(self._key_from_row(r))
        if not w:
            return ""
        if isinstance(w, ttk.Combobox):
            return (w.get() or "").strip()
        return (w.get() or "").strip()

    def _apply_cell_value(self, r: int, c: int, val: str) -> None:
        kind = self.ROWS[r][1]
        key = self._key_from_row(r)
        w = self.cells[c].get(key)
        if not w:
            return
        if isinstance(w, ttk.Combobox):
            try:
                w.set(val)
            except Exception:
                pass
        else:
            w.delete(0, tk.END)
            w.insert(0, val)

    def _key_from_row(self, r: int) -> str:
        mapa = {
            1: "t_etapa",
            3: "pos_ini",
            4: "t_a",
            5: "t_b",
            6: "pres",
            8: "p1",
            9: "p2",
            11: "m1_gas", 12: "m1_f",
            13: "m2_gas", 14: "m2_f",
            15: "m3_gas", 16: "m3_f",
            17: "m4_gas", 18: "m4_f",
            20: "t1",
            21: "t2",
        }
        return mapa.get(r, f"r{r}")

    def _read_int(self, entry: ttk.Entry, default: int = 0) -> int:
        try:
            v = int(float((entry.get() or "").strip()))
        except Exception:
            v = default
        return v

    def _read_float(self, entry: ttk.Entry, default: float = 0.0) -> float:
        try:
            v = float((entry.get() or "").strip())
        except Exception:
            v = default
        return v

    # ------------------------------------------------------------------
    # Entradas y límites
    # ------------------------------------------------------------------
    def _max_mfc(self, mfc_id: int, gas: str) -> int:
        gas = gas if gas in MFC_DEFAULTS[mfc_id][1] else MFC_DEFAULTS[mfc_id][0]
        return int(MFC_DEFAULTS[mfc_id][1][gas])

    def _attach_flow_logic(self, entry: ttk.Entry, mfc_id: int, cmb_gas: ttk.Combobox) -> None:
        """Asocia teclado numérico y capado por gas para el Entry de flujo."""
        entry.bind(
            "<Button-1>",
            lambda _e, en=entry: TecladoNumerico(self, en, on_submit=lambda v: self._apply_flow_value(en, v, mfc_id, cmb_gas)),
        )

    def _apply_flow_value(self, entry: ttk.Entry, valor, mfc_id: int, cmb_gas: ttk.Combobox) -> None:
        gas = cmb_gas.get()
        maxv = self._max_mfc(mfc_id, gas)
        try:
            f = float(valor)
        except Exception:
            f = 0.0
        f = clamp(f, 0.0, float(maxv))
        entry.delete(0, tk.END)
        entry.insert(0, str(int(f)) if float(f).is_integer() else f"{f}")

    def _make_entry_int(self, parent, default: str = "0", cap_max: int | None = None) -> ttk.Entry:
        e = ttk.Entry(parent, width=10)
        e.insert(0, default)
        def open_num():
            TecladoNumerico(self, e, on_submit=lambda v: self._on_submit_int(e, v, cap_max))
        e.bind("<Button-1>", lambda _e: open_num())
        return e

    def _on_submit_int(self, entry: ttk.Entry, valor, cap_max: int | None) -> None:
        try:
            v = int(float(valor))
        except Exception:
            v = 0
        if cap_max is not None:
            v = clamp(v, 0, cap_max)
        entry.delete(0, tk.END)
        entry.insert(0, str(v))

    def _make_entry_dec(self, parent, default: str = "0.0", max_dec: int = 1, cap_max: float | None = None) -> ttk.Entry:
        e = ttk.Entry(parent, width=10)
        e.insert(0, default)
        def open_num():
            TecladoNumerico(self, e, on_submit=lambda v: self._on_submit_dec(e, v, max_dec, cap_max))
        e.bind("<Button-1>", lambda _e: open_num())
        return e

    def _on_submit_dec(self, entry: ttk.Entry, valor, max_dec: int, cap_max: float | None) -> None:
        try:
            v = float(valor)
        except Exception:
            v = 0.0
        if cap_max is not None:
            v = clamp(v, 0.0, float(cap_max))
        fmt = f"{{:.{max_dec}f}}"
        entry.delete(0, tk.END)
        entry.insert(0, fmt.format(v))

    # ------------------------------------------------------------------
    # BYPASS (informativo)
    # ------------------------------------------------------------------
    def _leer_bypass(self) -> int:
        path = os.path.join(os.path.dirname(__file__), "valv_pos.csv")
        try:
            if os.path.exists(path):
                with open(path, newline="", encoding="utf-8") as f:
                    for nombre, pos in csv.reader(f):
                        if (nombre or "").strip().upper() == "BYP":
                            v = (pos or "").strip()
                            return 2 if v == "2" else 1
        except Exception:
            pass
        return 1

    # -----------------------------
    # Scroll táctil (panning en Canvas)
    # -----------------------------
    def _enable_touch_scroll(self) -> None:
        """Activa desplazamiento por arrastre en el canvas y rueda del mouse."""
        # Arrastre directo sobre el canvas
        self.canvas.bind("<ButtonPress-1>", self._on_scroll_start)
        self.canvas.bind("<B1-Motion>", self._on_scroll_move)

        # Arrastre también cuando el puntero está sobre widgets hijos del frame interno
        self.grid_frame.bind("<ButtonPress-1>", self._on_inner_scroll_start, add="+")
        self.grid_frame.bind("<B1-Motion>", self._on_inner_scroll_move, add="+")

        # Rueda del mouse (Windows/macOS)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        # Linux/X11: rueda arriba/abajo son Button-4/5
        self.canvas.bind_all("<Button-4>", lambda e: self._wheel_units(-3))
        self.canvas.bind_all("<Button-5>", lambda e: self._wheel_units(+3))

        # Shift + rueda para scroll horizontal (donde aplique)
        self.canvas.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel)

    def _on_scroll_start(self, event):
        """Marca el punto inicial de arrastre cuando el evento llega al canvas."""
        self.canvas.scan_mark(event.x, event.y)

    def _on_scroll_move(self, event):
        """Arrastra el contenido según el movimiento."""
        # gain=1 da una sensación más "pegada al dedo"; puedes probar 2 o 3 para más sensibilidad
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_inner_scroll_start(self, event):
        """Permite iniciar el arrastre aunque el puntero esté sobre un widget hijo."""
        cx = self._to_canvas_x(event)
        cy = self._to_canvas_y(event)
        self.canvas.scan_mark(cx, cy)

    def _on_inner_scroll_move(self, event):
        """Arrastra desde widgets hijos, transformando coords al sistema del canvas."""
        cx = self._to_canvas_x(event)
        cy = self._to_canvas_y(event)
        self.canvas.scan_dragto(cx, cy, gain=1)

    def _to_canvas_x(self, event) -> int:
        """Convierte coord X del evento (en coords del widget origen) a coords del canvas."""
        return int(self.canvas.canvasx(event.x_root - self.canvas.winfo_rootx()))

    def _to_canvas_y(self, event) -> int:
        """Convierte coord Y del evento (en coords del widget origen) a coords del canvas."""
        return int(self.canvas.canvasy(event.y_root - self.canvas.winfo_rooty()))

    def _on_mousewheel(self, event):
        """Scroll vertical con rueda (Windows/macOS)."""
        # En Windows, event.delta suele ser múltiplo de 120; en macOS puede ser más pequeño
        delta = event.delta
        if delta == 0:
            return
        steps = -1 if delta > 0 else +1
        self._wheel_units(steps * 3)  # ajusta 3 para más/menos sensibilidad

    def _on_shift_mousewheel(self, event):
        """Scroll horizontal con Shift + rueda."""
        delta = event.delta
        if delta == 0:
            return
        steps = -1 if delta > 0 else +1
        self.canvas.xview_scroll(steps * 3, "units")

    def _wheel_units(self, units: int):
        """Helper para desplazar N 'units' verticalmente (positivo = abajo)."""
        self.canvas.yview_scroll(units, "units")