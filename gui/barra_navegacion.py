import tkinter as tk
from tkinter import ttk
import os
from tkinter import PhotoImage


class BarraNavegacion(ttk.Frame):
    def __init__(self, parent, controlador):
        super().__init__(parent)

        # Estilo de boton
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("BotonMenu.TButton",
                        font=("Arial", 10, "bold"),
                        padding=5,
                        foreground="white",
                        background="#007acc")

        # Ruta a imagenes
        img_path = os.path.join(os.path.dirname(__file__), "..", "img")
        self.img_home = PhotoImage(file=os.path.join(img_path, "home.png"))
        self.img_mfc = PhotoImage(file=os.path.join(img_path, "mfc.png"))
        self.img_omega = PhotoImage(file=os.path.join(img_path, "omega.png"))
        self.img_valv = PhotoImage(file=os.path.join(img_path, "valv.png"))
        self.img_auto = PhotoImage(file=os.path.join(img_path, "auto.png"))
        self.img_graph = PhotoImage(file=os.path.join(img_path, "graph.png"))

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
            btn = ttk.Button(self,
                             text=texto,
                             image=imagen,
                             compound="top" if imagen else "",
                             style="BotonMenu.TButton",
                             command=lambda d=destino: controlador.mostrar_ventana(d))
            btn.grid(row=ro, column=0, pady=5)

            # Referencia para evitar que la imagen sea eliminada
            if imagen:
                btn.image = imagen  # type: ignore[attr-defined]
