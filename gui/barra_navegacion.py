import tkinter as tk
from tkinter import ttk
import os
from tkinter import PhotoImage


class BarraNavegacion(ttk.Frame):
    # Ancho uniforme para toda la app
    ANCHO = 170  # ajusta aquí una sola vez
     
    def __init__(self, parent, controlador):
        super().__init__(parent)

        # Estilo de boton
        style = ttk.Style(self)
        style.theme_use("clam")

        # [UI] ---- Tokens de color para sidebar y botones (iconos negros => botón claro) ----
        SIDEBAR_BG = "#0f172a"       # fondo barra (oscuro)
        BTN_BG = "#e5e7eb"           # fondo botón (claro)  <-- iconos negros resaltan
        BTN_BG_HOVER = "#d1d5db"     # hover más oscuro
        BTN_BG_PRESSED = "#cbd5e1"   # pressed
        BTN_FG = "#111827"           # texto oscuro sobre botón claro
        BTN_BORDER = "#374151"       # borde
        BTN_SELECTED = "#93c5fd"     # seleccionado (azul claro)
        BTN_SELECTED_HOVER = "#60a5fa"

        # [UI] Fondo de la barra y relleno
        self.configure(style="Sidebar.TFrame", padding=(10, 12))
        style.configure("Sidebar.TFrame", background=SIDEBAR_BG)

        # [UI] Botón con borde y relieve + colores claros para iconos negros
        style.configure(
            "BotonMenu.TButton",
            font=("Arial", 11, "bold"),   # tipografía un poquito mayor
            padding=(12, 10),
            foreground=BTN_FG,
            background=BTN_BG,
            relief="raised",
            borderwidth=2
        )
        style.map(
            "BotonMenu.TButton",
            background=[("active", BTN_BG_HOVER), ("pressed", BTN_BG_PRESSED)],
            relief=[("pressed", "sunken")]
        )

        # [UI] Variante “seleccionado” (por si luego quieres marcar la ventana activa)
        style.configure(
            "BotonMenuSelected.TButton",
            font=("Arial", 11, "bold"),
            padding=(12, 10),
            foreground=BTN_FG,
            background=BTN_SELECTED,
            relief="raised",
            borderwidth=2
        )
        style.map(
            "BotonMenuSelected.TButton",
            background=[("active", BTN_SELECTED_HOVER)],
            relief=[("pressed", "sunken")]
        )

        # Ruta a imagenes
        img_path = os.path.join(os.path.dirname(__file__), "..", "img")
        self.img_home = PhotoImage(file=os.path.join(img_path, "home.png"))
        self.img_mfc = PhotoImage(file=os.path.join(img_path, "mfc.png"))
        self.img_omega = PhotoImage(file=os.path.join(img_path, "omega.png"))
        self.img_valv = PhotoImage(file=os.path.join(img_path, "valv.png"))
        self.img_auto = PhotoImage(file=os.path.join(img_path, "auto.png"))
        self.img_graph = PhotoImage(file=os.path.join(img_path, "graph.png"))

        # [UI] La barra usa todo el alto y los botones se reparten el espacio vertical
        self.grid_columnconfigure(0, weight=1)

        # Botones
        botones = [
            ("Home", self.img_home, "VentanaPrincipal"),
            ("MFC", self.img_mfc, "VentanaMfc"),
            ("Temp", self.img_omega, "VentanaOmega"),
            ("Valv", self.img_valv, "VentanaValv"),
            ("Auto", self.img_auto, "VentanaAuto"),
            ("Graph", self.img_graph, "VentanaGraph"),
        ]

        for ro, (texto, imagen, destino) in enumerate(botones):
            # [UI] cada fila crece por igual para “llenar” de arriba a abajo
            self.grid_rowconfigure(ro, weight=1, uniform="menu")

            btn = ttk.Button(
                self,
                text=texto,
                image=imagen,
                compound="top" if imagen else "",
                style="BotonMenu.TButton",
                command=lambda d=destino: controlador.mostrar_ventana(d)
            )
            # [UI] el botón ocupa todo el ancho y alto de su celda (espacio vertical aprovechado)
            btn.grid(row=ro, column=0, padx=6, pady=6, sticky="nsew")

            # Referencia para evitar que la imagen sea eliminada
            if imagen:
                btn.image = imagen  # type: ignore[attr-defined]

        # [UI] Fila “espaciador”: asegura que, si hay más alto disponible, los botones se sigan estirando
        self.grid_rowconfigure(len(botones), weight=1, uniform="menu")

        # Fijar ancho y evitar que se compacte
        self.configure(width=self.ANCHO)
        self.grid_propagate(False)
