# gui/ventana_auto.py
import csv
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico


# ========================== Utilidades comunes ==========================

def clamp(v, a, b):
    """Recorta v al rango [a, b]."""
    return a if v < a else (b if v > b else v)


def mmss(seg):
    """Convierte segundos a 'MM:SS'."""
    seg = max(0, int(seg))
    m, s = divmod(seg, 60)
    return f"{m:02d}:{s:02d}"


# =================== Tabla de máximos por gas y MFC =====================

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

MAX_SP = 600         # setpoint hornos
MAX_PRES = 20.0      # presión máxima (bar, 1 decimal)


def flujo_a_pwm(flujo_ml_min: float, maximo: int) -> int:
    """
    Convierte flujo (mL/min) -> PWM [0..255] usando mapeo lineal 0..max -> 0..255.
    - flujo fuera de rango se recorta.
    - Resultado se redondea al entero más cercano y se recorta a [0,255].
    """
    maximo = max(1, int(maximo))  # evitar división por cero
    f = clamp(float(flujo_ml_min), 0.0, float(maximo))
    pwm = round((f / float(maximo)) * 255.0)
    return int(clamp(pwm, 0, 255))


# =========================== Ventana Auto (grid) ===========================

class VentanaAuto(tk.Frame):
    """
    Nueva ventana Auto con:
      - Barra de navegación (izquierda)
      - Fila 0: Botonera (Validar, Iniciar, Pausar, Reanudar, Detener, Guardar/Cargar preset)
      - Fila 2: Monitor (Etapa actual, Posición, Tiempo restante etapa, Tiempo para cambio de válvula, Presión configurada)
      - Debajo: Frame scrolleable (horizontal/vertical) con tabla tipo Excel:
          Columna 1 = categorías (etiquetas)
          Columnas 2..9 = Etapas 1..8 (editables)
    Ejecución:
      - Se consideran “activas” las columnas cuyo “Tiempo de etapa” > 0.
      - Al iniciar una etapa envía:
        $;4;POS_INI;PS*10;P1_ON;P2_ON;BYPASS;MFC1_PWM;MFC2_PWM;MFC3_PWM;MFC4_PWM;T1_SP;T2_SP;!
      - Alterna A↔B según “Tiempo en A/B (min)”, y en cada cambio de posición envía:
        $;3;1;0;{1|2};!   (1=A, 2=B)
    """

    # ------------- filas (categorías) del grid -------------
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

        # ----------- estado de ejecución -----------
        self._run_active = False
        self._paused = False
        self._tick_id = None

        # punteros y contadores
        self._active_cols = []        # columnas (1..8) activas por tiempo de etapa > 0
        self._col_ptr = -1            # índice dentro de _active_cols
        self._stage_remaining = 0     # seg restantes de la etapa actual
        self._seg_remaining = 0       # seg restantes del segmento (A o B)
        self._seg_pos = "A"
        self._seg_tA = 0              # seg duración A
        self._seg_tB = 0              # seg duración B

        # bypass persistido (BYP en valv_pos.csv)
        self._bypass = self._leer_bypass()

        # refs de celdas: dict[col][rowkey] -> widget
        self.cells = {c: {} for c in range(1, 9)}

        self._build_ui()

    # ============================ UI base ============================

    def _build_ui(self):
        # columnas: 0 barra, 1 contenido
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación (sin márgenes para aprovechar 1024x600)
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=120)
        barra.grid(row=0, column=0, sticky="ns")
        barra.grid_propagate(False)

        # Contenedor principal
        main = ttk.Frame(self)
        main.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        main.grid_rowconfigure(3, weight=1)  # fila del canvas scrolleable
        main.grid_columnconfigure(0, weight=1)

        # --------- fila 0: botonera ---------
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
        wrap.grid_columnconfigure(7, weight=1)  # separador elástico

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
        # Canvas con scroll H+V
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

        # ajustar región scrolleable al modificar el tamaño interior
        self.grid_frame.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # fuente/anchos para táctil 1024x600 (sin exagerar)
        label_padx = (6, 4)
        label_pady = (4, 2)
        cell_pad = dict(padx=3, pady=2)

        # Columna 0: etiquetas (categorías)
        for r, (text, kind) in enumerate(self.ROWS):
            lbl = ttk.Label(self.grid_frame, text=text, anchor="e", justify="right")
            lbl.grid(row=r, column=0, sticky="e", padx=label_padx, pady=label_pady)

        # Columnas 1..8: etapas
        for c in range(1, 9):
            # Cabecera fija con número de etapa
            head = ttk.Label(self.grid_frame, text=str(c), anchor="center")
            head.grid(row=0, column=c, sticky="nsew", **cell_pad)

            # Fila 1: Tiempo de etapa (entry entero, default 0)
            ent_t_etapa = self._make_entry_int(self.grid_frame, default="0")
            ent_t_etapa.grid(row=1, column=c, sticky="w", **cell_pad)

            # Fila 2: (espacio) -> nada

            # Válvulas
            cmb_pos = ttk.Combobox(self.grid_frame, values=("A", "B"), state="readonly", width=5)
            cmb_pos.set("A")
            cmb_pos.grid(row=3, column=c, sticky="w", **cell_pad)

            ent_ta = self._make_entry_int(self.grid_frame, default="0")
            ent_ta.grid(row=4, column=c, sticky="w", **cell_pad)

            ent_tb = self._make_entry_int(self.grid_frame, default="0")
            ent_tb.grid(row=5, column=c, sticky="w", **cell_pad)

            ent_pres = self._make_entry_dec(self.grid_frame, default="0.0", max_dec=1)
            ent_pres.grid(row=6, column=c, sticky="w", **cell_pad)

            # (espacio)

            cmb_p1 = ttk.Combobox(self.grid_frame, values=("OFF", "ON"), state="readonly", width=6)
            cmb_p1.set("OFF")
            cmb_p1.grid(row=8, column=c, sticky="w", **cell_pad)

            cmb_p2 = ttk.Combobox(self.grid_frame, values=("OFF", "ON"), state="readonly", width=6)
            cmb_p2.set("OFF")
            cmb_p2.grid(row=9, column=c, sticky="w", **cell_pad)

            # (espacio)

            # MFC1..4: gas + flujo con límites
            def make_gas_flow(row_gas, row_flow, mfc_id):
                gas_default = MFC_DEFAULTS[mfc_id][0]
                cmb = ttk.Combobox(self.grid_frame, values=GASES, state="readonly", width=8)
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

            # (espacio)

            ent_t1 = self._make_entry_int(self.grid_frame, default="0", cap_max=MAX_SP)
            ent_t1.grid(row=20, column=c, sticky="w", **cell_pad)

            ent_t2 = self._make_entry_int(self.grid_frame, default="0", cap_max=MAX_SP)
            ent_t2.grid(row=21, column=c, sticky="w", **cell_pad)

            # Guardar referencias por columna
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
        e = ttk.Entry(parent, width=8)
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
        e = ttk.Entry(parent, width=8)
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

        e.bind("<Button-1>", lambda _ev: TecladoNumerico(self, e, on_submit=lambda v: (e.delete(0, tk.END), e.insert(0, str(v)), _norm())))
        e.bind("<FocusOut>", lambda _e: _norm())
        vcmd = (self.register(self._validate_numeric), "%P", "%d", 0, max_dec)  # decimal
        e.configure(validate="key", validatecommand=vcmd)
        return e

    def _attach_flow_logic(self, entry: ttk.Entry, mfc_id: int, cmb_gas: ttk.Combobox):
        """Capar flujo por gas (enviar con teclado o al perder foco)."""
        def _norm_flow():
            gas = cmb_gas.get() if cmb_gas.get() in GASES else MFC_DEFAULTS[mfc_id][0]
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
        txt = (new_text or "").strip()
        if not txt:
            return True
        try:
            if es_entero:
                int(float(txt))
            else:
                float(txt)
                if "." in txt:
                    dec = txt.split(".", 1)[1]
                    if len(dec) > int(max_dec):
                        return False
        except Exception:
            return False
        return True

    # ====================== Bypass persistido ======================

    def _leer_bypass(self) -> int:
        """Lee BYP de valv_pos.csv (1/2). Default 1 si no existe."""
        pos_file = os.path.join(os.path.dirname(__file__), "valv_pos.csv")
        try:
            if os.path.exists(pos_file):
                with open(pos_file, newline="", encoding="utf-8") as f:
                    for nombre, pos in csv.reader(f):
                        if (nombre or "").strip().upper() == "BYP":
                            v = (pos or "").strip()
                            return 2 if v == "2" else 1
        except Exception:
            pass
        return 1

    # ====================== Acciones de botones ======================

    def _cmd_validar(self):
        incompletas = []
        for c in range(1, 9):
            if not self._col_is_complete(c):
                incompletas.append(str(c))
        if incompletas and len(incompletas) < 8:
            messagebox.showwarning(
                "Validación",
                "Las siguientes etapas no están completas (se ignorarán al iniciar): "
                + ", ".join(incompletas)
            )
        elif len(incompletas) == 8:
            messagebox.showerror("Validación", "No hay ninguna etapa completa.")
        else:
            messagebox.showinfo("Validación", "Todas las etapas están completas.")

    def _cmd_iniciar(self):
        if self._run_active:
            messagebox.showinfo("Auto", "El proceso ya está en ejecución.")
            return

        self._active_cols = [c for c in range(1, 9) if self._col_is_complete(c)]
        if not self._active_cols:
            messagebox.showerror("Auto", "No hay etapas completas para ejecutar.")
            return

        self._run_active = True
        self._paused = False
        self.btn_pausar.configure(state="normal")
        self.btn_reanudar.configure(state="disabled")

        self._col_ptr = -1
        self._iniciar_siguiente_etapa()

    def _cmd_pausar(self):
        if not self._run_active or self._paused:
            return
        self._paused = True
        if self._tick_id:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None
        self.btn_pausar.configure(state="disabled")
        self.btn_reanudar.configure(state="normal")

    def _cmd_reanudar(self):
        if not self._run_active or not self._paused:
            return
        self._paused = False
        self.btn_pausar.configure(state="normal")
        self.btn_reanudar.configure(state="disabled")
        self._tick()

    def _cmd_detener(self):
        self._stop_all("Proceso detenido por el usuario.")

    def _stop_all(self, msg: str = ""):
        self._run_active = False
        self._paused = False
        if self._tick_id:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None
        self.btn_pausar.configure(state="disabled")
        self.btn_reanudar.configure(state="disabled")
        self._reset_monitor()
        if msg:
            print("[AUTO]", msg)

    # ====================== Lógica de ejecución ======================

    def _col_is_complete(self, c: int) -> bool:
        """Criterio mínimo: Tiempo de etapa > 0, y tiempos A y B > 0."""
        t_etapa = self._get_int(self.cells[c]["t_etapa"])
        t_a = self._get_int(self.cells[c]["t_a"])
        t_b = self._get_int(self.cells[c]["t_b"])
        return t_etapa > 0 and t_a > 0 and t_b > 0

    def _iniciar_siguiente_etapa(self):
        self._col_ptr += 1
        if self._col_ptr >= len(self._active_cols):
            self._stop_all("Todas las etapas completas finalizaron.")
            return

        c = self._active_cols[self._col_ptr]

        # leer y normalizar datos de la columna c
        datos = self._collect_col_payload(c)

        # configurar contadores
        self._stage_remaining = datos["t_etapa"] * 60
        self._seg_tA = datos["t_a"] * 60
        self._seg_tB = datos["t_b"] * 60
        self._seg_pos = "A" if datos["pos_ini"] == 1 else "B"
        self._seg_remaining = self._seg_tA if self._seg_pos == "A" else self._seg_tB

        # monitor inicial
        self.var_mon_etapa.set(f"{self._col_ptr + 1}/{len(self._active_cols)}")
        self.var_mon_pos.set(self._seg_pos)
        self.var_mon_rest_etapa.set(mmss(self._stage_remaining))
        self.var_mon_rest_seg.set(mmss(self._seg_remaining))
        self.var_mon_pres.set(f"{datos['pres_bar']:.1f}")

        # enviar mensaje $;4;...;! con bypass incluido
        self._tx_etapa(datos)

        # arrancar loop 1 Hz
        if not self._paused:
            self._tick()

    def _tick(self):
        if not self._run_active or self._paused:
            return

        if self._stage_remaining <= 0:
            self._iniciar_siguiente_etapa()
            return

        if self._seg_remaining <= 0:
            # alternar A/B y enviar comando de cambio
            self._seg_pos = "B" if self._seg_pos == "A" else "A"
            self._send_valve_position(self._seg_pos)
            self._seg_remaining = self._seg_tB if self._seg_pos == "B" else self._seg_tA

        # decrementar contadores
        self._stage_remaining -= 1
        self._seg_remaining -= 1

        # actualizar monitor
        self.var_mon_rest_etapa.set(mmss(self._stage_remaining))
        self.var_mon_rest_seg.set(mmss(self._seg_remaining))
        self.var_mon_pos.set(self._seg_pos)

        self._tick_id = self.after(1000, self._tick)

    # ----------------------- TX helpers -----------------------

    def _tx(self, mensaje: str):
        print("[TX]", mensaje)
        if self.controlador and hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    def _tx_etapa(self, d: dict):
        """
        $;4;POS_INI;PS*10;P1_ON;P2_ON;BYPASS;M1_PWM;M2_PWM;M3_PWM;M4_PWM;T1_SP;T2_SP;!
        """
        partes = [
            "$;4",
            str(d["pos_ini"]), str(d["ps10"]),
            str(d["p1_on"]), str(d["p2_on"]),
            str(d["bypass"]),
            str(d["m1_pwm"]), str(d["m2_pwm"]), str(d["m3_pwm"]), str(d["m4_pwm"]),
            str(d["t1_sp"]), str(d["t2_sp"]),
        ]
        self._tx(";".join(partes) + ";!")

    def _send_valve_position(self, pos: str):
        """Cambio de posición automático durante la etapa."""
        code = "1" if pos.upper() == "A" else "2"
        self._tx(f"$;3;1;0;{code};!")

    # ======================== Helpers lectura ========================

    def _get_int(self, entry: ttk.Entry) -> int:
        txt = (entry.get() or "").strip()
        if not txt:
            return 0
        try:
            return int(float(txt))
        except Exception:
            return 0

    def _get_float(self, entry: ttk.Entry) -> float:
        txt = (entry.get() or "").strip()
        if not txt:
            return 0.0
        try:
            return float(txt)
        except Exception:
            return 0.0

    def _collect_col_payload(self, c: int) -> dict:
        """
        Extrae y normaliza todos los datos de la columna c (1..8) y
        calcula PWM de MFC según límites del gas seleccionado.
        """
        # tiempos
        t_etapa = max(0, self._get_int(self.cells[c]["t_etapa"]))
        t_a = max(0, self._get_int(self.cells[c]["t_a"]))
        t_b = max(0, self._get_int(self.cells[c]["t_b"]))

        # válvulas
        pos_ini = 1 if (self.cells[c]["pos_ini"].get() or "A").upper() == "A" else 2

        # presión
        pres_bar = clamp(round(self._get_float(self.cells[c]["pres"]), 1), 0.0, MAX_PRES)
        ps10 = int(round(pres_bar * 10))

        # peristálticas
        p1_on = 1 if (self.cells[c]["p1"].get() == "ON") else 2
        p2_on = 1 if (self.cells[c]["p2"].get() == "ON") else 2

        # bypass persistido (1/2)
        bypass = self._bypass

        # MFCs -> PWM
        def mfc_pwm(mid_key_g, mid_key_f, mfc_id):
            gas = self.cells[c][mid_key_g].get()
            if gas not in GASES:
                gas = MFC_DEFAULTS[mfc_id][0]
            lim = MFC_DEFAULTS[mfc_id][1][gas]
            flujo = clamp(self._get_int(self.cells[c][mid_key_f]), 0, lim)
            return flujo_a_pwm(flujo, lim)

        m1_pwm = mfc_pwm("m1_gas", "m1_f", 1)
        m2_pwm = mfc_pwm("m2_gas", "m2_f", 2)
        m3_pwm = mfc_pwm("m3_gas", "m3_f", 3)
        m4_pwm = mfc_pwm("m4_gas", "m4_f", 4)

        # Temperaturas
        t1_sp = clamp(self._get_int(self.cells[c]["t1"]), 0, MAX_SP)
        t2_sp = clamp(self._get_int(self.cells[c]["t2"]), 0, MAX_SP)

        return {
            "col": c,
            "t_etapa": t_etapa,
            "t_a": t_a,
            "t_b": t_b,
            "pos_ini": pos_ini,
            "pres_bar": pres_bar,
            "ps10": ps10,
            "p1_on": p1_on,
            "p2_on": p2_on,
            "bypass": bypass,
            "m1_pwm": m1_pwm,
            "m2_pwm": m2_pwm,
            "m3_pwm": m3_pwm,
            "m4_pwm": m4_pwm,
            "t1_sp": t1_sp,
            "t2_sp": t2_sp,
        }

    def _reset_monitor(self):
        self.var_mon_etapa.set("-")
        self.var_mon_pos.set("-")
        self.var_mon_rest_etapa.set("-")
        self.var_mon_rest_seg.set("-")
        self.var_mon_pres.set("-")

    # ======================== Presets CSV ========================

    def _cmd_guardar_preset(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            title="Guardar preset"
        )
        if not path:
            return

        # cabecera
        headers = ["col",
                   "t_etapa", "pos_ini", "t_a", "t_b", "ps10",
                   "p1_on", "p2_on",
                   "m1_gas", "m1_f", "m2_gas", "m2_f", "m3_gas", "m3_f", "m4_gas", "m4_f",
                   "t1_sp", "t2_sp"]

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(headers)
                for c in range(1, 9):
                    row = self._row_from_col(c)
                    w.writerow(row)
            messagebox.showinfo("Preset", "Preset guardado correctamente.")
        except Exception as ex:
            messagebox.showerror("Preset", f"No se pudo guardar el preset:\n{ex}")

    def _row_from_col(self, c: int):
        # helpers para string
        def ent_str(e: ttk.Entry, default="0"):
            v = (e.get() or "").strip()
            return v if v else default

        pos_ini = "1" if self.cells[c]["pos_ini"].get() == "A" else "2"

        # presión *10
        try:
            p = float((self.cells[c]["pres"].get() or "0").strip())
        except Exception:
            p = 0.0
        p = clamp(round(p, 1), 0.0, MAX_PRES)
        ps10 = str(int(round(p * 10)))

        return [
            str(c),
            ent_str(self.cells[c]["t_etapa"], "0"),
            pos_ini,
            ent_str(self.cells[c]["t_a"], "0"),
            ent_str(self.cells[c]["t_b"], "0"),
            ps10,
            "1" if self.cells[c]["p1"].get() == "ON" else "2",
            "1" if self.cells[c]["p2"].get() == "ON" else "2",
            self.cells[c]["m1_gas"].get(), ent_str(self.cells[c]["m1_f"], "0"),
            self.cells[c]["m2_gas"].get(), ent_str(self.cells[c]["m2_f"], "0"),
            self.cells[c]["m3_gas"].get(), ent_str(self.cells[c]["m3_f"], "0"),
            self.cells[c]["m4_gas"].get(), ent_str(self.cells[c]["m4_f"], "0"),
            ent_str(self.cells[c]["t1"], "0"),
            ent_str(self.cells[c]["t2"], "0"),
        ]

    def _cmd_cargar_preset(self):
        path = filedialog.askopenfilename(
            filetypes=[("CSV", "*.csv")],
            title="Cargar preset"
        )
        if not path:
            return

        try:
            with open(path, newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                for row in r:
                    try:
                        col = int(row.get("col", "0"))
                    except Exception:
                        continue
                    if 1 <= col <= 8:
                        self._apply_csv_row_to_col(col, row)
            messagebox.showinfo("Preset", "Preset cargado.")
        except Exception as ex:
            messagebox.showerror("Preset", f"No se pudo cargar el preset:\n{ex}")

    def _apply_csv_row_to_col(self, c: int, row: dict):
        def set_e(e: ttk.Entry, val: str):
            e.delete(0, tk.END)
            e.insert(0, val or "")

        # tiempos y posición
        set_e(self.cells[c]["t_etapa"], row.get("t_etapa", "0"))
        self.cells[c]["pos_ini"].set("A" if row.get("pos_ini", "1") == "1" else "B")
        set_e(self.cells[c]["t_a"], row.get("t_a", "0"))
        set_e(self.cells[c]["t_b"], row.get("t_b", "0"))

        # presión ps10 -> bar
        try:
            ps10 = int(row.get("ps10", "0"))
            p = clamp(ps10 / 10.0, 0.0, MAX_PRES)
            set_e(self.cells[c]["pres"], f"{p:.1f}")
        except Exception:
            set_e(self.cells[c]["pres"], "0.0")

        # peristálticas
        self.cells[c]["p1"].set("ON" if row.get("p1_on", "2") == "1" else "OFF")
        self.cells[c]["p2"].set("ON" if row.get("p2_on", "2") == "1" else "OFF")

        # MFCs
        for mid in (1, 2, 3, 4):
            gkey = f"m{mid}_gas"
            fkey = f"m{mid}_f"
            gas = row.get(gkey, MFC_DEFAULTS[mid][0])
            if gas not in GASES:
                gas = MFC_DEFAULTS[mid][0]
            self.cells[c][f"m{mid}_gas"].set(gas)
            set_e(self.cells[c][f"m{mid}_f"], row.get(fkey, "0"))
            # aplicar clamp por gas actual
            self._apply_flow_clamp(c, mid)

        # SPs
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
