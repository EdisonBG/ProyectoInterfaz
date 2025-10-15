"""
Widgets reutilizables con tamaños táctiles y estilos consistentes.

Este módulo define pequeñas fábricas/clases que envuelven a ttk para
reducir repetición en las ventanas y mantener tamaños mínimos adecuados.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.constants import (
    BTN_MIN_W,
    BTN_MIN_H,
    ENTRY_MIN_W,
    ENTRY_MIN_H,
)


class TouchButton(ttk.Button):
    """Botón ttk con tamaño mínimo táctil.

    No fuerza un ancho/alto en píxeles (grid/pack deciden), pero aplica
    tamaños mínimos razonables para objetivos de toque. El ancho mínimo en
    caracteres ayuda a mantener botones suficientemente anchos con textos cortos.
    """

    def __init__(self, master: tk.Misc | None = None, **kwargs):
        text = kwargs.get("text", "")
        # width en caracteres: aproximación para mantener un ancho mínimo
        kwargs.setdefault("width", max(len(str(text)), BTN_MIN_W // 10))
        super().__init__(master, **kwargs)
        # Alto mínimo: usa grid/pack_propagate en contenedores si se requiere forzar
        self.bind("<Map>", self._ensure_min_height)

    def _ensure_min_height(self, _e: tk.Event) -> None:
        try:
            if self.winfo_height() < BTN_MIN_H:
                self.configure(takefocus=True)  # mejora accesibilidad
        except Exception:
            pass


class TouchEntry(ttk.Entry):
    """Entry ttk con tamaño mínimo táctil."""

    def __init__(self, master: tk.Misc | None = None, **kwargs):
        kwargs.setdefault("width", ENTRY_MIN_W)
        super().__init__(master, **kwargs)
        self.bind("<Map>", self._ensure_min_height)

    def _ensure_min_height(self, _e: tk.Event) -> None:
        try:
            if self.winfo_height() < ENTRY_MIN_H:
                # No hay una API directa para alto de Entry; se mantiene como heurística.
                self.configure(takefocus=True)
        except Exception:
            pass


class Section(ttk.Frame):
    """Contenedor con separación estándar para agrupar controles relacionados."""

    def __init__(self, master: tk.Misc | None = None, padding=(12, 12), **kwargs):
        super().__init__(master, padding=padding, **kwargs)
        self.columnconfigure(0, weight=1)


class LabeledEntryNum(ttk.Frame):
    """Par etiqueta + Entry numérico con tamaño táctil.

    - Presenta un Label a la izquierda y un TouchEntry a la derecha.
    - No depende del teclado numérico; use `bind_numeric` para enlazarlo
      externamente y evitar dependencias circulares.
    - Ejemplo de uso:
        campo = LabeledEntryNum(frame, "Flujo (mL/min):", width=10)
        campo.grid(row=0, column=0, columnspan=2, sticky="w")
        campo.bind_numeric(
            lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
            on_submit=lambda v: handler(v),
        )
        # Acceso al Entry real: campo.entry
    """

    def __init__(self, master: tk.Misc | None, label: str, width: int = 10,
                 label_font=None, entry_font=None, entry_ipady: int | None = None, **kwargs):
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        self.label = ttk.Label(self, text=label, font=label_font)  
        self.label.grid(row=0, column=0, padx=5, pady=5, sticky="e")

        self.entry = TouchEntry(self, width=width, font=entry_font)  
        self.entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        if entry_ipady is not None:
            self.entry.grid_configure(ipady=entry_ipady)

    def bind_numeric(self, opener, on_submit=None) -> None:
        """Asocia un abridor de teclado numérico externo.

        Parámetros:
            opener: callable(entry, on_submit) -> abre el teclado numérico.
            on_submit: callable(valor) -> callback al confirmar.
        """
        self.entry.bind("<Button-1>", lambda _e: opener(self.entry, on_submit))
