"""
Ventana contenedora de dos PanelOmega (Omega 1 y Omega 2).

Cambios clave:
- Barra de navegación a la izquierda con ancho fijo coherente con el resto de la app.
- Dos paneles uniformes en columnas 1 y 2, usando `grid` sin `pack`.
- Comentarios y nombres clarificados; eliminación de tamaños rígidos innecesarios.
- Exposición de `paneles` por id_omega para ruteo desde la App.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .barra_navegacion import BarraNavegacion
from .panel_omega import PanelOmega


class VentanaOmega(tk.Frame):
    """Contenedor de dos paneles Omega con barra de navegación."""

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Registro para ruteo si el controlador mantiene un dict de ventanas
        if hasattr(self.controlador, "_ventanas"):
            self.controlador._ventanas["VentanaOmega"] = self

        self._construir_ui()

    def _construir_ui(self) -> None:
        # Fila principal expansible
        self.grid_rowconfigure(0, weight=1)

        # Columna 0 = barra; 1 y 2 = paneles uniformes y expansibles
        self.grid_columnconfigure(0, weight=0, minsize=140)
        self.grid_columnconfigure(1, weight=1, uniform="omega")
        self.grid_columnconfigure(2, weight=1, uniform="omega")

        # Barra de navegación
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="nsw")

        # Contenedor derecho con dos paneles Omega
        cont = ttk.Frame(self)
        cont.grid(row=0, column=1, columnspan=2, sticky="nsew", padx=8, pady=8)
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1, uniform="cols")
        cont.grid_columnconfigure(1, weight=1, uniform="cols")

        # Instanciación de paneles
        self.paneles: dict[int, PanelOmega] = {}
        p1 = PanelOmega(cont, id_omega=1, controlador=self.controlador, arduino=self.arduino)
        p2 = PanelOmega(cont, id_omega=2, controlador=self.controlador, arduino=self.arduino)
        p1.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        p2.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        self.paneles[1] = p1
        self.paneles[2] = p2

    # ------------------------------------------------------------------
    # API para la App (ruteo de datos desde el controlador)
    # ------------------------------------------------------------------
    def aplicar_estado_omegas(self, datos_omega1, datos_omega2) -> None:
        """Actualiza ambos paneles a partir de listas/tuplas con 7 elementos.
        Formato: [modo, sp, mem, svn, p, i, d]
        """
        if 1 in self.paneles and isinstance(datos_omega1, (list, tuple)) and len(datos_omega1) >= 7:
            self.paneles[1].cargar_desde_arduino(*datos_omega1[:7])
        if 2 in self.paneles and isinstance(datos_omega2, (list, tuple)) and len(datos_omega2) >= 7:
            self.paneles[2].cargar_desde_arduino(*datos_omega2[:7])

    def actualizar_parametros_omega(self, id_omega, svn, p, i, d) -> None:
        """Busca el PanelOmega por id y aplica parámetros recibidos."""
        try:
            idx = int(id_omega)
        except Exception:
            return
        panel = self.paneles.get(idx)
        if panel is not None and hasattr(panel, "aplicar_parametros"):
            panel.aplicar_parametros(svn, p, i, d)
