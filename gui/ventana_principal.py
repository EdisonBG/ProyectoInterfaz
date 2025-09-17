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

# ========================= FORMATEADORES =========================
def hhmm_from_hours(horas_float: float) -> str:
    try:
        total_min = int(float(horas_float) * 60)
    except Exception:
        total_min = 0
    h, m = divmod(total_min, 60)
    return f"{h:02d}:{m:02d}"


class VentanaPrincipal(tk.Frame):
    """
    Ventana principal de monitoreo:
      - Imagen de proceso como fondo (fija).
      - 15 labels tipo “chip” posicionados por .place() (coordenadas en LABEL_POS).
      - Actualización desde tramas CMD=5:
        $;5;Tomega1;Tomega2;Thorno1;Thorno2;Tcond1;Tcond2;Pmez*10;Ph2*10;Psal*10;
           Q_O2;Q_CO2;Q_N2;Q_H2;PotW;HorasOn;!
    """

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # registrar para ruteo (si tu app usa un dict _ventanas)
        if hasattr(self.controlador, "_ventanas"):
            self.controlador._ventanas["VentanaPrincipal"] = self

        # ======== Paleta / estilos sólo visuales (coherente con otras vistas) ========
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass

        self._BG       = "#0f172a"   # fondo app
        self._SURFACE  = "#111827"   # tarjetas / área gráfica
        self._BORDER   = "#334155"   # bordes
        self._TEXT     = "#e5e7eb"   # texto general
        self._MUTED    = "#9ca3af"   # texto suave

        # “Chips” por categoría (sólo UI)
        self._COLORS = {
            "temp":   ("#0ea5e9", "#082f49"),  # azul claro
            "pres":   ("#f59e0b", "#451a03"),  # ámbar
            "mfc":    ("#22c55e", "#052e16"),  # verde
            "power":  ("#a78bfa", "#2e1065"),  # violeta
            "time":   ("#f97316", "#431407"),  # naranja
        }

        # tipografía táctil ligeramente mayor
        self.option_add("*Font", ("TkDefaultFont", 12))
        self.option_add("*TLabel.Font", ("TkDefaultFont", 12))
        self.configure(bg=self._BG)

        # cargar imágenes
        img_path = os.path.join(os.path.dirname(__file__), "..", "img")
        fondo_file = os.path.join(img_path, "equipo_DFM.png")
        if not os.path.exists(fondo_file):
            fondo_file = os.path.join(img_path, "equipo_off.png")
        self.img_fondo = PhotoImage(file=fondo_file)

        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        # layout: barra izq fija, contenido der expandible
        self.grid_rowconfigure(0, weight=1)
        # Ancho uniforme de barra en TODAS las vistas
        self.grid_columnconfigure(0, weight=0, minsize=getattr(BarraNavegacion, "ANCHO", 230))
        self.grid_columnconfigure(1, weight=1)

        # barra navegación
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="nsw", padx=0, pady=10)

        # contenedor derecho
        cont = ttk.Frame(self)
        cont.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1)

        # Card que envuelve al área gráfica, con borde persistente
        card = tk.Frame(cont, bg=self._BG)
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)  # el cuerpo (row=1) es el que crece

        # Tira superior (header visual sutil)
        tk.Frame(card, bg=self._BORDER, height=2).grid(row=0, column=0, sticky="ew")

        # Marco con borde
        border = tk.Frame(card, bg=self._BORDER)
        border.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        border.grid_columnconfigure(0, weight=1)
        border.grid_rowconfigure(0, weight=1)

        # ---------- ÁREA GRÁFICA A PANTALLA COMPLETA ----------
        # SIN width/height fijos: que crezca al máximo
        self.area_grafica = tk.Frame(border, bg=self._SURFACE, highlightthickness=0)
        self.area_grafica.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        # permitir que reparta el espacio interno
        self.area_grafica.grid_rowconfigure(0, weight=1)
        self.area_grafica.grid_columnconfigure(0, weight=1)

        # Imagen de fondo (no escalada; la colocamos en 0,0)
        self.lbl_fondo = tk.Label(self.area_grafica, image=self.img_fondo,
                                  bg=self._SURFACE, borderwidth=0, anchor="nw")
        self.lbl_fondo.place(x=0, y=0)

        # Indicador del tamaño recomendado (esquina sup-izq)
        # Ojo: Tkinter no acepta colores con alfa; usamos negro opaco.
        self._size_hint = tk.Label(self.area_grafica, text="",
                                   bg="#000000", fg="white",
                                   font=("TkDefaultFont", 10, "bold"))
        self._size_hint.place(x=8, y=8)

        # crear labels de variables
        self._vars = {}
        self._labels = {}
        self._create_all_labels()

        # Reportar tamaño cuando se muestre y cada vez que cambie
        self.after(200, self._report_image_size)
        self.area_grafica.bind("<Configure>", lambda e: self._report_image_size())

    def _chip_style_for(self, key: str):
        """
        Devuelve (bg, fg, border) según el tipo de variable para mejorar legibilidad sobre el plano.
        """
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
            c_bg, c_txt = ("#e5e7eb", "#111827")  # neutro
        return c_bg, c_txt, "#0b1220"  # borde oscuro sutil

    def _create_all_labels(self):
        # Definición: clave -> (texto corto, unidad)
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

            # apariencia de “chip”
            bg, fg, br = self._chip_style_for(key)
            lbl = tk.Label(
                self.area_grafica, textvariable=v,
                bg=bg, fg=fg,
                font=("Arial", 11, "bold"),
                relief="solid", bd=1, highlightthickness=0,
                padx=8, pady=3
            )
            # Borde del chip un poco más oscuro
            lbl.configure(highlightbackground=br)
            lbl.place(x=x, y=y)
            self._labels[key] = lbl

    # ---------------- RX -> actualización ----------------
    def aplicar_datos_cmd5(self, partes: list[str]):
        """
        Recibe la lista 'partes' sin $ ni ! ya splitteada por ';'.
        Esperado: partes[0] == "5" y len(partes) == 16.
        """
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

        # Temps (°C, 1 decimal)
        t_omega1 = to_float(partes[1])
        t_omega2 = to_float(partes[2])
        t_h1     = to_float(partes[3])
        t_h2     = to_float(partes[4])
        t_c1     = to_float(partes[5])
        t_c2     = to_float(partes[6])

        # Presiones llegan *10
        p_mez    = to_float(partes[7]) / 10.0
        p_h2     = to_float(partes[8]) / 10.0
        p_out    = to_float(partes[9]) / 10.0

        # Flujos (mL/min)
        q_o2     = to_int(partes[10])
        q_co2    = to_int(partes[11])
        q_n2     = to_int(partes[12])
        q_h2     = to_int(partes[13])

        # Potencia (W)
        p_tot    = to_int(partes[14])

        # Horas (float) -> HH:MM
        hhmm     = hhmm_from_hours(partes[15])

        # volcamos en los StringVar
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

    # ---------- Indicador de tamaño de imagen recomendado ----------
    def _report_image_size(self):
        """
        Muestra e imprime el tamaño óptimo de imagen para que encaje sin escalado.
        """
        w = max(self.area_grafica.winfo_width(), 0)
        h = max(self.area_grafica.winfo_height(), 0)
        msg = f"Tamaño recomendado de imagen: {w} × {h}px"
        self._size_hint.config(text=msg)  # indicador en pantalla
        print("[Principal]", msg)         # y por consola
