# gui/ventana_graph.py
import os
import csv
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .barra_navegacion import BarraNavegacion


# ====== Definición de variables que graficamos / registramos ======
# clave -> (etiqueta, unidad, índice_en_msg, escalar)
SERIES_DEF = {
    "T_horno1": ("Temperatura horno 1", "°C", 3, 1.0),
    "T_horno2": ("Temperatura horno 2", "°C", 4, 1.0),
    "T_omega1": ("Temperatura omega 1", "°C", 1, 1.0),
    "T_omega2": ("Temperatura omega 2", "°C", 2, 1.0),
    "T_cond1":  ("Temperatura condensador 1", "°C", 5, 1.0),
    "T_cond2":  ("Temperatura condensador 2", "°C", 6, 1.0),
    "P_mezcla": ("Presión mezcla", "bar", 7, 0.1),   # ÷10
    "P_H2":     ("Presión H2", "bar", 8, 0.1),       # ÷10
    "P_salida": ("Presión salida", "bar", 9, 0.1),   # ÷10
    "MFC_O2":   ("MFC O2", "mL/min", 10, 0.1),       # ÷10
    "MFC_CO2":  ("MFC CO2", "mL/min", 11, 0.1),      # ÷10
    "MFC_N2":   ("MFC N2", "mL/min", 12, 0.1),       # ÷10
    "MFC_H2":   ("MFC H2", "mL/min", 13, 0.1),       # ÷10
}

SERIES_ORDER = [
    "T_horno1", "T_horno2",
    "T_omega1", "T_omega2",
    "T_cond1", "T_cond2",
    "P_mezcla", "P_H2", "P_salida",
    "MFC_O2", "MFC_CO2", "MFC_N2", "MFC_H2",
]


class VentanaGraph(tk.Frame):
    """
    - Botón toggle "Iniciar gráfica": muestreo periódico del último snapshot (periodo configurable).
    - Botón "Pausar/Reanudar": congela/continúa el tiempo relativo sin borrar datos.
    - Botón toggle "Registro CSV": escribe cada 1 s (append con cabecera si no existe).
    - Checkboxes para elegir variables a graficar (si ninguna, se avisa).
    - Eje X relativo en MM:SS que arranca en 0; al detener se limpia todo.
    - on_rx_cmd5(partes): recibe $;5;...;! con datos; presiones y flujos se dividen entre 10.
    """

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Exponer la ventana al controlador para recibir CMD=5 desde su manejador central
        if hasattr(self.controlador, "__setattr__"):
            setattr(self.controlador, "_ventana_graph", self)

        # Estado
        self._graph_active = False
        self._graph_paused = False
        self._log_active = False
        self._graph_job = None
        self._log_job = None

        # Tiempo relativo y periodo
        self._elapsed_sec = 0               # segundos acumulados MM:SS
        self._sample_period = 5             # segundos por tick de gráfica
        self._max_points = max(1, (2 * 60 * 60) // self._sample_period)  # ~2 horas

        # Último snapshot normalizado (unidades finales)
        self._last_snapshot = None  # dict o None

        # Buffers para gráfica
        self._buffers = {k: [] for k in SERIES_ORDER}
        self._times = []  # lista de segundos relativos (float/int)

        # CSV path en raíz del proyecto
        self._csv_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "registro_proceso.csv")
        )

        # Matplotlib embebido
        self.fig = None
        self.ax = None
        self.mpl_canvas = None

        self._lines = {}          # key -> Line2D
        self._series_vars = {}    # key -> BooleanVar
        self._need_legend_refresh = True

        self._build_ui()
        self.bind("<Destroy>", self._on_destroy)

    # ========================= UI =========================
    def _build_ui(self):
        # Layout raíz: barra izq (col 0), contenido (col 1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=120)
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        # Contenido principal (col 1): dos columnas -> izquierda (panel controles), derecha (figura)
        wrap = ttk.Frame(self)
        wrap.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=0, minsize=300)  # panel izquierdo
        wrap.grid_columnconfigure(1, weight=1)               # figura

        # --------- Panel izquierdo (vertical) ---------
        left = ttk.Frame(wrap)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        left.grid_rowconfigure(2, weight=1)  # que la lista crezca
        left.grid_columnconfigure(0, weight=1)

        # Sección acciones
        acciones = ttk.LabelFrame(left, text="Acciones")
        acciones.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        acciones.grid_columnconfigure(0, weight=1)

        self.btn_graph = ttk.Button(acciones, text="Iniciar gráfica", command=self._toggle_graph)
        self.btn_graph.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 3))

        self.btn_pause = ttk.Button(acciones, text="Pausar", command=self._toggle_pause, state="disabled")
        self.btn_pause.grid(row=1, column=0, sticky="ew", padx=6, pady=3)

        self.btn_log = ttk.Button(acciones, text="Iniciar registro (CSV)", command=self._toggle_log)
        self.btn_log.grid(row=2, column=0, sticky="ew", padx=6, pady=3)

        per_row = ttk.Frame(acciones)
        per_row.grid(row=3, column=0, sticky="ew", padx=6, pady=(6, 6))
        ttk.Label(per_row, text="Periodo (s):").pack(side="left")
        self.var_period = tk.IntVar(value=self._sample_period)
        spn = ttk.Spinbox(
            per_row, from_=1, to=60, width=5, textvariable=self.var_period,
            command=self._on_period_change, justify="center"
        )
        spn.pack(side="left", padx=(6, 0))
        spn.bind("<Return>", lambda _e: self._on_period_change())
        spn.bind("<FocusOut>", lambda _e: self._on_period_change())

        # Sección selección de series (lista vertical)
        selbox = ttk.LabelFrame(left, text="Variables a graficar")
        selbox.grid(row=1, column=0, sticky="nsew")
        selbox.grid_columnconfigure(0, weight=1)

        # Botones utilitarios para selección
        tools = ttk.Frame(selbox)
        tools.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(tools, text="Seleccionar todo", command=self._select_all).pack(side="left")
        ttk.Button(tools, text="Ninguno", command=self._select_none).pack(side="left", padx=(6, 0))

        # Lista de checkboxes en una sola columna (vertical)
        checks = ttk.Frame(selbox)
        checks.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        selbox.grid_rowconfigure(1, weight=1)
        checks.grid_columnconfigure(0, weight=1)

        for i, key in enumerate(SERIES_ORDER):
            var = tk.BooleanVar(value=False)
            self._series_vars[key] = var
            label, unit, *_ = SERIES_DEF[key]
            cb = ttk.Checkbutton(checks, text=f"{label} [{unit}]", variable=var, command=self._refresh_legend_next)
            cb.grid(row=i, column=0, sticky="w", pady=2)

        # Estado
        self.lbl_status = ttk.Label(left, text="Gráfica: OFF   |   Registro: OFF")
        self.lbl_status.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        # --------- Panel derecho (figura) ---------
        fig_frame = ttk.Frame(wrap)
        fig_frame.grid(row=0, column=1, sticky="nsew")
        fig_frame.grid_rowconfigure(0, weight=1)
        fig_frame.grid_columnconfigure(0, weight=1)

        self.fig = Figure(figsize=(9, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Tiempo (MM:SS)")
        self.ax.set_ylabel("Valor")
        self.ax.grid(True, linestyle="--", alpha=0.3)

        # Formateador MM:SS del eje X (segundos relativos)
        def _fmt_mmss(x, _pos):
            total = int(max(0, x))
            m, s = divmod(total, 60)
            return f"{m:02d}:{s:02d}"
        self.ax.xaxis.set_major_formatter(FuncFormatter(_fmt_mmss))

        # Líneas por serie (vacías; se dibujan si la serie está seleccionada)
        for key in SERIES_ORDER:
            line, = self.ax.plot([], [], label=self._series_label(key))
            self._lines[key] = line

        self._need_legend_refresh = True
        self._refresh_legend()

        self.mpl_canvas = FigureCanvasTkAgg(self.fig, master=fig_frame)
        self.mpl_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    # ========================= RX / Snapshot =========================
    def on_rx_cmd5(self, partes):
        """Recibe $;5;...;!; normaliza presiones y flujos (÷10), temperaturas tal cual."""
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
            # Verificar selección
            if not any(v.get() for v in self._series_vars.values()):
                messagebox.showwarning("Gráfica", "Selecciona al menos una variable para graficar.")
                return
            # Arranque limpio
            self._reset_plot_buffers()
            self._graph_active = True
            self._graph_paused = False
            self.btn_graph.configure(text="Detener gráfica")
            self.btn_pause.configure(text="Pausar", state="normal")
            self._graph_tick()
        else:
            # Detener y limpiar todo
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
            # Reanudar ciclo
            if self._graph_job:
                try:
                    self.after_cancel(self._graph_job)
                except Exception:
                    pass
            self._graph_job = self.after(self._sample_period * 1000, self._graph_tick)
        self._update_status()

    def _toggle_log(self):
        if not self._log_active:
            self._log_active = True
            self.btn_log.configure(text="Detener registro (CSV)")
            self._log_tick()  # arranca ciclo 1 s
        else:
            self._log_active = False
            self.btn_log.configure(text="Iniciar registro (CSV)")
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
        self.lbl_status.configure(
            text=f"Gráfica: {status_g}   |   Registro: {'ON' if self._log_active else 'OFF'}   |   Periodo: {self._sample_period}s"
        )

    # ========================= Ciclos (after) =========================
    def _graph_tick(self):
        """Cada periodo: toma el último snapshot y actualiza buffers/figura."""
        if not self._graph_active or self._graph_paused:
            return

        if self._last_snapshot is not None:
            # avanza tiempo relativo
            self._elapsed_sec += self._sample_period
            t = self._elapsed_sec
            self._times.append(t)
            if len(self._times) > self._max_points:
                self._times = self._times[-self._max_points:]

            # Actualizar buffers por serie
            for key in SERIES_ORDER:
                val = self._last_snapshot.get(key, 0.0)
                buf = self._buffers[key]
                buf.append(val)
                if len(buf) > self._max_points:
                    self._buffers[key] = buf[-self._max_points:]

            # Redibujar
            self._redraw_plot()

        # Reprogramar
        self._graph_job = self.after(self._sample_period * 1000, self._graph_tick)

    def _log_tick(self):
        """Cada 1 s: escribe línea CSV con timestamp + snapshot (si hay snapshot)."""
        if not self._log_active:
            return

        if self._last_snapshot is not None:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [ts] + [self._last_snapshot.get(k, 0.0) for k in SERIES_ORDER]
            self._append_csv(row)

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

        # Eje X relativo desde 0 hasta el último tiempo
        xmax = max(xs) if xs else 1
        self.ax.set_xlim(left=0, right=xmax if xmax > 1 else 1)

        # Autoscale Y según series visibles
        self.ax.relim()
        self.ax.autoscale_view(scalex=False, scaley=True)

        self._refresh_legend()
        self.mpl_canvas.draw_idle()

    def _reset_plot_buffers(self):
        """Limpia buffers y reinicia el tiempo relativo a 0; deja la figura en blanco."""
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

    # ========================= Periodo =========================
    def _on_period_change(self):
        """Lee el Spinbox, lo limita a [1..60], aplica el nuevo periodo y recalcula ventana."""
        try:
            val = int(self.var_period.get())
        except Exception:
            val = self._sample_period
        val = max(1, min(60, val))
        if val != self._sample_period:
            self._sample_period = val
            self.var_period.set(val)
            # Recalcular ~2h de historia
            self._max_points = max(1, (2 * 60 * 60) // self._sample_period)
            # Reprogramar siguiente tick si está corriendo y no en pausa
            if self._graph_active and not self._graph_paused:
                if self._graph_job:
                    try:
                        self.after_cancel(self._graph_job)
                    except Exception:
                        pass
                self._graph_job = self.after(self._sample_period * 1000, self._graph_tick)
        self._update_status()

    # ========================= CSV helpers =========================
    def _append_csv(self, row_values):
        """
        row_values: [timestamp, serie1, serie2, ...] en el orden SERIES_ORDER.
        Crea cabecera si no existe el archivo.
        """
        file_exists = os.path.exists(self._csv_path)
        try:
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
        # Cancela timers si destruyen el frame
        for job in (self._graph_job, self._log_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._graph_job = None
        self._log_job = None
# gui/ventana_graph.py
import os
import csv
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .barra_navegacion import BarraNavegacion


# ====== Definición de variables que graficamos / registramos ======
# clave -> (etiqueta, unidad, índice_en_msg, escalar)
SERIES_DEF = {
    "T_horno1": ("Temperatura horno 1", "°C", 3, 1.0),
    "T_horno2": ("Temperatura horno 2", "°C", 4, 1.0),
    "T_omega1": ("Temperatura omega 1", "°C", 1, 1.0),
    "T_omega2": ("Temperatura omega 2", "°C", 2, 1.0),
    "T_cond1":  ("Temperatura condensador 1", "°C", 5, 1.0),
    "T_cond2":  ("Temperatura condensador 2", "°C", 6, 1.0),
    "P_mezcla": ("Presión mezcla", "bar", 7, 0.1),   # ÷10
    "P_H2":     ("Presión H2", "bar", 8, 0.1),       # ÷10
    "P_salida": ("Presión salida", "bar", 9, 0.1),   # ÷10
    "MFC_O2":   ("MFC O2", "mL/min", 10, 0.1),       # ÷10
    "MFC_CO2":  ("MFC CO2", "mL/min", 11, 0.1),      # ÷10
    "MFC_N2":   ("MFC N2", "mL/min", 12, 0.1),       # ÷10
    "MFC_H2":   ("MFC H2", "mL/min", 13, 0.1),       # ÷10
}

SERIES_ORDER = [
    "T_horno1", "T_horno2",
    "T_omega1", "T_omega2",
    "T_cond1", "T_cond2",
    "P_mezcla", "P_H2", "P_salida",
    "MFC_O2", "MFC_CO2", "MFC_N2", "MFC_H2",
]


class VentanaGraph(tk.Frame):
    """
    - Botón toggle "Iniciar gráfica": muestreo periódico del último snapshot (periodo configurable).
    - Botón "Pausar/Reanudar": congela/continúa el tiempo relativo sin borrar datos.
    - Botón toggle "Registro CSV": escribe cada 1 s (append con cabecera si no existe).
    - Checkboxes para elegir variables a graficar (si ninguna, se avisa).
    - Eje X relativo en MM:SS que arranca en 0; al detener se limpia todo.
    - on_rx_cmd5(partes): recibe $;5;...;! con datos; presiones y flujos se dividen entre 10.
    """

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Exponer la ventana al controlador para recibir CMD=5 desde su manejador central
        if hasattr(self.controlador, "__setattr__"):
            setattr(self.controlador, "_ventana_graph", self)

        # Estado
        self._graph_active = False
        self._graph_paused = False
        self._log_active = False
        self._graph_job = None
        self._log_job = None

        # Tiempo relativo y periodo
        self._elapsed_sec = 0               # segundos acumulados MM:SS
        self._sample_period = 5             # segundos por tick de gráfica
        self._max_points = max(1, (2 * 60 * 60) // self._sample_period)  # ~2 horas

        # Último snapshot normalizado (unidades finales)
        self._last_snapshot = None  # dict o None

        # Buffers para gráfica
        self._buffers = {k: [] for k in SERIES_ORDER}
        self._times = []  # lista de segundos relativos (float/int)

        # CSV path en raíz del proyecto
        self._csv_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "registro_proceso.csv")
        )

        # Matplotlib embebido
        self.fig = None
        self.ax = None
        self.mpl_canvas = None

        self._lines = {}          # key -> Line2D
        self._series_vars = {}    # key -> BooleanVar
        self._need_legend_refresh = True

        self._build_ui()
        self.bind("<Destroy>", self._on_destroy)

    # ========================= UI =========================
    def _build_ui(self):
        # Layout raíz: barra izq (col 0), contenido (col 1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=230)
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        # Contenido principal (col 1): dos columnas -> izquierda (panel controles), derecha (figura)
        wrap = ttk.Frame(self)
        wrap.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=0, minsize=300)  # panel izquierdo
        wrap.grid_columnconfigure(1, weight=1)               # figura

        # --------- Panel izquierdo (vertical) ---------
        left = ttk.Frame(wrap)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        left.grid_rowconfigure(2, weight=1)  # que la lista crezca
        left.grid_columnconfigure(0, weight=1)

        # Sección acciones
        acciones = ttk.LabelFrame(left, text="Acciones")
        acciones.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        acciones.grid_columnconfigure(0, weight=1)

        self.btn_graph = ttk.Button(acciones, text="Iniciar gráfica", command=self._toggle_graph)
        self.btn_graph.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 3))

        self.btn_pause = ttk.Button(acciones, text="Pausar", command=self._toggle_pause, state="disabled")
        self.btn_pause.grid(row=1, column=0, sticky="ew", padx=6, pady=3)

        self.btn_log = ttk.Button(acciones, text="Iniciar registro (CSV)", command=self._toggle_log)
        self.btn_log.grid(row=2, column=0, sticky="ew", padx=6, pady=3)

        per_row = ttk.Frame(acciones)
        per_row.grid(row=3, column=0, sticky="ew", padx=6, pady=(6, 6))
        ttk.Label(per_row, text="Periodo (s):").pack(side="left")
        self.var_period = tk.IntVar(value=self._sample_period)
        spn = ttk.Spinbox(
            per_row, from_=1, to=60, width=5, textvariable=self.var_period,
            command=self._on_period_change, justify="center"
        )
        spn.pack(side="left", padx=(6, 0))
        spn.bind("<Return>", lambda _e: self._on_period_change())
        spn.bind("<FocusOut>", lambda _e: self._on_period_change())

        # Sección selección de series (lista vertical)
        selbox = ttk.LabelFrame(left, text="Variables a graficar")
        selbox.grid(row=1, column=0, sticky="nsew")
        selbox.grid_columnconfigure(0, weight=1)

        # Botones utilitarios para selección
        tools = ttk.Frame(selbox)
        tools.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(tools, text="Seleccionar todo", command=self._select_all).pack(side="left")
        ttk.Button(tools, text="Ninguno", command=self._select_none).pack(side="left", padx=(6, 0))

        # Lista de checkboxes en una sola columna (vertical)
        checks = ttk.Frame(selbox)
        checks.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        selbox.grid_rowconfigure(1, weight=1)
        checks.grid_columnconfigure(0, weight=1)

        for i, key in enumerate(SERIES_ORDER):
            var = tk.BooleanVar(value=False)
            self._series_vars[key] = var
            label, unit, *_ = SERIES_DEF[key]
            cb = ttk.Checkbutton(checks, text=f"{label} [{unit}]", variable=var, command=self._refresh_legend_next)
            cb.grid(row=i, column=0, sticky="w", pady=2)

        # Estado
        self.lbl_status = ttk.Label(left, text="Gráfica: OFF   |   Registro: OFF")
        self.lbl_status.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        # --------- Panel derecho (figura) ---------
        fig_frame = ttk.Frame(wrap)
        fig_frame.grid(row=0, column=1, sticky="nsew")
        fig_frame.grid_rowconfigure(0, weight=1)
        fig_frame.grid_columnconfigure(0, weight=1)

        self.fig = Figure(figsize=(9, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Tiempo (MM:SS)")
        self.ax.set_ylabel("Valor")
        self.ax.grid(True, linestyle="--", alpha=0.3)

        # Formateador MM:SS del eje X (segundos relativos)
        def _fmt_mmss(x, _pos):
            total = int(max(0, x))
            m, s = divmod(total, 60)
            return f"{m:02d}:{s:02d}"
        self.ax.xaxis.set_major_formatter(FuncFormatter(_fmt_mmss))

        # Líneas por serie (vacías; se dibujan si la serie está seleccionada)
        for key in SERIES_ORDER:
            line, = self.ax.plot([], [], label=self._series_label(key))
            self._lines[key] = line

        self._need_legend_refresh = True
        self._refresh_legend()

        self.mpl_canvas = FigureCanvasTkAgg(self.fig, master=fig_frame)
        self.mpl_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    # ========================= RX / Snapshot =========================
    def on_rx_cmd5(self, partes):
        """Recibe $;5;...;!; normaliza presiones y flujos (÷10), temperaturas tal cual."""
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
            # Verificar selección
            if not any(v.get() for v in self._series_vars.values()):
                messagebox.showwarning("Gráfica", "Selecciona al menos una variable para graficar.")
                return
            # Arranque limpio
            self._reset_plot_buffers()
            self._graph_active = True
            self._graph_paused = False
            self.btn_graph.configure(text="Detener gráfica")
            self.btn_pause.configure(text="Pausar", state="normal")
            self._graph_tick()
        else:
            # Detener y limpiar todo
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
            # Reanudar ciclo
            if self._graph_job:
                try:
                    self.after_cancel(self._graph_job)
                except Exception:
                    pass
            self._graph_job = self.after(self._sample_period * 1000, self._graph_tick)
        self._update_status()

    def _toggle_log(self):
        if not self._log_active:
            self._log_active = True
            self.btn_log.configure(text="Detener registro (CSV)")
            self._log_tick()  # arranca ciclo 1 s
        else:
            self._log_active = False
            self.btn_log.configure(text="Iniciar registro (CSV)")
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
        self.lbl_status.configure(
            text=f"Gráfica: {status_g}   |   Registro: {'ON' if self._log_active else 'OFF'}   |   Periodo: {self._sample_period}s"
        )

    # ========================= Ciclos (after) =========================
    def _graph_tick(self):
        """Cada periodo: toma el último snapshot y actualiza buffers/figura."""
        if not self._graph_active or self._graph_paused:
            return

        if self._last_snapshot is not None:
            # avanza tiempo relativo
            self._elapsed_sec += self._sample_period
            t = self._elapsed_sec
            self._times.append(t)
            if len(self._times) > self._max_points:
                self._times = self._times[-self._max_points:]

            # Actualizar buffers por serie
            for key in SERIES_ORDER:
                val = self._last_snapshot.get(key, 0.0)
                buf = self._buffers[key]
                buf.append(val)
                if len(buf) > self._max_points:
                    self._buffers[key] = buf[-self._max_points:]

            # Redibujar
            self._redraw_plot()

        # Reprogramar
        self._graph_job = self.after(self._sample_period * 1000, self._graph_tick)

    def _log_tick(self):
        """Cada 1 s: escribe línea CSV con timestamp + snapshot (si hay snapshot)."""
        if not self._log_active:
            return

        if self._last_snapshot is not None:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [ts] + [self._last_snapshot.get(k, 0.0) for k in SERIES_ORDER]
            self._append_csv(row)

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

        # Eje X relativo desde 0 hasta el último tiempo
        xmax = max(xs) if xs else 1
        self.ax.set_xlim(left=0, right=xmax if xmax > 1 else 1)

        # Autoscale Y según series visibles
        self.ax.relim()
        self.ax.autoscale_view(scalex=False, scaley=True)

        self._refresh_legend()
        self.mpl_canvas.draw_idle()

    def _reset_plot_buffers(self):
        """Limpia buffers y reinicia el tiempo relativo a 0; deja la figura en blanco."""
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

    # ========================= Periodo =========================
    def _on_period_change(self):
        """Lee el Spinbox, lo limita a [1..60], aplica el nuevo periodo y recalcula ventana."""
        try:
            val = int(self.var_period.get())
        except Exception:
            val = self._sample_period
        val = max(1, min(60, val))
        if val != self._sample_period:
            self._sample_period = val
            self.var_period.set(val)
            # Recalcular ~2h de historia
            self._max_points = max(1, (2 * 60 * 60) // self._sample_period)
            # Reprogramar siguiente tick si está corriendo y no en pausa
            if self._graph_active and not self._graph_paused:
                if self._graph_job:
                    try:
                        self.after_cancel(self._graph_job)
                    except Exception:
                        pass
                self._graph_job = self.after(self._sample_period * 1000, self._graph_tick)
        self._update_status()

    # ========================= CSV helpers =========================
    def _append_csv(self, row_values):
        """
        row_values: [timestamp, serie1, serie2, ...] en el orden SERIES_ORDER.
        Crea cabecera si no existe el archivo.
        """
        file_exists = os.path.exists(self._csv_path)
        try:
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
        # Cancela timers si destruyen el frame
        for job in (self._graph_job, self._log_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._graph_job = None
        self._log_job = None
