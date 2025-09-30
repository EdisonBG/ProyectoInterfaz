# gui/ventana_graph.py (modificado para 1024x538 y ajuste automático del canvas)
import os
import sys
import csv
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico


# ====== Definición de variables que graficamos / registramos ======
SERIES_DEF = {
    "T_horno1": ("Temperatura horno 1", "°C", 3, 1.0),
    "T_horno2": ("Temperatura horno 2", "°C", 4, 1.0),
    "T_omega1": ("Temperatura omega 1", "°C", 1, 1.0),
    "T_omega2": ("Temperatura omega 2", "°C", 2, 1.0),
    "T_cond1":  ("Temperatura condensador 1", "°C", 5, 1.0),
    "T_cond2":  ("Temperatura condensador 2", "°C", 6, 1.0),
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


class VentanaGraph(tk.Frame):
    # --- Objetivo de layout fijo (área útil) ---
    _TARGET_W = 1024
    _TARGET_H = 538

    # Nav lateral (BarraNavegacion) y márgenes que usa el layout actual
    _NAV_W = 149    # ancho fijo de BarraNavegacion (según comentario en tu código)
    _PAD = 8        # paddings en el wrap (padx/pady)
    _LEFT_MIN = 172 # minsize del panel izquierdo de controles

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        if hasattr(self.controlador, "__setattr__"):
            setattr(self.controlador, "_ventana_graph", self)

        # Estado
        self._graph_active = False
        self._graph_paused = False
        self._log_active = False
        self._graph_job = None
        self._log_job = None

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
        self.bind("<Destroy>", self._on_destroy)

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
        wrap.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=0, minsize=172)  # compacto
        wrap.grid_columnconfigure(1, weight=1)               # gráfica grande

        # --------- Panel izquierdo (vertical) ---------
        left = ttk.Frame(wrap)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        acciones = ttk.LabelFrame(left, text="Acciones")
        acciones.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        acciones.grid_columnconfigure(0, weight=1)

        self.btn_graph = ttk.Button(acciones, text="Iniciar gráfica", command=self._toggle_graph)
        self.btn_graph.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 3))

        self.btn_pause = ttk.Button(acciones, text="Pausar", command=self._toggle_pause, state="disabled")
        self.btn_pause.grid(row=1, column=0, sticky="ew", padx=6, pady=3)

        self.btn_log = ttk.Button(acciones, text="Iniciar registro (CSV)", command=self._toggle_log)
        self.btn_log.grid(row=2, column=0, sticky="ew", padx=6, pady=3)

        # Periodo -> Entry con TecladoNum
        per_row = ttk.Frame(acciones)
        per_row.grid(row=3, column=0, sticky="ew", padx=6, pady=(6, 6))
        ttk.Label(per_row, text="Periodo (s):").pack(side="left")
        self.ent_period = ttk.Entry(per_row, width=6, justify="center")
        self.ent_period.pack(side="left", padx=(6, 0))
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
        selbox = ttk.LabelFrame(left, text="Variables a graficar")
        selbox.grid(row=1, column=0, sticky="nsew")
        selbox.grid_columnconfigure(0, weight=1)

        tools = ttk.Frame(selbox)
        tools.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(tools, text="Seleccionar todo", command=self._select_all).pack(side="left")
        ttk.Button(tools, text="Ninguno", command=self._select_none).pack(side="left", padx=(6, 0))

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

        # Estado (leyenda corta)
        self.lbl_status = ttk.Label(left, text="Gráfica: OFF   |   Registro: OFF")
        self.lbl_status.grid(row=3, column=0, sticky="ew", pady=(8, 0))

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
            path = self._prompt_new_csv_path()
            if not path:
                return
            self._csv_path = path
            self._log_active = True
            self.btn_log.configure(text="Detener registro (CSV)")
            self._log_tick()
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
        self.lbl_status.configure(text=f"Gráfica: {status_g}   |   Registro: {'ON' if self._log_active else 'OFF'}")

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
        for job in (self._graph_job, self._log_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._graph_job = None
        self._log_job = None
