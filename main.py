from gui.app import Aplicacion
import tkinter as tk

if __name__ == "__main__":
    app = Aplicacion()

    # (opcional) tu tamaño:
    app.geometry("1024x600+0+0")

    app.update_idletasks()

    def bring_front_and_focus():
        try:
            # 1) Traer al frente y tomar foco
            app.lift()
            app.focus_force()
            # 2) Pulso de topmost para vencer al compositor
            app.attributes("-topmost", True)
            app.after(150, lambda: app.attributes("-topmost", False))
            # 3) Mini "grab" temporal para que el primer tap sea tuyo
            app.grab_set()
            app.after(200, app.grab_release)
            # 4) Micro-movimiento para invalidar el click que "cae" en VS Code
            x, y = app.winfo_x(), app.winfo_y()
            app.geometry(f"+{x}+{y+1}")
            app.after(50, lambda: app.geometry(f"+{x}+{y}"))
        except Exception:
            pass

    # Ejecuta al mostrar la ventana y en el primer idle
    app.bind("<Map>", lambda e: app.after(10, bring_front_and_focus))
    app.after_idle(bring_front_and_focus)


    app.mainloop()
