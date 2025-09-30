# gui/ventana_graph.py
import os
import re
import csv
import platform
import shutil
import signal
import subprocess
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox

try:
    from tkcalendar import DateEntry  # opcional
    _HAS_TKCAL = True
except Exception:
    _HAS_TKCAL = False

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico


# ====== Definición de variables que graficamos / registramos ======
# clave -> (etiqueta, unidad, índice_en_msg, escalar)
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
    "T_horno1", "T_horno2",
    "T_omega1", "T_omega2",
    "T_cond1", "T_cond2",
    "P_mezcla", "P_H2", "P_salida",
    "MFC_O2", "MFC_CO2", "MFC_N2", "MFC_H2",
]


# ========== Teclado del sistema (Windows / Linux-RPi) ==========
class _TecladoSistema:
    """
    Abre/cierra teclado en pantalla del SO.
    - Windows: TabTip/OSK evitando UAC en lo posible.
    - Linux/Raspberry: 'onboard' (dock inferior via gsettings) o 'matchbox-keyboard'.
    Asegura cierre al destruir.
    """
    def __init__(self):
        self._proc = None
        self._is_win = platform.system().lower().startswith("win")
        self._is_linux = platform.system().lower().startswith("lin")
        if self._is_win:
            self._tabtip = r"C:\Program Files\Common Files\Microsoft Shared\ink\TabTip.exe"
            self._osk = "osk.exe"

    def abrir(self):
        if self._proc and self._proc.poll() is None:
            return
        if self._is_win:
            self._abrir_windows()
            return
        if self._is_linux:
            self._abrir_linux()

    def cerrar(self):
        # cierre suave
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                try:
                    os.kill(self._proc.pid, signal.SIGTERM)
                except Exception:
                    pass
        # respaldo por nombre (por si el hijo lanzó a su vez otro proceso)
        if self._is_linux:
            self._pkill("onboard")
            self._pkill("matchbox-keyboard")
        self._proc = None

    # ---- Windows ----
    def _abrir_windows(self):
        # cadena de intentos para minimizar UAC
        for target in (self._tabtip, self._osk):
            if self._try_launch_win(target):
                return
        print("[Graph] No se pudo abrir teclado (Windows).")

    def _try_launch_win(self, target: str) -> bool:
        try:
            self._proc = subprocess.Popen(["explorer.exe", target])
            return True
        except Exception:
            pass
        try:
            # PowerShell Start-Process sin ventana
            self._proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                 "Start-Process", target],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            return True
        except Exception:
            pass
        try:
            self._proc = subprocess.Popen(f'start "" "{target}"', shell=True)
            return True
        except Exception:
            pass
        try:
            self._proc = subprocess.Popen([target])
            return True
        except Exception:
            return False

    # ---- Linux/RPi ----
    def _abrir_linux(self):
        # Preferir 'onboard' (dock inferior)
        if shutil.which("onboard"):
            self._config_onboard_bottom()
            try:
                self._proc = subprocess.Popen(["onboard"],
                                              stdout=subprocess.DEVNULL,
                                              stderr=subprocess.DEVNULL)
                return
            except Exception as e:
                print("[Graph] No se pudo abrir onboard:", e)
        # Fallback
        if shutil.which("matchbox-keyboard"):
            try:
                self._proc = subprocess.Popen(["matchbox-keyboard"],
                                              stdout=subprocess.DEVNULL,
                                              stderr=subprocess.DEVNULL)
                return
            except Exception as e:
                print("[Graph] No se pudo abrir matchbox-keyboard:", e)
        print("[Graph] No se encontró 'onboard' ni 'matchbox-keyboard'.")

    def _config_onboard_bottom(self):
        def _gs(schema, key, value):
            try:
                subprocess.run(
                    ["gsettings", "set", schema, key, value],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass
        _gs("org.onboard.window", "docking-enabled", "true")
        _gs("org.onboard.window", "dock-expand", "true")
        _gs("org.onboard.window", "dock-edge", "bottom")
        _gs("org.onboard.window", "landscape-height", "220")

    def _pkill(self, name: str):
        try:
            if shutil.which("pkill"):
                subprocess.run(["pkill", "-f", name], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


# ========== Diálogo de datos de experimento ==========
class _DialogoExperimento(tk.Toplevel):
    """
    Pide Nombre y Fecha para el CSV.
    - Mantiene foco en el Entry tras abrir el teclado (after).
    - Cierra teclado al aceptar/cancelar y al destruir.
    - Si hay tkcalendar, usa DateEntry; si no, Entry normal.
    """
    def __init__(self, master, *, on_ok):
        super().__init__(master)
        self.title("Datos del experimento")
        self.transient(master)
        self.resizable(False, False)
        self._on_ok = on_ok
        self._teclado = _TecladoSistema()

        # centrar/modo modal
        self.update_idletasks()
        self.geometry("+%d+%d" % (master.winfo_rootx() + 60, master.winfo_rooty() + 50))
        self.grab_set()

        # UI
        frm = ttk.Frame(self, padding=8)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.grid_columnconfigure(1, weight=1)

        ttk.Label(frm, text="Nombre (Nombre Apellido):").grid(row=0, column=0, sticky="e", padx=(0, 6), pady=6)
        self.ent_nombre = ttk.Entry(frm, width=32)
        self.ent_nombre.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(frm, text="Fecha:").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=6)
        if _HAS_TKCAL:
            self.ent_fecha = DateEntry(frm, date_pattern="yyyy-mm-dd", width=14)
            self.ent_fecha.set_date(datetime.now().date())
            self.ent_fecha.grid(row=1, column=1, sticky="w", pady=6)
        else:
            self.ent_fecha = ttk.Entry(frm, width=14)
            self.ent_fecha.insert(0, datetime.now().strftime("%Y-%m-%d"))
            self.ent_fecha.grid(row=1, column=1, sticky="w", pady=6)
            # con teclado numérico como apoyo si no hay tkcalendar
            self.ent_fecha.bind("<Button-1>", lambda e:
                TecladoNumerico(self, self.ent_fecha, on_submit=lambda v: self._set_and_focus(self.ent_fecha, v)))

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancelar", command=self._cancelar).grid(row=0, column=0, padx=6)
        ttk.Button(btns, text="Aceptar",  command=self._aceptar ).grid(row=0, column=1, padx=6)

        # Al abrir: teclado + foco (re-forzar foco después)
        self.after(50, self._abrir_teclado_y_enfocar)

        self.protocol("WM_DELETE_WINDOW", self._cancelar)

    def _set_and_focus(self, entry, value):
        entry.delete(0, tk.END)
        entry.insert(0, str(value))
        entry.focus_force()

    def _abrir_teclado_y_enfocar(self):
        # abrir teclado
        self._teclado.abrir()
        # re-forzar foco (el teclado a veces roba el foco)
        self.after(250, lambda: self.ent_nombre.focus_force())

    def _sanear_nombre(self, s: str) -> str:
        s = s.strip()
        # Permitir letras, números y guiones bajos; espacios -> guion bajo
        s = re.sub(r"\s+", "_", s)
        # quitar caracteres problemáticos en nombre de archivo
        s = re.sub(r"[^A-Za-z0-9_\-]", "", s)
        return s[:40] if s else "Usuario"

    def _leer_fecha(self) -> str:
        if _HAS_TKCAL:
            try:
                return self.ent_fecha.get_date().strftime("%Y-%m-%d")
            except Exception:
                pass
        # fallback Entry
        txt = (self.ent_fecha.get() or "").strip()
        try:
            # validar formato simple
            datetime.strptime(txt, "%Y-%m-%d")
            return txt
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")

    def _aceptar(self):
        nombre = self._sanear_nombre(self.ent_nombre.get())
        fecha = self._leer_fecha()
        try:
            self._on_ok(nombre, fecha)
        finally:
            self._teclado.cerrar()
            self.grab_release()
            self.destroy()

    def _cancelar(self):
        self._teclado.cerrar()
        self.grab_release()
        self.destroy()


class VentanaGraph(tk.Frame):
    """
    - Iniciar/Detener gráfica (muestreo del último snapshot cada _sample_period s).
    - Pausar/Reanudar.
    - Registro CSV con ventana táctil (Nombre/Fecha) -> cada 1 s escribe línea.
    - Checkboxes para elegir variables a graficar (si ninguna, se avisa).
    - Eje X:
        * 0..2 h: se expande.
        * >2 h: ventana deslizante de 2 h (se “corre” junto con el gráfico).
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
        self._elapsed_sec = 0
        self._sample_period = 5  # oculto en UI (dejamos 5 s por defecto)
        self._max_points = max(1, (2 * 60 * 60) // self._sample_period)  # ~2h de buffer visible

        # Último snapshot normalizado (unidades finales)
        self._last_snapshot = None  # dict o None

        # Buffers para gráfica
        self._buffers = {k: [] for k in SERIES_ORDER}
        self._times = []  # lista de segundos relativos

        # CSV: carpeta de registros y archivo actual (se fija al iniciar registro)
        self._reg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "registros_experimento"))
        os.makedirs(self._reg_dir, exist_ok=True)
        self._csv_path = None  # se define cuando el usuario introduce nombre/fecha

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

        # Barra navegación (149px de ancho)
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=149)
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        # Contenido principal
        wrap = ttk.Frame(self)
        wrap.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=0, minsize=200)  # panel izquierdo
        wrap.grid_columnconfigure(1, weight=1)               # figura grande

        # --------- Panel izquierdo (vertical) ---------
        left = ttk.Frame(wrap)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # Acciones (solo botones; sin periodo ni selector de csv)
        acciones = ttk.LabelFrame(left, text="Acciones")
        acciones.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        acciones.grid_columnconfigure(0, weight=1)

        self.btn_graph = ttk.Button(acciones, text="Iniciar gráfica", command=self._toggle_graph)
        self.btn_graph.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 3))

        self.btn_pause = ttk.Button(acciones, text="Pausar", command=self._toggle_pause, state="disabled")
        self.btn_pause.grid(row=1, column=0, sticky="ew", padx=6, pady=3)

        # Botón de Registro con estilo grande (similar a los de barra)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("BotonMenu.TButton",
                        font=("Arial", 10, "bold"),
                        padding=5,
                        foreground="white",
                        background="#007acc")
        self.btn_log = ttk.Button(acciones, text="Registro CSV", style="BotonMenu.TButton",
                                  command=self._toggle_log)
        self.btn_log.grid(row=2, column=0, sticky="ew", padx=6, pady=(6, 8))

        # Sección selección de series
        selbox = ttk.LabelFrame(left, text="Variables a graficar")
        selbox.grid(row=1, column=0, sticky="nsew")
        selbox.grid_columnconfigure(0, weight=1)

        checks = ttk.Frame(selbox)
        checks.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        selbox.grid_rowconfigure(0, weight=1)
        checks.grid_columnconfigure(0, weight=1)

        # Botones utilitarios
        tools = ttk.Frame(selbox)
        tools.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))
        ttk.Button(tools, text="Seleccionar todo", command=self._select_all).pack(side="left")
        ttk.Button(tools, text="Ninguno", command=self._select_none).pack(side="left", padx=(6, 0))

        for i, key in enumerate(SERIES_ORDER):
            var = tk.BooleanVar(value=False)
            self._series_vars[key] = var
            label, unit, *_ = SERIES_DEF[key]
            cb = ttk.Checkbutton(checks, text=f"{label} [{unit}]",
                                 variable=var, command=self._refresh_legend_next)
            cb.grid(row=i, column=0, sticky="w", pady=2)

        # Estado (leyenda simple)
        self.lbl_status = ttk.Label(left, text="Gráfica: OFF   |   Registro: OFF")
        self.lbl_status.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        # --------- Panel derecho (figura grande) ---------
        fig_frame = ttk.Frame(wrap)
        fig_frame.grid(row=0, column=1, sticky="nsew")
        fig_frame.grid_rowconfigure(0, weight=1)
        fig_frame.grid_columnconfigure(0, weight=1)

        self.fig = Figure(figsize=(9.5, 6.2), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Tiempo (MM:SS)")
        self.ax.set_ylabel("Valor")
        self.ax.grid(True, linestyle="--", alpha=0.3)

        # Formateador MM:SS del eje X
        def _fmt_mmss(x, _pos):
            total = int(max(0, x))
            m, s = divmod(total, 60)
            return f"{m:02d}:{s:02d}"
        self.ax.xaxis.set_major_formatter(FuncFormatter(_fmt_mmss))

        # Líneas por serie
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
            # pedir datos con diálogo táctil
            def _ok(nombre, fecha):
                # construir ruta segura
                fname = f"RegistroDatos_{nombre}_{fecha}.csv"
                fname = re.sub(r"[/\\]+", "_", fname)
                self._csv_path = os.path.join(self._reg_dir, fname)
                # arrancar registro
                self._log_active = True
                self.btn_log.configure(text="Detener registro")
                self._append_csv_header_if_needed()
                self._log_tick()

            _DialogoExperimento(self, on_ok=_ok)
        else:
            self._log_active = False
            self.btn_log.configure(text="Registro CSV")
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
            text=f"Gráfica: {status_g}   |   Registro: {'ON' if self._log_active else 'OFF'}"
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

        # Eje X:
        # - hasta 2h: [0 .. t]
        # - más de 2h: ventana deslizante de 2h
        if self._elapsed_sec <= 2 * 3600:
            xmax = max(xs) if xs else 1
            self.ax.set_xlim(left=0, right=xmax if xmax > 1 else 1)
        else:
            right = self._elapsed_sec
            left = right - 2 * 3600
            self.ax.set_xlim(left=left, right=right)

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

    # ========================= CSV helpers =========================
    def _append_csv_header_if_needed(self):
        if not self._csv_path:
            return
        file_exists = os.path.exists(self._csv_path)
        if file_exists:
            return
        try:
            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=",")
                header = ["timestamp"] + SERIES_ORDER
                w.writerow(header)
        except Exception as ex:
            print("[Graph] Error creando CSV:", ex)

    def _append_csv(self, row_values):
        """Append de una fila (ya con timestamp al inicio)."""
        if not self._csv_path:
            return
        try:
            with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=",")
                w.writerow(row_values)
        except Exception as ex:
            print("[Graph] Error escribiendo CSV:", ex)

    # ========================= Limpieza =========================
    def _on_destroy(self, _e):
        # Cancela timers
        for job in (self._graph_job, self._log_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._graph_job = None
        self._log_job = None
        # En caso de que quedara un teclado abierto por algún diálogo huérfano
        try:
            _TecladoSistema().cerrar()
        except Exception:
            pass
