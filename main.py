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
    app.after(120, _show_after_withdraw)

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
    
    # --- Pantalla completa gestionada + "recordar volver a fullscreen" ---
    app.attributes("-fullscreen", True)   # sin barra de título
    app._want_fullscreen = True           # bandera de preferencia

    def _reapply_fullscreen(_=None):
        # Al restaurar desde la barra de tareas, vuelve a fullscreen si así se prefirió
        if getattr(app, "_want_fullscreen", False):
            app.after(50, lambda: app.attributes("-fullscreen", True))

    # Cuando reaparece o toma foco (tras minimizar/restaurar)
    app.bind("<Map>", _reapply_fullscreen, add="+")
    app.bind("<FocusIn>", _reapply_fullscreen, add="+")

    # (Opcional) salir de fullscreen con ESC, y NO volver automáticamente
    def _exit_fs(_=None):
        app._want_fullscreen = False
        app.attributes("-fullscreen", False)
    app.bind("<Escape>", _exit_fs)
    
    app.mainloop()
