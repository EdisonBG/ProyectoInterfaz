import os
import tkinter as tk
from tkinter import ttk, PhotoImage
from .barra_navegacion import BarraNavegacion

# ========================= POSICIONES DE LOS LABELS =========================
LABEL_POS = {
    "temp_omega1":       (120,  60),
    "temp_omega2":       (120, 100),
    "temp_horno1":       (530, 140),
    "temp_horno2":       (530, 180),
    "temp_cond1":        (740,  80),
    "temp_cond2":        (740, 120),
    "presion_mezcla":    (260, 260),
    "presion_h2":        (260, 300),
    "presion_salida":    (260, 340),
    "mfc_o2":            (120, 420),
    "mfc_co2":           (120, 460),
    "mfc_n2":            (120, 500),
    "mfc_h2":            (120, 540),
    "potencia_total":    (700, 500),
    "tiempo_encendido":  (700, 540),
}

def hhmm_from_hours(horas_float: float) -> str:
    try:
        total_min = int(float(horas_float) * 60)
    except Exception:
        total_min = 0
    h, m = divmod(total_min, 60)
    return f"{h:02d}:{m:02d}"


class VentanaPrincipal(tk.Frame):
    """
    Ventana principal con Canvas:
      - Dibuja la imagen de fondo con create_image
      - Coloca los labels como ventanas del Canvas (create_window)
      - Evita problemas de stacking/ocultamiento
    """

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        if hasattr(self.controlador, "_ventanas"):
            self.controlador._ventanas["VentanaPrincipal"] = self

        # ===== Estilo coherente =====
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass

        self._BG       = "#0f172a"
        self._SURFACE  = "#111827"
        self._BORDER   = "#334155"
        self._TEXT     = "#e5e7eb"
        self._MUTED    = "#9ca3af"

        self._COLORS = {
            "temp":   ("#0ea5e9", "#082f49"),
            "pres":   ("#f59e0b", "#451a03"),
            "mfc":    ("#22c55e", "#052e16"),
            "power":  ("#a78bfa", "#2e1065"),
            "time":   ("#f97316", "#431407"),
        }

        self.option_add("*Font", ("TkDefaultFont", 12))
        self.option_add("*TLabel.Font", ("TkDefaultFont", 12))
        self.configure(bg=self._BG)

        # cargar imagen de fondo
        img_path = os.path.join(os.path.dirname(__file__), "..", "img")
        fondo_file = os.path.join(img_path, "equipo_DFM.png")
        if not os.path.exists(fondo_file):
            fondo_file = os.path.join(img_path, "equipo_off.png")
        self.img_fondo = PhotoImage(file=fondo_file)  # mantener referencia en self

        self._build_ui()

    def _build_ui(self):
        # layout
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=getattr(BarraNavegacion, "ANCHO", 230))
        self.grid_columnconfigure(1, weight=1)

        BarraNavegacion(self, self.controlador).grid(row=0, column=0, sticky="nsw", padx=0, pady=10)

        cont = ttk.Frame(self)
        cont.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1)

        # Card con borde
        card = tk.Frame(cont, bg=self._BG)
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)  # <— ¡ANTES estaba 0!

        tk.Frame(card, bg=self._BORDER, height=2).grid(row=0, column=0, sticky="ew")
        border = tk.Frame(card, bg=self._BORDER)
        border.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        border.grid_columnconfigure(0, weight=1)
        border.grid_rowconfigure(0, weight=1)

        # Área gráfica con CANVAS (ocupa todo)
        self.canvas = tk.Canvas(border, bg=self._SURFACE, highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)

        # Imagen de fondo
        self._bg_img_id = self.canvas.create_image(0, 0, image=self.img_fondo, anchor="nw")

        # Hint de tamaño (opcional)
        self._size_hint = tk.Label(self, text="", bg="#000000", fg="white", font=("TkDefaultFont", 10, "bold"))
        self._size_hint_win = self.canvas.create_window(8, 8, anchor="nw", window=self._size_hint)

        # Labels sobre el canvas
        self._vars = {}
        self._labels = {}
        self._label_windows = {}
        self._create_all_labels()

        # Actualiza hint
        self.after(200, self._report_image_size)
        self.canvas.bind("<Configure>", lambda e: self._report_image_size())


    def _chip_style_for(self, key: str):
        if key.startswith("temp_"):
            c_bg, c_txt = self._COLORS["temp"]
        elif key.startswith("presion_"):
            c_bg, c_txt = self._COLORS["pres"]
        elif key.startswith("mfc_"):
            c_bg, c_txt = self._COLORS["mfc"]
        elif key in ("potencia_total",):
            c_bg, c_txt = self._COLORS["power"]
        elif key in ("tiempo_encendido",):
            c_bg, c_txt = self._COLORS["time"]
        else:
            c_bg, c_txt = ("#e5e7eb", "#111827")
        return c_bg, c_txt, "#0b1220"

    def _create_all_labels(self):
        campos = {
            "temp_omega1":      ("Ω1",      "°C"),
            "temp_omega2":      ("Ω2",      "°C"),
            "temp_horno1":      ("H1",      "°C"),
            "temp_horno2":      ("H2",      "°C"),
            "temp_cond1":       ("Cond1",   "°C"),
            "temp_cond2":       ("Cond2",   "°C"),
            "presion_mezcla":   ("P Mez",   "bar"),
            "presion_h2":       ("P H2",    "bar"),
            "presion_salida":   ("P Out",   "bar"),
            "mfc_o2":           ("O2",      "mL/min"),
            "mfc_co2":          ("CO2",     "mL/min"),
            "mfc_n2":           ("N2",      "mL/min"),
            "mfc_h2":           ("H2",      "mL/min"),
            "potencia_total":   ("P Tot",   "W"),
            "tiempo_encendido": ("On",      "HH:MM"),
        }

        for key, (short, unit) in campos.items():
            v = tk.StringVar(value=f"{short}: -- {unit if unit!='HH:MM' else ''}".strip())
            self._vars[key] = v
            x, y = LABEL_POS.get(key, (10, 10))

            bg, fg, _ = self._chip_style_for(key)
            lbl = tk.Label(self.canvas, textvariable=v,
                           bg=bg, fg=fg,
                           font=("Arial", 11, "bold"),
                           relief="solid", bd=1, padx=8, pady=3, highlightthickness=0)
            # Colocar el label dentro del canvas
            win_id = self.canvas.create_window(x, y, anchor="nw", window=lbl)

            self._labels[key] = lbl
            self._label_windows[key] = win_id

    # ---------------- RX -> actualización ----------------
    def aplicar_datos_cmd5(self, partes: list[str]):
        if len(partes) < 16:
            return

        def to_float(s, default=0.0):
            try:
                return float(s)
            except Exception:
                return default

        def to_int(s, default=0):
            try:
                return int(float(s))
            except Exception:
                return default

        t_omega1 = to_float(partes[1])
        t_omega2 = to_float(partes[2])
        t_h1     = to_float(partes[3])
        t_h2     = to_float(partes[4])
        t_c1     = to_float(partes[5])
        t_c2     = to_float(partes[6])

        p_mez    = to_float(partes[7]) / 10.0
        p_h2     = to_float(partes[8]) / 10.0
        p_out    = to_float(partes[9]) / 10.0

        q_o2     = to_int(partes[10])
        q_co2    = to_int(partes[11])
        q_n2     = to_int(partes[12])
        q_h2     = to_int(partes[13])

        p_tot    = to_int(partes[14])
        hhmm     = hhmm_from_hours(partes[15])

        self._vars["temp_omega1"].set(f"Ω1: {t_omega1:.1f} °C")
        self._vars["temp_omega2"].set(f"Ω2: {t_omega2:.1f} °C")
        self._vars["temp_horno1"].set(f"H1: {t_h1:.1f} °C")
        self._vars["temp_horno2"].set(f"H2: {t_h2:.1f} °C")
        self._vars["temp_cond1"].set(f"Cond1: {t_c1:.1f} °C")
        self._vars["temp_cond2"].set(f"Cond2: {t_c2:.1f} °C")

        self._vars["presion_mezcla"].set(f"P Mez: {p_mez:.1f} bar")
        self._vars["presion_h2"].set(f"P H2: {p_h2:.1f} bar")
        self._vars["presion_salida"].set(f"P Out: {p_out:.1f} bar")

        self._vars["mfc_o2"].set(f"O2: {q_o2} mL/min")
        self._vars["mfc_co2"].set(f"CO2: {q_co2} mL/min")
        self._vars["mfc_n2"].set(f"N2: {q_n2} mL/min")
        self._vars["mfc_h2"].set(f"H2: {q_h2} mL/min")

        self._vars["potencia_total"].set(f"P Tot: {p_tot} W")
        self._vars["tiempo_encendido"].set(f"On: {hhmm}")

    def _report_image_size(self):
        w = max(self.canvas.winfo_width(), 0)
        h = max(self.canvas.winfo_height(), 0)
        msg = f"Tamaño recomendado de imagen: {w} × {h}px"
        self._size_hint.config(text=msg)
        # Mantener el hint arriba a la izquierda
        self.canvas.coords(self._size_hint_win, 8, 8)
        print("[Principal]", msg)

