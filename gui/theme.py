"""
Tema ttk centralizado para la aplicación.

Responsabilidades:
- Aplicar escalado táctil global.
- Establecer colores base (fondos blancos, controles grises, texto negro).
- Configurar estilos ttk coherentes: TFrame, TLabel, TButton, TEntry, TCombobox.
- Mantener tamaños y paddings adecuados para interacción táctil.

Este módulo no crea widgets; solo define apariencia y métricas base.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.constants import (
    TK_SCALING,
    FONT_BASE,
    FONT_HEADING,
    BTN_PAD,
    ENTRY_PAD,
)

# Colores base
BG = "#FFFFFF"  # fondo blanco
FG = "#000000"  # texto negro
CTL = "#E0E0E0"  # controles grises
PR = "#D0D0D0"   # presionado/activo


def apply_theme(root: tk.Tk) -> None:
    """Aplica un tema ttk uniforme para entorno táctil.

    - Escalado global de Tk.
    - Tema ttk (clam) y estilos de widgets.
    - Fuentes Calibri.
    - Paddings y colores coherentes.
    """
    # Escalado táctil global
    try:
        root.tk.call("tk", "scaling", TK_SCALING)
    except Exception:
        pass

    # Fuente global
    try:
        root.option_add("*Font", f"{FONT_BASE[0]} {FONT_BASE[1]}")
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Fondo principal
    root.configure(bg=BG)

    # Estilos base
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG, padding=(6, 4))

    # Encabezados
    style.configure("Heading.TLabel", font=f"{FONT_HEADING[0]} {FONT_HEADING[1]}")

    # Botones
    style.configure(
        "TButton",
        background=CTL,
        foreground=FG,
        padding=BTN_PAD,
        relief="raised",
    )
    style.map("TButton", background=[("active", PR)])

    # Entry
    style.configure(
        "TEntry",
        fieldbackground=BG,
        padding=ENTRY_PAD,
        relief="solid",
    )

    # Combobox
    style.configure(
        "TCombobox",
        fieldbackground=BG,
        padding=(8, 8),
    )

    # Scrollbar (opcional: coherencia con esquema de grises)
    style.configure("TScrollbar", troughcolor=BG)
