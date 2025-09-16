# gui/ventana_graph.py
import os
import csv
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from .barra_navegacion import BarraNavegacion


# ====== Definición de variables que graficamos / registramos ======
# Mapeo: clave interna -> (etiqueta legible, unidad, índice_en_msg, escalar)
# * Índices en el mensaje CMD=5 (después del "5"):
#   1: T_omega1, 2: T_omega2, 3: T_horno1, 4: T_horno2,
#   5: T_cond1, 6: T_cond2,
#   7: P_mezcla, 8: P_H2, 9: P_salida,
#   10: MFC_O2, 11: MFC_CO2, 12: MFC_N2, 13: MFC_H2,
#   14: Potencia (NO se usa), 15: Uptime (NO se usa)
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

# Orden sugerido para UI/CSV
SERIES_ORDER = [
    "T_horno1", "T_horno2",
    "T_omega1", "T_omega2",
    "T_cond1", "T_cond2",
    "P_mezcla", "P_H2", "P_salida",
    "MFC_O2", "MFC_CO2", "MFC_N2", "MFC_H2",
]

# tope de puntos en memoria para la gráfica (2h a 5s ≈ 1440)
MAX_POINTS = 2 * 60 * 60 // 5


class VentanaGraph(tk.Frame):
    """
    - Botón toggle "Activar gráfica": muestreo cada 5 s (no bloqueante) de self._last_snapshot
    - Botón toggle "Registrar valores": escribe CSV cada 1 s (append, con cabecera si no existe)
    - Checkboxes para elegir variables a graficar (si ninguna marcada, se avisa y no inicia)
    - Gráfica matplotlib embebida en Tk
    - Método público on_rx_cmd5(partes) para alimentar la ventana con el último snapshot
    """

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Exponer la ventana al controlador para recibir CMD=5
        # (tu manejador central hace: getattr(self, "_ventana_graph", None))
        if hasattr(self.controlador, "__setattr__"):
            setattr(self.controlador, "_ventana_graph", self)

        # Estado
        self._graph_active = False
        self._log_active = False
        self._graph_job = None
        self._log_job = None

        # Último snapshot normalizado (unidades finales)
        self._last_snapshot = None  # dict o None

        # Buffers para gráfica
        self._buffers = {k: [] for k in SERIES_ORDER}
        self._times = []  # datetime

        # CSV path en raíz del proyecto
        self._csv_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "registro_proceso.csv")
        )

        # Matplotlib embebido
        self.fig = None
        self.ax = None
        self.mpl_canvas = None  # <- IMPORTANTE: canvas de Matplotlib

        self._lines = {}  # key -> Line2D
        self._series_vars = {}  # key -> BooleanVar
        self._need_legend_refresh = True

        self._build_ui()

        # Cancelar timers si destruyen el frame (evita callbacks huérfanos)
        self.bind("<Destroy>", self._on_destroy)

    # ========================= UI =========================
    def _build_ui(self):
        # Layout: barra izq (col 0), contenido (col 1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=230)
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        # Contenido
        wrap = ttk.Frame(self)
        wrap.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        wrap.grid_rowconfigure(2, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        # Controles superiores
        controls = ttk.Frame(wrap)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        controls.grid_columnconfigure(6, weight=1)

        self.btn_graph = ttk.Button(controls, text="Activar gráfica", command=self._toggle_graph)
        self.btn_graph.grid(row=0, column=0, padx=4)

        self.btn_log = ttk.Button(controls, text="Iniciar registro (CSV)", command=self._toggle_log)
        self.btn_log.grid(row=0, column=1, padx=4)

        ttk.Button(controls, text="Seleccionar todo", command=self._select_all).grid(row=0, column=3, padx=(20, 4))
        ttk.Button(controls, text="Ninguno", command=self._select_none).grid(row=0, column=4, padx=4)

        self.lbl_status = ttk.Label(controls, text="Gráfica: OFF   |   Registro: OFF")
        self.lbl_status.grid(row=0, column=5, padx=10, sticky="w")

        # Selección de series (checkboxes)
        selbox = ttk.LabelFrame(wrap, text="Variables a graficar")
        selbox.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        cols = 3
        for i, key in enumerate(SERIES_ORDER):
            row, col = divmod(i, cols)
            var = tk.BooleanVar(value=False)
            self._series_vars[key] = var
            label, unit, *_ = SERIES_DEF[key]
            cb = ttk.Checkbutton(selbox, text=f"{label} [{unit}]", variable=var, command=self._refresh_legend_next)
            cb.grid(row=row, column=col, sticky="w", padx=6, pady=2)
        for c in range(cols):
            selbox.grid_columnconfigure(c, weight=1)

        # Figura matplotlib
        fig_frame = ttk.Frame(wrap)
        fig_frame.grid(row=2, column=0, sticky="nsew")
        fig_frame.grid_rowconfigure(0, weight=1)
        fig_frame.grid_columnconfigure(0, weight=1)

        self.fig = Figure(figsize=(7, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Tiempo")
        self.ax.set_ylabel("Valor")
        self.ax.grid(True, linestyle="--", alpha=0.3)

        # --- Formato de tiempo HH:MM en el eje X ---
        locator = mdates.AutoDateLocator(minticks=3, maxticks=8)
        formatter = mdates.DateFormatter("%H:%M:%S")
        self.ax.xaxis.set_major_locator(locator)
        self.ax.xaxis.set_major_formatter(formatter)
        self.fig.autofmt_xdate()  # opcional: inclina etiquetas si hace falta

        # Crear línea por serie (se vacían si no están seleccionadas)
        self._lines = {}
        for key in SERIES_ORDER:
            line, = self.ax.plot([], [], label=self._series_label(key))
            self._lines[key] = line

        self._need_legend_refresh = True
        self._refresh_legend()

        self.mpl_canvas = FigureCanvasTkAgg(self.fig, master=fig_frame)
        self.mpl_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    # ========================= RX / Snapshot =========================
    def on_rx_cmd5(self, partes):
        """
        Llamar desde el manejador central cuando llegue: $;5;...;!
        'partes' es la lista de tokens sin '$' ni '!' (p.ej. ['5','omega1','omega2',...])
        Normaliza presiones (÷10) y flujos (÷10). Temperaturas igual.
        """
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
                # Redondeo suave
                if key.startswith("P_") or key.startswith("MFC_"):
                    val = round(val, 1)
                snap[key] = val

            self._last_snapshot = snap

        except Exception as ex:
            print("[Graph] Error parseando CMD=5:", ex)

    # ========================= Toggle actions =========================
    def _toggle_graph(self):
        if not self._graph_active:
            # Verificar que haya al menos una serie seleccionada
            if not any(v.get() for v in self._series_vars.values()):
                messagebox.showwarning("Gráfica", "Selecciona al menos una variable para graficar.")
                return
            self._graph_active = True
            self.btn_graph.configure(text="Detener gráfica")
            self._graph_tick()  # arranca ciclo 5 s
        else:
            self._graph_active = False
            self.btn_graph.configure(text="Activar gráfica")
            if self._graph_job:
                try:
                    self.after_cancel(self._graph_job)
                except Exception:
                    pass
                self._graph_job = None
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
        self.lbl_status.configure(
            text=f"Gráfica: {'ON' if self._graph_active else 'OFF'}   |   Registro: {'ON' if self._log_active else 'OFF'}"
        )

    # ========================= Ciclos (after) =========================
    def _graph_tick(self):
        """Cada 5 s: toma el último snapshot y actualiza buffers y figura."""
        if not self._graph_active:
            return

        if self._last_snapshot is not None:
            now = datetime.now()
            self._times.append(now)
            if len(self._times) > MAX_POINTS:
                self._times = self._times[-MAX_POINTS:]

            # Actualizar buffers por serie
            for key in SERIES_ORDER:
                val = self._last_snapshot.get(key, 0.0)
                buf = self._buffers[key]
                buf.append(val)
                if len(buf) > MAX_POINTS:
                    self._buffers[key] = buf[-MAX_POINTS:]

            # Redibujar
            self._redraw_plot()

        # Reprogramar
        self._graph_job = self.after(5000, self._graph_tick)

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

        # Mostrar en leyenda solo las series seleccionadas
        handles = []
        labels = []
        for key in SERIES_ORDER:
            if self._series_vars[key].get():
                handles.append(self._lines[key])
                labels.append(self._series_label(key))

        # Limpiar leyenda previa
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

        # Actualizar data en líneas (las no seleccionadas se vacían)
        xs = self._times
        for key in SERIES_ORDER:
            ln = self._lines[key]
            if self._series_vars[key].get():
                ln.set_data(xs, self._buffers[key])
            else:
                ln.set_data([], [])

        # Autoscale y eje tiempo
        self.ax.relim()
        self.ax.autoscale_view()
        self.fig.autofmt_xdate()

        self._refresh_legend()  # por si cambió la selección
        self.mpl_canvas.draw_idle()

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
