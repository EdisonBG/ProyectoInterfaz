# main.py
import platform
import tkinter as tk
from gui.app import Aplicacion


def _setup_fullscreen(app: Aplicacion):
    """
    Arranca en pantalla completa en cualquier SO.
    - F11: toggle pantalla completa ON/OFF
    - ESC: salir de pantalla completa (en Windows deja la ventana maximizada)
    """
    so = platform.system().lower()

    # Arranque en pantalla completa (sin bordes si el WM lo soporta)
    try:
        app.attributes("-fullscreen", True)
    except Exception:
        # Fallback: maximizar (por si algún WM no soporta -fullscreen)
        try:
            app.state("zoomed")  # Windows
        except Exception:
            # Fallback genérico: ocupar toda la pantalla
            sw = app.winfo_screenwidth()
            sh = app.winfo_screenheight()
            app.geometry(f"{sw}x{sh}+0+0")

    def toggle_fullscreen(_e=None):
        try:
            current = bool(app.attributes("-fullscreen"))
        except Exception:
            current = False
        # Cambiar estado
        try:
            app.attributes("-fullscreen", not current)
        except Exception:
            pass
        # Si salimos de fullscreen en Windows, deja la ventana maximizada
        if so == "windows" and current:
            try:
                app.state("zoomed")
            except Exception:
                pass
        return "break"

    def exit_fullscreen(_e=None):
        try:
            app.attributes("-fullscreen", False)
        except Exception:
            pass
        # En Windows, al salir, mantener maximizado
        if so == "windows":
            try:
                app.state("zoomed")
            except Exception:
                pass
        return "break"

    # Atajos de teclado
    app.bind("<F11>", toggle_fullscreen)
    app.bind("<Escape>", exit_fullscreen)


def _setup_focus_sticky(app: Aplicacion):
    """
    Mantiene la ventana al frente y con foco. Útil en Raspberry para evitar
    que un toque en pantalla “salte” a otra app (p.ej., VS Code abierta detrás).
    No deja 'topmost' permanente para no interferir con diálogos.
    """
    def _bring_front():
        try:
            app.update_idletasks()
            app.lift()
            app.attributes("-topmost", True)
            # Forzar foco a la raíz; si usas Toplevels, podrías enfocarlos también
            app.focus_force()
            # Soltar 'topmost' tras un instante para no molestar a filedialogs, etc.
            app.after(300, lambda: app.attributes("-topmost", False))
        except Exception:
            pass

    # Primer “empujón” poco después de crear la ventana
    app.after(100, _bring_front)
    # Si el WM quita el foco, lo recuperamos suave
    app.bind("<FocusOut>", lambda _e: app.after(50, _bring_front))
    # También cuando la ventana vuelve a mostrarse
    app.bind("<Map>", lambda _e: app.after(50, _bring_front))


if __name__ == "__main__":
    app = Aplicacion()
    _setup_fullscreen(app)
    _setup_focus_sticky(app)
    app.mainloop()
