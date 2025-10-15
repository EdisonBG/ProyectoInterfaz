# main.py

import tkinter as tk
from gui.app import Aplicacion

if __name__ == "__main__":
    app = Aplicacion()
    app.overrideredirect(True)  # <- quita la barra de título/bordes del sistema
    # (opcional) alguna geometría inicial:
    # app.geometry("1280x800+0+0")
    # (opcional) tecla para cerrar si no tienes botón de salir:
    # app.bind("<Escape>", lambda e: app.destroy())
    app.mainloop()