import tkinter as tk
from gui.app import Aplicacion

if __name__ == "__main__":
    app = Aplicacion()
    app.geometry("1024x600+0+0")  # si la usas

    # --- Solución anticlick-through (RPi Bookworm/Wayland) ---

    app.update_idletasks()

    def _ensure_front_and_focus():
        try:
            app.lift()
            app.focus_force()
            # pulso de topmost (True -> False) para vencer al compositor
            app.attributes("-topmost", True)
            app.after(120, lambda: app.attributes("-topmost", False))
        except Exception:
            pass

    # 1) Mostrar con pequeño retraso: VS Code suelta foco
    def _show_after_withdraw():
        try:
            app.deiconify()
        except Exception:
            pass
        _ensure_front_and_focus()

    # ocultar 150 ms y luego mostrar al frente
    try:
        app.withdraw()
    except Exception:
        pass
    app.after(150, _show_after_withdraw)

    # 2) Ciclo corto de refuerzos (durante ~1.2 s)
    def _focus_cycle(n=0):
        _ensure_front_and_focus()
        if n < 9:  # 10 intentos cada 120 ms
            app.after(120, lambda: _focus_cycle(n+1))
    app.after(160, _focus_cycle)

    # 3) Si el primer click llega demasiado pronto, lo “tragamos” y pedimos foco
    _first_click_done = {"v": False}
    def _swallow_until_focused(ev=None):
        if not _first_click_done["v"]:
            _ensure_front_and_focus()
            _first_click_done["v"] = True
            return "break"  # evita que ese primer click llegue a VS Code
    app.bind_all("<ButtonPress-1>", _swallow_until_focused, add="+")
    # también al map/idle por si el WM ignora el primero
    app.bind("<Map>", lambda e: app.after(10, _ensure_front_and_focus))
    app.after_idle(_ensure_front_and_focus)

    W, H = app.winfo_width(), app.winfo_height()
    app.resizable(True, True)  # puedes dejarlo True; igual vamos a forzar el tamaño

    _restoring = {"on": False}

    def _keep_size(evt=None):
        if _restoring["on"]:
            return
        cur_w, cur_h = app.winfo_width(), app.winfo_height()
        if cur_w != W or cur_h != H or app.state() != 'normal':
            _restoring["on"] = True
            try:
                # vuelve a estado normal y al tamaño deseado
                app.state('normal')
                app.geometry(f"{W}x{H}+{app.winfo_x()}+{app.winfo_y()}")
            finally:
                # pequeño delay evita bucles en Wayland
                app.after(50, lambda: _restoring.__setitem__("on", False))

    # Engancha cuando el WM intenta cambiar tamaño/estado
    app.bind("<Configure>", _keep_size)


    app.mainloop()
