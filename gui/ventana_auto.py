import tkinter as tk
from tkinter import ttk
from .barra_navegacion import BarraNavegacion


class VentanaAuto(tk.Frame):
    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino
        self.crear_widgets()

    def crear_widgets(self):

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Barra de navegacion en la parte superior
        BarraNavegacion(self, self.controlador).grid(row=0, column=0, pady=10)
