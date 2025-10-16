import tkinter as tk
from gui.app import Aplicacion

if __name__ == "__main__":
    app = Aplicacion()
    # app.geometry("1280x800+0+0")  # si la usas

    app.update_idletasks()

    def bring_front_and_focus():
        try:
            app.lift()
            app.focus_force()
            app.attributes("-topmost", True)
            app.after(150, lambda: app.attributes("-topmost", False))
            app.grab_set()
            app.after(200, app.grab_release)
            x, y = app.winfo_x(), app.winfo_y()
            app.geometry(f"+{x}+{y+1}")
            app.after(50, lambda: app.geometry(f"+{x}+{y}"))
        except Exception:
            pass

    # -- FIRST CLICK HOOK (aquí) --
    _first_click = {"done": False}
    def _take_focus_on_first_click(event=None):
        if not _first_click["done"]:
            bring_front_and_focus()
            _first_click["done"] = True

    # dispara al mostrar la ventana y en el primer idle
    app.bind("<Map>", lambda e: app.after(10, bring_front_and_focus))
    app.after_idle(bring_front_and_focus)

    # <<<<< ESTA ES LA LÍNEA CLAVE DEL "FIRST CLICK" >>>>>
    app.bind_all("<Button-1>", _take_focus_on_first_click, add="+")
    # ^ se puede quitar después si ya no lo necesitas

    app.mainloop()
