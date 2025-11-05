# gui/ventana_graph.py (modificado para 1024x538 y ajuste automático del canvas)
import os
import sys
import csv
from datetime import datetime
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico
from ui.widgets import TouchButton, TouchEntry, LabeledEntryNum


# ====== Definición de variables que graficamos / registramos ======
SERIES_DEF = {
    "T_horno1": ("Temp. horno 1", "°C", 3, 1.0),
    "T_horno2": ("Temp. horno 2", "°C", 4, 1.0),
    "T_omega1": ("Temp. omega 1", "°C", 1, 1.0),
    "T_omega2": ("Temp. omega 2", "°C", 2, 1.0),
    "T_cond1":  ("Temp. cond. 1", "°C", 5, 1.0),
    "T_cond2":  ("Temp. cond. 2", "°C", 6, 1.0),
    "P_mezcla": ("Presión mezcla", "bar", 7, 0.1),
    "P_H2":     ("Presión H2", "bar", 8, 0.1),
    "P_salida": ("Presión salida", "bar", 9, 0.1),
    "MFC_O2":   ("MFC O2", "mL/min", 10, 0.1),
    "MFC_CO2":  ("MFC CO2", "mL/min", 11, 0.1),
    "MFC_N2":   ("MFC N2", "mL/min", 12, 0.1),
    "MFC_H2":   ("MFC H2", "mL/min", 13, 0.1),
}
SERIES_ORDER = [
    "T_horno1","T_horno2","T_omega1","T_omega2","T_cond1","T_cond2",
    "P_mezcla","P_H2","P_salida","MFC_O2","MFC_CO2","MFC_N2","MFC_H2",
]


def _app_base_dir() -> str:
    """Carpeta base donde persistimos (soporta ejecutable 'congelado')."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))



class _C_:
    FONT_BASE = ("Calibri", 13)
    ENTRY_WIDTH = 12
    COMBO_WIDTH = 12
C = _C_()

POS = {
    1: {
        "btn_graph":   (0, 0),
        "btn_pause": (0,  45),     
        "btn_log":   (0,  90), 
        "lbl_period":     (5, 140),  "ent_period":  (100,  140),
        "btn_select_todo": (15, 0),   "btn_desselect": (105, 0),
        "lbl_status": (43, 380),
    },
}

class VentanaGraph(tk.Frame):
    # --- Objetivo de layout fijo (área útil) ---
    _TARGET_W = 1024
    _TARGET_H = 538

    # Nav lateral (BarraNavegacion) y márgenes que usa el layout actual
    _NAV_W = 149    # ancho fijo de BarraNavegacion 
    _PAD = 8        # paddings en el wrap (padx/pady)
    _LEFT_MIN = 172 # minsize del panel izquierdo de controles

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        self._configurar_estilos()

        if hasattr(self.controlador, "__setattr__"):
            setattr(self.controlador, "_ventana_graph", self)

        # Estado
        self._graph_active = False
        self._graph_paused = False
        self._log_active = False
        self._graph_job = None
        self._log_job = None

        self._usb_monitor_job = None  # para monitorear USB

        # Tiempo relativo y periodo
        self._elapsed_sec = 0
        self._sample_period = 5
        self._max_points = max(1, (2 * 60 * 60) // self._sample_period)

        # Último snapshot normalizado
        self._last_snapshot = None

        # Buffers para gráfica
        self._buffers = {k: [] for k in SERIES_ORDER}
        self._times = []

        # Carpeta de registros (al lado del exe/proyecto)
        self._reg_dir = os.path.join(_app_base_dir(), "registros_experimento")
        os.makedirs(self._reg_dir, exist_ok=True)
        self._csv_path = None  # se define al iniciar registro

        # Matplotlib
        self.fig = None
        self.ax = None
        self.mpl_canvas = None

        self._lines = {}
        self._series_vars = {}
        self._need_legend_refresh = True

        self._build_ui()

        # Iniciar monitoreo de USB
        self._monitorear_usb()

        self.bind("<Destroy>", self._on_destroy)
    
    def _monitorear_usb(self):
        """Monitorea continuamente el estado de la USB y actualiza el botón"""
        usb_conectada = self._detectar_usb() is not None
        
        # Actualizar estado del botón
        if usb_conectada:
            self.btn_log.configure(state="normal")
        else:
            self.btn_log.configure(state="disabled")
            # Si la USB se desconecta durante el registro, detenerlo
            if self._log_active:
                self._detener_registro_por_usb()
        
        # Programar siguiente verificación (cada 2 segundos)
        self._usb_monitor_job = self.after(2000, self._monitorear_usb)

    def _detener_registro_por_usb(self):
        """Detiene el registro automáticamente cuando se desconecta la USB"""
        self._log_active = False
        self.btn_log.configure(text="Iniciar registro CSV")
        if self._log_job:
            try:
                self.after_cancel(self._log_job)
            except Exception:
                pass
            self._log_job = None
        self._update_status()
        
        # Limpiar ruta
        self._csv_path = None
    
    def _detectar_usb(self):
        """
        Detecta memorias USB conectadas en Raspberry Pi.
        Retorna la ruta de la primera USB encontrada o None si no hay.
        """
        # Posibles puntos de montaje de USB en Raspberry Pi
        posibles_montajes = [
            "/media/pi",  # Raspberry Pi OS con usuario 'pi'
            "/media",     # Otras distribuciones
            "/media/eia",
            "/mnt",       # Punto de montaje tradicional
            "/run/media/pi"  # Algunas distribuciones modernas
        ]
    
        for montaje in posibles_montajes:
            if os.path.exists(montaje):
                try:
                    # Listar dispositivos en el punto de montaje
                    dispositivos = os.listdir(montaje)
                    for dispositivo in dispositivos:
                        ruta_completa = os.path.join(montaje, dispositivo)
                        # Verificar que es un directorio y no está vacío (puede ser USB)
                        if os.path.isdir(ruta_completa) and dispositivo:
                            # Verificar permisos de escritura
                            if os.access(ruta_completa, os.W_OK):
                                return ruta_completa
                except (PermissionError, OSError):
                    continue
    
        return None

    def _configurar_estilos(self):
        """Configura estilos igual que en ventana_auto.py"""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("B.TButton", padding=(16, 8), font=getattr(C, "FONT_BASE", ("Calibri", 13)))
        style.map("B.TButton", background=[("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")])

        style.configure("BSelected.TButton", padding=(16, 8), font=getattr(C, "FONT_BASE", ("Calibri", 13)), background="#bdbdbd")
        style.map("BSelected.TButton", background=[("!disabled", "#bdbdbd"), ("pressed", "#9e9e9e")])
        
    def _fit_mpl_to_available_space(self):
        """
        Calcula el espacio real del contenedor del canvas y ajusta el tamaño de la
        Figure en pulgadas (px/dpi) para que el lienzo encaje exactamente sin recortes.
        """
        if self.mpl_canvas is None or self.fig is None:
            return
        # Asegurar geometría actualizada
        self.update_idletasks()
        fig_widget = self.mpl_canvas.get_tk_widget()
        avail_w = max(1, fig_widget.winfo_width())
        avail_h = max(1, fig_widget.winfo_height())
        dpi = self.fig.get_dpi() or 100
        self.fig.set_size_inches(avail_w / dpi, avail_h / dpi, forward=True)
        # Márgenes razonables
        self.fig.subplots_adjust(left=0.08, right=0.98, top=0.95, bottom=0.12)
        self.mpl_canvas.draw_idle()

    # ========================= UI =========================
    def _build_ui(self):
        # Layout raíz: barra izq (col 0), contenido (col 1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación (ahora fija a 149 px en la clase de barra)
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="ns")
        barra.grid_propagate(False)

        # Contenido principal: panel izquierdo mínimo para controles; resto la gráfica
        wrap = ttk.Frame(self)
        wrap.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=0, minsize=205)  # compacto
        wrap.grid_columnconfigure(1, weight=1)               # gráfica grande

        # --------- Panel izquierdo (vertical) ---------
        left = ttk.Frame(wrap)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 0))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # ===== ACCIONES ===== (sin título, más compacto)
        acciones = ttk.Frame(left,width=205, height=175, borderwidth=2, relief="groove", padding=(6, 2))  # Cambiado de LabelFrame a Frame normal
        acciones.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        acciones.grid_propagate(False)  # Importante: evitar que el frame se ajuste al contenido

        # Fila 0: Dos botones - Iniciar gráfica y Pausar        
        self.btn_graph = TouchButton(acciones, text="Iniciar gráfica", width=15, style="B.TButton", command=self._toggle_graph)
        self.btn_graph.place(x=POS[1]["btn_graph"][0], y=POS[1]["btn_graph"][1])
        
        self.btn_pause = TouchButton(acciones, text="Pausar", width=15, style="B.TButton",command=self._toggle_pause, state="disabled")
        self.btn_pause.place(x=POS[1]["btn_pause"][0], y=POS[1]["btn_pause"][1])

        # Fila 1: Un botón - Iniciar registro
        self.btn_log = TouchButton(acciones, text="Iniciar registro CSV", width=15, style="B.TButton",command=self._toggle_log, state="disabled")
        self.btn_log.place(x=POS[1]["btn_log"][0], y=POS[1]["btn_log"][1])
        

        # Fila 2: Label y Entry del periodo
        self.lbl_period = ttk.Label(acciones, text="Periodo (s):", font=C.FONT_BASE)
        self.lbl_period.place(x=POS[1]["lbl_period"][0], y=POS[1]["lbl_period"][1])
        
        self.ent_period = ttk.Entry(acciones, width=8,justify="center", font=C.FONT_BASE)
        self.ent_period.place(x=POS[1]["ent_period"][0], y=POS[1]["ent_period"][1])
       
        self.ent_period.insert(0, str(self._sample_period))

        def _norm_period():
            txt = (self.ent_period.get() or "").strip()
            try:
                v = int(float(txt))
            except Exception:
                v = self._sample_period
            v = max(1, min(60, v))
            self.ent_period.delete(0, tk.END)
            self.ent_period.insert(0, str(v))
            if v != self._sample_period:
                self._sample_period = v
                self._max_points = max(1, (2 * 60 * 60) // self._sample_period)
                if self._graph_active and not self._graph_paused:
                    if self._graph_job:
                        try:
                            self.after_cancel(self._graph_job)
                        except Exception:
                            pass
                    self._graph_job = self.after(self._sample_period * 1000, self._graph_tick)
            self._update_status()

        self.ent_period.bind(
            "<Button-1>",
            lambda _e: TecladoNumerico(
                self,
                self.ent_period,
                on_submit=lambda v: (self.ent_period.delete(0, tk.END),
                                     self.ent_period.insert(0, str(v)),
                                     _norm_period()),
            ),
        )
        vcmd = (self.register(self._validate_numeric), "%P", "%d", 1, 0)
        self.ent_period.configure(validate="key", validatecommand=vcmd)
        self.ent_period.bind("<FocusOut>", lambda _e: _norm_period())

        # Selección de series
        # Frame con tamaño fijo y mismo estilo que "acciones"
        selbox = ttk.Frame(left, width=205, height=415, borderwidth=2, relief="groove", padding=(6, 2))
        selbox.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        selbox.grid_propagate(False)


        self.btn_select_todo = TouchButton(selbox, text="✓", width=4, style="B.TButton",command=self._select_all)
        self.btn_select_todo.place(x=POS[1]["btn_select_todo"][0], y=POS[1]["btn_select_todo"][1])

        self.btn_desselect = TouchButton(selbox, text="☐", width=4, style="B.TButton",command=self._select_none)
        self.btn_desselect.place(x=POS[1]["btn_desselect"][0], y=POS[1]["btn_desselect"][1])

        # Configurar estilo para los checkbuttons
        style = ttk.Style()
        style.configure("GraphCheck.TCheckbutton", font=C.FONT_BASE)

        # Checkboxes directamente en el frame
        for i, key in enumerate(SERIES_ORDER):
            var = tk.BooleanVar(value=False)
            self._series_vars[key] = var
            label, unit, *_ = SERIES_DEF[key]
            
            cb = ttk.Checkbutton(
                selbox, 
                text=f"{label} [{unit}]", 
                variable=var, 
                command=self._refresh_legend_next,
                style="GraphCheck.TCheckbutton"  # Aplicar el estilo con la fuente
            )
            #cb.configure(font=C.FONT_BASE)
            cb.place(x=0, y=45 + i*25, width=193, height=30)

        # Estado (leyenda corta)
        self.lbl_status = ttk.Label(selbox, text="Registro:OFF", font=C.FONT_BASE)
        self.lbl_status.place(x=POS[1]["lbl_status"][0], y=POS[1]["lbl_status"][1])
        

        # --------- Panel derecho (figura) más grande ---------
        fig_frame = ttk.Frame(wrap)
        fig_frame.grid(row=0, column=1, sticky="nsew")
        fig_frame.grid_rowconfigure(0, weight=1)
        fig_frame.grid_columnconfigure(0, weight=1)

        # Figura con tamaño neutro: la ajustaremos a píxeles reales
        self.fig = Figure(figsize=(6.0, 3.2), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Tiempo (MM:SS)")
        self.ax.set_ylabel("Valor")
        self.ax.grid(True, linestyle="--", alpha=0.3)

        def _fmt_mmss(x, _pos):
            total = int(max(0, x))
            m, s = divmod(total, 60)
            return f"{m:02d}:{s:02d}"
        self.ax.xaxis.set_major_formatter(FuncFormatter(_fmt_mmss))

        for key in SERIES_ORDER:
            line, = self.ax.plot([], [], label=self._series_label(key))
            self._lines[key] = line

        self._need_legend_refresh = True
        self._refresh_legend()

        self.mpl_canvas = FigureCanvasTkAgg(self.fig, master=fig_frame)
        self.mpl_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        # Ajuste automático al espacio real cuando la UI ya está lista
        self.after_idle(self._fit_mpl_to_available_space)
        # Reajustar también si cambia el tamaño del contenedor (por si ajustas la raíz)
        fig_frame.bind("<Configure>", lambda _e: self._fit_mpl_to_available_space())

    # ========================= RX / Snapshot =========================
    def on_rx_cmd5(self, partes):
        try:
            if not partes or partes[0] != "5":
                return

            def fidx(idx, default=0.0):
                try:
                    return float(partes[idx])
                except Exception:
                    return default

            snap = {}
            for key in SERIES_ORDER:
                _, _, idx, scale = SERIES_DEF[key]
                val = fidx(idx, 0.0) * scale
                if key.startswith("P_") or key.startswith("MFC_"):
                    val = round(val, 1)
                snap[key] = val

            self._last_snapshot = snap
        except Exception as ex:
            print("[Graph] Error parseando CMD=5:", ex)

    # ========================= Toggle actions =========================
    def _toggle_graph(self):
        if not self._graph_active:
            if not any(v.get() for v in self._series_vars.values()):
                messagebox.showwarning("Gráfica", "Selecciona al menos una variable para graficar.")
                return
            self._reset_plot_buffers()
            self._graph_active = True
            self._graph_paused = False
            self.btn_graph.configure(text="Detener gráfica")
            self.btn_pause.configure(text="Pausar", state="normal")
            self._graph_tick()
        else:
            self._graph_active = False
            self._graph_paused = False
            self.btn_graph.configure(text="Iniciar gráfica")
            self.btn_pause.configure(text="Pausar", state="disabled")
            if self._graph_job:
                try:
                    self.after_cancel(self._graph_job)
                except Exception:
                    pass
                self._graph_job = None
            self._reset_plot_buffers()
        self._update_status()

    def _toggle_pause(self):
        if not self._graph_active:
            return
        self._graph_paused = not self._graph_paused
        self.btn_pause.configure(text=("Reanudar" if self._graph_paused else "Pausar"))
        if not self._graph_paused:
            if self._graph_job:
                try:
                    self.after_cancel(self._graph_job)
                except Exception:
                    pass
            self._graph_job = self.after(self._sample_period * 1000, self._graph_tick)
        self._update_status()

    def _toggle_log(self):
        if not self._log_active:
            # Crear popup similar al de guardar preset
            popup = tk.Toplevel(self)
            popup.title("Datos del experimento")
            popup.geometry("600x400+140+50")
            popup.resizable(False, False)

            # === Copiar estilo/colores como en TecladoNumerico ===
            st = ttk.Style(popup)
            try:
                st.theme_use("clam")
            except Exception:
                pass

            bg_theme = st.lookup("TFrame", "background")
            if not bg_theme:
                bg_theme = popup.cget("bg")
            popup.configure(bg=bg_theme)

            # Fuente coherente
            _font = tkfont.Font(family="Calibri", size=16)

            # Hacerlo modal/transiente
            popup.transient(self.winfo_toplevel())
            popup.wait_visibility()
            popup.lift()
            popup.focus_force()
            popup.grab_set()
            popup.protocol("WM_DELETE_WINDOW", popup.destroy)

            # Variables para los campos
            result = {"path": None}
            current_entry = None  # Para saber qué entry está activo

            # --- Frame para los campos (horizontal) ---
            campos_frame = tk.Frame(popup, bg=bg_theme)
            campos_frame.pack(pady=20)

            # Campo 1: Nombre (izquierda)
            nombre_frame = tk.Frame(campos_frame, bg=bg_theme)
            nombre_frame.pack(side="left", padx=20)

            tk.Label(nombre_frame, text="Nombre (Nombre_Apellido):", font=("Calibri", 14), bg=bg_theme)\
                .pack(pady=(0, 6))

            entry_nombre = tk.Entry(nombre_frame, font=("Calibri", 16), width=20, justify="center")
            entry_nombre.pack(pady=(0, 10))

            # Campo 2: Fecha (derecha)
            fecha_frame = tk.Frame(campos_frame, bg=bg_theme)
            fecha_frame.pack(side="left", padx=20)

            tk.Label(fecha_frame, text="Fecha (YYYYMMDD):", font=("Calibri", 14), bg=bg_theme)\
                .pack(pady=(0, 6))

            entry_fecha = tk.Entry(fecha_frame, font=("Calibri", 16), width=20, justify="center")
            entry_fecha.pack(pady=(0, 10))
            entry_fecha.insert(0, datetime.now().strftime("%Y%m%d"))

            # Función para enfocar entry
            def focus_entry(entry):
                nonlocal current_entry
                current_entry = entry
                entry.focus_set()

            # Bind para cambiar entre entries
            entry_nombre.bind("<Button-1>", lambda e: focus_entry(entry_nombre))
            entry_fecha.bind("<Button-1>", lambda e: focus_entry(entry_fecha))

            # === Teclado alfanumérico ===
            filas_teclas = [
                ["1","2","3","4","5","6","7","8","9","0"],
                ["Q","W","E","R","T","Y","U","I","O","P"],
                ["A","S","D","F","G","H","J","K","L"],
                ["Z","X","C","V","B","N","M","_","-"],
            ]

            frame_teclado = tk.Frame(popup, bg=bg_theme, highlightthickness=0, bd=0)
            frame_teclado.pack(pady=20)

            KEY_W, KEY_H = 2, 1

            def escribir(tecla):
                if current_entry:
                    if tecla == "<-":
                        txt = current_entry.get()
                        if txt:
                            current_entry.delete(len(txt)-1, tk.END)
                    else:
                        current_entry.insert(tk.END, tecla)

            # Crear teclado
            for r in (0, 1):
                for c, tecla in enumerate(filas_teclas[r]):
                    tk.Button(
                        frame_teclado,
                        text=tecla,
                        font=_font,
                        width=KEY_W, height=KEY_H,
                        command=lambda k=tecla: escribir(k),
                        bg=bg_theme, activebackground=bg_theme,
                        relief="raised"
                    ).grid(row=r, column=c, padx=4, pady=4, sticky="")

            for r in (2, 3):
                for c, tecla in enumerate(filas_teclas[r]):
                    tk.Button(
                        frame_teclado,
                        text=tecla,
                        font=_font,
                        width=KEY_W, height=KEY_H,
                        command=lambda k=tecla: escribir(k),
                        bg=bg_theme, activebackground=bg_theme,
                        relief="raised"
                    ).grid(row=r, column=c, padx=4, pady=4, sticky="")

            # Botón "<-"
            tk.Button(
                frame_teclado,
                text="<-",
                font=_font,
                width=KEY_W, height=KEY_H * 2,
                command=lambda: escribir("<-"),
                bg=bg_theme, activebackground=bg_theme,
                relief="raised"
            ).grid(row=2, column=9, rowspan=2, padx=4, pady=4, sticky="nsew")

            # === Funcionalidad de guardado ===
            def aceptar():
                nombre = self._safe_slug(entry_nombre.get())
                fecha = self._safe_slug(entry_fecha.get())
                
                if not nombre:
                    messagebox.showerror("Registro", "Ingresa un nombre válido.", parent=popup)
                    return
                if not (len(fecha) == 8 and fecha.isdigit()):
                    messagebox.showerror("Registro", "La fecha debe tener formato YYYYMMDD.", parent=popup)
                    return
                
                # Obtener ruta de USB (ya verificada por el monitoreo)
                usb_path = self._detectar_usb()
                if not usb_path:
                    messagebox.showerror("USB desconectada", 
                                    "La USB ha sido desconectada.\n\n"
                                    "Vuelva a conectar la USB e intente nuevamente.", 
                                    parent=popup)
                    return
                
                filename = f"RegistroDatos_{nombre}_{fecha}.csv"
                path = os.path.join(usb_path, filename)
                result["path"] = os.path.abspath(path)
                
                # Crear el archivo con headers
                try:
                    with open(result["path"], "w", newline="", encoding="utf-8") as f:
                        w = csv.writer(f, delimiter=",")
                        header = ["timestamp"] + SERIES_ORDER
                        w.writerow(header)
                except Exception as ex:
                    messagebox.showerror("Registro", f"No se pudo crear el archivo:\n{ex}", parent=popup)
                    return
                
                popup.destroy()

            def cancelar():
                result["path"] = None
                popup.destroy()

            # Barra de acciones
            acciones = tk.Frame(popup, bg=bg_theme)
            acciones.pack(pady=20)
            
            tk.Button(acciones, text="Aceptar", font=("Calibri", 16),
                    command=aceptar, bg=bg_theme, activebackground=bg_theme)\
                .pack(side="left", padx=8)
            tk.Button(acciones, text="Cancelar", font=("Calibri", 16),
                    command=cancelar, bg=bg_theme, activebackground=bg_theme)\
                .pack(side="left", padx=8)

            # Atajos
            popup.bind("<Return>", lambda e: aceptar())
            popup.bind("<Escape>", lambda e: cancelar())

            # Enfocar el primer entry por defecto
            focus_entry(entry_nombre)

            # Esperar a que se cierre el popup
            self.wait_window(popup)

            # Si se obtuvo una ruta válida, iniciar el registro
            if result["path"]:
                self._csv_path = result["path"]
                self._log_active = True
                self.btn_log.configure(text="Detener registro")
                self._log_tick()
                self._update_status()
        else:
            # Detener registro
            self._log_active = False
            self.btn_log.configure(text="Iniciar registro CSV")
            if self._log_job:
                try:
                    self.after_cancel(self._log_job)
                except Exception:
                    pass
                self._log_job = None
            self._update_status()

    def _select_all(self):
        for v in self._series_vars.values():
            v.set(True)
        self._refresh_legend_next()

    def _select_none(self):
        for v in self._series_vars.values():
            v.set(False)
        self._refresh_legend_next()

    def _update_status(self):
        status_g = "ON" if self._graph_active else "OFF"
        if self._graph_active and self._graph_paused:
            status_g += " (PAUSA)"
        self.lbl_status.configure(text=f"Registro: {'ON' if self._log_active else 'OFF'}")

    # ========================= Ciclos (after) =========================
    def _graph_tick(self):
        if not self._graph_active or self._graph_paused:
            return

        if self._last_snapshot is not None:
            self._elapsed_sec += self._sample_period
            t = self._elapsed_sec
            self._times.append(t)
            if len(self._times) > self._max_points:
                self._times = self._times[-self._max_points:]

            for key in SERIES_ORDER:
                val = self._last_snapshot.get(key, 0.0)
                buf = self._buffers[key]
                buf.append(val)
                if len(buf) > self._max_points:
                    self._buffers[key] = buf[-self._max_points:]

            self._redraw_plot()

        self._graph_job = self.after(self._sample_period * 1000, self._graph_tick)

    def _log_tick(self):
        if not self._log_active:
            return
        if self._last_snapshot is not None and self._csv_path:
            try:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                row = [ts] + [self._last_snapshot.get(k, 0.0) for k in SERIES_ORDER]
                self._append_csv(row)
            except (IOError, OSError) as e:
                pass

        self._log_job = self.after(1000, self._log_tick)

    # ========================= Plot helpers =========================
    def _series_label(self, key):
        label, unit, *_ = SERIES_DEF[key]
        return f"{label} [{unit}]"

    def _refresh_legend_next(self):
        self._need_legend_refresh = True
        self._refresh_legend()

    def _refresh_legend(self):
        if not self._need_legend_refresh or self.ax is None:
            return
        handles, labels = [], []
        for key in SERIES_ORDER:
            if self._series_vars[key].get():
                handles.append(self._lines[key])
                labels.append(self._series_label(key))
        leg = self.ax.get_legend()
        if leg:
            leg.remove()
        if handles:
            self.ax.legend(handles, labels, loc="upper left", fontsize=8)
        self._need_legend_refresh = False
        if self.mpl_canvas is not None:
            self.mpl_canvas.draw_idle()

    def _redraw_plot(self):
        if self.ax is None or self.mpl_canvas is None:
            return
        xs = self._times
        for key in SERIES_ORDER:
            ln = self._lines[key]
            if self._series_vars[key].get():
                ln.set_data(xs, self._buffers[key])
            else:
                ln.set_data([], [])
        # ------- Ventana deslizante en X -------
        xmax = max(xs) if xs else 1
        win_sec = self._max_points * self._sample_period
        if xmax <= win_sec:
            left = 0
            right = xmax if xmax > 1 else 1
        else:
            left = xmax - win_sec
            right = xmax
        self.ax.set_xlim(left=left, right=right)

        # Autoscale Y según series visibles
        self.ax.relim()
        self.ax.autoscale_view(scalex=False, scaley=True)

        self._refresh_legend()
        self.mpl_canvas.draw_idle()

    def _reset_plot_buffers(self):
        self._elapsed_sec = 0
        self._times = []
        self._buffers = {k: [] for k in SERIES_ORDER}
        for key, ln in self._lines.items():
            ln.set_data([], [])
        self.ax.set_xlim(0, 1)
        self.ax.relim()
        self.ax.autoscale_view(scalex=False, scaley=True)
        if self.mpl_canvas:
            self.mpl_canvas.draw_idle()

    # ========================= Validación numérica =========================
    @staticmethod
    def _validate_numeric(new_text: str, action: str, es_entero: int, max_dec: int):
        if action == "0":
            return True
        txt = (new_text or "").strip()
        if not txt:
            return True
        try:
            if es_entero:
                int(float(txt))
            else:
                float(txt)
                if "." in txt:
                    dec = txt.split(".", 1)[1]
                    if len(dec) > int(max_dec):
                        return False
        except Exception:
            return False
        return True

    # ========================= CSV helpers =========================
    def _safe_slug(self, s: str) -> str:
        s = (s or "").strip().replace(" ", "_")
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        return "".join(ch for ch in s if ch in allowed)

    def _prompt_new_csv_path(self) -> str | None:
        top = tk.Toplevel(self)
        top.title("Datos del experimento")
        top.transient(self.winfo_toplevel())
        top.grab_set()
        top.resizable(False, False)

        ttk.Label(top, text="Nombre (Nombre_Apellido):").grid(row=0, column=0, padx=8, pady=(10, 4), sticky="e")
        ent_nombre = ttk.Entry(top, width=28)
        ent_nombre.grid(row=0, column=1, padx=8, pady=(10, 4), sticky="w")

        ttk.Label(top, text="Fecha (YYYYMMDD):").grid(row=1, column=0, padx=8, pady=4, sticky="e")
        ent_fecha = ttk.Entry(top, width=16)
        ent_fecha.grid(row=1, column=1, padx=8, pady=4, sticky="w")
        ent_fecha.insert(0, datetime.now().strftime("%Y%m%d"))

        result = {"path": None}

        def aceptar():
            nombre = self._safe_slug(ent_nombre.get())
            fecha = self._safe_slug(ent_fecha.get())
            if not nombre:
                messagebox.showerror("Registro", "Ingresa un nombre válido.")
                return
            if not (len(fecha) == 8 and fecha.isdigit()):
                messagebox.showerror("Registro", "La fecha debe tener formato YYYYMMDD.")
                return
            filename = f"RegistroDatos_{nombre}_{fecha}.csv"
            path = os.path.join(self._reg_dir, filename)
            result["path"] = os.path.abspath(path)
            top.destroy()

        def cancelar():
            result["path"] = None
            top.destroy()

        btns = ttk.Frame(top)
        btns.grid(row=2, column=0, columnspan=2, pady=(8, 10))
        ttk.Button(btns, text="Aceptar", command=aceptar).pack(side="left", padx=6)
        ttk.Button(btns, text="Cancelar", command=cancelar).pack(side="left", padx=6)

        top.update_idletasks()
        parent = self.winfo_toplevel()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (top.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (top.winfo_height() // 2)
        top.geometry(f"+{x}+{y}")

        self.wait_window(top)
        return result["path"]

    def _append_csv(self, row_values):
        if not self._csv_path:
            return
        file_exists = os.path.exists(self._csv_path)
        try:
            os.makedirs(os.path.dirname(self._csv_path), exist_ok=True)
            with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=",")
                if not file_exists:
                    header = ["timestamp"] + SERIES_ORDER
                    w.writerow(header)
                w.writerow(row_values)
        except Exception as ex:
            print("[Graph] Error escribiendo CSV:", ex)

    # ========================= Limpieza =========================
    def _on_destroy(self, _e):
        for job in (self._graph_job, self._log_job, self._usb_monitor_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._graph_job = None
        self._log_job = None
        self._usb_monitor_job = None
