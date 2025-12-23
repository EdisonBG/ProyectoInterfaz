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
    def __init__(self, parent, controlador, arduino=None):
        super().__init__(parent)
        self.controlador = controlador
        self.arduino = arduino

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
            font=("Calibri", 10, "bold"),
            padding=14,
            foreground="white",
            background="#081D66",
        )
        style.configure(
            "CerrarMenu.TButton",
            font=("Calibri", 10, "bold"),
            padding=14,
            foreground="white",
            background="#e74c3c",
        )
        style.map("BotonMenu.TButton", background=[('active', "#7F89AF"), ('pressed', "#7F89AF")])

        # Im�genes (opcionales)
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

        # Diccionario para guardar referencias a botones importantes
        self.botones = {}

        # Botones (incluye Registros SIN separadores)
        botones_def = [
            ("", self.img_home, "VentanaPrincipal", None, "home"),
            ("", self.img_mfc, "VentanaMfc", None, "mfc"),
            ("", self.img_omega, "VentanaOmega", None, "omega"),
            ("", self.img_valv, None, self._ir_a_valv_actualizada, "valv"),
            ("", self.img_auto, "VentanaAuto", None, "auto"),
            ("", self.img_graph, "VentanaGraph", None, "graph"),
            ("Cerrar", self.img_folder, None, self._cerrar_app, "cerrar"),
            ("Minimizar", self.img_folder, None, self._minimizar_app, "minimizar")
        ]

        for ro, (texto, imagen, destino, cmd_alt, clave) in enumerate(botones_def):
            cmd = (lambda d=destino: self.controlador.mostrar_ventana(d)) if destino else cmd_alt
            btn_style = "CerrarMenu.TButton" if texto == "Cerrar" else "BotonMenu.TButton"
            btn = ttk.Button(
                self,
                text=texto,
                image=imagen,
                compound="center" if imagen else "",
                style=btn_style,
                command=cmd,
            )
            btn.grid(row=ro, column=0, pady=5, sticky="ew")
            if imagen:
                btn.image = imagen  # evitar GC
            
            # Guardar referencia para botones importantes
            self.botones[clave] = btn

        if hasattr(self.controlador, 'registrar_barra_navegacion'):
            self.controlador.registrar_barra_navegacion(self)
            
        # Inicializar con el estado actual del modo especial
        if hasattr(self.controlador, 'modo_especial_activo'):
            self._actualizar_modo_especial(self.controlador.modo_especial_activo)
            
    def _cerrar_app(self):
        #Enviar mensaje antes de cerrar
        mensaje = "$7;0;2;0;!"
        print(f"[TX] cerrando app: {mensaje}")

        #Enviar a través del controlador
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

        #pausa para asegurar que se envie el mensaje
        self.after(100, self._real_cerrar_app)

    def _ir_a_valv_actualizada(self):
        """Cambia a VentanaValv y actualiza sus botones"""
        self.controlador.mostrar_ventana("VentanaValv")
        if hasattr(self.controlador, '_ventana_valv'):
            self.controlador._ventana_valv.actualizar_desde_csv()

    def _actualizar_modo_especial(self, modo_activo):
        """Actualiza el estado de los botones seg�n el modo especial"""
        # Solo deshabilitar el bot�n de Auto cuando el modo especial est� activo
        if 'auto' in self.botones:
            if modo_activo:
                self.botones['auto'].configure(state="disabled")
            else:
                self.botones['auto'].configure(state="normal")
        
        # El bot�n de v�lvulas SIEMPRE debe estar habilitado para poder ver el estado
        if 'valv' in self.botones:
            self.botones['valv'].configure(state="normal")

    def _real_cerrar_app(self):
        top = self.winfo_toplevel()
        try:
            top.destroy()
        except Exception:
            import tkinter as tk
            tk._default_root.destroy()
    
    def _minimizar_app(self):
        top = self.winfo_toplevel()
        # queremos volver en fullscreen cuando se restaure
        top._want_fullscreen = True
        try:
            top.attributes("-fullscreen", False)  # salir de fullscreen para que minimice normal
        except Exception:
            pass
        try:
            top.iconify()
        except Exception:
            pass
            