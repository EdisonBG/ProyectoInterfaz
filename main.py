import tkinter as tk
from gui.app import Aplicacion

def _make_title_buttons_shield(root: tk.Tk, cluster_w: int = 160):
    """
    Crea un Toplevel invisible y sin bordes que se coloca encima del
    grupo de botones de la barra de título (lado derecho), bloqueando toques/clics.
    cluster_w: ancho aproximado (px) ocupado por [min, max, close].
    """

    # 1) calcular alto real de la barra de título (diferencia rooty - y)
    root.update_idletasks()
    title_h = root.winfo_rooty() - root.winfo_y()
    if title_h <= 0:
        title_h = 32  # heurística

    # 2) crear escudo
    shield = tk.Toplevel(root)
    shield.overrideredirect(True)          # sin bordes/decoro
    try:
        shield.attributes("-alpha", 0.01)  # casi invisible, pero clicable
    except Exception:
        pass
    try:
        shield.attributes("-topmost", True)
    except Exception:
        pass

    # 3) función para recolocar el escudo cuando la ventana cambie
    def _reposition(_=None):
        try:
            root.update_idletasks()
            # esquina sup. izquierda de la ventana en pantalla
            rx, ry = root.winfo_rootx(), root.winfo_rooty()
            rw, rh = root.winfo_width(), root.winfo_height()
            # escudo ocupa (cluster_w x title_h) en el extremo derecho
            x = rx + max(0, rw - cluster_w)
            y = ry
            shield.geometry(f"{cluster_w}x{title_h}+{x}+{y}")
            shield.lift()  # encima de la ventana
        except Exception:
            pass

    # 4) bloquear eventos de ratón/táctil sobre el escudo
    for seq in ("<ButtonPress-1>", "<ButtonRelease-1>", "<B1-Motion>",
                "<ButtonPress-2>", "<ButtonPress-3>", "<ButtonRelease-2>", "<ButtonRelease-3>"):
        shield.bind(seq, lambda e: "break")

    # 5) seguir a la ventana principal
    root.bind("<Configure>", _reposition, add="+")
    root.bind("<Map>", _reposition, add="+")
    root.bind("<FocusIn>", _reposition, add="+")
    _reposition()

    # 6) limpiar al cerrar
    def _cleanup():
        try:
            if shield.winfo_exists():
                shield.destroy()
        except Exception:
            pass
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", _cleanup)

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

    _make_title_buttons_shield(app, cluster_w=160)

    
    app.mainloop()
