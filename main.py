# main.py

import tkinter as tk
from gui.app import Aplicacion

if __name__ == "__main__":
    app = Aplicacion()
    app.overrideredirect(True)  # <- quita la barra de título/bordes del sistema
    
    # cuando la ventana vuelve a mostrarse (deiconify), reactivar overrideredirect
    def _reapply_over(_e=None):
        # un pequeño delay evita parpadeos en algunos WMs
        app.after(50, lambda: app.overrideredirect(True))

    app.bind("<Map>", _reapply_over)
    
    app.mainloop()