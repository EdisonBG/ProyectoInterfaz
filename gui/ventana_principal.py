import tkinter as tk
from tkinter import ttk, PhotoImage
import os
from .barra_navegacion import BarraNavegacion


class VentanaPrincipal(tk.Frame):
    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Cargar imagenes
        img_path = os.path.join(os.path.dirname(__file__), "..", "img")
        self.img_equipo_off = PhotoImage(
            file=os.path.join(img_path, "equipo_off.png"))
        self.img_equipo_on = PhotoImage(
            file=os.path.join(img_path, "equipo_on.png"))

        self.estado_equipo_on = False  # para alternar texto del boton
        self.crear_widgets()

    def crear_widgets(self):
        # Layout raiz: barra fija (col 0), contenido expandible (col 1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=230)  # ancho fijo barra
        self.grid_columnconfigure(1, weight=1)

        # Barra de navegacion (vertical)
        BarraNavegacion(self, self.controlador).grid(
            row=0, column=0, sticky="ns", padx=0, pady=10)

        # Contenedor derecho
        cont = ttk.Frame(self)
        cont.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        cont.grid_rowconfigure(0, weight=1)   # area grafica crece
        cont.grid_columnconfigure(0, weight=1)

        # area grafica (fija en tamano, expandible visualmente)
        area_grafica = tk.Frame(cont, width=900, height=600, bg="white",
                                highlightthickness=1, highlightbackground="#ddd")
        area_grafica.grid(row=0, column=0, sticky="nsew")
        area_grafica.grid_propagate(False)

        # Imagen de equipo (estado inicial: apagado)
        self.equipo_label = tk.Label(
            area_grafica, image=self.img_equipo_off, bg="white", borderwidth=0)
        self.equipo_label.place(x=100, y=80)

        # Boton de estado (debajo del area grafica, en el contenedor derecho)
        self.boton_estado = ttk.Button(
            cont, text="Activar equipo", command=self.activar_equipo)
        self.boton_estado.grid(row=1, column=0, pady=(10, 0), sticky="w")

    def activar_equipo(self):
        self.estado_equipo_on = not self.estado_equipo_on
        # Cambiar imagen
        self.equipo_label.configure(
            image=self.img_equipo_on if self.estado_equipo_on else self.img_equipo_off)
        # Cambiar texto del boton
        self.boton_estado.configure(
            text="Desactivar equipo" if self.estado_equipo_on else "Activar equipo")
