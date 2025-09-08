import tkinter as tk
from tkinter import ttk
from .barra_navegacion import BarraNavegacion
from .panel_omega import PanelOmega


class VentanaOmega(tk.Frame):
    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino
        self.crear_widgets()

    def crear_widgets(self):
        # Fila principal expansible
        self.grid_rowconfigure(0, weight=1)

        # Columna 0 = barra fija; 1 y 2 = paneles expansibles y uniformes
        self.grid_columnconfigure(
            0, weight=0)     # ancho fijo de barra
        self.grid_columnconfigure(1, weight=1, uniform="omega")  # panel 1
        self.grid_columnconfigure(2, weight=1, uniform="omega")  # panel 2

        # Barra de navegacion (vertical a la izquierda)
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=230)
        barra.grid(row=0, column=0, sticky="nsw")       # <-- sin padding
        barra.grid_propagate(False)

        # Tamano fijo del marco del panel (ajustar / pantalla 1280x800)
        PANEL_W = 280
        PANEL_H = 240

        self.paneles = {}  # <--- Guardamos referencias por id_omega

        # Wrapper 1
        wrapper1 = tk.Frame(self, width=PANEL_W, height=PANEL_H)
        wrapper1.grid(row=0, column=1, padx=10, pady=10, sticky="n")
        wrapper1.grid_propagate(True)              # permitir crecer en alto

        panel1 = PanelOmega(wrapper1, id_omega=1,
                            controlador=self.controlador, arduino=self.arduino)
        panel1.pack()  # usa pack simple dentro del wrapper (o .grid, pero sin place)
        self.paneles[1] = panel1

        # Wrapper 2
        wrapper2 = tk.Frame(self, width=PANEL_W)
        wrapper2.grid(row=0, column=2, padx=10, pady=10, sticky="n")
        wrapper2.grid_propagate(True)

        panel2 = PanelOmega(wrapper2, id_omega=2,
                            controlador=self.controlador, arduino=self.arduino)
        panel2.pack()
        self.paneles[2] = panel2

        # --- Metodo llamado desde la App para volcar estados en los dos paneles ---
    def aplicar_estado_omegas(self, datos_omega1, datos_omega2):
        """
        datos_omegaX es una tupla/lista: [modo, sp, mem, svn, p, i, d]
        """
        if 1 in self.paneles and len(datos_omega1) >= 7:
            self.paneles[1].cargar_desde_arduino(*datos_omega1[:7])
        if 2 in self.paneles and len(datos_omega2) >= 7:
            self.paneles[2].cargar_desde_arduino(*datos_omega2[:7])

    def actualizar_parametros_omega(self, id_omega, svn, p, i, d):
        """
        Busca el PanelOmega por id_omega y aplica los parametros recibidos.
        """
        try:
            p = int(id_omega)
        except Exception:
            return
        panel = self.paneles.get(p)

        if panel is not None and hasattr(panel, "aplicar_parametros"):
            panel.aplicar_parametros(svn, p, i, d)
