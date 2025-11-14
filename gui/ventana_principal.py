import os
import tkinter as tk
from tkinter import ttk, PhotoImage
from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico
from .mfc_manager import mfc_gas_manager  # Importar el manager
from PIL import Image, ImageTk  # Nuevo: Para manejar imágenes
from ui.widgets import TouchButton
import fitz  # PyMuPDF para manejar PDFs
import io

# Constantes táctiles (anchos/fuentes). Si no existen, usa valores por defecto.
try:
    from ui import constants as C
except Exception:
    class _C_:
        FONT_BASE = ("Calibri", 10)
    C = _C_()
    
# ========================= CONFIGURACIÓN DE FUENTE =========================
FUENTE_LABELS = ("Calibri", 15)  # Fuente modificable desde aquí
FUENTE_VALORES = ("Calibri", 15)

# ========================= POSICIONES DE LOS LABELS =========================
LABEL_POS = {
    "temp_omega1":       (400, 170),
    "temp_omega2":       (660, 170),
    "temp_horno1":       (530, 140),
    "temp_horno2":       (530, 180),
    "temp_cond1":        (740,  80),
    "temp_cond2":        (740, 120),
    "presion_mezcla":    (260, 260),
    "presion_h2":        (260, 300),
    "presion_salida":    (260, 340),
    # Posiciones para nombres MFC
    "mfc_o2_nombre":     (120, 420),
    "mfc_co2_nombre":    (120, 460),
    "mfc_n2_nombre":     (120, 500),
    "mfc_h2_nombre":     (120, 540),
    # Posiciones para valores MFC
    "mfc_o2_valor":      (160, 420),
    "mfc_co2_valor":     (160, 460),
    "mfc_n2_valor":      (160, 500),
    "mfc_h2_valor":      (160, 540),
    "potencia_horno1":    (700, 500),
    "potencia_horno2":    (500, 500),
}

# ========================= COLORES DE FONDO =========================
COLOR_LABELS = {
    "temp_omega1":      "#fac689",
    "temp_omega2":      "#fac689",
    "temp_horno1":      "#fac689",
    "temp_horno2":      "#fac689",
    "temp_cond1":       "#fac689",
    "temp_cond2":       "#fac689",
    "presion_mezcla":   "#dfe598",
    "presion_h2":       "#dfe598",
    "presion_salida":   "#dfe598",
    "mfc_o2_nombre":    "#90c6e5",
    "mfc_co2_nombre":   "#90c6e5",
    "mfc_n2_nombre":    "#90c6e5",
    "mfc_h2_nombre":    "#90c6e5",
    "mfc_o2_valor":     "#90c6e5",
    "mfc_co2_valor":    "#90c6e5",
    "mfc_n2_valor":     "#90c6e5",
    "mfc_h2_valor":     "#90c6e5",
    "potencia_horno1":   "#fce0bf",
    "potencia_horno2":   "#fce0bf",
}



    
# ========================= FORMATEADORES =========================
def hhmm_from_hours(horas_float: float) -> str:
    try:
        total_min = int(float(horas_float) * 60)
    except Exception:
        total_min = 0
    h, m = divmod(total_min, 60)
    return f"{h:02d}:{m:02d}"


class VentanaPrincipal(tk.Frame):
    """
    Ventana principal de monitoreo:
      - Imagen de proceso como fondo (fija).
      - 15 labels con fondo blanco, negrilla, tamaño medio, posicionados por .place() (coordenadas en LABEL_POS).
      - Actualización desde tramas CMD=5:
        $;5;Tomega1;Tomega2;Thorno1;Thorno2;Tcond1;Tcond2;Pmez*10;Ph2*10;Psal*10;
           Q_O2;Q_CO2;Q_N2;Q_H2;PotW;HorasOn;!
    """

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        self._configurar_estilos()
        # registrar para ruteo (si tu app usa un dict _ventanas)
        if hasattr(self.controlador, "_ventanas"):
            self.controlador._ventanas["VentanaPrincipal"] = self

        # cargar imágenes
        img_path = os.path.join(os.path.dirname(__file__), "..", "img")
        # Usa una sola imagen (fondo). Ajusta el nombre a tu archivo real.
        fondo_file = os.path.join(img_path, "equipo_DFM.png")
        if not os.path.exists(fondo_file):
            # fallback por si no existe
            fondo_file = os.path.join(img_path, "equipo_off.png")
        self.img_fondo = PhotoImage(file=fondo_file)

        self._build_ui()       

        # Registrar callbacks para cambios de gas
        self._register_gas_callbacks()

    def _configurar_estilos(self):

        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
            # Aplicar fuente táctil a los botones de selección
            # boton de send
        st.configure("SelBtn.TButton", padding=(16, 8),
                        font=getattr(C, "FONT_BASE", ("Calibri", 10)))
        st.map("SelBtn.TButton", background=[
                ("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")])
        
        st.configure("popup.TButton", padding=(16, 8),
                        font=getattr(C, "FONT_BASE", ("Calibri", 10)))
        st.map("popup.TButton", background=[
                ("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")])
    
    # ---------------- UI ----------------
    def _build_ui(self):
        # layout: barra izq fija, contenido der expandible
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=100)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=120)
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        # contenedor derecho
        cont = ttk.Frame(self)
        cont.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1)

        # área gráfica fija
        self.area_grafica = tk.Frame(
            cont, width=900, height=600, bg="white",
            highlightthickness=1, highlightbackground="#ddd"
        )
        self.area_grafica.grid(row=0, column=0, sticky="nsew")
        self.area_grafica.grid_propagate(False)

        # fondo con imagen
        self.lbl_fondo = tk.Label(self.area_grafica, image=self.img_fondo, bg="white", borderwidth=0)
        # ajusta la posición de la imagen dentro del área (x=0,y=0 la deja en la esquina)
        self.lbl_fondo.place(x=0, y=0)

                 # ========================= BOTONES SUPERIORES DERECHOS =========================
        frame_botones_superiores = tk.Frame(self.area_grafica, bg="white")
        frame_botones_superiores.place(relx=1.0, x=-10, y=10, anchor="ne")  # Esquina superior derecha
        
        # Botón "Equipo" - abre ventana de diagramas
        btn_equipo = TouchButton(
            frame_botones_superiores, 
            text="Equipo", 
            command=self.abrir_diagramas,
            width=6,
            style="SelBtn.TButton"
        )
        btn_equipo.pack(side=tk.LEFT, padx=(0, 5))
        
        # Botón "Info" - abre ventana del manual
        btn_info = TouchButton(
            frame_botones_superiores, 
            text="Info", 
            command=self.abrir_manual,
            width=6,
            style="SelBtn.TButton"
        )
        btn_info.pack(side=tk.LEFT)

        # crear labels de variables
        self._vars = {}
        self._labels = {}
        self._create_all_labels()

    def abrir_diagramas(self):
        """Abre la ventana de diagramas del equipo"""
        VentanaDiagramas(self)
    
    def abrir_manual(self):
        """Abre la ventana del manual del equipo"""
        VentanaManual(self)

    def _register_gas_callbacks(self):
        """Registra las funciones callback para cambios de gas"""
        # Mapeo de MFC ID a clave de variable
        mfc_mapping = {
            1: "mfc_o2_nombre",
            2: "mfc_co2_nombre", 
            3: "mfc_n2_nombre",
            4: "mfc_h2_nombre"
        }
        
        def actualizar_gas_label(mfc_id, nuevo_gas):
            """Callback que actualiza el label cuando cambia el gas"""
            variable_key = mfc_mapping.get(mfc_id)
            if variable_key and hasattr(self, '_vars') and variable_key in self._vars:
                self._vars[variable_key].set(nuevo_gas)
        
        # Registrar callbacks para los 4 MFCs
        for mfc_id in range(1, 5):
            mfc_gas_manager.register_callback_ejecucion(mfc_id, actualizar_gas_label)

    def _create_all_labels(self):
        # Definición para variables normales
        campos_normales = {
            "temp_omega1":      ("Ω1",      "°C"),
            "temp_omega2":      ("Ω2",      "°C"),
            "temp_horno1":      ("H1",      "°C"),
            "temp_horno2":      ("H2",      "°C"),
            "temp_cond1":       ("Cond1",   "°C"),
            "temp_cond2":       ("Cond2",   "°C"),
            "presion_mezcla":   ("P Mez",   "bar"),
            "presion_h2":       ("P H2",    "bar"),
            "presion_salida":   ("P Out",   "bar"),
            "potencia_horno1":   ("P h1",   "W"),
            "potencia_horno2":   ("P h2",   "W"),
        }

        # Crear labels normales
        for key, (short, unit) in campos_normales.items():
            v = tk.StringVar(value=f"{short}: -- {unit}")
            self._vars[key] = v
            x, y = LABEL_POS.get(key, (10, 10))
            color_fondo = COLOR_LABELS.get(key, "white")
            
            lbl = tk.Label(
                self.area_grafica, textvariable=v,
                bg=color_fondo, fg="#111", font=FUENTE_LABELS,
                relief="solid", bd=1, padx=6, pady=3
            )
            lbl.place(x=x, y=y)
            self._labels[key] = lbl

        # Crear labels separados para MFC
        mfc_gases = {
            "mfc_o2": mfc_gas_manager.get_gas_en_ejecucion(1),  # Usar gases en ejecución
            "mfc_co2": mfc_gas_manager.get_gas_en_ejecucion(2),
            "mfc_n2": mfc_gas_manager.get_gas_en_ejecucion(3),
            "mfc_h2": mfc_gas_manager.get_gas_en_ejecucion(4)
        }

        for key, nombre_gas in mfc_gases.items():
            # Label para el nombre del gas
            v_nombre = tk.StringVar(value=nombre_gas)
            
            # Determinar MFC ID basado en la clave
            mfc_id = {"mfc_o2": 1, "mfc_co2": 2, "mfc_n2": 3, "mfc_h2": 4}[key]
            self._vars[f"{key}_nombre"] = v_nombre
            
            x_nombre, y_nombre = LABEL_POS.get(f"{key}_nombre", (10, 10))
            color_nombre = COLOR_LABELS.get(f"{key}_nombre", "#F0F8FF")
            
            lbl_nombre = tk.Label(
                self.area_grafica, textvariable=v_nombre,
                bg=color_nombre, fg="#111", font=FUENTE_LABELS,
                relief="solid", bd=1, padx=8, pady=3
            )
            lbl_nombre.place(x=x_nombre, y=y_nombre)
            self._labels[f"{key}_nombre"] = lbl_nombre

            #Label para el VALOR del MFC (flujo)
            texto_inicial = "--\nmL/min"
            x_valor, y_valor = LABEL_POS.get(f"{key}_valor", (160, 10))
            color_valor = COLOR_LABELS.get(f"{key}_valor", "#90c6e5")
            
            lbl_valor = tk.Label(
                self.area_grafica, text=texto_inicial,
                bg=color_valor, fg="#111", font=FUENTE_VALORES,
                relief="solid", bd=1, padx=4, pady=2,
                justify=tk.CENTER  # Para centrar el texto de las 2 líneas
            )
            lbl_valor.place(x=x_valor, y=y_valor)
            self._labels[f"{key}_valor"] = lbl_valor

    def aplicar_datos_cmd5(self, partes: list[str]):
        """
        Actualización de datos para el nuevo formato de MFC
        """
        if len(partes) < 16:
            return

        def to_float(s, default=0.0):
            try:
                return float(s)
            except Exception:
                return default

        def to_int(s, default=0):
            try:
                return int(float(s))
            except Exception:
                return default

        # Temps (°C)
        t_omega1 = to_float(partes[1])
        t_omega2 = to_float(partes[2])
        t_h1     = to_float(partes[3])
        t_h2     = to_float(partes[4])
        t_c1     = to_float(partes[5])
        t_c2     = to_float(partes[6])

        # Presiones llegan *10
        p_mez    = to_float(partes[7]) / 10.0
        p_h2     = to_float(partes[8]) / 10.0
        p_out    = to_float(partes[9]) / 10.0

        # Flujos (mL/min)
        q_o2     = to_int(partes[10]) / 10.0
        q_co2    = to_int(partes[11]) / 10.0
        q_n2     = to_int(partes[12]) / 10.0
        q_h2     = to_int(partes[13]) / 10.0

        # Potencia (W)
        p_h1    = to_int(partes[14])
        p_horno2    = to_int(partes[15])

        # Actualizar variables normales
        self._vars["temp_omega1"].set(f"Ω1: {t_omega1:.1f} °C")
        self._vars["temp_omega2"].set(f"Ω2: {t_omega2:.1f} °C")
        self._vars["temp_horno1"].set(f"H1: {t_h1:.1f} °C")
        self._vars["temp_horno2"].set(f"H2: {t_h2:.1f} °C")
        self._vars["temp_cond1"].set(f"Cond1: {t_c1:.1f} °C")
        self._vars["temp_cond2"].set(f"Cond2: {t_c2:.1f} °C")

        self._vars["presion_mezcla"].set(f"P Mez: {p_mez:.1f} bar")
        self._vars["presion_h2"].set(f"P H2: {p_h2:.1f} bar")
        self._vars["presion_salida"].set(f"P Out: {p_out:.1f} bar")

        # Actualizar MFC con formato vertical - directamente en el label
        self._labels["mfc_o2_valor"].config(text=f"{q_o2}\nmL/min")
        self._labels["mfc_co2_valor"].config(text=f"{q_co2}\nmL/min")
        self._labels["mfc_n2_valor"].config(text=f"{q_n2}\nmL/min")
        self._labels["mfc_h2_valor"].config(text=f"{q_h2}\nmL/min")

        self._vars["potencia_horno1"].set(f"P Tot: {p_h1} W")
        self._vars["potencia_horno2"].set(f"P Tot: {p_horno2} W")

class VentanaDiagramas(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.transient(master)  # Hace que la ventana sea "hija" de la principal
        self.title("Diagramas del Equipo")
        self.geometry("800x600")

        # Aplicar la misma lógica de foco que en la ventana principal
        self._apply_focus_fix()

        # Lista de diagramas (ajusta las rutas según tus archivos)
        img_path = os.path.join(os.path.dirname(__file__), "..", "img")
        self.diagramas = [
            os.path.join(img_path, "diagrama1.png"),
            os.path.join(img_path, "diagrama2.png")
        ]
        
        # Verificar que los archivos existen, si no, usar placeholder
        self.diagramas = [d for d in self.diagramas if os.path.exists(d)]
        if not self.diagramas:
            # Si no hay diagramas, mostrar mensaje
            self.diagramas = [None]
        
        self.indice_actual = 0
        
        # Frame principal
        frame_principal = ttk.Frame(self)
        frame_principal.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Frame para navegación
        frame_navegacion = ttk.Frame(frame_principal)
        frame_navegacion.pack(fill=tk.X, pady=5)
        
        # Botones de navegación con TouchButton
        btn_anterior = TouchButton(frame_navegacion, text="← Anterior", style="popup.TButton", command=self.diagrama_anterior, width=9)
        btn_anterior.pack(side=tk.LEFT, padx=5)
        
        btn_siguiente = TouchButton(frame_navegacion, text="Siguiente →", style="popup.TButton", command=self.diagrama_siguiente, width=9)
        btn_siguiente.pack(side=tk.RIGHT, padx=5)
        
        # Label para mostrar el número de diagrama
        self.lbl_contador = ttk.Label(frame_navegacion, text="", font=("Calibri", 15))
        self.lbl_contador.pack(side=tk.TOP, pady=5)
        
        # Frame para la imagen con scrollbars
        frame_imagen = ttk.Frame(frame_principal)
        frame_imagen.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(frame_imagen, orient=tk.VERTICAL)
        h_scrollbar = ttk.Scrollbar(frame_imagen, orient=tk.HORIZONTAL)
        
        # Canvas para la imagen
        self.canvas = tk.Canvas(frame_imagen, bg="white",
                               yscrollcommand=v_scrollbar.set,
                               xscrollcommand=h_scrollbar.set)
        
        v_scrollbar.config(command=self.canvas.yview)
        h_scrollbar.config(command=self.canvas.xview)
        
        # Grid layout
        self.canvas.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        frame_imagen.grid_rowconfigure(0, weight=1)
        frame_imagen.grid_columnconfigure(0, weight=1)
        
        # Cargar y mostrar el primer diagrama
        self.mostrar_diagrama_actual()
        
    def _apply_focus_fix(self):
        """Aplica la misma solución de foco que la ventana principal"""
        self.update_idletasks()

        def _ensure_front_and_focus():
            try:
                self.lift()
                self.focus_force()
                # pulso de topmost (True -> False) para vencer al compositor
                self.attributes("-topmost", True)
                self.after(120, lambda: self.attributes("-topmost", False))
            except Exception:
                pass

        # 1) Mostrar con pequeño retraso
        def _show_after_withdraw():
            try:
                self.deiconify()
            except Exception:
                pass
            _ensure_front_and_focus()

        # ocultar 150 ms y luego mostrar al frente
        try:
            self.withdraw()
        except Exception:
            pass
        self.after(120, _show_after_withdraw)

        # 2) Ciclo corto de refuerzos (durante ~1.2 s)
        def _focus_cycle(n=0):
            _ensure_front_and_focus()
            if n < 9: # 10 intentos cada 120 ms
                self.after(120, lambda: _focus_cycle(n+1))
        self.after(160, _focus_cycle)

        # 3) Si el primer click llega demasiado pronto, lo "tragamos" y pedimos foco
        _first_click_done = {"v": False}

        def _swallow_until_focused(ev=None):
            if not _first_click_done["v"]:
                _ensure_front_and_focus()
                _first_click_done["v"] = True
                return "break" # evita que ese primer click llegue a VS Code
            
        self.bind_all("<ButtonPress-1>", _swallow_until_focused, add="+")
        # también al map/idle por si el WM ignora el primero
        self.bind("<Map>", lambda e: self.after(10, _ensure_front_and_focus))
        self.after_idle(_ensure_front_and_focus)

    def mostrar_diagrama_actual(self):
        """Muestra el diagrama actual en el canvas"""
        if not self.diagramas or self.diagramas[0] is None:
            self.canvas.delete("all")
            self.canvas.create_text(400, 300, text="No se encontraron diagramas", font=("Calibri", 15))
            self.lbl_contador.config(text="No hay diagramas disponibles")
            return
            
        if 0 <= self.indice_actual < len(self.diagramas):
            ruta_diagrama = self.diagramas[self.indice_actual]
            
            try:
                # Cargar imagen con PIL
                imagen_pil = Image.open(ruta_diagrama)
                self.imagen_tk = ImageTk.PhotoImage(imagen_pil)
                
                # Limpiar canvas y mostrar nueva imagen
                self.canvas.delete("all")
                self.canvas.create_image(0, 0, anchor=tk.NW, image=self.imagen_tk)
                
                # Configurar región de scroll
                self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
                
                # Actualizar contador
                self.lbl_contador.config(
                    text=f"Diagrama {self.indice_actual + 1} de {len(self.diagramas)}"
                )
            except Exception as e:
                self.canvas.delete("all")
                self.canvas.create_text(400, 300, text=f"Error al cargar imagen:\n{str(e)}")
        else:
            self.canvas.delete("all")
            self.canvas.create_text(400, 300, text="Índice de diagrama inválido")
    
    def diagrama_siguiente(self):
        """Muestra el siguiente diagrama"""
        if self.indice_actual < len(self.diagramas) - 1:
            self.indice_actual += 1
            self.mostrar_diagrama_actual()
    
    def diagrama_anterior(self):
        """Muestra el diagrama anterior"""
        if self.indice_actual > 0:
            self.indice_actual -= 1
            self.mostrar_diagrama_actual()
            
class VentanaManual(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.transient(master)  # Hace que la ventana sea "hija" de la principal
        self.title("Manual del Equipo")
        self.geometry("1000x800")

        # Aplicar la misma lógica de foco que en la ventana principal
        self._apply_focus_fix()
        
        # Variables para el PDF
        self.doc = None
        self.paginas = []
        self.pagina_actual = 0
        self.zoom_scale = 1.0
        
        # Frame principal
        frame_principal = ttk.Frame(self)
        frame_principal.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Frame para controles
        frame_controles = ttk.Frame(frame_principal)
        frame_controles.pack(fill=tk.X, pady=5)
        
        # Botones de navegación con TouchButton
        btn_anterior = TouchButton(frame_controles, text="← Página Anterior", style="popup.TButton", command=self.pagina_anterior, width=15)
        btn_anterior.pack(side=tk.LEFT, padx=5)
        
        btn_siguiente = TouchButton(frame_controles, text="Página Siguiente →", style="popup.TButton", command=self.pagina_siguiente, width=15)
        btn_siguiente.pack(side=tk.LEFT, padx=5)
        
        # Controles de zoom
        btn_zoom_in = TouchButton(frame_controles, text="Zoom +", style="popup.TButton", command=self.zoom_in, width=6)
        btn_zoom_in.pack(side=tk.RIGHT, padx=5)
        
        btn_zoom_out = TouchButton(frame_controles, text="Zoom -", style="popup.TButton", command=self.zoom_out, width=6)
        btn_zoom_out.pack(side=tk.RIGHT, padx=5)
        
        # Label para mostrar número de página
        self.lbl_pagina = ttk.Label(frame_controles, text="", font=("Calibri", 15))
        self.lbl_pagina.pack(side=tk.TOP, pady=5)
        
        # Frame para el PDF con scrollbars
        frame_pdf = ttk.Frame(frame_principal)
        frame_pdf.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(frame_pdf, orient=tk.VERTICAL)
        h_scrollbar = ttk.Scrollbar(frame_pdf, orient=tk.HORIZONTAL)
        
        # Canvas para el PDF
        self.canvas = tk.Canvas(frame_pdf, bg="white",
                               yscrollcommand=v_scrollbar.set,
                               xscrollcommand=h_scrollbar.set)
        
        v_scrollbar.config(command=self.canvas.yview)
        h_scrollbar.config(command=self.canvas.xview)
        
        # Grid layout
        self.canvas.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        frame_pdf.grid_rowconfigure(0, weight=1)
        frame_pdf.grid_columnconfigure(0, weight=1)
        
        # Bind eventos de scroll del mouse
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        
        # Cargar el manual PDF
        self.cargar_pdf()
    
    def _apply_focus_fix(self):
        """Aplica la misma solución de foco que la ventana principal"""
        self.update_idletasks()

        def _ensure_front_and_focus():
            try:
                self.lift()
                self.focus_force()
                # pulso de topmost (True -> False) para vencer al compositor
                self.attributes("-topmost", True)
                self.after(120, lambda: self.attributes("-topmost", False))
            except Exception:
                pass

        # 1) Mostrar con pequeño retraso
        def _show_after_withdraw():
            try:
                self.deiconify()
            except Exception:
                pass
            _ensure_front_and_focus()

        # ocultar 150 ms y luego mostrar al frente
        try:
            self.withdraw()
        except Exception:
            pass
        self.after(120, _show_after_withdraw)

        # 2) Ciclo corto de refuerzos (durante ~1.2 s)
        def _focus_cycle(n=0):
            _ensure_front_and_focus()
            if n < 9: # 10 intentos cada 120 ms
                self.after(120, lambda: _focus_cycle(n+1))
        self.after(160, _focus_cycle)

        # 3) Si el primer click llega demasiado pronto, lo "tragamos" y pedimos foco
        _first_click_done = {"v": False}

        def _swallow_until_focused(ev=None):
            if not _first_click_done["v"]:
                _ensure_front_and_focus()
                _first_click_done["v"] = True
                return "break" # evita que ese primer click llegue a VS Code
            
        self.bind_all("<ButtonPress-1>", _swallow_until_focused, add="+")
        # también al map/idle por si el WM ignora el primero
        self.bind("<Map>", lambda e: self.after(10, _ensure_front_and_focus))
        self.after_idle(_ensure_front_and_focus)

    def cargar_pdf(self):
        """Carga el manual en PDF"""
        ruta_manual = os.path.join(os.path.dirname(__file__), "..", "docs", "manual_gasificador.pdf")
        
        try:
            if os.path.exists(ruta_manual):
                # Abrir el PDF
                self.doc = fitz.open(ruta_manual)
                self.pagina_actual = 0
                self.mostrar_pagina_actual()
            else:
                self.mostrar_error(f"Archivo no encontrado:\n{ruta_manual}")
        except Exception as e:
            self.mostrar_error(f"Error al cargar PDF:\n{str(e)}")
    
    def mostrar_pagina_actual(self):
        """Muestra la página actual del PDF"""
        if self.doc is None or self.pagina_actual >= len(self.doc):
            return
            
        try:
            # Obtener la página
            pagina = self.doc[self.pagina_actual]
            
            # Renderizar la página con zoom
            mat = fitz.Matrix(self.zoom_scale, self.zoom_scale)
            pix = pagina.get_pixmap(matrix=mat)
            
            # Convertir a formato que PIL pueda manejar
            img_data = pix.tobytes("ppm")
            img_pil = Image.open(io.BytesIO(img_data))
            
            # Convertir a PhotoImage para Tkinter
            self.img_tk = ImageTk.PhotoImage(img_pil)
            
            # Limpiar canvas y mostrar nueva imagen
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.img_tk)
            
            # Configurar región de scroll
            self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
            
            # Actualizar contador de página
            self.lbl_pagina.config(
                text=f"Página {self.pagina_actual + 1} de {len(self.doc)}"
            )
            
        except Exception as e:
            self.mostrar_error(f"Error al mostrar página:\n{str(e)}")
    
    def mostrar_error(self, mensaje):
        """Muestra un mensaje de error en el canvas"""
        self.canvas.delete("all")
        self.canvas.create_text(500, 400, text=mensaje, font=("Calibri", 15), fill="red")
        self.lbl_pagina.config(text="Error")
    
    def pagina_siguiente(self):
        """Va a la siguiente página"""
        if self.doc and self.pagina_actual < len(self.doc) - 1:
            self.pagina_actual += 1
            self.mostrar_pagina_actual()
    
    def pagina_anterior(self):
        """Va a la página anterior"""
        if self.doc and self.pagina_actual > 0:
            self.pagina_actual -= 1
            self.mostrar_pagina_actual()
    
    def zoom_in(self):
        """Aumenta el zoom"""
        self.zoom_scale *= 1.2
        if self.zoom_scale > 3.0:
            self.zoom_scale = 3.0
        self.mostrar_pagina_actual()
    
    def zoom_out(self):
        """Disminuye el zoom"""
        self.zoom_scale /= 1.2
        if self.zoom_scale < 0.5:
            self.zoom_scale = 0.5
        self.mostrar_pagina_actual()
    
    def _on_mousewheel(self, event):
        """Maneja el scroll del mouse"""
        if event.delta > 0 or event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        else:
            self.canvas.yview_scroll(1, "units")
    
    def __del__(self):
        """Cierra el documento PDF al destruir la ventana"""
        if self.doc:
            self.doc.close()
