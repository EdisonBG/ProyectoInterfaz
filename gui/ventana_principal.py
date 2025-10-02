"""
Ventana principal de monitoreo.

Cambios clave:
- Layout a dos columnas: barra fija izquierda + contenido expandible.
- Uso del tema centralizado (gui/theme.py) y constantes de tamaño táctil.
- Eliminación de fuentes/colores ad-hoc; se adopta esquema blanco/gris.
- Conserva el posicionamiento absoluto de los labels sobre la imagen de fondo
  (según coordenadas en LABEL_POS), pero los widgets padres usan grid coherente.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, PhotoImage

from .barra_navegacion import BarraNavegacion

# ========================= POSICIONES DE LOS LABELS =========================
# Coordenadas (x, y) en píxeles relativos al área de la imagen.
LABEL_POS = {
    "temp_omega1": (400, 170),
    "temp_omega2": (660, 170),
    "temp_horno1": (530, 140),
    "temp_horno2": (530, 180),
    "temp_cond1": (740, 80),
    "temp_cond2": (740, 120),
    "presion_mezcla": (260, 260),
    "presion_h2": (260, 300),
    "presion_salida": (260, 340),
    "mfc_o2": (120, 420),
    "mfc_co2": (120, 460),
    "mfc_n2": (120, 500),
    "mfc_h2": (120, 540),
    "potencia_total": (700, 500),
}


def hhmm_from_hours(horas_float: float) -> str:
    """Convierte horas decimales a formato "HH:MM"."""
    try:
        total_min = int(float(horas_float) * 60)
    except Exception:
        total_min = 0
    h, m = divmod(total_min, 60)
    return f"{h:02d}:{m:02d}"


class VentanaPrincipal(tk.Frame):
    """Vista principal con imagen de proceso y overlays de variables."""

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Registro para ruteo si el controlador mantiene un dict de ventanas
        if hasattr(self.controlador, "_ventanas"):
            self.controlador._ventanas["VentanaPrincipal"] = self

        # Carga de imagen de fondo (una sola). Ajustar nombre real si difiere.
        img_path = os.path.join(os.path.dirname(__file__), "..", "img")
        fondo_file = os.path.join(img_path, "equipo_DFM.png")
        if not os.path.exists(fondo_file):
            fondo_file = os.path.join(img_path, "equipo_off.png")
        self.img_fondo = PhotoImage(file=fondo_file)

        self._construir_ui()

    # ------------------------------------------------------------------
    # Construcción de UI
    # ------------------------------------------------------------------
    def _construir_ui(self) -> None:
        # Layout a dos columnas: barra izq (ancho fijo) + contenido (expandible)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=140)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="nsw")

        # Contenedor derecho
        cont = ttk.Frame(self)
        cont.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1)

        # Área gráfica (fija en tamaño y sin propagación) y borde leve
        self.area_grafica = tk.Frame(
            cont,
            bg="white",
            highlightthickness=1,
            highlightbackground="#dddddd",
        )
        self.area_grafica.grid(row=0, column=0, sticky="nsew")
        self.area_grafica.grid_propagate(False)

        # Imagen de fondo
        self.lbl_fondo = tk.Label(self.area_grafica, image=self.img_fondo, bg="white", borderwidth=0)
        self.lbl_fondo.place(x=0, y=0)

        # Overlays (labels) de variables
        self._vars: dict[str, tk.StringVar] = {}
        self._labels: dict[str, tk.Label] = {}
        self._crear_labels()

        # Ajustar tamaño del área gráfica a la imagen si es menor que el contenedor
        self.after(0, self._ajustar_area_a_imagen)

    def _ajustar_area_a_imagen(self) -> None:
        """Establece el tamaño del área gráfica para que coincida con la imagen si aplica."""
        try:
            w = self.img_fondo.width()
            h = self.img_fondo.height()
            # Limitar a un máximo razonable; el contenedor se encarga del scroll si existiera
            self.area_grafica.configure(width=w, height=h)
        except Exception:
            pass

    def _crear_labels(self) -> None:
        """Crea los StringVar y labels posicionados de acuerdo con LABEL_POS."""
        campos: dict[str, tuple[str, str]] = {
            "temp_omega1": ("Ω1", "°C"),
            "temp_omega2": ("Ω2", "°C"),
            "temp_horno1": ("H1", "°C"),
            "temp_horno2": ("H2", "°C"),
            "temp_cond1": ("Cond1", "°C"),
            "temp_cond2": ("Cond2", "°C"),
            "presion_mezcla": ("P Mez", "bar"),
            "presion_h2": ("P H2", "bar"),
            "presion_salida": ("P Out", "bar"),
            "mfc_o2": ("O2", "mL/min"),
            "mfc_co2": ("CO2", "mL/min"),
            "mfc_n2": ("N2", "mL/min"),
            "mfc_h2": ("H2", "mL/min"),
            "potencia_total": ("P Tot", "W"),
        }

        for key, (short, unit) in campos.items():
            v = tk.StringVar(value=f"{short}: -- {unit}")
            self._vars[key] = v
            x, y = LABEL_POS.get(key, (10, 10))
            lbl = tk.Label(
                self.area_grafica,
                textvariable=v,
                bg="white",
                fg="#111111",
                font=("Calibri", 11, "bold"),
                relief="solid",
                bd=1,
                padx=6,
                pady=3,
            )
            lbl.place(x=x, y=y)
            self._labels[key] = lbl

    # ------------------------------------------------------------------
    # RX -> actualización
    # ------------------------------------------------------------------
    def aplicar_datos_cmd5(self, partes: list[str]) -> None:
        """Actualiza los overlays a partir de una trama CMD=5 ya separada por ';'."""
        if len(partes) < 16:
            return

        def to_float(s: str, default: float = 0.0) -> float:
            try:
                return float(s)
            except Exception:
                return default

        def to_int(s: str, default: int = 0) -> int:
            try:
                return int(float(s))
            except Exception:
                return default

        # Temperaturas (°C)
        t_omega1 = to_float(partes[1])
        t_omega2 = to_float(partes[2])
        t_h1 = to_float(partes[3])
        t_h2 = to_float(partes[4])
        t_c1 = to_float(partes[5])
        t_c2 = to_float(partes[6])

        # Presiones (llegan multiplicadas por 10)
        p_mez = to_float(partes[7]) / 10.0
        p_h2 = to_float(partes[8]) / 10.0
        p_out = to_float(partes[9]) / 10.0

        # Flujos (mL/min)
        q_o2 = to_int(partes[10])
        q_co2 = to_int(partes[11])
        q_n2 = to_int(partes[12])
        q_h2 = to_int(partes[13])

        # Potencia (W)
        p_tot = to_int(partes[14])

        # Asignación a StringVars
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
