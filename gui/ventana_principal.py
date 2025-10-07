# gui/ventana_principal.py
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

# Imagen (Pillow opcional)
try:
    from PIL import Image, ImageTk
    PIL_OK = True
except Exception:
    PIL_OK = False

from .barra_navegacion import BarraNavegacion

# Constantes táctiles
try:
    from ui import constants as C
except Exception:
    class _C_:
        USABLE_WIDTH = 1024
        USABLE_HEIGHT = 530
        FONT_FAMILY = "Calibri"
        FONT_SIZE_BASE = 16
        FONT_SIZE_HEADING = 20
        FONT_BASE = (FONT_FAMILY, FONT_SIZE_BASE)
        FONT_HEADING = (FONT_FAMILY, FONT_SIZE_HEADING)
        GAP_X = 8
        GAP_Y = 8
    C = _C_()


class VentanaPrincipal(tk.Frame):
    """
    Ventana principal con:
    - Barra de navegación (izquierda).
    - Imagen de fondo (banner) redimensionada al contenedor.
    - Labels superpuestos (overlays) sobre la imagen, posicionados con .place(x, y).

    Notas:
    - Los overlays son tk.Label (no ttk) para controlar color de fondo/primer plano.
    - Existen helpers para crear/mover/actualizar overlays sin reescribir lógica.
    """

    # Ruta de la imagen por defecto (ajustar a la real). Se puede cambiar en tiempo de ejecución.
    DEFAULT_IMG = os.path.join(os.path.dirname(__file__), "img", "principal.png")

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Imagen y referencias
        self._img_path = self.DEFAULT_IMG
        self._img_tk = None  # mantener referencia para evitar GC

        # Overlays: nombre -> {"var": StringVar, "label": tk.Label, "x": int, "y": int, ...}
        self._overlays: dict[str, dict] = {}

        self._build_ui()
        self.after_idle(self._resize_banner)

        # Ejemplo de overlays iniciales (posiciones de muestra). Ajustar con .mover_overlay(...)
        # Se pueden borrar si no son necesarios.
        self.crear_overlay("Estado conexión", "Desconectado", x=40, y=40, font=C.FONT_HEADING, fg="#222", bg=None)
        self.crear_overlay("Puerto serie", "—", x=40, y=90, font=C.FONT_BASE, fg="#222", bg=None)
        self.crear_overlay("Versión SW", "—", x=40, y=130, font=C.FONT_BASE, fg="#222", bg=None)
        self.crear_overlay("Operador", "—", x=40, y=170, font=C.FONT_BASE, fg="#222", bg=None)
        self.crear_overlay("Fecha", "—", x=40, y=210, font=C.FONT_BASE, fg="#222", bg=None)
        self.crear_overlay("Hora", "—", x=40, y=250, font=C.FONT_BASE, fg="#222", bg=None)

    # ---------------------------------------------------------------------
    # Construcción de UI
    # ---------------------------------------------------------------------
    def _build_ui(self):
        # Rejilla principal: barra (col=0) + contenedor (col=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=140)
        self.grid_columnconfigure(1, weight=1)

        # Barra izquierda
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="nsw")

        # Contenedor derecho
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=C.GAP_X, pady=C.GAP_Y)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # Marco del banner (soporta <Configure> para redimensionar)
        self.banner_frame = ttk.Frame(right)
        self.banner_frame.grid(row=0, column=0, sticky="nsew")
        self.banner_frame.bind("<Configure>", lambda _e: self._resize_banner())

        # Label de fondo que contendrá la imagen
        # Se usa tk.Label para poder colocar hijos con .place() encima.
        self.lbl_fondo = tk.Label(self.banner_frame, bd=0, highlightthickness=0)
        self.lbl_fondo.place(relx=0, rely=0, relwidth=1, relheight=1)  # ocupa todo el frame

    # ---------------------------------------------------------------------
    # Imagen/banner
    # ---------------------------------------------------------------------
    def _resize_banner(self):
        """Redimensiona la imagen al tamaño del contenedor, manteniendo relación y cubriendo el área."""
        if not PIL_OK:
            # Placeholder cuando Pillow no está instalado
            self.lbl_fondo.configure(
                text="(Instalar Pillow para mostrar imagen)\n`pip install pillow`",
                font=C.FONT_BASE, anchor="center", bg="#f0f0f0"
            )
            return

        self.update_idletasks()
        w = max(1, self.banner_frame.winfo_width())
        h = max(1, self.banner_frame.winfo_height())

        if not os.path.exists(self._img_path):
            # Placeholder si no existe imagen
            from PIL import Image, ImageTk, ImageDraw
            img = Image.new("RGB", (w, h), color=(240, 240, 240))
            drw = ImageDraw.Draw(img)
            drw.text((10, 10), "Sin imagen principal", fill=(80, 80, 80))
            self._img_tk = ImageTk.PhotoImage(img)
            self.lbl_fondo.configure(image=self._img_tk, text="")
            return

        # Redimensionado tipo "cover": llena el contenedor (recorta lados si hace falta)
        try:
            from PIL import Image, ImageTk
            with Image.open(self._img_path) as im:
                im = im.convert("RGB")
                im_ratio = im.width / im.height
                frame_ratio = w / h

                if frame_ratio > im_ratio:
                    # contenedor más ancho -> altura define; escalar por alto, recortar ancho
                    new_h = h
                    new_w = int(h * im_ratio)
                else:
                    # contenedor más alto -> ancho define; escalar por ancho, recortar alto
                    new_w = w
                    new_h = int(w / im_ratio)

                im = im.resize((new_w, new_h), Image.LANCZOS)

                # Pegar centrado en un lienzo del tamaño del frame
                canvas = Image.new("RGB", (w, h), (255, 255, 255))
                off_x = (w - new_w) // 2
                off_y = (h - new_h) // 2
                canvas.paste(im, (off_x, off_y))

                self._img_tk = ImageTk.PhotoImage(canvas)
                self.lbl_fondo.configure(image=self._img_tk, text="", bg="#ffffff")
        except Exception:
            # Fallback simple (stretch)
            self._simple_fit(w, h)

    def _simple_fit(self, w: int, h: int):
        """Ajuste de imagen simple sin recorte (relleno blanco)."""
        if not PIL_OK or not os.path.exists(self._img_path):
            self.lbl_fondo.configure(text="(Imagen no disponible)", font=C.FONT_BASE, bg="#f0f0f0")
            return
        from PIL import Image, ImageTk
        try:
            with Image.open(self._img_path) as im:
                im = im.convert("RGB")
                im = im.resize((w, h), Image.LANCZOS)
                self._img_tk = ImageTk.PhotoImage(im)
                self.lbl_fondo.configure(image=self._img_tk, text="", bg="#ffffff")
        except Exception:
            self.lbl_fondo.configure(text="(Error cargando imagen)", font=C.FONT_BASE, bg="#f0f0f0")

    # ---------------------------------------------------------------------
    # Overlays (labels superpuestos)
    # ---------------------------------------------------------------------
    def crear_overlay(self, nombre: str, texto: str, *, x: int = 0, y: int = 0,
                      font=None, fg: str = "#000", bg: str | None = None, anchor: str = "nw") -> None:
        """
        Crea un overlay si no existe; en caso contrario solo actualiza texto y posición.
        - nombre: clave identificadora única.
        - texto: valor inicial a mostrar.
        - x, y: posición absoluta en píxeles dentro de banner_frame.
        - font: tupla Tk (familia, tamaño[, estilo]); por defecto C.FONT_BASE.
        - fg: color de texto (hex o nombre).
        - bg: color de fondo del label; si None, usa fondo "transparente" lógico (igual al del contenedor).
        - anchor: ancla del label respecto a (x, y) ("nw", "center", etc.).
        """
        if font is None:
            font = getattr(C, "FONT_BASE", ("Calibri", 16))

        if nombre in self._overlays:
            self.set_overlay(nombre, texto)
            self.mover_overlay(nombre, x, y, anchor=anchor)
            return

        # tk.Label para manejar colores fácilmente sobre imagen
        lbl = tk.Label(self.banner_frame, text=texto, font=font, fg=fg,
                       bg=(bg if bg is not None else self.lbl_fondo.cget("bg")))
        lbl.place(x=x, y=y, anchor=anchor)

        var = tk.StringVar(value=texto)
        # Mantener var si se quiere enlazar en el futuro
        self._overlays[nombre] = {"var": var, "label": lbl, "x": x, "y": y, "anchor": anchor}

    def set_overlay(self, nombre: str, texto: str) -> None:
        """Actualiza el texto de un overlay existente. Si no existe, no hace nada."""
        info = self._overlays.get(nombre)
        if not info:
            return
        lbl: tk.Label = info["label"]
        lbl.configure(text=str(texto))
        info["var"].set(str(texto))

    def mover_overlay(self, nombre: str, x: int, y: int, *, anchor: str | None = None) -> None:
        """Mueve el overlay a (x, y). Permite cambiar anchor."""
        info = self._overlays.get(nombre)
        if not info:
            return
        lbl: tk.Label = info["label"]
        if anchor is None:
            anchor = info.get("anchor", "nw")
        lbl.place_configure(x=int(x), y=int(y), anchor=anchor)
        info["x"], info["y"], info["anchor"] = int(x), int(y), anchor

    def set_overlays(self, data: dict[str, str]) -> None:
        """Actualiza múltiples overlays: {nombre: texto}."""
        if not data:
            return
        for k, v in data.items():
            self.set_overlay(k, v)

    def borrar_overlay(self, nombre: str) -> None:
        """Elimina un overlay por nombre."""
        info = self._overlays.pop(nombre, None)
        if info:
            try:
                info["label"].destroy()
            except Exception:
                pass

    def limpiar_overlays(self) -> None:
        """Elimina todos los overlays."""
        for info in self._overlays.values():
            try:
                info["label"].destroy()
            except Exception:
                pass
        self._overlays.clear()

    # ---------------------------------------------------------------------
    # API pública sugerida (para otras partes de la app)
    # ---------------------------------------------------------------------
    def set_img_path(self, path: str) -> None:
        """Cambia la imagen de fondo y fuerza redimensionado."""
        if path and os.path.exists(path):
            self._img_path = path
            self._resize_banner()

    # Ejemplos de uso desde la App (no obligatorio):
    # vp = controlador._ventanas.get("VentanaPrincipal")
    # if vp:
    #     vp.set_overlay("Estado conexión", "Conectado")
    #     vp.mover_overlay("Estado conexión", 60, 60)
    #     vp.set_overlays({"Fecha": "2025-10-03", "Hora": "14:25"})
