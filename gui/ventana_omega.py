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

        # [UI] Columna 0 con minsize fijo (no uses .configure(width) en la barra)
        self.grid_columnconfigure(0, weight=0, minsize=230)  # ancho fijo de barra
        self.grid_columnconfigure(1, weight=1, uniform="omega")  # panel 1
        self.grid_columnconfigure(2, weight=1, uniform="omega")  # panel 2

        # [UI] Tema/estilos base coherentes con el resto de la app (solo visual)
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass

        # [UI] Tokens de color (oscuro) – no afecta a lógica
        BG = "#0f172a"
        SURFACE = "#111827"
        TEXT = "#e5e7eb"
        BORDER = "#1f2937"

        # [UI] Fondo del contenedor y fuente general ligeramente mayor para táctil
        self.configure(background=BG)
        self.option_add("*Font", ("TkDefaultFont", 12))

        # [UI] Frame “panel” (wrapper) estilizado como tarjeta
        st.configure("OmegaPanel.TFrame", background=SURFACE)
        st.configure("Omega.TSeparator", background=BORDER)

        # Barra de navegacion (vertical a la izquierda)
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="nsw")
        self.grid_columnconfigure(0, minsize=BarraNavegacion.ANCHO)  # asegura mismo ancho


        # Tamano fijo del marco del panel (ajustar / pantalla 1280x800)
        PANEL_W = 280
        PANEL_H = 240

        self.paneles = {}  # <--- Guardamos referencias por id_omega

        # [UI] Tema y colores base
        st = ttk.Style(self)
        try: st.theme_use("clam")
        except: pass
        BG = "#0f172a"; SURFACE = "#111827"
        self.configure(background=BG)
        st.configure("OmegaWrapper.TFrame", background=SURFACE)

        # Wrapper 1
        wrapper1 = ttk.Frame(self, style="OmegaWrapper.TFrame", padding=(14,14))  # [UI]
        wrapper1.grid(row=0, column=1, padx=12, pady=12, sticky="nsew")           # [UI]
        wrapper1.grid_propagate(True)
        panel1 = PanelOmega(wrapper1, id_omega=1, controlador=self.controlador, arduino=self.arduino)
        panel1.pack(fill="both", expand=True)  # [UI]

        # Wrapper 2
        wrapper2 = ttk.Frame(self, style="OmegaWrapper.TFrame", padding=(14,14))  # [UI]
        wrapper2.grid(row=0, column=2, padx=12, pady=12, sticky="nsew")           # [UI]
        wrapper2.grid_propagate(True)
        panel2 = PanelOmega(wrapper2, id_omega=2, controlador=self.controlador, arduino=self.arduino)
        panel2.pack(fill="both", expand=True)  # [UI]

        # [UI] Forzar un repintado con estilos ya aplicados (evita parches claros al abrir)
        self.update_idletasks()
        self.after_idle(self.update_idletasks)

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
            idx = int(id_omega)
        except Exception:
            return
        panel = self.paneles.get(idx)

        if panel is not None and hasattr(panel, "aplicar_parametros"):
            panel.aplicar_parametros(svn, p, i, d)
