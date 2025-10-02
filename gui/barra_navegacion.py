"""
Barra de navegación reutilizable para todas las ventanas de la aplicación.

Cambios clave:
- Uso de estilos/colores centralizados (tema en gui/theme.py).
- Botones táctiles con tamaños mínimos (usa TouchButton de ui.widgets).
- Eliminación de estilos ad-hoc (azules); se adopta esquema gris y fuente Calibri.
- Ancho fijo y no propagación de grid para estabilidad en 1024x530.
- Apertura de carpeta de registros multiplataforma con manejo de errores.
"""

from __future__ import annotations

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, PhotoImage

from ui.widgets import TouchButton


def _app_base_dir() -> str:
    """Devuelve la carpeta base de la aplicación (compatible con binarios congelados)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class BarraNavegacion(ttk.Frame):
    """Barra vertical con botones para navegar entre ventanas y acciones utilitarias."""

    def __init__(self, parent: tk.Misc, controlador) -> None:
        super().__init__(parent)
        self.controlador = controlador

        # Ancho fijo para garantizar layout estable en 1024x530
        self.configure(width=140)
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)

        # Carga perezosa de imágenes (opcionales)
        img_path = os.path.join(_app_base_dir(), "img")

        def _img(nombre: str) -> PhotoImage | None:
            ruta = os.path.join(img_path, nombre)
            return PhotoImage(file=ruta) if os.path.exists(ruta) else None

        self.img_home = _img("home.png")
        self.img_mfc = _img("mfc.png")
        self.img_omega = _img("omega.png")
        self.img_valv = _img("valv.png")
        self.img_auto = _img("auto.png")
        self.img_graph = _img("graph.png")
        self.img_folder = _img("folder.png")

        # Definición de botones: (texto, imagen, destino | None, comando alterno | None)
        botones: list[tuple[str, PhotoImage | None, str | None, callable | None]] = [
            ("Home", self.img_home, "VentanaPrincipal", None),
            ("MFC", self.img_mfc, "VentanaMfc", None),
            ("Temp", self.img_omega, "VentanaOmega", None),
            ("Valv", self.img_valv, "VentanaValv", None),
            ("Auto", self.img_auto, "VentanaAuto", None),
            ("Graph", self.img_graph, "VentanaGraph", None),
            ("Registros", self.img_folder, None, self._abrir_carpeta_registros),
        ]

        for i, (texto, imagen, destino, cmd_alt) in enumerate(botones):
            cmd = (lambda d=destino: self.controlador.mostrar_ventana(d)) if destino else cmd_alt
            btn = TouchButton(
                self,
                text=texto,
                image=imagen,
                compound="top" if imagen else "none",
                command=cmd,
                takefocus=True,
            )
            btn.grid(row=i, column=0, padx=6, pady=6, sticky="ew")
            if imagen is not None:
                btn.image = imagen  # evitar GC

        # Relleno inferior para ocupar alto total
        self.rowconfigure(len(botones), weight=1)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def _abrir_carpeta_registros(self) -> None:
        """Abre la carpeta de registros del experimento con el explorador del sistema."""
        reg_dir = os.path.join(_app_base_dir(), "registros_experimento")
        os.makedirs(reg_dir, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(reg_dir)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", reg_dir])
            else:
                subprocess.Popen(["xdg-open", reg_dir])
        except Exception as ex:
            import tkinter.messagebox as mb

            mb.showinfo(
                "Registros",
                f"Carpeta de registros:\n{reg_dir}\n\n(No se pudo abrir el explorador: {ex})",
            )
