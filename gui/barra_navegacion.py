import tkinter as tk
from tkinter import ttk
import os
from tkinter import PhotoImage
import sys
import subprocess


def _app_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class BarraNavegacion(ttk.Frame):
    def __init__(self, parent, controlador):
        super().__init__(parent)
        self.controlador = controlador

        # ancho fijo solicitado
        self.configure(width=149)
        self.grid_propagate(False)

        # Estilo botones
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "BotonMenu.TButton",
            font=("Arial", 10, "bold"),
            padding=5,
            foreground="white",
            background="#007acc",
        )
        style.configure(
            "CerrarMenu.TButton",
            font=("Arial", 10, "bold"),
            padding=5,
            foreground="white",
            background="#e74c3c",
        )

        # Imágenes (opcionales)
        img_path = os.path.join(_app_base_dir(), "img")
        def _img(name):
            p = os.path.join(img_path, name)
            return PhotoImage(file=p) if os.path.exists(p) else None

        self.img_home = _img("home.png")
        self.img_mfc = _img("mfc.png")
        self.img_omega = _img("omega.png")
        self.img_valv = _img("valv.png")
        self.img_auto = _img("auto.png")
        self.img_graph = _img("graph.png")
        self.img_folder = _img("folder.png")

        # Botones (incluye Registros SIN separadores)
        botones = [
            ("Home", self.img_home, "VentanaPrincipal", None),
            ("MFC", self.img_mfc, "VentanaMfc", None),
            ("Temp", self.img_omega, "VentanaOmega", None),
            ("Valv", self.img_valv, "VentanaValv", None),
            ("Auto", self.img_auto, "VentanaAuto", None),
            ("Graph", self.img_graph, "VentanaGraph", None),
            ("Registros", self.img_folder, None, self._abrir_carpeta_registros),
            ("Cerrar", self.img_folder, None, self._cerrar_app),
            ("Minimizar", self.img_folder, None, self._minimizar_app)
        ]

        for ro, (texto, imagen, destino, cmd_alt) in enumerate(botones):
            cmd = (lambda d=destino: self.controlador.mostrar_ventana(d)) if destino else cmd_alt
            btn_style = "CerrarMenu.TButton" if texto == "Cerrar" else "BotonMenu.TButton"
            btn = ttk.Button(
                self,
                text=texto,
                image=imagen,
                compound="top" if imagen else "",
                style=btn_style,
                command=cmd,
            )
            btn.grid(row=ro, column=0, pady=5, sticky="ew")
            if imagen:
                btn.image = imagen  # evitar GC

    def _abrir_carpeta_registros(self):
        reg_dir = os.path.join(_app_base_dir(), "registros_experimento")
        os.makedirs(reg_dir, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(reg_dir)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", reg_dir])
            else:
                subprocess.Popen(["xdg-open", reg_dir])
        except Exception as ex:
            import tkinter.messagebox as mb
            mb.showinfo("Registros",
                        f"Carpeta de registros:\n{reg_dir}\n\n(No se pudo abrir el explorador: {ex})")
    def _cerrar_app(self):
        top = self.winfo_toplevel()
        try:
            top.destroy()
        except Exception:
            import tkinter as tk
            tk._default_root.destroy()
    
    def _minimizar_app(self):
        top = self.winfo_toplevel()
        try: 
            top.overrideredirect(False)
            top.update_idletasks()
            try:
                top.iconify()            # Minimiza la ventana (deja ver el panel/menú)
            except Exception:
                top.state('iconic')
        except Exception:
            pass