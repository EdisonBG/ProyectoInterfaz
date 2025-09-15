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


# ========================= Etapa (acordeón) =============================

class EtapaAccordion(ttk.Frame):
    """
    Un panel plegable ("acordeón") que representa una etapa del proceso.
    Contiene:
      - Tiempo de proceso (min)
      - Válvulas: posición inicial A/B, tiempo A, tiempo B, presión seg (0..20.0, 1 decimal),
                  peristáltica 1 (toggle + tiempo), peristáltica 2 (toggle + tiempo)
      - MFC 1..4: selector de gas + flujo (con leyenda min/max)
      - Temperatura: Horno1 SP, Horno2 SP

    Métodos principales:
      - set_collapsed(True/False): pliega/despliega
      - is_complete() -> bool: valida que la etapa esté lista para ejecutarse
      - collect_payload(idx) -> dict: datos normalizados (se usan para construir el TX y la lógica local).
    """

    def __init__(self, master, indice: int, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.indice = indice  # 1..6
        self._collapsed = True  # arrancar colapsado

        # ---------- Cabecera (botón para colapsar/expandir) ----------
        header = ttk.Frame(self)
        header.pack(fill="x")

        self.btn_toggle = ttk.Button(
            header, text=f"Etapa {self.indice} ▸",
            command=self._toggle_collapse
        )
        self.btn_toggle.pack(side="left", padx=4, pady=(6, 2))

        # ---------- Contenido ----------
        self.body = ttk.Frame(self)
        # inicia colapsado: no se empaqueta todavía

        # Bloque 1: Tiempo de proceso
        b1 = ttk.LabelFrame(self.body, text="Tiempo de proceso")
        b1.pack(fill="x", pady=4)
        ttk.Label(b1, text="Minutos:").grid(row=0, column=0, padx=4, pady=4, sticky="e")
        self.ent_tmin = ttk.Entry(b1, width=8)
        self.ent_tmin.grid(row=0, column=1, padx=4, pady=4, sticky="w")
        self._bind_numeric(self.ent_tmin, entero=True, on_norm=lambda: self._norm_int_min1(self.ent_tmin))

        # Bloque 2: Válvulas
        b2 = ttk.LabelFrame(self.body, text="Válvulas")
        b2.pack(fill="x", pady=4)

        ttk.Label(b2, text="Posición inicial:").grid(row=0, column=0, padx=4, pady=4, sticky="e")
        self.cmb_pos_ini = ttk.Combobox(b2, state="readonly", width=6, values=("A", "B"))
        self.cmb_pos_ini.set("A")
        self.cmb_pos_ini.grid(row=0, column=1, padx=4, pady=4, sticky="w")

        ttk.Label(b2, text="Tiempo en A (min):").grid(row=1, column=0, padx=4, pady=4, sticky="e")
        self.ent_ta = ttk.Entry(b2, width=8)
        self.ent_ta.grid(row=1, column=1, padx=4, pady=4, sticky="w")
        self._bind_numeric(self.ent_ta, entero=True, on_norm=lambda: self._norm_int_min1(self.ent_ta))

        ttk.Label(b2, text="Tiempo en B (min):").grid(row=2, column=0, padx=4, pady=4, sticky="e")
        self.ent_tb = ttk.Entry(b2, width=8)
        self.ent_tb.grid(row=2, column=1, padx=4, pady=4, sticky="w")
        self._bind_numeric(self.ent_tb, entero=True, on_norm=lambda: self._norm_int_min1(self.ent_tb))

        ttk.Label(b2, text="Presión seguridad (bar):").grid(row=0, column=2, padx=4, pady=4, sticky="e")
        self.ent_ps = ttk.Entry(b2, width=8)
        self.ent_ps.grid(row=0, column=3, padx=4, pady=4, sticky="w")
        self._bind_numeric(self.ent_ps, entero=False, max_dec=1, on_norm=self._norm_pressure)
        ttk.Label(b2, text="(máx 20.0)").grid(row=0, column=4, padx=4, pady=4, sticky="w")

        # Peristálticas
        self.peri1_on = tk.BooleanVar(value=False)
        self.peri2_on = tk.BooleanVar(value=False)

        ttk.Checkbutton(b2, text="Peristáltica 1", variable=self.peri1_on, command=self._update_peri_states)\
            .grid(row=1, column=2, padx=4, pady=4, sticky="w")
        self.ent_p1_t = ttk.Entry(b2, width=8, state="disabled")
        self.ent_p1_t.grid(row=1, column=3, padx=4, pady=4, sticky="w")
        ttk.Label(b2, text="min").grid(row=1, column=4, padx=0, pady=4, sticky="w")
        self._bind_numeric(self.ent_p1_t, entero=True, on_norm=lambda: self._norm_int_min1(self.ent_p1_t))

        ttk.Checkbutton(b2, text="Peristáltica 2", variable=self.peri2_on, command=self._update_peri_states)\
            .grid(row=2, column=2, padx=4, pady=4, sticky="w")
        self.ent_p2_t = ttk.Entry(b2, width=8, state="disabled")
        self.ent_p2_t.grid(row=2, column=3, padx=4, pady=4, sticky="w")
        ttk.Label(b2, text="min").grid(row=2, column=4, padx=0, pady=4, sticky="w")
        self._bind_numeric(self.ent_p2_t, entero=True, on_norm=lambda: self._norm_int_min1(self.ent_p2_t))

        # Bloque 3: MFCs
        b3 = ttk.LabelFrame(self.body, text="MFC (flujo mL/min)")
        b3.pack(fill="x", pady=4)

        self.mfc = {}  # id -> dict con widgets y límites
        for row, mfc_id in enumerate((1, 2, 3, 4)):
            ttk.Label(b3, text=f"MFC{mfc_id} Gas:").grid(row=row*2, column=0, padx=4, pady=4, sticky="e")
            cmb = ttk.Combobox(b3, state="readonly", width=8, values=GASES)
            default_gas, limits = MFC_DEFAULTS[mfc_id]
            cmb.set(default_gas)
            cmb.grid(row=row*2, column=1, padx=4, pady=4, sticky="w")

            ttk.Label(b3, text=f"MFC{mfc_id} Flujo:").grid(row=row*2, column=2, padx=4, pady=4, sticky="e")
            ent = ttk.Entry(b3, width=10)
            ent.grid(row=row*2, column=3, padx=4, pady=4, sticky="w")
            self._bind_numeric(ent, entero=True, on_norm=lambda mid=mfc_id: self._norm_flow(mid))

            lbl = ttk.Label(b3, text=self._legend_for(mfc_id, default_gas))
            lbl.grid(row=row*2+1, column=3, padx=4, pady=(0, 6), sticky="w")

            # callback al cambiar gas
            cmb.bind("<<ComboboxSelected>>",
                     lambda _e, mid=mfc_id, cb=cmb, lab=lbl: self._on_mfc_gas_change(mid, cb, lab))

            self.mfc[mfc_id] = {"cmb": cmb, "ent": ent, "lbl": lbl, "limits": limits}

        # Bloque 4: Temperatura
        b4 = ttk.LabelFrame(self.body, text="Temperatura")
        b4.pack(fill="x", pady=4)

        ttk.Label(b4, text="Horno 1 SP:").grid(row=0, column=0, padx=4, pady=4, sticky="e")
        self.ent_t1_sp = ttk.Entry(b4, width=8)
        self.ent_t1_sp.grid(row=0, column=1, padx=4, pady=4, sticky="w")
        self._bind_numeric(self.ent_t1_sp, entero=True, on_norm=lambda: self._norm_sp(self.ent_t1_sp))

        ttk.Label(b4, text=f"(0 – {MAX_SP})").grid(row=1, column=1, padx=4, sticky="w")

        ttk.Label(b4, text="Horno 2 SP:").grid(row=0, column=2, padx=4, pady=4, sticky="e")
        self.ent_t2_sp = ttk.Entry(b4, width=8)
        self.ent_t2_sp.grid(row=0, column=3, padx=4, pady=4, sticky="w")
        self._bind_numeric(self.ent_t2_sp, entero=True, on_norm=lambda: self._norm_sp(self.ent_t2_sp))

        ttk.Label(b4, text=f"(0 – {MAX_SP})").grid(row=1, column=3, padx=4, sticky="w")

    # ---------- helpers UI ----------
    def _toggle_collapse(self):
        """Plega/despliega el cuerpo del acordeón."""
        if self._collapsed:
            # expandir
            self.body.pack(fill="x", padx=8, pady=(2, 8))
            self.btn_toggle.configure(text=f"Etapa {self.indice} ▾")
            self._collapsed = False
        else:
            # colapsar
            self.body.forget()
            self.btn_toggle.configure(text=f"Etapa {self.indice} ▸")
            self._collapsed = True

    def set_collapsed(self, value: bool):
        """Fuerza el estado colapsado/expandido."""
        if value and not self._collapsed:
            self._toggle_collapse()
        elif not value and self._collapsed:
            self._toggle_collapse()

    def _bind_numeric(self, entry: ttk.Entry, *, entero: bool, max_dec: int = 0, on_norm=None):
        """
        Adjunta TecladoNumerico al click, valida mientras escribe y normaliza al salir.
        - entero=True => solo enteros; entero=False => admite decimal (max_dec decimales).
        - on_norm: callback para aplicar el clamp y reflejar en UI.
        """
        entry.bind("<Button-1>", lambda e, ent=entry, cb=on_norm:
                   TecladoNumerico(self, ent, on_submit=lambda v: (ent.delete(0, tk.END), ent.insert(0, str(v)), cb() if cb else None)))
        vcmd = (self.register(self._validate_numeric), "%P", "%d", int(entero), max_dec)
        entry.configure(validate="key", validatecommand=vcmd)
        if on_norm:
            entry.bind("<FocusOut>", lambda _e: on_norm())

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

    def _legend_for(self, mfc_id: int, gas: str) -> str:
        lim = MFC_DEFAULTS[mfc_id][1][gas]
        return f"min: 0   max: {lim}"

    def _on_mfc_gas_change(self, mfc_id: int, cmb: ttk.Combobox, lbl: ttk.Label):
        """Actualiza leyenda de max y recorta el flujo si excede el nuevo máximo."""
        gas = cmb.get()
        lim = MFC_DEFAULTS[mfc_id][1][gas]
        lbl.configure(text=f"min: 0   max: {lim}")
        self._norm_flow(mfc_id)

    def _update_peri_states(self):
        """Habilita/deshabilita los entries de tiempo de peristálticas según su toggle."""
        self.ent_p1_t.configure(state=("normal" if self.peri1_on.get() else "disabled"))
        self.ent_p2_t.configure(state=("normal" if self.peri2_on.get() else "disabled"))
        # al habilitar, clamp inmediato
        if self.peri1_on.get():
            self._norm_int_min1(self.ent_p1_t)
        if self.peri2_on.get():
            self._norm_int_min1(self.ent_p2_t)

    # ---------- normalizadores que reflejan en UI ----------
    def _norm_int_min1(self, entry: ttk.Entry):
        txt = (entry.get() or "").strip()
        try:
            n = int(float(txt))
        except Exception:
            n = 1
        n = max(1, n)
        entry.delete(0, tk.END)
        entry.insert(0, str(n))

    def _norm_pressure(self):
        txt = (self.ent_ps.get() or "").strip()
        try:
            v = float(txt)
        except Exception:
            v = 0.0
        v = clamp(round(v, 1), 0.0, MAX_PRES)
        self.ent_ps.delete(0, tk.END)
        self.ent_ps.insert(0, f"{v:.1f}")

    def _norm_sp(self, entry: ttk.Entry):
        txt = (entry.get() or "").strip()
        try:
            n = int(float(txt))
        except Exception:
            n = 0
        n = clamp(n, 0, MAX_SP)
        entry.delete(0, tk.END)
        entry.insert(0, str(n))

    def _norm_flow(self, mfc_id: int):
        gas = self.mfc[mfc_id]["cmb"].get()
        lim = MFC_DEFAULTS[mfc_id][1][gas]
        ent = self.mfc[mfc_id]["ent"]
        txt = (ent.get() or "").strip()
        try:
            n = int(float(txt))
        except Exception:
            n = 0
        n = clamp(n, 0, lim)
        ent.delete(0, tk.END)
        ent.insert(0, str(n))

    # ---------- validación y recolección ----------
    def _int_or_zero(self, entry: ttk.Entry) -> int:
        txt = (entry.get() or "").strip()
        if not txt:
            return 0
        try:
            return int(float(txt))
        except Exception:
            return 0

    def _float_or_zero(self, entry: ttk.Entry) -> float:
        txt = (entry.get() or "").strip()
        if not txt:
            return 0.0
        try:
            return float(txt)
        except Exception:
            return 0.0

    def is_complete(self) -> bool:
        """
        Mínimos para considerar la etapa "lista":
          - tmin > 0
          - tiempos A y B > 0
          - si peri ON => su tiempo > 0
        """
        tmin = self._int_or_zero(self.ent_tmin)
        ta = self._int_or_zero(self.ent_ta)
        tb = self._int_or_zero(self.ent_tb)
        if tmin <= 0 or ta <= 0 or tb <= 0:
            return False
        if self.peri1_on.get() and self._int_or_zero(self.ent_p1_t) <= 0:
            return False
        if self.peri2_on.get() and self._int_or_zero(self.ent_p2_t) <= 0:
            return False
        return True

    def collect_payload(self, idx_etapa: int) -> dict:
        """
        Devuelve un dict con todos los datos normalizados:
          - tmin, pos_ini (1=A,2=B), ta, tb
          - ps10 (int, presión*10 con tope 20.0)
          - p1_on, p1_t, p2_on, p2_t
          - mfc1..mfc4: PWM (0..255)
          - t1_sp, t2_sp
        """
        # Tiempos (clamp en UI ya hecho por normalizadores)
        tmin = clamp(self._int_or_zero(self.ent_tmin), 1, 10**6)
        ta = clamp(self._int_or_zero(self.ent_ta), 1, 10**6)
        tb = clamp(self._int_or_zero(self.ent_tb), 1, 10**6)

        # Posición inicial
        pos_ini = 1 if self.cmb_pos_ini.get().strip().upper() == "A" else 2

        # Presión -> entero x10
        ps = clamp(round(self._float_or_zero(self.ent_ps), 1), 0.0, MAX_PRES)
        ps10 = int(round(ps * 10))

        # Peristálticas
        p1_on = 1 if self.peri1_on.get() else 0
        p2_on = 1 if self.peri2_on.get() else 0
        p1_t = clamp(self._int_or_zero(self.ent_p1_t), 1, 10**6) if p1_on else 0
        p2_t = clamp(self._int_or_zero(self.ent_p2_t), 1, 10**6) if p2_on else 0

        # MFCs -> PWM
        mfc_pwm = {}
        for mfc_id in (1, 2, 3, 4):
            gas = self.mfc[mfc_id]["cmb"].get()
            lim = MFC_DEFAULTS[mfc_id][1][gas]
            flujo = clamp(self._int_or_zero(self.mfc[mfc_id]["ent"]), 0, lim)
            mfc_pwm[mfc_id] = flujo_a_pwm(flujo, lim)

        # Temperatura (SP entero, clamp)
        t1_sp = clamp(self._int_or_zero(self.ent_t1_sp), 0, MAX_SP)
        t2_sp = clamp(self._int_or_zero(self.ent_t2_sp), 0, MAX_SP)

        return {
            "i": idx_etapa,
            "tmin": tmin,
            "pos_ini": pos_ini,
            "ta": ta,
            "tb": tb,
            "ps10": ps10,
            "p1_on": p1_on, "p1_t": p1_t,
            "p2_on": p2_on, "p2_t": p2_t,
            "mfc1": mfc_pwm[1], "mfc2": mfc_pwm[2],
            "mfc3": mfc_pwm[3], "mfc4": mfc_pwm[4],
            "t1_sp": t1_sp, "t2_sp": t2_sp,
        }


# =========================== Ventana Auto ===============================

class VentanaAuto(tk.Frame):
    """
    Ventana de automatización con:
      - Barra de navegación (izquierda)
      - 6 etapas en acordeón con scroll vertical (derecha)
      - Controles: Validar, Iniciar, Pausar, Reanudar, Detener, Guardar/Cargar preset,
                   Colapsar/Expandir todo
      - Monitor en vivo (etapa, posición, tiempos restantes, P1/P2)

    Ejecución:
      - Recorre sólo las etapas completas (en orden).
      - Al iniciar cada etapa, envía:
        $;4;POS_INI;PS*10;P1_ON;P2_ON;MFC1_PWM;MFC2_PWM;MFC3_PWM;MFC4_PWM;T1_SP;T2_SP;!
      - Alterna A↔B usando TA/TB de forma local (no se envían).
      - Peristálticas: si ON con tiempo, al finalizar se envía:
        $;3;6;0;2;!  (P1 OFF auto)
        $;3;7;0;2;!  (P2 OFF auto)
      - Contador 1 Hz con `after` (sin threads). Pausa/Reanuda/Detiene.
    """

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # estado de ejecución
        self._run_active = False
        self._paused = False
        self._tick_id = None

        # estado de etapa/segmento
        self._etapas_order = []      # índices 1..6 de etapas completas a ejecutar
        self._etapa_idx_ptr = -1     # puntero dentro de _etapas_order
        self._stage_remaining = 0    # seg restantes de la etapa actual
        self._seg_remaining = 0      # seg restantes del segmento actual (A o B)
        self._seg_pos = "A"          # "A" o "B"
        self._seg_tA = 0             # seg duración A
        self._seg_tB = 0             # seg duración B

        # timers de peristálticas por etapa
        self._p1_on = False
        self._p2_on = False
        self._p1_remaining = 0
        self._p2_remaining = 0
        self._p1_off_sent = False
        self._p2_off_sent = False

        self._build_ui()

    # ------------------------- UI base -------------------------
    def _build_ui(self):
        # columnas: 0 barra, 1 contenido
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra izquierda
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=230)
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        # Contenido (columna 1) con scroll
        content = ttk.Frame(self)
        content.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        content.grid_rowconfigure(1, weight=1)
        content.grid_columnconfigure(0, weight=1)

        # ------ fila 0: controles y monitor ------
        self._build_controls(content)
        self._build_monitor(content)

        # ------ fila 1: canvas con scroll y etapas ------
        canvas = tk.Canvas(content, highlightthickness=0)
        vsb = ttk.Scrollbar(content, orient="vertical", command=canvas.yview)
        self.stage_holder = ttk.Frame(canvas)

        self.stage_holder.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.stage_holder, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)

        canvas.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, sticky="ns")

        # Etapas 1..6 (acordeón) — INICIAN COLAPSADAS
        self.etapas = []
        for i in range(1, 7):
            etapa = EtapaAccordion(self.stage_holder, i)
            etapa.pack(fill="x", pady=4)
            self.etapas.append(etapa)
        self._set_all_collapsed(True)

    def _build_controls(self, parent):
        wrap = ttk.Frame(parent)
        wrap.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        wrap.grid_columnconfigure(7, weight=1)

        ttk.Button(wrap, text="Validar", command=self._cmd_validar).grid(row=0, column=0, padx=4)
        ttk.Button(wrap, text="Iniciar", command=self._cmd_iniciar).grid(row=0, column=1, padx=4)

        self.btn_pausar = ttk.Button(wrap, text="Pausar", command=self._cmd_pausar, state="disabled")
        self.btn_pausar.grid(row=0, column=2, padx=4)

        self.btn_reanudar = ttk.Button(wrap, text="Reanudar", command=self._cmd_reanudar, state="disabled")
        self.btn_reanudar.grid(row=0, column=3, padx=4)

        ttk.Button(wrap, text="Detener", command=self._cmd_detener).grid(row=0, column=4, padx=4)

        ttk.Button(wrap, text="Guardar preset", command=self._cmd_guardar_preset).grid(row=0, column=5, padx=10)
        ttk.Button(wrap, text="Cargar preset", command=self._cmd_cargar_preset).grid(row=0, column=6, padx=4)

        ttk.Button(wrap, text="Colapsar todo", command=lambda: self._set_all_collapsed(True))\
            .grid(row=0, column=8, padx=(20, 4))
        ttk.Button(wrap, text="Expandir todo", command=lambda: self._set_all_collapsed(False))\
            .grid(row=0, column=9, padx=4)

    def _build_monitor(self, parent):
        box = ttk.LabelFrame(parent, text="Monitor")
        box.grid(row=2, column=0, sticky="ew")

        self.var_mon_etapa = tk.StringVar(value="-")
        self.var_mon_pos = tk.StringVar(value="-")
        self.var_mon_rest_etapa = tk.StringVar(value="-")
        self.var_mon_rest_seg = tk.StringVar(value="-")
        self.var_mon_p1 = tk.StringVar(value="-")
        self.var_mon_p2 = tk.StringVar(value="-")

        ttk.Label(box, text="Etapa:").grid(row=0, column=0, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_etapa).grid(row=0, column=1, padx=2, pady=4, sticky="w")

        ttk.Label(box, text="Posición:").grid(row=0, column=2, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_pos).grid(row=0, column=3, padx=2, pady=4, sticky="w")

        ttk.Label(box, text="Restante etapa:").grid(row=0, column=4, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_rest_etapa).grid(row=0, column=5, padx=2, pady=4, sticky="w")

        ttk.Label(box, text="Restante segmento:").grid(row=0, column=6, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_rest_seg).grid(row=0, column=7, padx=2, pady=4, sticky="w")

        ttk.Label(box, text="P1:").grid(row=0, column=8, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_p1).grid(row=0, column=9, padx=2, pady=4, sticky="w")

        ttk.Label(box, text="P2:").grid(row=0, column=10, padx=6, pady=4, sticky="e")
        ttk.Label(box, textvariable=self.var_mon_p2).grid(row=0, column=11, padx=2, pady=4, sticky="w")

    # ------------------ acciones de barra superior ------------------

    def _set_all_collapsed(self, value: bool):
        for e in self.etapas:
            e.set_collapsed(value)

    def _cmd_validar(self):
        """Valida todas las etapas y resalta cuáles están incompletas (se ignorarán al iniciar)."""
        incompletas = [str(e.indice) for e in self.etapas if not e.is_complete()]
        if incompletas:
            messagebox.showwarning(
                "Validación",
                "Las siguientes etapas no están completas (se ignorarán al iniciar): "
                + ", ".join(incompletas)
            )
        else:
            messagebox.showinfo("Validación", "Todas las etapas están completas.")

    def _cmd_iniciar(self):
        """Construye la lista de etapas completas y arranca la ejecución (no bloqueante)."""
        if self._run_active:
            messagebox.showinfo("Auto", "El proceso ya está en ejecución.")
            return

        # recolectar etapas completas en orden
        self._etapas_order = [e.indice for e in self.etapas if e.is_complete()]
        if not self._etapas_order:
            messagebox.showerror("Auto", "No hay etapas completas para ejecutar.")
            return

        self._run_active = True
        self._paused = False
        self.btn_pausar.configure(state="normal")
        self.btn_reanudar.configure(state="disabled")

        self._etapa_idx_ptr = -1  # se avanzará a 0 en _iniciar_siguiente_etapa()
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
        """Cancela timers y limpia estado de ejecución."""
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

    # ------------------- ciclo por etapas/segmentos -------------------

    def _iniciar_siguiente_etapa(self):
        """Avanza al siguiente índice en _etapas_order y la inicia; si no hay, termina."""
        self._etapa_idx_ptr += 1
        if self._etapa_idx_ptr >= len(self._etapas_order):
            self._stop_all("Todas las etapas completas finalizaron.")
            return

        idx = self._etapas_order[self._etapa_idx_ptr]
        etapa = self.etapas[idx - 1]
        data = etapa.collect_payload(idx)

        # Configurar contadores de etapa
        self._stage_remaining = int(data["tmin"]) * 60
        self._seg_tA = int(data["ta"]) * 60
        self._seg_tB = int(data["tb"]) * 60
        self._seg_pos = "A" if data["pos_ini"] == 1 else "B"
        self._seg_remaining = self._seg_tA if self._seg_pos == "A" else self._seg_tB

        # Timers de peristálticas (solo locales, no viajan en el $;4)
        self._p1_on = bool(data["p1_on"])
        self._p2_on = bool(data["p2_on"])
        self._p1_remaining = int(data["p1_t"]) * 60 if self._p1_on else 0
        self._p2_remaining = int(data["p2_t"]) * 60 if self._p2_on else 0
        self._p1_off_sent = False
        self._p2_off_sent = False

        # Monitor inicial
        self.var_mon_etapa.set(f"{idx}/{len(self._etapas_order)}")
        self.var_mon_pos.set(self._seg_pos)
        self.var_mon_rest_etapa.set(mmss(self._stage_remaining))
        self.var_mon_rest_seg.set(mmss(self._seg_remaining))
        self.var_mon_p1.set("ON" if self._p1_on else "OFF")
        self.var_mon_p2.set("ON" if self._p2_on else "OFF")

        # 1) Enviar mensaje de etapa ($;4;...!) — SIN tiempos
        self._tx_etapa(data)

        # 2) Arrancar el loop de 1Hz
        if not self._paused:
            self._tick()

    def _tick(self):
        """Avanza 1 segundo: maneja cambio A↔B, peristálticas y fin de etapa."""
        if not self._run_active or self._paused:
            return

        # Fin de etapa -> siguiente
        if self._stage_remaining <= 0:
            self._iniciar_siguiente_etapa()
            return

        # Alternancia A/B local (no viaja por serial)
        if self._seg_remaining <= 0:
            self._seg_pos = "B" if self._seg_pos == "A" else "A"
            self._send_valve_position(self._seg_pos)
            self._seg_remaining = self._seg_tB if self._seg_pos == "B" else self._seg_tA

        # Timers de peristálticas locales -> auto OFF
        if self._p1_on and self._p1_remaining > 0:
            self._p1_remaining -= 1
            if self._p1_remaining <= 0 and not self._p1_off_sent:
                self._tx_peri_auto_off(6)  # ID=6
                self._p1_off_sent = True
                self._p1_on = False
                self.var_mon_p1.set("OFF")

        if self._p2_on and self._p2_remaining > 0:
            self._p2_remaining -= 1
            if self._p2_remaining <= 0 and not self._p2_off_sent:
                self._tx_peri_auto_off(7)  # ID=7
                self._p2_off_sent = True
                self._p2_on = False
                self.var_mon_p2.set("OFF")

        # Decrementos generales
        self._stage_remaining -= 1
        self._seg_remaining -= 1

        # Actualizar monitor
        self.var_mon_rest_etapa.set(mmss(self._stage_remaining))
        self.var_mon_rest_seg.set(mmss(self._seg_remaining))
        self.var_mon_pos.set(self._seg_pos)

        # Reprogramar próximo tick
        self._tick_id = self.after(1000, self._tick)

    # ----------------------- TX helpers -----------------------

    def _tx(self, mensaje: str):
        """Envía por el controlador si existe."""
        print("[TX]", mensaje)
        if self.controlador and hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    def _tx_etapa(self, d: dict):
        """
        Construye y envía (nuevo formato, sin tiempos):
        $;4;POS_INI;PS*10;P1_ON;P2_ON;MFC1_PWM;MFC2_PWM;MFC3_PWM;MFC4_PWM;T1_SP;T2_SP;!
        """
        partes = [
            "$;4",
            str(d["pos_ini"]), str(d["ps10"]),
            str(d["p1_on"]), str(d["p2_on"]),
            str(d["mfc1"]), str(d["mfc2"]), str(d["mfc3"]), str(d["mfc4"]),
            str(d["t1_sp"]), str(d["t2_sp"]),
        ]
        msg = ";".join(partes) + ";!"
        self._tx(msg)

    def _tx_peri_auto_off(self, peri_id: int):
        """Envía auto-OFF para la peristáltica indicada (6 o 7)."""
        if peri_id not in (6, 7):
            return
        self._tx(f"$;3;{peri_id};0;2;!")

    def _send_valve_position(self, pos: str):
        """Envía cambio de posición para V. entrada: $;3;1;0;POS;!   (POS: 1=A, 2=B)"""
        code = "1" if pos.upper() == "A" else "2"
        self._tx(f"$;3;1;0;{code};!")

    def _reset_monitor(self):
        self.var_mon_etapa.set("-")
        self.var_mon_pos.set("-")
        self.var_mon_rest_etapa.set("-")
        self.var_mon_rest_seg.set("-")
        self.var_mon_p1.set("-")
        self.var_mon_p2.set("-")

    # ----------------------- presets CSV -----------------------

    def _cmd_guardar_preset(self):
        """
        Guarda las 6 etapas al CSV. Formato: una fila por etapa con todas las columnas.
        Aunque algunas etapas no estén completas, se guardan sus valores actuales.
        """
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            title="Guardar preset"
        )
        if not path:
            return

        headers = [
            "i", "tmin", "pos_ini", "ta", "tb", "ps10", "p1_on", "p1_t", "p2_on", "p2_t",
            "mfc1_gas", "mfc1_flujo",
            "mfc2_gas", "mfc2_flujo",
            "mfc3_gas", "mfc3_flujo",
            "mfc4_gas", "mfc4_flujo",
            "t1_sp", "t2_sp"
        ]

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(headers)
                for e in self.etapas:
                    row = self._row_from_etapa_for_csv(e)
                    w.writerow(row)
            messagebox.showinfo("Preset", "Preset guardado correctamente.")
        except Exception as ex:
            messagebox.showerror("Preset", f"No se pudo guardar el preset:\n{ex}")

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
                        idx = int(row.get("i", "0"))
                    except Exception:
                        continue
                    if 1 <= idx <= 6:
                        self._apply_csv_row_to_etapa(self.etapas[idx - 1], row)
            messagebox.showinfo("Preset", "Preset cargado.")
        except Exception as ex:
            messagebox.showerror("Preset", f"No se pudo cargar el preset:\n{ex}")

    def _row_from_etapa_for_csv(self, e: EtapaAccordion):
        """Extrae valores amigables para CSV (sin PWM)."""
        def get_entry(ent: ttk.Entry, default="0"):
            v = (ent.get() or "").strip()
            return v if v else default

        tmin = get_entry(e.ent_tmin, "")
        pos_ini = "1" if e.cmb_pos_ini.get() == "A" else "2"
        ta = get_entry(e.ent_ta, "")
        tb = get_entry(e.ent_tb, "")

        # presión *10 (máx 20.0)
        try:
            ps = float((e.ent_ps.get() or "0").strip())
        except Exception:
            ps = 0.0
        ps = clamp(round(ps, 1), 0.0, MAX_PRES)
        ps10 = str(int(round(ps * 10)))

        # peri
        p1_on = "1" if e.peri1_on.get() else "0"
        p1_t = get_entry(e.ent_p1_t, "0") if e.peri1_on.get() else "0"
        p2_on = "1" if e.peri2_on.get() else "0"
        p2_t = get_entry(e.ent_p2_t, "0") if e.peri2_on.get() else "0"

        # mfc gas + flujo
        def gf(mid):
            gas = e.mfc[mid]["cmb"].get()
            flw = (e.mfc[mid]["ent"].get() or "0").strip() or "0"
            return gas, flw

        m1g, m1f = gf(1)
        m2g, m2f = gf(2)
        m3g, m3f = gf(3)
        m4g, m4f = gf(4)

        # temperatura
        t1_sp = get_entry(e.ent_t1_sp, "0")
        t2_sp = get_entry(e.ent_t2_sp, "0")

        return [
            str(e.indice), tmin, pos_ini, ta, tb, ps10, p1_on, p1_t, p2_on, p2_t,
            m1g, m1f, m2g, m2f, m3g, m3f, m4g, m4f,
            t1_sp, t2_sp
        ]

    def _apply_csv_row_to_etapa(self, e: EtapaAccordion, row: dict):
        """Vuelca una fila del CSV sobre la UI de la etapa (con clamps visuales)."""
        def set_entry(ent: ttk.Entry, val: str):
            ent.delete(0, tk.END)
            ent.insert(0, val or "")

        # básicos
        set_entry(e.ent_tmin, row.get("tmin", ""))
        e._norm_int_min1(e.ent_tmin)

        e.cmb_pos_ini.set("A" if row.get("pos_ini", "1") == "1" else "B")

        set_entry(e.ent_ta, row.get("ta", ""))
        e._norm_int_min1(e.ent_ta)

        set_entry(e.ent_tb, row.get("tb", ""))
        e._norm_int_min1(e.ent_tb)

        # presión (ps10 -> float con 1 decimal, máx 20.0)
        try:
            ps10 = int(row.get("ps10", "0"))
            ps = clamp(ps10 / 10.0, 0.0, MAX_PRES)
            set_entry(e.ent_ps, f"{ps:.1f}")
        except Exception:
            set_entry(e.ent_ps, "0.0")
        e._norm_pressure()

        # peristálticas
        e.peri1_on.set(row.get("p1_on", "0") == "1")
        e.peri2_on.set(row.get("p2_on", "0") == "1")
        e._update_peri_states()

        set_entry(e.ent_p1_t, row.get("p1_t", "0") if e.peri1_on.get() else "")
        if e.peri1_on.get():
            e._norm_int_min1(e.ent_p1_t)

        set_entry(e.ent_p2_t, row.get("p2_t", "0") if e.peri2_on.get() else "")
        if e.peri2_on.get():
            e._norm_int_min1(e.ent_p2_t)

        # MFCs
        for mid in (1, 2, 3, 4):
            gas_key = f"mfc{mid}_gas"
            flw_key = f"mfc{mid}_flujo"
            gas = row.get(gas_key, MFC_DEFAULTS[mid][0])
            if gas not in GASES:
                gas = MFC_DEFAULTS[mid][0]
            e.mfc[mid]["cmb"].set(gas)
            e._on_mfc_gas_change(mid, e.mfc[mid]["cmb"], e.mfc[mid]["lbl"])

            set_entry(e.mfc[mid]["ent"], row.get(flw_key, "0"))
            e._norm_flow(mid)

        # Temperatura
        set_entry(e.ent_t1_sp, row.get("t1_sp", "0"))
        e._norm_sp(e.ent_t1_sp)

        set_entry(e.ent_t2_sp, row.get("t2_sp", "0"))
        e._norm_sp(e.ent_t2_sp)
