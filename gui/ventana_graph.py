# gui/ventana_graph.py
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

import subprocess, os, signal, platform, shlex

# ====== PATCH: imports extra ======
import platform, subprocess, signal, re  # <- añadir
try:
    from tkcalendar import DateEntry     # <- añadir
    _HAS_TKCALENDAR = True
except Exception:
    _HAS_TKCALENDAR = False
# ==================================


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




class _TecladoSistema:
    """
    Abre/cierra teclado en pantalla del SO.
    - Windows: intenta lanzar TabTip/OSK por medio del shell (explorer / powershell / start)
               para evitar UAC 'requiere elevación'.
    - Linux: matchbox-keyboard (o 'onboard').
    """

    def __init__(self):
        self._proc = None
        self._is_windows = platform.system().lower().startswith("win")
        if self._is_windows:
            self._tabtip = r"C:\Program Files\Common Files\Microsoft Shared\ink\TabTip.exe"
            self._osk = "osk.exe"
        else:
            self._linux_cmds = [("matchbox-keyboard",), ("onboard",)]

    def abrir(self):
        # si ya hay uno vivo, no abras otro
        if self._proc and self._proc.poll() is None:
            return

        if self._is_windows:
            # ---- Cadena de intentos para TabTip ----
            if self._try_launch_win(self._tabtip):
                return
            # ---- Si TabTip no levantó, intenta OSK ----
            if self._try_launch_win(self._osk):
                return
            print("[Graph] No se pudo abrir teclado (Windows): agotados intentos.")
            self._proc = None
            return
        else:
            # Linux
            for cmd in self._linux_cmds:
                try:
                    self._proc = subprocess.Popen(cmd)
                    return
                except Exception as e:
                    print("[Graph] No se pudo abrir teclado:", cmd, "-", e)
            self._proc = None

    def cerrar(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                try:
                    os.kill(self._proc.pid, signal.SIGTERM)
                except Exception:
                    pass
        self._proc = None

    # ---------- Helpers Windows ----------
    def _try_launch_win(self, target_path_or_cmd: str) -> bool:
        """
        Intenta lanzar el teclado vía distintos mecanismos que no requieren elevación.
        Devuelve True si alguno funciona.
        """
        # 1) explorer.exe <ruta>
        try:
            self._proc = subprocess.Popen(["explorer.exe", target_path_or_cmd])
            return True
        except Exception as e:
            print("[Graph] explorer.exe fallo:", e)

        # 2) powershell Start-Process -WindowStyle Hidden -FilePath "<ruta>"
        try:
            ps_cmd = ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                      "Start-Process", shlex.quote(target_path_or_cmd)]
            self._proc = subprocess.Popen(ps_cmd, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception as e:
            print("[Graph] PowerShell Start-Process fallo:", e)

        # 3) start "" "<ruta>" (cmd) con shell=True
        try:
            cmdline = f'start "" "{target_path_or_cmd}"'
            self._proc = subprocess.Popen(cmdline, shell=True)
            return True
        except Exception as e:
            print("[Graph] cmd start fallo:", e)

        # 4) Último recurso: ejecución directa (probablemente vuelve a pedir elevación)
        try:
            self._proc = subprocess.Popen([target_path_or_cmd])
            return True
        except Exception as e:
            print("[Graph] Ejecución directa fallo:", e)
            return False


class VentanaGraph(tk.Frame):
    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # ====== PATCH: estado para CSV por experimento ======
        self._csv_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "registros_experimento")
        )
        os.makedirs(self._csv_dir, exist_ok=True)
        self._osk = _TecladoSistema()   # teclado del sistema
        # =====================================================

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

        # Periodo -> Entry con TecladoNum (no mostrar en estado para dejar más espacio a la gráfica)
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

        self.fig = Figure(figsize=(10.8, 5.3), dpi=100)  # más ancho para 1024x600
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
        
        # ------- NUEVO: ventana deslizante en X -------
        # Tamaño de ventana (en segundos) = max_points * periodo
        # - Mientras xmax <= ventana: muestra 0..xmax (como antes).
        # - Cuando xmax > ventana: desliza a [xmax-ventana, xmax].
        xmax = max(xs) if xs else 1
        win_sec = self._max_points * self._sample_period
        if xmax <= win_sec:
            left = 0
            right = xmax if xmax > 1 else 1
        else:
            left = xmax - win_sec
            right = xmax
        self.ax.set_xlim(left=left, right=right)
        # ----------------------------------------------

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

    # ========================= Toggle actions =========================
    def _toggle_log(self):
        if not self._log_active:
            # ====== PATCH: pedir nombre y fecha antes de arrancar ======
            meta = self._ask_csv_metadata()
            if not meta:
                return  # cancelado
            nombre_sanit, fecha_str = meta
            filename = f"RegistroDatos_{nombre_sanit}_{fecha_str}.csv"
            self._csv_path = os.path.join(self._csv_dir, filename)
            # ===========================================================

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

    # ====== PATCH: diálogo para Nombre + Fecha con teclado en pantalla ======
    def _ask_csv_metadata(self):
        """
        Abre un diálogo modal para pedir:
          - Nombre y apellido (Entry + teclado en pantalla del sistema)
          - Fecha (DateEntry si tkcalendar está disponible; si no, Entry texto)
        Devuelve (nombre_sanitizado, fecha_YYYYMMDD) o None si cancelado.
        """
        dlg = tk.Toplevel(self)
        dlg.title("Nuevo registro CSV")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.resizable(False, False)

        frm = ttk.Frame(dlg, padding=10)
        frm.grid(row=0, column=0)

        ttk.Label(frm, text="Nombre y apellido:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        ent_nombre = ttk.Entry(frm, width=32)
        ent_nombre.grid(row=0, column=1, sticky="w", padx=6, pady=6)

        # Abrir teclado en pantalla al enfocar el Entry de nombre
        ent_nombre.bind("<FocusIn>", lambda _e: self._osk.abrir())
        # Si quieres cerrarlo al salir del diálogo, lo hacemos al final (OK/Cancelar)

        ttk.Label(frm, text="Fecha:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        if _HAS_TKCALENDAR:
            # Calendario táctil
            ent_fecha = DateEntry(frm, date_pattern="yyyy-mm-dd", width=12)
            ent_fecha.grid(row=1, column=1, sticky="w", padx=6, pady=6)
        else:
            # Fallback simple
            ent_fecha = ttk.Entry(frm, width=12)
            ent_fecha.insert(0, datetime.now().strftime("%Y-%m-%d"))
            ent_fecha.grid(row=1, column=1, sticky="w", padx=6, pady=6)

        # Botones
        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, pady=(12, 0))
        ok_clicked = {"ok": False}

        def _ok():
            nombre = (ent_nombre.get() or "").strip()
            if not nombre:
                messagebox.showwarning("Registro CSV", "Ingresa el nombre y apellido.")
                ent_nombre.focus_set()
                return
            fecha_txt = ent_fecha.get() if _HAS_TKCALENDAR else (ent_fecha.get() or "").strip()
            # Validar fecha muy básica (YYYY-MM-DD)
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", fecha_txt):
                messagebox.showwarning("Registro CSV", "Selecciona/ingresa una fecha válida (YYYY-MM-DD).")
                return
            # Sanitizar nombre para archivo (letras, números, guión y guión bajo)
            nombre_sanit = re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñ0-9_-]+", "_", nombre).strip("_")
            # Formato de salida YYYYMMDD
            fecha_out = fecha_txt.replace("-", "")
            ok_clicked["ok"] = True
            dlg.destroy()

            # Cerrar teclado (si está abierto)
            self._osk.cerrar()

            ok_clicked["payload"] = (nombre_sanit, fecha_out)

        def _cancel():
            dlg.destroy()
            self._osk.cerrar()

        ttk.Button(btns, text="Cancelar", command=_cancel).grid(row=0, column=0, padx=6)
        ttk.Button(btns, text="Aceptar", command=_ok).grid(row=0, column=1, padx=6)

        # Foco inicial en nombre (para abrir teclado enseguida)
        ent_nombre.focus_set()

        # Enter = OK, Escape = Cancel
        dlg.bind("<Return>", lambda _e: _ok())
        dlg.bind("<Escape>", lambda _e: _cancel())

        # Centrar sobre la ventana principal
        dlg.update_idletasks()
        try:
            x0 = self.winfo_toplevel().winfo_rootx()
            y0 = self.winfo_toplevel().winfo_rooty()
            w0 = self.winfo_toplevel().winfo_width()
            h0 = self.winfo_toplevel().winfo_height()
            w, h = dlg.winfo_width(), dlg.winfo_height()
            dlg.geometry(f"+{x0 + (w0 - w)//2}+{y0 + (h0 - h)//2}")
        except Exception:
            pass

        dlg.wait_window()
        return ok_clicked.get("payload") if ok_clicked.get("ok") else None
    # =========================================================================
