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
        # Raíz: barra izquierda fija + contenedor de secciones
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=95)  # ancho fijo de la barra
        self.grid_columnconfigure(1, weight=1)

        # --- Estilo opcional para fondo gris continuo (solo si usas ttk Frames) ---
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        

        # Barra (NO uses bd/highlightthickness si es ttk.Frame)
        barra = BarraNavegacion(self, self.controlador)
        # nada de: barra.configure(bd=0, highlightthickness=0) -> rompe si es ttk
        barra.grid(row=0, column=0, sticky="nsw")
        

        # Contenedor a la derecha, igual que en MFC
        cont = ttk.Frame(self, style="Omega.TFrame")
        cont.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)

        # 1 fila x 2 columnas uniformes
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1, uniform="omega")
        cont.grid_columnconfigure(1, weight=1, uniform="omega")

        # Secciones con relieve (“cards”) – mismo layout, pero con borde
        section1 = ttk.Frame(cont, style="Omega.TFrame", borderwidth=2, relief="groove")
        section2 = ttk.Frame(cont, style="Omega.TFrame", borderwidth=2, relief="groove")
        section1.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=3)
        section2.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=3)

        # Permitir expansión de lo interno
        for s in (section1, section2):
            s.grid_rowconfigure(0, weight=1)
            s.grid_columnconfigure(0, weight=1)

        # Paneles Omega dentro de cada “card”
        self.paneles = {}
        panel1 = PanelOmega(section1, id_omega=1, controlador=self.controlador, arduino=self.arduino)
        panel2 = PanelOmega(section2, id_omega=2, controlador=self.controlador, arduino=self.arduino)

        # (Opcional) mismo estilo de fondo dentro del card si PanelOmega es ttk.Frame
        try:
            panel1.configure(style="Omega.TFrame")
            panel2.configure(style="Omega.TFrame")
        except Exception:
            pass  # si no aplica, ignora

        # Padding interno del card para que no pegue al borde
        panel1.pack(fill="both", expand=True, padx=10, pady=10)
        panel2.pack(fill="both", expand=True, padx=10, pady=10)

        # Guardar referencias
        self.paneles[1] = panel1
        self.paneles[2] = panel2

    
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
            idx = int(id_omega)
        except Exception:
            return
        panel = self.paneles.get(idx)

        if panel is not None and hasattr(panel, "aplicar_parametros"):
            panel.aplicar_parametros(svn, p, i, d)
