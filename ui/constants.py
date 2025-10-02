"""
Constantes de interfaz para unificar dimensiones, fuentes y tiempos.

Estas constantes permiten mantener una apariencia y tamaños coherentes
entre todas las ventanas y widgets, y facilitan ajustes globales
para pantallas táctiles.
"""

# Dimensiones del área útil de la ventana principal
USABLE_WIDTH: int = 1024
USABLE_HEIGHT: int = 530

# Escalado general de Tk para entorno táctil (afecta fuentes y métricas base)
TK_SCALING: float = 1.20

# Fuentes (se usa Calibri; si no está instalada, Tkinter caerá a la fuente por defecto)
FONT_FAMILY: str = "Calibri"
FONT_SIZE_BASE: int = 11
FONT_SIZE_HEADING: int = 14
FONT_BASE = (FONT_FAMILY, FONT_SIZE_BASE)
FONT_HEADING = (FONT_FAMILY, FONT_SIZE_HEADING)

# Espaciados
GAP_X: int = 8
GAP_Y: int = 8
PADDING_FRAME = (12, 12)

# Botones táctiles
BTN_PAD = (16, 12)   # padding interno (x, y)
BTN_MIN_W = 100      # ancho mínimo sugerido
BTN_MIN_H = 48       # alto mínimo para toque

# Entry táctil
ENTRY_PAD = (10, 10)
ENTRY_MIN_W = 16     # en caracteres (orientativo)
ENTRY_MIN_H = 44     # en píxeles (orientativo)

# Combobox táctil
COMBO_PAD = (8, 8)

# Temporizadores
POLL_MS: int = 50  # intervalo de sondeo para comunicación serie
