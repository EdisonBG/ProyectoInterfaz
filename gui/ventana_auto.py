# gui/ventana_auto.py
import csv
import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog

from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico
from ui.widgets import TouchButton, TouchEntry, LabeledEntryNum

# Constantes táctiles (anchos/fuentes). Si no existen, usa valores por defecto.


class _C_:
    FONT_BASE = ("Calibri", 13)
    ENTRY_WIDTH = 12
    COMBO_WIDTH = 12


C = _C_()

# --- Título movible por píxeles y con fuente configurable (solo en modo absoluto) ---
# Posición del "título" dibujado manualmente dentro de cada sección (x, y).
TITLE_POS = {
    1: (8, 2),
}
# Fuente (familia, tamaño, estilo) por sección para el título.
TITLE_FONT = {
    1: ("Calibri", 13, "bold"),
}

# Coordenadas por MFC (horizontal, vertical) para cada control dentro de su LabelFrame.
# Nota: "entry" posiciona el contenedor LabeledEntryNum completo (label+entry).
POS = {
    1: {
        "btn_validar":   (0, 0),
        "btn_iniciar": (103,  0),
        "btn_pausar":   (206,  0),
        "btn_reanudar":     (309, 0),
        "btn_detener":  (433,  0),
        "btn_guardar_pre":  (546,  0),
        "btn_cargar_pre": (710, 0),
    },
}

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
        $;4;POS_INI;PS*10;P1_ON;BYPASS(1-OFF-Normal/2-ON-Secundaria);MFC1_PWM;MFC2_PWM;MFC3_PWM;MFC4_PWM;T1_SP;T2_SP;!
      - Alterna A↔B según “Tiempo en A/B (min)”, y en cada cambio de posición envía:
        $;3;1;0;{1|2};!   (1=A, 2=B)
    """

    # ------------- filas (categorías) del grid -------------
    ROWS = [
        ("StNu", "label"),
        ("TiSt (min)", "int"),
        ("", "spacer"),
        ("VaPo", "combo_pos"),
        ("TiPo-A (min)", "int"),
        ("TiPo-B (min)", "int"),
        ("WoPr (bar)", "decimal1"),
        ("", "spacer"),
        ("CoPu", "combo_onoff"),
        ("ByPa", "combo_onoff"),
        ("", "spacer"),
        ("GS-O₂", "combo_gas"),
        ("FW-O₂ (mL/min)", "flow_mfc1"),
        ("GS-CO₂", "combo_gas"),
        ("FW-CO₂ (mL/min)", "flow_mfc2"),
        ("GS-N₂", "combo_gas"),
        ("FW-N₂ (mL/min)", "flow_mfc3"),
        ("GS-H₂", "combo_gas"),
        ("FW-H₂ (mL/min)", "flow_mfc4"),
        ("", "spacer"),
        ("WoTe 1 (°C)", "sp_temp"),
        ("WoTe 2 (°C)", "sp_temp"),
    ]

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        self._configurar_estilos()

        # ----------- estado de ejecución -----------
        self._run_active = False
        self._paused = False
        self._tick_id = None

        # punteros y contadores
        # columnas (1..8) activas por tiempo de etapa > 0
        self._active_cols = []
        self._col_ptr = -1            # índice dentro de _active_cols
        self._stage_remaining = 0     # seg restantes de la etapa actual
        self._seg_remaining = 0       # seg restantes del segmento (A o B)
        self._seg_pos = "A"
        self._seg_tA = 0              # seg duración A
        self._seg_tB = 0              # seg duración B

        self._pos_file = os.path.join(
            os.path.dirname(__file__), "valv_pos.csv")

        self._max_stage = 0                 # 0 = todo deshabilitado al inicio
        self._stage_chk_vars = {}           # {c: tk.IntVar} por etapa 1..8

        # refs de celdas: dict[col][rowkey] -> widget
        self.cells = {c: {} for c in range(1, 9)}

        self._build_ui()

    # ============================ UI base ============================
        # ------------- Estilos -------------
    def _configurar_estilos(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        GREEN = "#9bd7b1"    # verde
        GREEN_D = "#27ae60"   # verde oscuro (pressed / activo)

        RED = "#FF4B3B"     # rojo
        RED_D = "#db4231"     # rojo oscuro (pressed / activo)

        style.configure("iniciar.TButton", padding=(16, 8),
                        font=getattr(C, "FONT_BASE", ("Calibri", 13)))
        style.map("iniciar.TButton", background=[
                  ("!disabled", GREEN), ("pressed", GREEN_D)])

        style.configure("detener.TButton", padding=(16, 8),
                        font=getattr(C, "FONT_BASE", ("Calibri", 13)))
        style.map("detener.TButton", background=[
                  ("!disabled", RED), ("pressed", RED_D)])

        style.configure("B.TButton", padding=(16, 8),
                        font=getattr(C, "FONT_BASE", ("Calibri", 13)))
        style.map("B.TButton", background=[
                  ("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")])

        style.configure("BSelected.TButton", padding=(16, 8), font=getattr(
            C, "FONT_BASE", ("Calibri", 13)), background="#bdbdbd")
        style.map("BSelected.TButton", background=[
                  ("!disabled", "#bdbdbd"), ("pressed", "#9e9e9e")])

        style.configure("StageChk.TCheckbutton",
                        padding=(8, 2))  # área clic mayor

    def _build_ui(self):
        # columnas: 0 barra, 1 contenido
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación (sin márgenes para aprovechar 1024x600)
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="ns")

        # Contenedor principal
        main = ttk.Frame(self)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(3, weight=1)  # fila del canvas scrolleable
        main.grid_columnconfigure(0, weight=1)

        # --------- fila 0: botonera ---------
        self._build_controls(main)

        # --------- fila 2: monitor ---------
        self._build_monitor(main)

        # --------- fila 3: canvas scrolleable con grid ---------
        self._build_grid(main)

    def _build_controls(self, parent):
        # 1) Frame con tamaño fijo
        wrap = ttk.Frame(parent, borderwidth=2)
        wrap.configure(width=300, height=50)       # <- tamaño visible
        wrap.grid(row=0, column=0, padx=0, pady=2, sticky="nsew")
        wrap.grid_propagate(False)                  # <- que no se encoja

        # El parent: la FILA no debe estirarse; la COLUMNA sí.
        parent.grid_rowconfigure(0, weight=0)     # <- no crecer en alto
        parent.grid_columnconfigure(0, weight=1)  # <- sí crecer a lo ancho

        self.btn_validar = TouchButton(
            wrap, text="Validar", width=6, style="B.TButton", command=self._cmd_validar)
        self.btn_validar.place(
            x=POS[1]["btn_validar"][0], y=POS[1]["btn_validar"][1])

        self.btn_iniciar = TouchButton(
            wrap, text="Iniciar", width=6, style="iniciar.TButton", command=self._cmd_iniciar)
        self.btn_iniciar.place(
            x=POS[1]["btn_iniciar"][0], y=POS[1]["btn_iniciar"][1])

        self.btn_pausar = TouchButton(
            wrap, text="Pausar", width=6, style="B.TButton", command=self._cmd_pausar, state="disabled")
        self.btn_pausar.place(x=POS[1]["btn_pausar"]
                              [0], y=POS[1]["btn_pausar"][1])

        self.btn_reanudar = TouchButton(
            wrap, text="Reanudar", width=8, style="B.TButton", command=self._cmd_reanudar, state="disabled")
        self.btn_reanudar.place(
            x=POS[1]["btn_reanudar"][0], y=POS[1]["btn_reanudar"][1])

        self.btn_detener = TouchButton(
            wrap, text="Detener", width=7, style="detener.TButton", command=self._cmd_detener)
        self.btn_detener.place(
            x=POS[1]["btn_detener"][0], y=POS[1]["btn_detener"][1])

        self.btn_guardar_pre = TouchButton(
            wrap, text="Guardar preset", width=12, style="B.TButton", command=self._cmd_guardar_preset)
        self.btn_guardar_pre.place(
            x=POS[1]["btn_guardar_pre"][0], y=POS[1]["btn_guardar_pre"][1])

        self.btn_cargar_pre = TouchButton(
            wrap, text="Cargar preset", width=12, style="B.TButton", command=self._cmd_cargar_preset)
        self.btn_cargar_pre.place(
            x=POS[1]["btn_cargar_pre"][0], y=POS[1]["btn_cargar_pre"][1])

    def _build_monitor(self, parent):
        FONT = ("Calibri", 11)
        FONT_B = ("Calibri", 11, "bold")  # título y tiempos en bold

        box = ttk.Frame(parent, borderwidth=2, relief="groove", padding=(6, 2))
        box.grid(row=2, column=0, sticky="ew", pady=(2, 4))
        # solo el contenedor crece a lo ancho
        parent.grid_columnconfigure(0, weight=1)

        # --- UNA SOLA FILA ---
        # Col 0: título dentro del frame
        # ttk.Label(box, text="Monitor", font=FONT_B).grid(row=0, column=0, padx=(6, 8), pady=1, sticky="w")

        # Vars (valores que tú actualizas luego)
        self.var_mon_etapa = tk.StringVar(value="-")  # "1/8"
        self.var_mon_pos = tk.StringVar(value="-")  # "A"/"B"
        self.var_mon_rest_etapa = tk.StringVar(value="-")  # "mm:ss"
        self.var_mon_rest_seg = tk.StringVar(value="-")  # "mm:ss"
        self.var_mon_pres = tk.StringVar(value="-")  # "25.0"

        # Pares etiqueta/valor (tamaño fijo por width, nada de expansión)
        ttk.Label(box, text="Etapa:", font=FONT).grid(
            row=0, column=0, padx=(0, 4), pady=1, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_etapa, font=FONT_B, width=1, anchor="e").grid(
            row=0, column=1, padx=(0, 8), pady=1, sticky="w")   # "1/8" => 3 chars

        ttk.Label(box, text="Posición válvulas:", font=FONT).grid(
            row=0, column=2, padx=(0, 4), pady=1, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_pos, font=FONT_B, width=1, anchor="w").grid(
            row=0, column=3, padx=(0, 8), pady=1, sticky="w")   # "A"/"B" => 1 char

        ttk.Label(box, text="Restante etapa:", font=FONT).grid(
            row=0, column=4, padx=(0, 4), pady=1, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_rest_etapa, font=FONT_B, width=5, anchor="e").grid(
            row=0, column=5, padx=(0, 8), pady=1, sticky="w")   # "mm:ss" => 5 chars

        ttk.Label(box, text="Cambio válvulas en:", font=FONT).grid(
            row=0, column=6, padx=(0, 4), pady=1, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_rest_seg, font=FONT_B, width=5, anchor="e").grid(
            row=0, column=7, padx=(0, 8), pady=1, sticky="w")   # "mm:ss" => 5 chars

        ttk.Label(box, text="Presión etapa (bar):", font=FONT).grid(
            row=0, column=8, padx=(0, 4), pady=1, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_pres, font=FONT_B, width=4, anchor="e").grid(
            row=0, column=9, padx=(0, 8), pady=1, sticky="w")  # "25.0" => 4 chars

        # --- Configurar columnas: todas sin expansión ---
        for c in range(0, 10):
            box.grid_columnconfigure(c, weight=0)

        # Una sola columna elástica (espaciador) antes del botón "?"
        # box.grid_columnconfigure(10, weight=0)

        # Botón "?" a la derecha
        self.btn_info_con = TouchButton(box, text="?", width=10)
        self.btn_info_con.grid(
            row=0, column=11, padx=(0, 4), pady=1, sticky="e")
        self.btn_info_con.configure(
            command=lambda: messagebox.showinfo(
                "Información de variables",
                " StNu: Número de etapa\n TiSt: Tiempo de la etapa\n VaPo: Posición válvulas 4 vías\n TiPo-A: Tiempo en posición A\n"
                " TiPo-B: Tiempo en posición B\n WoPr: Presión de trabajo\n CoPu: Bomba peristáltica\n ByPa: Bypass\n"
                " GS-O₂: Gas para MFC de O₂\n FW-O₂: Flujo MFC de O₂\n GS-CO₂: Gas para MFC de CO₂\n FW-CO₂: Flujo MFC de CO₂\n"
                " GS-N₂: Gas para MFC de N₂\n FW-N₂: Flujo MFC de N₂\n GS-H₂: Gas para MFC de H₂\n FW-H₂: Flujo MFC de H₂\n"
                " WoTe 1: Temperatura de trabajo horno 1\n WoTe 2: Temperatura de trabajo horno 2\n"
            )
        )

    def _build_grid(self, parent):
        # Canvas con scroll H+V
        holder = ttk.Frame(parent)
        holder.grid(row=3, column=0, sticky="nsew")
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(holder, highlightthickness=0)
        vsb = tk.Scrollbar(holder, orient="vertical",
                           command=self.canvas.yview, width=24)
        hsb = tk.Scrollbar(holder, orient="horizontal",
                           command=self.canvas.xview, width=24)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.grid_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")

        # ajustar región scrolleable al modificar el tamaño interior
        self.grid_frame.bind("<Configure>", lambda _e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))

        # ======= FUENTE SOLO PARA ESTE FRAME =======
        GRID_FONT_SIZE = 13  # <-- ajusta entre 10 y 13 según necesites
        FONT = ("Calibri", GRID_FONT_SIZE)
        FONT_B = ("Calibri", GRID_FONT_SIZE, "bold")

        # fuente/anchos para táctil 1024x600 (sin exagerar)
        label_padx = (6, 4)
        label_pady = (4, 2)
        cell_pad = dict(padx=3, pady=2)

        # *** Repartir ancho: columnas 1..8 iguales y elásticas ***
        # etiquetas (categorías) no se estiran
        self.grid_frame.grid_columnconfigure(0, weight=0)
        for c in range(1, 9):
            self.grid_frame.grid_columnconfigure(c, weight=1, uniform="cols")

        # Columna 0: etiquetas (categorías)
        for r, (text, kind) in enumerate(self.ROWS):
            lbl = ttk.Label(self.grid_frame, text=text,
                            anchor="e", justify="right")
            lbl.configure(font=FONT)
            lbl.grid(row=r, column=0, sticky="e",
                     padx=label_padx, pady=label_pady)

        # Columnas 1..8: etapas
        for c in range(1, 9):
            # Cabecera: checkbox (izq) + número (der) sin halo
            head_wrap = ttk.Frame(self.grid_frame)
            head_wrap.grid(row=0, column=c, sticky="nsew", **cell_pad)

            var_chk = tk.IntVar(value=0)
            self._stage_chk_vars[c] = var_chk

            chk = ttk.Checkbutton(
                head_wrap,
                variable=var_chk,
                command=lambda cc=c: self._on_stage_checkbox(cc),
                takefocus=False,
                style="StageChk.TCheckbutton",
            )
            chk.pack(side="left")

            ttk.Label(head_wrap, text=str(c), font=FONT_B).pack(
                side="left", padx=(6, 0))

            # Fila 1: Tiempo de etapa (entry entero, default 0)
            ent_t_etapa = self._make_entry_int(self.grid_frame, default="0")
            ent_t_etapa.configure(font=FONT)
            ent_t_etapa.grid(row=1, column=c, sticky="ew", **cell_pad)

            # Fila 2: (espacio) -> nada

            # Válvulas
            cmb_pos = ttk.Combobox(self.grid_frame, values=(
                "A", "B"), state="readonly", width=5)
            cmb_pos.configure(font=FONT)
            cmb_pos.set("A")
            cmb_pos.grid(row=3, column=c, sticky="ew", **cell_pad)
            cmb_pos.option_add("*TCombobox*Listbox*Font", ("Calibri", 14))

            ent_ta = self._make_entry_int(self.grid_frame, default="0")
            ent_ta.configure(font=FONT)
            ent_ta.grid(row=4, column=c, sticky="ew", **cell_pad)

            ent_tb = self._make_entry_int(self.grid_frame, default="0")
            ent_tb.configure(font=FONT)
            ent_tb.grid(row=5, column=c, sticky="ew", **cell_pad)

            ent_pres = self._make_entry_dec(
                self.grid_frame, default="0.0", max_dec=1)
            ent_pres.configure(font=FONT)
            ent_pres.grid(row=6, column=c, sticky="ew", **cell_pad)

            # (espacio)

            # Bomba peristáltica
            cmb_p1 = ttk.Combobox(self.grid_frame, values=(
                "OFF", "ON"), state="readonly", width=6)
            cmb_p1.configure(font=FONT)
            cmb_p1.set("OFF")
            cmb_p1.grid(row=8, column=c, sticky="ew", **cell_pad)
            cmb_p1.option_add("*TCombobox*Listbox*Font", ("Calibri", 14))

            # Bypass
            cmb_bypass = ttk.Combobox(self.grid_frame, values=(
                "1", "2"), state="readonly", width=6)
            cmb_bypass.configure(font=FONT)
            cmb_bypass.set("1")
            cmb_bypass.grid(row=9, column=c, sticky="ew", **cell_pad)
            cmb_bypass.option_add("*TCombobox*Listbox*Font", ("Calibri", 14))

            # (espacio)

            # MFC1..4: gas + flujo con límites
            def make_gas_flow(row_gas, row_flow, mfc_id):
                gas_default = MFC_DEFAULTS[mfc_id][0]
                cmb = ttk.Combobox(
                    self.grid_frame, values=GASES, state="readonly", width=8)
                cmb.configure(font=FONT)
                cmb.set(gas_default)
                cmb.grid(row=row_gas, column=c, sticky="ew", **cell_pad)
                cmb.option_add("*TCombobox*Listbox*Font", ("Calibri", 14))

                ent = self._make_entry_int(self.grid_frame, default="0")
                ent.configure(font=FONT)
                ent.grid(row=row_flow, column=c, sticky="ew", **cell_pad)

                # al abrir teclado y al salir, normaliza con límite del gas actual
                self._attach_flow_logic(ent, mfc_id, cmb)

                return cmb, ent

            cmb_m1, ent_m1 = make_gas_flow(11, 12, 1)
            cmb_m2, ent_m2 = make_gas_flow(13, 14, 2)
            cmb_m3, ent_m3 = make_gas_flow(15, 16, 3)
            cmb_m4, ent_m4 = make_gas_flow(17, 18, 4)

            # (espacio)

            ent_t1 = self._make_entry_int(
                self.grid_frame, default="0", cap_max=MAX_SP)
            ent_t1.configure(font=FONT)
            ent_t1.grid(row=20, column=c, sticky="ew", **cell_pad)

            ent_t2 = self._make_entry_int(
                self.grid_frame, default="0", cap_max=MAX_SP)
            ent_t2.configure(font=FONT)
            ent_t2.grid(row=21, column=c, sticky="ew", **cell_pad)

            # Guardar referencias por columna
            self.cells[c] = {
                "t_etapa": ent_t_etapa,
                "pos_ini": cmb_pos,
                "t_a": ent_ta,
                "t_b": ent_tb,
                "pres": ent_pres,
                "p1": cmb_p1,
                "bypass": cmb_bypass,
                "m1_gas": cmb_m1, "m1_f": ent_m1,
                "m2_gas": cmb_m2, "m2_f": ent_m2,
                "m3_gas": cmb_m3, "m3_f": ent_m3,
                "m4_gas": cmb_m4, "m4_f": ent_m4,
                "t1": ent_t1, "t2": ent_t2,
            }

            # Al iniciar: todo deshabilitado
            self._set_stage_enabled(c, False)

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
        # e.bind("<Button-1>", lambda _ev: TecladoNumerico(self, e, on_submit=lambda v: (e.delete(0, tk.END), e.insert(0, str(v)), _norm())))
        e.bind("<Button-1>", lambda _ev, w=e,
               norm=_norm: self._open_kbd_if_enabled(w, norm))
        e.bind("<FocusOut>", lambda _e: _norm())
        # validación en escritura
        vcmd = (self.register(self._validate_numeric),
                "%P", "%d", 1, 0)  # entero
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

        # e.bind("<Button-1>", lambda _ev: TecladoNumerico(self, e, on_submit=lambda v: (e.delete(0, tk.END), e.insert(0, str(v)), _norm())))
        e.bind("<Button-1>", lambda _ev, w=e,
               norm=_norm: self._open_kbd_if_enabled(w, norm))
        e.bind("<FocusOut>", lambda _e: _norm())
        vcmd = (self.register(self._validate_numeric),
                "%P", "%d", 0, max_dec)  # decimal
        e.configure(validate="key", validatecommand=vcmd)
        return e

    def _attach_flow_logic(self, entry: ttk.Entry, mfc_id: int, cmb_gas: ttk.Combobox):
        """Capar flujo por gas (enviar con teclado o al perder foco)."""
        def _norm_flow():
            gas = cmb_gas.get() if cmb_gas.get(
            ) in GASES else MFC_DEFAULTS[mfc_id][0]
            lim = MFC_DEFAULTS[mfc_id][1][gas]
            txt = (entry.get() or "").strip()
            try:
                n = int(float(txt))
            except Exception:
                n = 0
            n = clamp(n, 0, lim)
            entry.delete(0, tk.END)
            entry.insert(0, str(n))

        # entry.bind("<Button-1>", lambda _ev: TecladoNumerico(self, entry, on_submit=lambda v: (entry.delete(0, tk.END), entry.insert(0, str(v)), _norm_flow())))
        entry.bind("<Button-1>", lambda _ev,
                   w=entry: self._open_kbd_if_enabled(w, _norm_flow))
        entry.bind("<FocusOut>", lambda _e: _norm_flow())
        cmb_gas.bind("<<ComboboxSelected>>", lambda _e: _norm_flow())
        cmb_gas.option_add("*TCombobox*Listbox*Font", ("Calibri", 14))

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

    def _open_kbd_if_enabled(self, widget: ttk.Entry, on_submit):
        """Abre el TecladoNumerico sólo si el entry NO está 'disabled'."""
        try:
            if str(widget.cget("state")) != "disabled":
                TecladoNumerico(self, widget,
                                on_submit=lambda v: (widget.delete(0, tk.END), widget.insert(0, str(v)), on_submit()))
        except Exception:
            # Si el widget no tiene 'state' por alguna razón, intenta comportamiento seguro
            pass

    # ====================== Acciones de botones ======================

    def _cmd_validar(self):
        incompletas = []
        for c in range(1, 9):
            if self._stage_chk_vars[c].get() and not self._col_is_complete(c):
                incompletas.append(str(c))

        if incompletas and len(incompletas) < 8:
            messagebox.showwarning(
                "Validación",
                "Las siguientes etapas habilitadas no están completas (se ignorarán al iniciar): "
                + ", ".join(incompletas)
            )
        elif len(incompletas) == 8:
            messagebox.showerror(
                "Validación", "No hay ninguna etapa completa entre las habilitadas.")
        else:
            messagebox.showinfo(
                "Validación", "Todas las etapas habilitadas están completas.")

    def _cmd_iniciar(self):
        if self._run_active:
            messagebox.showinfo("Auto", "El proceso ya está en ejecución.")
            return

        self._active_cols = [c for c in range(1, 9) if self._col_is_complete(c)]
        if not self._active_cols:
            messagebox.showerror(
                "Auto", "No hay etapas completas y habilitadas para ejecutar.")
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
        """Criterio mínimo: Tiempo de etapa > 0, y tiempos A y B > 0.Checkbox habilitado"""
        if not self._stage_chk_vars[c].get():
            return False
        
        t_etapa = self._get_int(self.cells[c]["t_etapa"])
        t_a = self._get_int(self.cells[c]["t_a"])
        t_b = self._get_int(self.cells[c]["t_b"])
        return t_etapa > 0 and t_a > 0 and t_b > 0

    def _iniciar_siguiente_etapa(self):
        self._col_ptr += 1
        if self._col_ptr >= len(self._active_cols):
            self._stop_all("Todas las etapas completas finalizaron.")
            try:
                messagebox.showwarning(
                    "Modo Auto",
                    "Las etapas concluyeron.\nEl sistema permanecerá en las condiciones especificadas en la última etapa habilitada."
                )
            except Exception:
                pass
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

    def _on_stage_checkbox(self, c: int):
        """
        Cuando el usuario marca la casilla de la etapa 'c', se interpreta como:
        'quiero habilitar desde la etapa 1 hasta la etapa c'.
        """
        # Fijar máximo y reflejar el estado en todas las casillas
        self._max_stage = c
        for i in range(1, 9):
            self._stage_chk_vars[i].set(1 if i <= c else 0)
        # Habilitar/Deshabilitar controles de columnas
        self._refresh_stage_enable()

    def _refresh_stage_enable(self):
        for i in range(1, 9):
            self._set_stage_enabled(i, enabled=(i <= self._max_stage))

    def _set_stage_enabled(self, c: int, enabled: bool):
        """
        Habilita/deshabilita TODOS los widgets de la columna 'c'.
        - Entries: 'normal' / 'disabled'
        - Comboboxes: 'readonly' / 'disabled'
        """
        cells = self.cells.get(c, {})

        # Entradas numéricas
        for key in ("t_etapa", "t_a", "t_b", "pres", "m1_f", "m2_f", "m3_f", "m4_f", "t1", "t2"):
            w = cells.get(key)
            if w:
                try:
                    w.configure(state=("normal" if enabled else "disabled"))
                except Exception:
                    pass

        # Comboboxes
        for key in ("pos_ini", "p1", "bypass", "m1_gas", "m2_gas", "m3_gas", "m4_gas"):
            w = cells.get(key)
            if w:
                try:
                    w.configure(state=("readonly" if enabled else "disabled"))
                except Exception:
                    pass

    # ====================== Actualización archivo CSV: BYP, V1 = V2 ======================

    def _write_valv_pos(self, v_pos: str | None = None, bypass_on: int | None = None):
        """
        Escribe valv_pos.csv con estructura fija y orden:
            V1,<A|B>
            V2,<A|B>
            BYP,<1|2>

        - Si v_pos es None, conserva el valor previo (por defecto "A").
        - Si bypass_on es None, conserva el valor previo (por defecto 1).
        """
        # Valores actuales por defecto
        cur_v = "A"
        cur_byp = 1

        # Cargar existentes (si hay)
        try:
            if os.path.exists(self._pos_file):
                with open(self._pos_file, newline="", encoding="utf-8") as f:
                    for nombre, pos in csv.reader(f):
                        key = (nombre or "").strip().upper()
                        val = (pos or "").strip().upper()
                        if key in ("V1", "V2") and val in ("A", "B"):
                            # Si V1 y V2 difieren, priorizamos V1; modo auto igualará ambos.
                            cur_v = val
                        elif key == "BYP" and val in ("1", "2"):
                            try:
                                cur_byp = int(val)
                            except Exception:
                                cur_byp = 1
        except Exception as e:
            print(f"[WARN] No se pudo leer {self._pos_file}: {e}")

        # Aplicar overrides
        if v_pos is not None:
            vv = (v_pos or "").strip().upper()
            if vv in ("A", "B"):
                cur_v = vv
            else:
                print("[WARN] _write_valv_pos: v_pos inválido, se conserva:", cur_v)

        if bypass_on is not None:
            try:
                cur_byp = int(bypass_on)
                if cur_byp not in (1, 2):
                    raise ValueError
            except Exception:
                print(
                    "[WARN] _write_valv_pos: bypass_on inválido, se conserva:", cur_byp)

        # Reescribir exactamente 3 filas en el mismo orden que la otra ventana
        try:
            with open(self._pos_file, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["V1", cur_v])
                w.writerow(["V2", cur_v])
                w.writerow(["BYP", str(cur_byp)])
        except Exception as e:
            print(f"[WARN] No se pudo escribir {self._pos_file}: {e}")

    # ----------------------- TX helpers -----------------------

    def _tx(self, mensaje: str) -> bool:
        print("[TX]", mensaje)
        try:
            if self.controlador and hasattr(self.controlador, "enviar_a_arduino"):
                self.controlador.enviar_a_arduino(mensaje)
                return True   # OK: enviado sin excepciones
            else:
                print("[WARN][TX] No hay controlador/enviar_a_arduino; no se envió.")
                return False
        except Exception as e:
            print("[WARN][TX] Falla enviando a Arduino:", e)
            return False

    def _tx_etapa(self, d: dict):
        """
        $;4;POS_INI;PS*10;P1_ON;BYPASS;M1_PWM;M2_PWM;M3_PWM;M4_PWM;T1_SP;T2_SP;!
        """
        partes = [
            "$;4",
            str(d["pos_ini"]), str(d["ps10"]),
            str(d["p1_on"]),
            str(d["bypass_on"]),
            str(d["m1_pwm"]), str(d["m2_pwm"]), str(
                d["m3_pwm"]), str(d["m4_pwm"]),
            str(d["t1_sp"]), str(d["t2_sp"]),
        ]

        # se envía el mensaje al arduino
        estado_mensaje = self._tx(";".join(partes) + ";!")

        # 2) Persistencia (modo auto): V1 = V2 = pos_ini; BYP de la etapa
        pos_ini_char = "A" if int(d.get("pos_ini", 1)) == 1 else "B"
        if estado_mensaje:
            self._write_valv_pos(v_pos=pos_ini_char,
                                 bypass_on=int(d.get("bypass_on", 1)))

    def _send_valve_position(self, pos: str):
        """Cambio de posición automático durante la etapa."""
        code = "1" if pos.upper() == "A" else "2"
        estado_mensaje_v = self._tx(f"$;3;1;0;{code};!")

        # Persistencia (modo auto): V1 = V2 = pos; BYP se conserva
        if estado_mensaje_v:
            self._write_valv_pos(v_pos=pos.upper(), bypass_on=None)

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
        pos_ini = 1 if (self.cells[c]["pos_ini"].get()
                        or "A").upper() == "A" else 2

        # presión
        pres_bar = clamp(round(self._get_float(
            self.cells[c]["pres"]), 1), 0.0, MAX_PRES)
        ps10 = int(round(pres_bar * 10))

        # peristálticas
        p1_on = 1 if (self.cells[c]["p1"].get() == "ON") else 2

        # Bypass: 1 - OFF, 2 - ON
        bypass_on = 1 if (self.cells[c]["bypass"].get() == "1") else 2

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
            "bypass_on": bypass_on,
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
        # Crear instancia de la clase anidada
        popup = self._GuardarPresetPopup(self)
    # No necesitamos hacer más aquí, la clase se encarga de todo

    # Definir la clase anidada para el popup de guardar preset
    class _GuardarPresetPopup(tk.Toplevel):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.title("Guardar preset")
            self.geometry("600x340+300+50")
            self.resizable(False, False)

            # Configurar el cierre de la ventana
            self.protocol("WM_DELETE_WINDOW", self._on_close)

            # Inicializar la interfaz
            self._inicializar_ui()

            # Configurar modalidad
            self.transient(parent)
            self.grab_set()

            # Enfoque diferente: siempre enfocar el entry y habilitar teclado
            self.after(100, self._enfocar_entry)

        def _enfocar_entry(self):
            """Enfocar el entry y habilitar el teclado"""
            self.entry_nombre.focus_set()
            self.entry_nombre.icursor(tk.END)
            self.focus_force()

        def _inicializar_ui(self):
            # === Copiar estilo/colores como en TecladoNumerico ===
            st = ttk.Style(self)
            try:
                st.theme_use("clam")
            except Exception:
                pass  # mantener robustez

            self.bg_theme = st.lookup("TFrame", "background")
            if not self.bg_theme:
                self.bg_theme = self.cget("bg")
            self.configure(bg=self.bg_theme)

            # Fuente coherente con tu teclado numérico
            self._font = tkfont.Font(family="Calibri", size=16)

            # --- título + entry (con mismo fondo) ---
            tk.Label(self, text="Nombre del archivo:", font=("Calibri", 14), bg=self.bg_theme)\
                .pack(pady=(12, 6))

            self.entry_nombre = tk.Entry(self, font=(
                "Calibri", 18), width=32, justify="center")
            self.entry_nombre.pack(pady=(0, 10))

            # === Teclado alfanumérico (sin espacio) ===
            filas_teclas = [
                ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],  # fila 0
                ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],  # fila 1
                ["A", "S", "D", "F", "G", "H", "J", "K",
                    "L"],       # fila 2 (col 9 libre)
                ["Z", "X", "C", "V", "B", "N", "M", "_",
                    "-"],       # fila 3 (col 9 libre)
            ]

            self.frame_teclado = tk.Frame(
                self, bg=self.bg_theme, highlightthickness=0, bd=0)
            self.frame_teclado.pack(pady=12)

            # Teclas más grandes
            KEY_W, KEY_H = 2, 1

            # Crear teclado
            self._crear_teclado(filas_teclas, KEY_W, KEY_H)

            # === Botones de guardado ===
            self._crear_botones_guardado()

            # Atajos coherentes
            self.bind("<Return>", lambda e: self.guardar())
            self.bind("<Escape>", lambda e: self._on_close())

            # Enfocar el entry después de que la UI esté completamente cargada
            self.after(200, self._enfocar_entry)

        def _crear_teclado(self, filas_teclas, key_w, key_h):
            # Filas 0 y 1 completas (10 columnas)
            for r in (0, 1):
                for c, tecla in enumerate(filas_teclas[r]):
                    btn = tk.Button(
                        self.frame_teclado,
                        text=tecla,
                        font=self._font,
                        width=key_w, height=key_h,
                        command=lambda k=tecla: self.escribir(k),
                        bg=self.bg_theme, activebackground=self.bg_theme,
                        relief="raised",
                        takefocus=False
                    )
                    btn.grid(row=r, column=c, padx=4, pady=4, sticky="")

            # Filas 2 y 3 con 9 columnas (dejando libre col 9)
            for r in (2, 3):
                for c, tecla in enumerate(filas_teclas[r]):
                    tk.Button(
                        self.frame_teclado,
                        text=tecla,
                        font=self._font,
                        width=key_w, height=key_h,
                        command=lambda k=tecla: self.escribir(k),
                        bg=self.bg_theme, activebackground=self.bg_theme,
                        relief="raised",
                        takefocus=False
                    ).grid(row=r, column=c, padx=4, pady=4, sticky="")

            # Botón "<-" vertical ocupando la columna 9 en filas 2 y 3
            tk.Button(
                self.frame_teclado,
                text="<-",
                font=self._font,
                width=key_w, height=key_h * 2,  # más alto
                command=lambda: self.escribir("<-"),
                bg=self.bg_theme, activebackground=self.bg_theme,
                relief="raised",
                takefocus=False
            ).grid(row=2, column=9, rowspan=2, padx=4, pady=4, sticky="nsew")

        def _crear_botones_guardado(self):
            # Barra de acciones (mismo fondo)
            acciones = tk.Frame(self, bg=self.bg_theme)
            acciones.pack(pady=8)
            tk.Button(acciones, text="Guardar", font=("Calibri", 16),
                      command=self.guardar, bg=self.bg_theme, activebackground=self.bg_theme)\
                .pack(side="left", padx=8)
            tk.Button(acciones, text="Cancelar", font=("Calibri", 16),
                      command=self._on_close, bg=self.bg_theme, activebackground=self.bg_theme)\
                .pack(side="left", padx=8)

        def escribir(self, tecla):
            # Insertar la tecla directamente sin verificación de supresión
            if tecla == "<-":
                txt = self.entry_nombre.get()
                if txt:
                    self.entry_nombre.delete(len(txt)-1, tk.END)
            else:
                self.entry_nombre.insert(tk.END, tecla)

        def guardar(self):
            nombre = (self.entry_nombre.get() or "").strip()
            if not nombre:
                messagebox.showwarning(
                    "Guardar preset", "Por favor ingresa un nombre.", parent=self)
                return

            # Ruta destino (ajústala a lo que uses en tu proyecto)
            carpeta_destino = os.path.expanduser("~/home/eia/Documents/preset")
            os.makedirs(carpeta_destino, exist_ok=True)
            path = os.path.join(carpeta_destino, f"{nombre}.csv")

            headers = ["StNu", "TiSt", "VaPo", "TiPo_A", "TiPo_B", "WoPr10",
                       "CoPu", "ByPa", "GS_O2", "FW_O2", "GS_CO2", "FW_CO2",
                       "GS_N2", "FW_N2", "GS_H2", "FW_H2", "WoTe1", "WoTe2"]

            try:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(headers)
                    for c in range(1, 9):
                        row = self.parent._row_from_col(c)
                        w.writerow(row)
                # Messagebox indicando la RUTA COMPLETA
                messagebox.showinfo(
                    "Preset", f"Preset guardado correctamente en:\n{path}", parent=self)
                self._on_close()
            except Exception as ex:
                messagebox.showerror(
                    "Preset", f"No se pudo guardar el preset:\n{ex}", parent=self)

        def _on_close(self):
            self.destroy()

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
            str(c),  # StNu
            ent_str(self.cells[c]["t_etapa"], "0"),  # TiSt
            pos_ini,  # VaPo
            ent_str(self.cells[c]["t_a"], "0"),  # TiPo_A
            ent_str(self.cells[c]["t_b"], "0"),  # TiPo_B
            ps10,  # WoPr10
            "1" if self.cells[c]["p1"].get() == "ON" else "2",  # CoPu
            "1" if self.cells[c]["bypass"].get() == "1" else "2",  # ByPa
            self.cells[c]["m1_gas"].get(), ent_str(self.cells[c]["m1_f"], "0"),  # GS_O2, FW_O2
            self.cells[c]["m2_gas"].get(), ent_str(self.cells[c]["m2_f"], "0"),  # GS_CO2, FW_CO2
            self.cells[c]["m3_gas"].get(), ent_str(self.cells[c]["m3_f"], "0"),  # GS_N2, FW_N2
            self.cells[c]["m4_gas"].get(), ent_str(self.cells[c]["m4_f"], "0"),  # GS_H2, FW_H2
            ent_str(self.cells[c]["t1"], "0"),  # WoTe1
            ent_str(self.cells[c]["t2"], "0"),  # WoTe2
        ]

    def _cmd_cargar_preset(self):
        carpeta_destino = os.path.expanduser("~/home/eia/Documents/preset")
        os.makedirs(carpeta_destino, exist_ok=True)

        path = filedialog.askopenfilename(
            initialdir=carpeta_destino,
            filetypes=[("CSV", "*.csv")],
            title="Cargar preset"
        )
        if not path:
            return

        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
                # Primero: determinar qué columnas habilitar basado en TiSt > 0
                stages_to_enable = []
                for row in rows:
                    try:
                        col = int(row.get("StNu", "0").strip())
                        t_etapa = int(row.get("TiSt", "0").strip())
                        if t_etapa > 0 and 1 <= col <= 8:
                            stages_to_enable.append(col)
                    except:
                        continue
            
                # Habilitar las columnas necesarias
                if stages_to_enable:
                    max_stage = max(stages_to_enable)
                    self._on_stage_checkbox(max_stage)
            
                # Segundo: cargar los datos
                for row in rows:
                    try:
                        col = int(row.get("StNu", "0").strip())
                        if 1 <= col <= 8:
                            self._apply_csv_row_to_col(col, row)
                    except Exception as e:
                        print(f"DEBUG: Error procesando fila: {e}")
                        continue
                    
            messagebox.showinfo("Preset", "Preset cargado correctamente.")
        except Exception as ex:
            messagebox.showerror(
                "Preset", f"No se pudo cargar el preset:\n{ex}")
        
    def _apply_csv_row_to_col(self, c: int, row: dict):
        def set_e(e: ttk.Entry, val: str):
            e.delete(0, tk.END)
            e.insert(0, val or "")

        # tiempos y posición
        set_e(self.cells[c]["t_etapa"], row.get("TiSt", "0"))
        self.cells[c]["pos_ini"].set(
            "A" if row.get("VaPo", "1") == "1" else "B")
        set_e(self.cells[c]["t_a"], row.get("TiPo_A", "0"))
        set_e(self.cells[c]["t_b"], row.get("TiPo_B", "0"))

        # presión WoPr10 -> bar
        try:
            WoPr10 = int(row.get("WoPr10", "0"))
            p = clamp(WoPr10 / 10.0, 0.0, MAX_PRES)
            set_e(self.cells[c]["pres"], f"{p:.1f}")
        except Exception:
            set_e(self.cells[c]["pres"], "0.0")

        # peristálticas
        self.cells[c]["p1"].set("ON" if row.get(
            "CoPu", "2") == "1" else "OFF")
        self.cells[c]["bypass"].set(
            "2" if row.get("ByPa", "2") == "1" else "1")

        # MFCs - usando los nombres exactos del CSV
        self.cells[c]["m1_gas"].set(row.get("GS_O2", "O2"))
        set_e(self.cells[c]["m1_f"], row.get("FW_O2", "0"))
    
        self.cells[c]["m2_gas"].set(row.get("GS_CO2", "CO2"))
        set_e(self.cells[c]["m2_f"], row.get("FW_CO2", "0"))
    
        self.cells[c]["m3_gas"].set(row.get("GS_N2", "N2"))
        set_e(self.cells[c]["m3_f"], row.get("FW_N2", "0"))
    
        self.cells[c]["m4_gas"].set(row.get("GS_H2", "H2"))
        set_e(self.cells[c]["m4_f"], row.get("FW_H2", "0"))

        # Aplicar clamp para cada MFC después de cargar los valores
        self._apply_flow_clamp(c, 1)
        self._apply_flow_clamp(c, 2)
        self._apply_flow_clamp(c, 3)
        self._apply_flow_clamp(c, 4)

        # SPs - usando los nuevos nombres
        set_e(self.cells[c]["t1"], row.get("WoTe1", "0"))
        set_e(self.cells[c]["t2"], row.get("WoTe2", "0"))  # Corregido a "WoTe2"

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
