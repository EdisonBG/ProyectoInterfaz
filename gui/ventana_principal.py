import os
import tkinter as tk
from tkinter import ttk, PhotoImage
from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico
from .mfc_manager import mfc_gas_manager  # Importar el manager

# ========================= CONFIGURACIÓN DE FUENTE =========================
FUENTE_LABELS = ("Calibri", 15)  # Fuente modificable desde aquí
FUENTE_VALORES = ("Calibri", 15)

# ========================= POSICIONES DE LOS LABELS =========================
LABEL_POS = {
    "temp_omega1":       (400, 170),
    "temp_omega2":       (660, 170),
    "temp_horno1":       (530, 140),
    "temp_horno2":       (530, 180),
    "temp_cond1":        (740,  80),
    "temp_cond2":        (740, 120),
    "presion_mezcla":    (260, 260),
    "presion_h2":        (260, 300),
    "presion_salida":    (260, 340),
    # Posiciones para nombres MFC
    "mfc_o2_nombre":     (120, 420),
    "mfc_co2_nombre":    (120, 460),
    "mfc_n2_nombre":     (120, 500),
    "mfc_h2_nombre":     (120, 540),
    # Posiciones para valores MFC
    "mfc_o2_valor":      (160, 420),
    "mfc_co2_valor":     (160, 460),
    "mfc_n2_valor":      (160, 500),
    "mfc_h2_valor":      (160, 540),
    "potencia_horno1":    (700, 500),
    "potencia_horno2":    (500, 500),
}

# ========================= COLORES DE FONDO =========================
COLOR_LABELS = {
    "temp_omega1":      "#fac689",
    "temp_omega2":      "#fac689",
    "temp_horno1":      "#fac689",
    "temp_horno2":      "#fac689",
    "temp_cond1":       "#fac689",
    "temp_cond2":       "#fac689",
    "presion_mezcla":   "#dfe598",
    "presion_h2":       "#dfe598",
    "presion_salida":   "#dfe598",
    "mfc_o2_nombre":    "#90c6e5",
    "mfc_co2_nombre":   "#90c6e5",
    "mfc_n2_nombre":    "#90c6e5",
    "mfc_h2_nombre":    "#90c6e5",
    "mfc_o2_valor":     "#90c6e5",
    "mfc_co2_valor":    "#90c6e5",
    "mfc_n2_valor":     "#90c6e5",
    "mfc_h2_valor":     "#90c6e5",
    "potencia_horno1":   "#fce0bf",
    "potencia_horno2":   "#fce0bf",
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
      - 15 labels con fondo blanco, negrilla, tamaño medio, posicionados por .place() (coordenadas en LABEL_POS).
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

        # cargar imágenes
        img_path = os.path.join(os.path.dirname(__file__), "..", "img")
        # Usa una sola imagen (fondo). Ajusta el nombre a tu archivo real.
        fondo_file = os.path.join(img_path, "equipo_DFM.png")
        if not os.path.exists(fondo_file):
            # fallback por si no existe
            fondo_file = os.path.join(img_path, "equipo_off.png")
        self.img_fondo = PhotoImage(file=fondo_file)

        self._build_ui()

        self.after(100, lambda: TecladoNumerico(self))

        # Registrar callbacks para cambios de gas
        self._register_gas_callbacks()

    # ---------------- UI ----------------
    def _build_ui(self):
        # layout: barra izq fija, contenido der expandible
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=100)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=120)
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        # contenedor derecho
        cont = ttk.Frame(self)
        cont.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1)

        # área gráfica fija
        self.area_grafica = tk.Frame(
            cont, width=900, height=600, bg="white",
            highlightthickness=1, highlightbackground="#ddd"
        )
        self.area_grafica.grid(row=0, column=0, sticky="nsew")
        self.area_grafica.grid_propagate(False)

        # fondo con imagen
        self.lbl_fondo = tk.Label(self.area_grafica, image=self.img_fondo, bg="white", borderwidth=0)
        # ajusta la posición de la imagen dentro del área (x=0,y=0 la deja en la esquina)
        self.lbl_fondo.place(x=0, y=0)

        # crear labels de variables
        self._vars = {}
        self._labels = {}
        self._create_all_labels()

    def _register_gas_callbacks(self):
        """Registra las funciones callback para cambios de gas"""
        # Mapeo de MFC ID a clave de variable
        mfc_mapping = {
            1: "mfc_o2_nombre",
            2: "mfc_co2_nombre", 
            3: "mfc_n2_nombre",
            4: "mfc_h2_nombre"
        }
        
        def actualizar_gas_label(mfc_id, nuevo_gas):
            """Callback que actualiza el label cuando cambia el gas"""
            variable_key = mfc_mapping.get(mfc_id)
            if variable_key and hasattr(self, '_vars') and variable_key in self._vars:
                self._vars[variable_key].set(nuevo_gas)
        
        # Registrar callbacks para los 4 MFCs
        for mfc_id in range(1, 5):
            mfc_gas_manager.register_callback_ejecucion(mfc_id, actualizar_gas_label)

    def _create_all_labels(self):
        # Definición para variables normales
        campos_normales = {
            "temp_omega1":      ("Ω1",      "°C"),
            "temp_omega2":      ("Ω2",      "°C"),
            "temp_horno1":      ("H1",      "°C"),
            "temp_horno2":      ("H2",      "°C"),
            "temp_cond1":       ("Cond1",   "°C"),
            "temp_cond2":       ("Cond2",   "°C"),
            "presion_mezcla":   ("P Mez",   "bar"),
            "presion_h2":       ("P H2",    "bar"),
            "presion_salida":   ("P Out",   "bar"),
            "potencia_horno1":   ("P h1",   "W"),
            "potencia_horno2":   ("P h2",   "W"),
        }

        # Crear labels normales
        for key, (short, unit) in campos_normales.items():
            v = tk.StringVar(value=f"{short}: -- {unit}")
            self._vars[key] = v
            x, y = LABEL_POS.get(key, (10, 10))
            color_fondo = COLOR_LABELS.get(key, "white")
            
            lbl = tk.Label(
                self.area_grafica, textvariable=v,
                bg=color_fondo, fg="#111", font=FUENTE_LABELS,
                relief="solid", bd=1, padx=6, pady=3
            )
            lbl.place(x=x, y=y)
            self._labels[key] = lbl

        # Crear labels separados para MFC
        mfc_gases = {
            "mfc_o2": mfc_gas_manager.get_gas_en_ejecucion(1),  # Usar gases en ejecución
            "mfc_co2": mfc_gas_manager.get_gas_en_ejecucion(2),
            "mfc_n2": mfc_gas_manager.get_gas_en_ejecucion(3),
            "mfc_h2": mfc_gas_manager.get_gas_en_ejecucion(4)
        }

        for key, nombre_gas in mfc_gases.items():
            # Label para el nombre del gas
            v_nombre = tk.StringVar(value=nombre_gas)
            
            # Determinar MFC ID basado en la clave
            mfc_id = {"mfc_o2": 1, "mfc_co2": 2, "mfc_n2": 3, "mfc_h2": 4}[key]
            self._vars[f"{key}_nombre"] = v_nombre
            
            x_nombre, y_nombre = LABEL_POS.get(f"{key}_nombre", (10, 10))
            color_nombre = COLOR_LABELS.get(f"{key}_nombre", "#F0F8FF")
            
            lbl_nombre = tk.Label(
                self.area_grafica, textvariable=v_nombre,
                bg=color_nombre, fg="#111", font=FUENTE_LABELS,
                relief="solid", bd=1, padx=8, pady=3
            )
            lbl_nombre.place(x=x_nombre, y=y_nombre)
            self._labels[f"{key}_nombre"] = lbl_nombre

            #Label para el VALOR del MFC (flujo)
            texto_inicial = "--\nmL/min"
            x_valor, y_valor = LABEL_POS.get(f"{key}_valor", (160, 10))
            color_valor = COLOR_LABELS.get(f"{key}_valor", "#90c6e5")
            
            lbl_valor = tk.Label(
                self.area_grafica, text=texto_inicial,
                bg=color_valor, fg="#111", font=FUENTE_VALORES,
                relief="solid", bd=1, padx=4, pady=2,
                justify=tk.CENTER  # Para centrar el texto de las 2 líneas
            )
            lbl_valor.place(x=x_valor, y=y_valor)
            self._labels[f"{key}_valor"] = lbl_valor

    def aplicar_datos_cmd5(self, partes: list[str]):
        """
        Actualización de datos para el nuevo formato de MFC
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

        # Temps (°C)
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
        p_h1    = to_int(partes[14])
        p_h2    = to_int(partes[15])

        # Actualizar variables normales
        self._vars["temp_omega1"].set(f"Ω1: {t_omega1:.1f} °C")
        self._vars["temp_omega2"].set(f"Ω2: {t_omega2:.1f} °C")
        self._vars["temp_horno1"].set(f"H1: {t_h1:.1f} °C")
        self._vars["temp_horno2"].set(f"H2: {t_h2:.1f} °C")
        self._vars["temp_cond1"].set(f"Cond1: {t_c1:.1f} °C")
        self._vars["temp_cond2"].set(f"Cond2: {t_c2:.1f} °C")

        self._vars["presion_mezcla"].set(f"P Mez: {p_mez:.1f} bar")
        self._vars["presion_h2"].set(f"P H2: {p_h2:.1f} bar")
        self._vars["presion_salida"].set(f"P Out: {p_out:.1f} bar")

        # Actualizar MFC con formato vertical - directamente en el label
        self._labels["mfc_o2_valor"].config(text=f"{q_o2}\nmL/min")
        self._labels["mfc_co2_valor"].config(text=f"{q_co2}\nmL/min")
        self._labels["mfc_n2_valor"].config(text=f"{q_n2}\nmL/min")
        self._labels["mfc_h2_valor"].config(text=f"{q_h2}\nmL/min")

        self._vars["potencia_horno1"].set(f"P Tot: {p_h1} W")
        self._vars["potencia_horno2"].set(f"P Tot: {p_h2} W")