from gui.app import Aplicacion
import tkinter as tk

if __name__ == "__main__":
    app = Aplicacion()

    # (opcional) tu tamaño:
    app.geometry("1024x600+0+0")

    # --- Traer al frente y tomar foco con “impulso” corto de topmost ---
    app.update_idletasks()
    app.lift()
    app.focus_force()
    app.attributes("-topmost", True)
    app.after(150, lambda: app.attributes("-topmost", False))  # suelta topmost

    # Por si el WM ignora el primer intento, repite al entrar al mapa/primer idle:
    def _ensure_front(_=None):
        app.lift()
        app.focus_force()
    app.bind("<Map>", _ensure_front)           # cuando la ventana se muestra
    app.after_idle(_ensure_front)              # al primer idle del loop

    app.mainloop()
