import os
import tkinter as tk
from tkinter import ttk, PhotoImage
from .barra_navegacion import BarraNavegacion

# ========================= POSICIONES DE LOS LABELS =========================
# Editar estas coordenadas (x, y). Están en píxeles relativos al área de la imagen.
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
    "mfc_o2":            (120, 420),
    "mfc_co2":           (120, 460),
    "mfc_n2":            (120, 500),
    "mfc_h2":            (120, 540),
    "potencia_total":    (700, 500),
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
        }

        for key, (short, unit) in campos.items():
            v = tk.StringVar(value=f"{short}: -- {unit if unit!='HH:MM' else ''}".strip())
            self._vars[key] = v
            x, y = LABEL_POS.get(key, (10, 10))
            lbl = tk.Label(
                self.area_grafica, textvariable=v,
                bg="white", fg="#111", font=("Arial", 11, "bold"),
                relief="solid", bd=1, padx=6, pady=3
            )
            lbl.place(x=x, y=y)
            self._labels[key] = lbl

    # ---------------- RX -> actualización ----------------
    def aplicar_datos_cmd5(self, partes: list[str]):
        """
        Recibe la lista 'partes' sin $ ni ! ya splitteada por ';'.
        Esperado: partes[0] == "5" y len(partes) == 16.
        Orden:
          1: Tω1  2: Tω2  3: Th1 4: Th2 5: Tc1 6: Tc2
          7: Pmez*10 8: Ph2*10 9: Psal*10
          10: Q_O2 11: Q_CO2 12: Q_N2 13: Q_H2
          14: Potencia(W) 15: HorasEncendido(float)
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

        # Temps (°C, las muestro con 1 decimal)
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

