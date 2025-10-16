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

    # --- Wayland: neutralizar "Maximizar" sin quitar barra de título ---

    

    # Tamaño "bueno" (tu tamaño de pantalla/área útil en modo ventana)
    W0, H0 = app.winfo_width(), app.winfo_height()

    # Deja que el usuario pueda cerrar/minimizar normalmente
    app.resizable(True, True)  # No desactiva la barra; solo preparamos el antimax.

    # Guard para evitar bucles
    _restoring = {"on": False}

    def _restore_size_and_front():
        """Vuelve a tamaño normal y trae la ventana al frente (sin maximizar)."""
        try:
            app.state('normal')  # por si el WM puso 'zoomed'
        except Exception:
            pass
        # Restablece tamaño y posición actual (no tocamos X/Y salvo que quieras fijarlos)
        app.geometry(f"{W0}x{H0}+{app.winfo_x()}+{app.winfo_y()}")
        # Pulso topmost para vencer al compositor si el panel se superpone
        app.lift()
        app.attributes("-topmost", True)
        app.after(120, lambda: app.attributes("-topmost", False))

    def _anti_maximize(evt=None):
        # Si ya estamos restaurando, no reentrar
        if _restoring["on"]:
            return
        # Detecta intento del WM: estado 'zoomed' o tamaño distinto al fijo
        zoomed = (app.state() == 'zoomed')
        sizediff = (app.winfo_width() != W0 or app.winfo_height() != H0)
        if zoomed or sizediff:
            _restoring["on"] = True
            try:
                # pequeña espera ayuda a evitar “rebote” visual en Wayland
                app.after(30, _restore_size_and_front)
            finally:
                app.after(80, lambda: _restoring.__setitem__("on", False))

    # Engancha cuando el WM cambia estado/tamaño (clic en maximizar, tile, etc.)
    app.bind("<Configure>", _anti_maximize)


    app.mainloop()
