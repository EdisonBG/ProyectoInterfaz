# main.py
import platform
from gui.app import Aplicacion

def _setup_fullscreen(app: Aplicacion):
    """
    Arranca en pantalla completa en cualquier SO.
    - F11: toggle pantalla completa ON/OFF
    - ESC: salir de pantalla completa (en Windows deja la ventana maximizada)
    """
    so = platform.system().lower()

    # Arranque en pantalla completa (sin bordes)
    try:
        app.attributes("-fullscreen", True)
    except Exception:
        # Fallback: maximizar (por si algún WM no soporta -fullscreen)
        try:
            app.state("zoomed")  # en Windows
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

if __name__ == "__main__":
    app = Aplicacion()
    _setup_fullscreen(app)
    app.mainloop()
