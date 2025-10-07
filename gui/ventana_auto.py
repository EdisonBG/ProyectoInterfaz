# gui/ventana_auto.py
import csv
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico
from ui.widgets import TouchButton
try:
    from ui import constants as C
except Exception:
    class _C_:
        FONT_BASE = ("Calibri", 16)
        ENTRY_WIDTH = 12
        COMBO_WIDTH = 12
    C = _C_()


# ========================== Utilidades comunes ==========================

def clamp(v, a, b):
    """Recorta v al rango [a, b]."""
    return a if v < a else (b if v > b else v)


def mmss(segundos: int) -> str:
    """Devuelve MM:SS desde un entero de segundos (recortado a >=0)."""
    s = max(0, int(segundos))
    m, s = divmod(s, 60)
    return f"{m:02d}:{s:02d}"


def flujo_a_pwm(flujo_ml_min: float, maximo: int) -> int:
    """Convierte flujo en mL/min a un PWM [0..255] dado un máximo por gas."""
    maximo = max(1, int(maximo))
    f = clamp(float(flujo_ml_min), 0.0, float(maximo))
    return int(clamp(round((f / float(maximo)) * 255.0), 0, 255))


# ======================= Límites y defaults MFC =========================

GASES = ("O2", "N2", "H2", "CO2", "CO", "Aire")

# MFC1 (por defecto O2)
MFC1_LIMITS = {
    "O2": 10000, "N2": 10000, "H2": 10100, "CO2": 7370, "CO": 10000, "Aire": 10060
}
# MFC2 (por defecto CO2)
MFC2_LIMITS = {
    "O2": 9920, "N2": 10000, "H2": 10100, "CO2": 10000, "CO": 10000, "Aire": 10060
}
# MFC3 (por defecto N2)
MFC3_LIMITS = {
    "O2": 9920, "N2": 10000, "H2": 10100, "CO2": 7370, "CO": 10000, "Aire": 10060
}
# MFC4 (por defecto H2)
MFC4_LIMITS = {
    "O2": 9920, "N2": 10000, "H2": 10000, "CO2": 7370, "CO": 10000, "Aire": 10060
}

MFC_DEFAULTS = {
    1: ("O2", MFC1_LIMITS),
    2: ("CO2", MFC2_LIMITS),
    3: ("N2", MFC3_LIMITS),
    4: ("H2", MFC4_LIMITS),
}

MAX_SP = 600
MAX_PRES = 20.0


class VentanaAuto(tk.Frame):
    """Secuenciador automático por etapas con control de Válvulas, Peristálticas, MFC y SP de hornos."""

    # Definición de filas (títulos y tipo de celda)
    ROWS = [
        ("Etapa", "label"),
        ("Tiempo de etapa (min)", "int"),
        ("", "spacer"),
        ("Válvulas - Posición inicial", "combo_pos"),
        ("Válvulas - Tiempo en A (min)", "int"),
        ("Válvulas - Tiempo en B (min)", "int"),
        ("Presión de proceso (bar)", "decimal1"),
        ("", "spacer"),
        ("Peristáltica 1", "combo_onoff"),
        ("Peristáltica 2", "combo_onoff"),
        ("", "spacer"),
        ("MFC1 - Gas", "combo_gas"),
        ("MFC1 - Flujo (mL/min)", "flow_mfc1"),
        ("MFC2 - Gas", "combo_gas"),
        ("MFC2 - Flujo (mL/min)", "flow_mfc2"),
        ("MFC3 - Gas", "combo_gas"),
        ("MFC3 - Flujo (mL/min)", "flow_mfc3"),
        ("MFC4 - Gas", "combo_gas"),
        ("MFC4 - Flujo (mL/min)", "flow_mfc4"),
        ("", "spacer"),
        ("Setpoint Horno 1 (°C)", "sp_temp"),
        ("Setpoint Horno 2 (°C)", "sp_temp"),
    ]

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Estado de ejecución
        self._run_active = False
        self._paused = False
        self._tick_id = None
        self._active_cols = []   # columnas (1..8) con etapas válidas
        self._col_ptr = -1       # índice en _active_cols
        self._stage_remaining = 0
        self._seg_remaining = 0
        self._seg_pos = "A"
        self._seg_tA = 0
        self._seg_tB = 0

        # Estado BYPASS leído desde ventana de válvulas
        self._bypass = self._leer_bypass()

        # Referencias a celdas por columna
        self.cells: dict[int, dict[str, tk.Widget]] = {c: {} for c in range(1, 9)}

        self._build_ui()

    # ------------------------------------------------------------------
    # Construcción de UI (barra, paneles, grilla)
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --------- barra de navegación (columna 0) ---------
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=140)
        barra.grid(row=0, column=0, sticky="ns")
        barra.grid_propagate(False)

        # --------- contenedor derecho (columna 1) ---------
        main = ttk.Frame(self)
        main.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        main.grid_rowconfigure(3, weight=1)  # fila de la grilla
        main.grid_columnconfigure(0, weight=1)

        # --------- fila 1: controles superiores ---------
        self._build_controls(main)

        # --------- fila 2: monitor ---------
        self._build_monitor(main)

        # --------- fila 3: canvas scrolleable con grid ---------
        self._build_grid(main)

    def _build_controls(self, parent):
        wrap = ttk.Frame(parent)
        wrap.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        # expandir al centro para que “quepa” cómodamente en 1024x600
        for i in range(0, 7):
            wrap.grid_columnconfigure(i, weight=0)
        wrap.grid_columnconfigure(7, weight=1)

        TouchButton(wrap, text="Validar", command=self._cmd_validar).grid(row=0, column=0, padx=4, pady=2)
        TouchButton(wrap, text="Iniciar", command=self._cmd_iniciar).grid(row=0, column=1, padx=4, pady=2)

        self.btn_pausar = TouchButton(wrap, text="Pausar", command=self._cmd_pausar, state="disabled")
        self.btn_pausar.grid(row=0, column=2, padx=4, pady=2)

        self.btn_reanudar = TouchButton(wrap, text="Reanudar", command=self._cmd_reanudar, state="disabled")
        self.btn_reanudar.grid(row=0, column=3, padx=4, pady=2)

        TouchButton(wrap, text="Detener", command=self._cmd_detener).grid(row=0, column=4, padx=4, pady=2)

        TouchButton(wrap, text="Guardar preset", command=self._cmd_guardar_preset).grid(row=0, column=5, padx=8, pady=2)
        TouchButton(wrap, text="Cargar preset", command=self._cmd_cargar_preset).grid(row=0, column=6, padx=4, pady=2)

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

        def lbl(r, c, text=None, var=None):
            if text:
                ttk.Label(box, text=text, font=C.FONT_BASE).grid(row=0, column=c, padx=6, pady=4, sticky="e")
            if var:
                ttk.Label(box, textvariable=var, font=C.FONT_BASE).grid(row=0, column=c+1, padx=2, pady=4, sticky="w")

        lbl(0, 0, "Etapa:", self.var_mon_etapa)
        lbl(0, 2, "Posición válvulas:", self.var_mon_pos)
        lbl(0, 4, "Restante etapa:", self.var_mon_rest_etapa)
        lbl(0, 6, "Cambio válvulas en:", self.var_mon_rest_seg)
        lbl(0, 8, "Presión etapa (bar):", self.var_mon_pres)

    def _build_grid(self, parent):
        holder = ttk.Frame(parent)
        holder.grid(row=3, column=0, sticky="nsew")
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        # Canvas con scrollbars
        self.canvas = tk.Canvas(holder, highlightthickness=0)
        vsb = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        hsb = ttk.Scrollbar(holder, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Frame interno dentro del canvas
        self.grid_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        label_padx = (6, 4)
        label_pady = (4, 2)
        cell_pad = dict(padx=3, pady=2)

        # Columna 0: etiquetas (categorías)
        for r, (text, kind) in enumerate(self.ROWS):
            lbl = ttk.Label(self.grid_frame, text=text, anchor="e", justify="right", font=C.FONT_BASE)
            lbl.grid(row=r, column=0, sticky="e", padx=label_padx, pady=label_pady)

        # Columnas 1..8: etapas
        for c in range(1, 9):
            # Cabecera fija con número de etapa
            head = ttk.Label(self.grid_frame, text=str(c), anchor="center", font=C.FONT_BASE)
            head.grid(row=0, column=c, sticky="nsew", **cell_pad)

            # Fila 1: Tiempo de etapa (entry entero, default 0)
            ent_t_etapa = self._make_entry_int(self.grid_frame, default="0")
            ent_t_etapa.grid(row=1, column=c, sticky="w", **cell_pad)

            # Fila 3: Posición inicial válvulas (A/B)
            cmb_pos = ttk.Combobox(self.grid_frame, values=("A", "B"), state="readonly", width=C.COMBO_WIDTH, font=C.FONT_BASE)
            cmb_pos.set("A")
            cmb_pos.grid(row=3, column=c, sticky="w", **cell_pad)

            # Fila 4 y 5: tiempos A y B
            ent_ta = self._make_entry_int(self.grid_frame, default="0")
            ent_ta.grid(row=4, column=c, sticky="w", **cell_pad)
            ent_tb = self._make_entry_int(self.grid_frame, default="0")
            ent_tb.grid(row=5, column=c, sticky="w", **cell_pad)

            # Fila 6: presión de proceso
            ent_pres = self._make_entry_dec(self.grid_frame, default="0.0", max_dec=1)
            ent_pres.grid(row=6, column=c, sticky="w", **cell_pad)

            # Fila 8 y 9: peristálticas ON/OFF
            cmb_p1 = ttk.Combobox(self.grid_frame, values=("OFF", "ON"), state="readonly", width=C.COMBO_WIDTH, font=C.FONT_BASE)
            cmb_p1.set("OFF")
            cmb_p1.grid(row=8, column=c, sticky="w", **cell_pad)

            cmb_p2 = ttk.Combobox(self.grid_frame, values=("OFF", "ON"), state="readonly", width=C.COMBO_WIDTH, font=C.FONT_BASE)
            cmb_p2.set("OFF")
            cmb_p2.grid(row=9, column=c, sticky="w", **cell_pad)

            # (espacio)

            # MFC1..4: gas + flujo con límites
            def make_gas_flow(row_gas, row_flow, mfc_id):
                gas_default = MFC_DEFAULTS[mfc_id][0]
                cmb = ttk.Combobox(self.grid_frame, values=GASES, state="readonly", width=C.COMBO_WIDTH, font=C.FONT_BASE)
                cmb.set(gas_default)
                cmb.grid(row=row_gas, column=c, sticky="w", **cell_pad)

                ent = self._make_entry_int(self.grid_frame, default="0")
                ent.grid(row=row_flow, column=c, sticky="w", **cell_pad)

                # al abrir teclado y al salir, normaliza con límite del gas actual
                self._attach_flow_logic(ent, mfc_id, cmb)

                return cmb, ent

            cmb_m1, ent_m1 = make_gas_flow(11, 12, 1)
            cmb_m2, ent_m2 = make_gas_flow(13, 14, 2)
            cmb_m3, ent_m3 = make_gas_flow(15, 16, 3)
            cmb_m4, ent_m4 = make_gas_flow(17, 18, 4)

            # Fila 20-21: SP hornos 1 y 2 (capado a 600)
            ent_t1 = self._make_entry_int(self.grid_frame, default="0", cap_max=MAX_SP)
            ent_t1.grid(row=20, column=c, sticky="w", **cell_pad)
            ent_t2 = self._make_entry_int(self.grid_frame, default="0", cap_max=MAX_SP)
            ent_t2.grid(row=21, column=c, sticky="w", **cell_pad)

            # Registro de referencias de la columna
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

    # ---------------------- helpers de celdas ----------------------
    def _make_entry_int(self, parent, *, default="0", cap_max=None):
        e = ttk.Entry(parent, width=C.ENTRY_WIDTH, font=C.FONT_BASE)
        e.insert(0, default)

        def _norm():
            txt = (e.get() or "").strip()
            try:
                v = int(float(txt))
            except Exception:
                v = 0
            if cap_max is not None:
                v = clamp(v, 0, cap_max)
            else:
                v = max(0, v)
            e.delete(0, tk.END)
            e.insert(0, str(v))

        # teclado y normalización
        e.bind("<Button-1>", lambda _ev: TecladoNumerico(self, e, on_submit=lambda v: (e.delete(0, tk.END), e.insert(0, str(v)), _norm())))
        e.bind("<FocusOut>", lambda _e: _norm())
        # validación en escritura
        vcmd = (self.register(self._validate_numeric), "%P", "%d", 1, 0)  # entero
        e.configure(validate="key", validatecommand=vcmd)
        return e

    def _make_entry_dec(self, parent, *, default="0.0", max_dec=1):
        e = ttk.Entry(parent, width=C.ENTRY_WIDTH, font=C.FONT_BASE)
        e.insert(0, default)

        def _norm():
            txt = (e.get() or "").strip()
            try:
                v = float(txt)
            except Exception:
                v = 0.0
            v = clamp(round(v, max_dec), 0.0, MAX_PRES)
            e.delete(0, tk.END)
            e.insert(0, f"{v:.{max_dec}f}")

        # teclado y normalización
        e.bind("<Button-1>", lambda _ev: TecladoNumerico(self, e, on_submit=lambda v: (e.delete(0, tk.END), e.insert(0, f"{float(v):.{max_dec}f}"), _norm())))
        e.bind("<FocusOut>", lambda _e: _norm())
        # validación en escritura
        vcmd = (self.register(self._validate_numeric), "%P", "%d", 0, max_dec)  # decimal con max_dec
        e.configure(validate="key", validatecommand=vcmd)
        return e

    def _attach_flow_logic(self, entry: ttk.Entry, mfc_id: int, cmb_gas: ttk.Combobox):
        """Asocia normalización de flujo según gas seleccionado en el MFC indicado."""
        def _norm_flow():
            gas = cmb_gas.get()
            if gas not in GASES:
                gas = MFC_DEFAULTS[mfc_id][0]
            lim = MFC_DEFAULTS[mfc_id][1][gas]
            txt = (entry.get() or "").strip()
            try:
                n = int(float(txt))
            except Exception:
                n = 0
            n = clamp(n, 0, lim)
            entry.delete(0, tk.END)
            entry.insert(0, str(n))

        entry.bind("<Button-1>", lambda _ev: TecladoNumerico(self, entry, on_submit=lambda v: (entry.delete(0, tk.END), entry.insert(0, str(v)), _norm_flow())))
        entry.bind("<FocusOut>", lambda _e: _norm_flow())
        cmb_gas.bind("<<ComboboxSelected>>", lambda _e: _norm_flow())

    @staticmethod
    def _validate_numeric(new_text: str, action: str, es_entero: int, max_dec: int):
        """Valida números mientras se escribe (permite vacío)."""
        if action == "0":  # borrado siempre ok
            return True
        s = (new_text or "").strip()
        if s == "":
            return True
        try:
            if es_entero:
                int(float(s))
            else:
                # limitar cantidad de decimales
                if s.count(".") > 1:
                    return False
                if "." in s:
                    dec = s.split(".", 1)[1]
                    if len(dec) > max_dec:
                        return False
                float(s)
            return True
        except Exception:
            return False

    # ---------------------- BYPASS desde CSV ----------------------
    def _leer_bypass(self) -> int:
        """Lee BYPASS (1 o 2) desde el CSV de valv_pos.csv si existe; por defecto 1."""
        try:
            fpath = os.path.join(os.path.dirname(__file__), "valv_pos.csv")
            if not os.path.exists(fpath):
                return 1
            with open(fpath, newline="", encoding="utf-8") as f:
                rd = csv.reader(f)
                for nombre, pos in rd:
                    if (nombre or "").strip().upper() == "BYP":
                        v = (pos or "").strip()
                        return 2 if v == "2" else 1
        except Exception:
            pass
        return 1

    # ===================== COMANDOS SUPERIORES =====================
    def _cmd_validar(self):
        """Valida las 8 columnas y marca las columnas activas."""
        activos = []
        for c in range(1, 9):
            try:
                if self._col_valida(c):
                    activos.append(c)
            except Exception:
                pass
        self._active_cols = activos
        if not activos:
            messagebox.showwarning("Validación", "No hay etapas válidas.")
        else:
            messagebox.showinfo("Validación", f"Etapas válidas: {', '.join(map(str, activos))}")

    def _cmd_iniciar(self):
        if not self._active_cols:
            self._cmd_validar()
            if not self._active_cols:
                return
        if self._run_active:
            return
        self._run_active = True
        self._paused = False
        self.btn_pausar.configure(state="normal")
        self.btn_reanudar.configure(state="disabled")
        self._col_ptr = 0
        self._iniciar_etapa(self._active_cols[self._col_ptr])
        self._tick()

    def _cmd_pausar(self):
        if not self._run_active or self._paused:
            return
        self._paused = True
        self.btn_pausar.configure(state="disabled")
        self.btn_reanudar.configure(state="normal")

    def _cmd_reanudar(self):
        if not self._run_active or not self._paused:
            return
        self._paused = False
        self.btn_pausar.configure(state="normal")
        self.btn_reanudar.configure(state="disabled")

    def _cmd_detener(self):
        if not self._run_active:
            return
        self._run_active = False
        self._paused = False
        self.btn_pausar.configure(state="disabled")
        self.btn_reanudar.configure(state="disabled")
        self._stage_remaining = 0
        self._seg_remaining = 0
        self._seg_pos = "A"
        self._col_ptr = -1
        self._active_cols = []
        if self._tick_id:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
        self._tick_id = None
        messagebox.showinfo("Auto", "Proceso detenido.")

    def _cmd_guardar_preset(self):
        path = filedialog.asksaveasfilename(
            title="Guardar preset",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["col", "t_etapa", "pos_ini", "t_a", "t_b", "pres",
                            "p1", "p2",
                            "m1_gas", "m1_f", "m2_gas", "m2_f", "m3_gas", "m3_f", "m4_gas", "m4_f",
                            "t1_sp", "t2_sp"])
                for c in range(1, 9):
                    row = self._collect_column(c)
                    if row is None:
                        continue
                    w.writerow([
                        c,
                        row.get("t_etapa", "0"),
                        row.get("pos_ini", "A"),
                        row.get("t_a", "0"),
                        row.get("t_b", "0"),
                        row.get("pres", "0.0"),
                        row.get("p1", "OFF"),
                        row.get("p2", "OFF"),
                        row.get("m1_gas", "O2"), row.get("m1_f", "0"),
                        row.get("m2_gas", "CO2"), row.get("m2_f", "0"),
                        row.get("m3_gas", "N2"), row.get("m3_f", "0"),
                        row.get("m4_gas", "H2"), row.get("m4_f", "0"),
                        row.get("t1_sp", "0"), row.get("t2_sp", "0"),
                    ])
            messagebox.showinfo("Preset", "Preset guardado correctamente.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}")

    def _cmd_cargar_preset(self):
        path = filedialog.askopenfilename(
            title="Cargar preset",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            with open(path, newline="", encoding="utf-8") as f:
                rd = csv.DictReader(f)
                for row in rd:
                    try:
                        c = int(row.get("col", "0"))
                    except Exception:
                        continue
                    if not (1 <= c <= 8):
                        continue
                    self._apply_row(c, row)
            messagebox.showinfo("Preset", "Preset cargado.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar:\n{e}")

    # ===================== LÓGICA PRINCIPAL AUTO =====================
    def _tick(self):
        """Reloj de 1s para actualizar tiempos cuando el proceso está activo."""
        if not self._run_active:
            return
        if self._paused:
            self._tick_id = self.after(1000, self._tick)
            return

        # Decremento de contadores
        if self._seg_remaining > 0:
            self._seg_remaining -= 1
        self._stage_remaining = max(0, self._stage_remaining - 1)

        # Cambio de posición de válvula si corresponde
        if self._seg_remaining <= 0 and self._stage_remaining > 0:
            self._flip_valve_pos()

        # Fin de etapa
        if self._stage_remaining <= 0:
            # Siguiente etapa
            self._col_ptr += 1
            if self._col_ptr >= len(self._active_cols):
                self._cmd_detener()
                return
            self._iniciar_etapa(self._active_cols[self._col_ptr])

        # Actualización visual del monitor
        self._refresh_monitor()

        # Reprogramar
        self._tick_id = self.after(1000, self._tick)

    def _flip_valve_pos(self):
        """Alterna posición A/B y reinicia temporizador de segmento."""
        self._seg_pos = "B" if self._seg_pos == "A" else "A"
        tA = self._seg_tA
        tB = self._seg_tB
        self._seg_remaining = 60 * (tA if self._seg_pos == "A" else tB)

    def _iniciar_etapa(self, c: int):
        """Carga setpoints/estados de la columna y envía comandos iniciales."""
        row = self._collect_column(c)
        if row is None:
            return

        # Tiempo de etapa y temporizadores de segmento
        try:
            tmin = int(float(row.get("t_etapa", "0")))
        except Exception:
            tmin = 0
        self._stage_remaining = 60 * max(0, tmin)

        self._seg_tA = max(0, int(float(row.get("t_a", "0"))))
        self._seg_tB = max(0, int(float(row.get("t_b", "0"))))
        self._seg_pos = row.get("pos_ini", "A")
        self._seg_remaining = 60 * (self._seg_tA if self._seg_pos == "A" else self._seg_tB)

        # Envío de presión (capada a 20.0)
        try:
            p = float(row.get("pres", "0.0"))
        except Exception:
            p = 0.0
        p = clamp(round(p, 1), 0.0, MAX_PRES)
        # CMD válvula solenoide (id 5): set presión
        p10 = int(round(p * 10))
        self._tx(f"$;3;5;0;{p10};!")

        # Peristálticas
        p1 = row.get("p1", "OFF").upper().strip() == "ON"
        p2 = row.get("p2", "OFF").upper().strip() == "ON"
        self._tx(f"$;3;6;1;{'1' if p1 else '2'};!")
        self._tx(f"$;3;7;1;{'1' if p2 else '2'};!")

        # MFC: gases y flujos a PWM
        for mfc_id in (1, 2, 3, 4):
            gas = row.get(f"m{mfc_id}_gas", MFC_DEFAULTS[mfc_id][0])
            if gas not in GASES:
                gas = MFC_DEFAULTS[mfc_id][0]
            lim = MFC_DEFAULTS[mfc_id][1][gas]
            try:
                f = float(row.get(f"m{mfc_id}_f", "0"))
            except Exception:
                f = 0.0
            f = clamp(f, 0.0, float(lim))
            pwm = flujo_a_pwm(f, lim)
            self._tx(f"$;1;{mfc_id};1;{pwm};!")

        # Hornos SP
        for horno_id in (1, 2):
            k = f"t{horno_id}_sp"
            try:
                sp = int(float(row.get(k, "0")))
            except Exception:
                sp = 0
            sp = clamp(sp, 0, MAX_SP)
            self._tx(f"$;2;{horno_id};2;1;{sp};!")

        self._refresh_monitor()

    def _refresh_monitor(self):
        """Pinta monitor con etapa actual, posición de válvulas y tiempos restantes."""
        if self._col_ptr < 0 or self._col_ptr >= len(self._active_cols):
            self.var_mon_etapa.set("-")
            self.var_mon_pos.set("-")
            self.var_mon_rest_etapa.set("-")
            self.var_mon_rest_seg.set("-")
            self.var_mon_pres.set("-")
            return
        c = self._active_cols[self._col_ptr]
        self.var_mon_etapa.set(str(c))
        self.var_mon_pos.set(self._seg_pos)
        self.var_mon_rest_etapa.set(mmss(self._stage_remaining))
        self.var_mon_rest_seg.set(mmss(self._seg_remaining))
        # Mostrar presión configurada de la columna actual
        row = self._collect_column(c)
        try:
            p = float(row.get("pres", "0.0")) if row else 0.0
        except Exception:
            p = 0.0
        self.var_mon_pres.set(f"{clamp(round(p, 1), 0.0, MAX_PRES):.1f}")

    # ================== VALIDACIÓN / PRESETS / HELPERS ==================
    def _collect_column(self, c: int):
        """Agrupa valores de la columna c en un dict con claves canónicas."""
        col = self.cells.get(c)
        if not col:
            return None

        def get_e(name, default=""):
            w = col.get(name)
            if w is None:
                return default
            if isinstance(w, ttk.Combobox):
                return (w.get() or "").strip()
            if isinstance(w, ttk.Entry):
                return (w.get() or "").strip()
            return default

        return {
            "t_etapa": get_e("t_etapa", "0"),
            "pos_ini": get_e("pos_ini", "A"),
            "t_a": get_e("t_a", "0"),
            "t_b": get_e("t_b", "0"),
            "pres": get_e("pres", "0.0"),
            "p1": get_e("p1", "OFF"),
            "p2": get_e("p2", "OFF"),
            "m1_gas": get_e("m1_gas", MFC_DEFAULTS[1][0]),
            "m1_f": get_e("m1_f", "0"),
            "m2_gas": get_e("m2_gas", MFC_DEFAULTS[2][0]),
            "m2_f": get_e("m2_f", "0"),
            "m3_gas": get_e("m3_gas", MFC_DEFAULTS[3][0]),
            "m3_f": get_e("m3_f", "0"),
            "m4_gas": get_e("m4_gas", MFC_DEFAULTS[4][0]),
            "m4_f": get_e("m4_f", "0"),
            "t1_sp": get_e("t1", "0"),
            "t2_sp": get_e("t2", "0"),
        }

    def _apply_row(self, c: int, row: dict):
        """Carga en UI la fila de preset para la columna c."""
        def set_e(e: ttk.Entry, val: str):
            try:
                e.delete(0, tk.END)
                e.insert(0, str(val))
            except Exception:
                pass

        def set_cmb(cm: ttk.Combobox, val: str):
            try:
                cm.set(val)
            except Exception:
                pass

        set_e(self.cells[c]["t_etapa"], row.get("t_etapa", "0"))
        set_cmb(self.cells[c]["pos_ini"], row.get("pos_ini", "A"))
        set_e(self.cells[c]["t_a"], row.get("t_a", "0"))
        set_e(self.cells[c]["t_b"], row.get("t_b", "0"))
        set_e(self.cells[c]["pres"], row.get("pres", "0.0"))
        set_cmb(self.cells[c]["p1"], row.get("p1", "OFF"))
        set_cmb(self.cells[c]["p2"], row.get("p2", "OFF"))
        set_cmb(self.cells[c]["m1_gas"], row.get("m1_gas", MFC_DEFAULTS[1][0]))
        set_e(self.cells[c]["m1_f"], row.get("m1_f", "0"))
        set_cmb(self.cells[c]["m2_gas"], row.get("m2_gas", MFC_DEFAULTS[2][0]))
        set_e(self.cells[c]["m2_f"], row.get("m2_f", "0"))
        set_cmb(self.cells[c]["m3_gas"], row.get("m3_gas", MFC_DEFAULTS[3][0]))
        set_e(self.cells[c]["m3_f"], row.get("m3_f", "0"))
        set_cmb(self.cells[c]["m4_gas"], row.get("m4_gas", MFC_DEFAULTS[4][0]))
        set_e(self.cells[c]["m4_f"], row.get("m4_f", "0"))
        set_e(self.cells[c]["t1"], row.get("t1_sp", "0"))
        set_e(self.cells[c]["t2"], row.get("t2_sp", "0"))

    def _apply_flow_clamp(self, c: int, mfc_id: int):
        gas = self.cells[c][f"m{mfc_id}_gas"].get()
        if gas not in GASES:
            gas = MFC_DEFAULTS[mfc_id][0]
        lim = MFC_DEFAULTS[mfc_id][1][gas]
        ent = self.cells[c][f"m{mfc_id}_f"]
        try:
            v = int(float((ent.get() or "0").strip()))
        except Exception:
            v = 0
        v = clamp(v, 0, lim)
        ent.delete(0, tk.END)
        ent.insert(0, str(v))

    # ===================== VALIDACIÓN DE ETAPA =====================
    def _col_valida(self, c: int) -> bool:
        """Valida una etapa: tiempos no negativos, presiones en rango, flujos dentro de límites."""
        col = self._collect_column(c)
        if col is None:
            return False

        # tiempo de etapa (>0 para considerarse válida)
        try:
            t = int(float(col.get("t_etapa", "0")))
        except Exception:
            t = 0
        if t <= 0:
            return False

        # tiempos A/B
        try:
            tA = int(float(col.get("t_a", "0")))
        except Exception:
            tA = 0
        try:
            tB = int(float(col.get("t_b", "0")))
        except Exception:
            tB = 0
        if tA < 0 or tB < 0:
            return False

        # presión
        try:
            p = float(col.get("pres", "0.0"))
        except Exception:
            p = 0.0
        if not (0.0 <= p <= MAX_PRES):
            return False

        # peristálticas
        if col.get("p1", "OFF") not in ("OFF", "ON"):
            return False
        if col.get("p2", "OFF") not in ("OFF", "ON"):
            return False

        # mfc flows
        for m in (1, 2, 3, 4):
            gas = col.get(f"m{m}_gas", MFC_DEFAULTS[m][0])
            if gas not in GASES:
                return False
            try:
                f = int(float(col.get(f"m{m}_f", "0")))
            except Exception:
                f = 0
            lim = MFC_DEFAULTS[m][1][gas]
            if f < 0 or f > lim:
                return False

        # SP hornos
        for k in ("t1_sp", "t2_sp"):
            try:
                sp = int(float(col.get(k, "0")))
            except Exception:
                sp = 0
            if not (0 <= sp <= MAX_SP):
                return False

        return True

    # ===================== ENVÍO A ARDUINO =====================
    def _tx(self, msg: str):
        print("[TX Auto]", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            try:
                self.controlador.enviar_a_arduino(msg)
            except Exception:
                pass

    # ===================== SCROLL TÁCTIL =====================
    def _enable_touch_scroll(self):
        """Habilita desplazamiento táctil (drag) además de las barras de scroll."""
        sf = {"x": 0, "y": 0}

        def _start(e):
            sf["x"], sf["y"] = e.x, e.y
            self.canvas.scan_mark(e.x, e.y)

        def _drag(e):
            self.canvas.scan_dragto(e.x, e.y, gain=1)

        self.canvas.bind("<ButtonPress-1>", _start)
        self.canvas.bind("<B1-Motion>", _drag)
