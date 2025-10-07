"""
Panel de control para un Omega – táctil.
- Usa LabeledEntryNum para Setpoint, SVN, Banda P, Tiempo I, Tiempo D.
- Mantiene lógica de envío al Arduino y manejo de modos PID/Rampa.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

# Ventanas auxiliares
from .ventana_rampa import VentanaRampa
try:
    from .ventana_autotuning import VentanaAutotuning  # opcional si existe
except Exception:
    VentanaAutotuning = None  # type: ignore[assignment]

# Widgets reutilizables
from ui.widgets import TouchButton, LabeledEntryNum

# Constantes táctiles
try:
    from ui import constants as C
except Exception:
    class _C_:
        FONT_BASE = ("Calibri", 16)
        ENTRY_WIDTH = 12
        COMBO_WIDTH = 10
    C = _C_()


class PanelOmega(ttk.Frame):
    """Panel de un solo Omega con controles PID/Rampa y memoria."""

    def __init__(self, master, id_omega: int, controlador, arduino, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.id_omega = id_omega
        self.controlador = controlador
        self.arduino = arduino

        # Estado
        self.modo_control = tk.StringVar(value="PID")   # "PID" | "Rampa"
        self.memoria = tk.StringVar(value="M0")         # M0..M4
        self.setpoint_valor: int | None = None          # SP entero [0..600]
        self.estado_omega = tk.BooleanVar(value=False)  # Run/Stop

        self._modo_inicializado = False
        self._ultimo_modo_enviado: str | None = None

        # Layout columnas
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Título
        ttk.Label(self, text=f"Omega {id_omega}", style="Heading.TLabel").grid(
            row=0, column=0, columnspan=2, pady=(6, 8)
        )

        # Selector de modo
        selector = ttk.Frame(self)
        selector.grid(row=1, column=0, columnspan=2, pady=(0, 6))
        ttk.Radiobutton(
            selector, text="PID", variable=self.modo_control, value="PID",
            command=self._on_modo_cambiado
        ).pack(side="left", padx=6)
        ttk.Radiobutton(
            selector, text="Rampa", variable=self.modo_control, value="Rampa",
            command=self._on_modo_cambiado
        ).pack(side="left", padx=6)

        # --- PID: Setpoint + acciones ---
        self.frame_pid = ttk.Frame(self)
        self.frame_pid.grid_columnconfigure(0, weight=1)
        self.frame_pid.grid_columnconfigure(1, weight=1)

        campo_sp = LabeledEntryNum(self.frame_pid, "Setpoint:",
                                   width=getattr(C, "ENTRY_WIDTH", 12))
        campo_sp.grid(row=0, column=0, columnspan=2, sticky="w")
        campo_sp.bind_numeric(
            lambda entry, on_submit: self._abrir_teclado(entry, on_submit),
            on_submit=self._guardar_setpoint_int,
        )
        self.entry_setpoint = campo_sp.entry

        btns_pid = ttk.Frame(self.frame_pid)
        btns_pid.grid(row=1, column=0, columnspan=2, padx=5, pady=(8, 4), sticky="w")
        TouchButton(btns_pid, text="Enviar",
                    command=self.enviar_pid_solo_sp).grid(row=0, column=0, padx=(0, 8), sticky="w")
        TouchButton(btns_pid, text="Enviar parámetros",
                    command=self.enviar_parametros).grid(row=0, column=1, padx=(0, 8), sticky="w")
        TouchButton(btns_pid, text="Iniciar autotuning",
                    command=self.enviar_autotuning_directo).grid(row=0, column=2, padx=(0, 8), sticky="w")

        # --- Memoria ---
        self.frame_mem = ttk.Frame(self)
        self.frame_mem.grid_columnconfigure(0, weight=0)
        self.frame_mem.grid_columnconfigure(1, weight=1)
        ttk.Label(self.frame_mem, text="Memoria:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.combo_mem = ttk.Combobox(
            self.frame_mem,
            values=["M0", "M1", "M2", "M3", "M4"],
            textvariable=self.memoria,
            state="readonly",
            width=getattr(C, "COMBO_WIDTH", 10)
        )
        self.combo_mem.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.combo_mem.bind("<<ComboboxSelected>>", self._on_memoria_cambiada)

        # --- Parámetros PID (SVN, P, I, D) ---
        self.frame_param = ttk.Frame(self)
        self.frame_param.grid_columnconfigure(0, weight=1)
        self.frame_param.grid_columnconfigure(1, weight=1)

        campo_svn = LabeledEntryNum(self.frame_param, "SVN:",
                                    width=getattr(C, "ENTRY_WIDTH", 12))
        campo_svn.grid(row=0, column=0, columnspan=2, sticky="w")
        campo_svn.bind_numeric(lambda entry, on_submit: self._abrir_teclado(entry, on_submit))
        self.entry_svn = campo_svn.entry

        campo_bp = LabeledEntryNum(self.frame_param, "Banda P:",
                                   width=getattr(C, "ENTRY_WIDTH", 12))
        campo_bp.grid(row=1, column=0, columnspan=2, sticky="w")
        campo_bp.bind_numeric(lambda entry, on_submit: self._abrir_teclado(entry, on_submit))
        self.entry_bp = campo_bp.entry

        campo_ti = LabeledEntryNum(self.frame_param, "Tiempo I:",
                                   width=getattr(C, "ENTRY_WIDTH", 12))
        campo_ti.grid(row=2, column=0, columnspan=2, sticky="w")
        campo_ti.bind_numeric(lambda entry, on_submit: self._abrir_teclado(entry, on_submit))
        self.entry_ti = campo_ti.entry

        campo_td = LabeledEntryNum(self.frame_param, "Tiempo D:",
                                   width=getattr(C, "ENTRY_WIDTH", 12))
        campo_td.grid(row=3, column=0, columnspan=2, sticky="w")
        campo_td.bind_numeric(lambda entry, on_submit: self._abrir_teclado(entry, on_submit))
        self.entry_td = campo_td.entry

        # --- Rampa ---
        self.boton_rampa = TouchButton(self, text="Configurar rampa",
                                       command=self.abrir_ventana_rampa)
        self.btn_enviar_param_rampa = TouchButton(self, text="Enviar parámetros",
                                                  command=self.enviar_parametros)

        # --- Toggle Run/Stop ---
        self.btn_toggle = TouchButton(self, text=self._texto_toggle(),
                                      command=self._toggle_omega)

        # Inicializar vista
        self.actualizar_vista()
        self._aplicar_visibilidad_parametros()
        self._modo_inicializado = True
        self._ultimo_modo_enviado = self.modo_control.get()

    # ------------------------------------------------------------------
    # Teclado numérico (inyectado desde widgets)
    # ------------------------------------------------------------------
    def _abrir_teclado(self, entry: ttk.Entry, on_submit) -> None:
        from .teclado_numerico import TecladoNumerico  # import local para evitar costos al cargar
        TecladoNumerico(self, entry, on_submit=on_submit)

    # ------------------------------------------------------------------
    # Cambios de modo
    # ------------------------------------------------------------------
    def _on_modo_cambiado(self) -> None:
        self.actualizar_vista()
        self._enviar_cambio_modo()

    def _enviar_cambio_modo(self) -> None:
        if not self._modo_inicializado:
            return
        modo_actual = self.modo_control.get()
        if modo_actual == self._ultimo_modo_enviado:
            return
        modo_code = "1" if modo_actual == "PID" else "3"
        msg = f"$;2;{self.id_omega};{modo_code};6;!"
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
        self._ultimo_modo_enviado = modo_actual

    # ------------------------------------------------------------------
    # Toggle Run/Stop
    # ------------------------------------------------------------------
    def _texto_toggle(self) -> str:
        return "Run" if not self.estado_omega.get() else "Stop"

    def _toggle_omega(self) -> None:
        nuevo = not self.estado_omega.get()
        self.estado_omega.set(nuevo)
        self.btn_toggle.configure(text=self._texto_toggle())
        accion = "1" if nuevo else "0"
        mensaje = f"$;2;{self.id_omega};{accion};5;!"
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    def ui_set_omega_started(self) -> None:
        if not self.estado_omega.get():
            self.estado_omega.set(True)
            self.btn_toggle.configure(text=self._texto_toggle())

    # ------------------------------------------------------------------
    # Memorias
    # ------------------------------------------------------------------
    def _on_memoria_cambiada(self, _ev=None) -> None:
        self._aplicar_visibilidad_parametros()
        self._solicitar_parametros_memoria()

    def _solicitar_parametros_memoria(self) -> None:
        mem_idx = self._indice_memoria()
        msg = f"$;2;{self.id_omega};4;4;{mem_idx};!"
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _indice_memoria(self) -> int:
        try:
            val = self.combo_mem.get().strip().upper()
            return int(val.replace("M", ""))
        except Exception:
            return 0

    def _aplicar_visibilidad_parametros(self) -> None:
        if self.memoria.get().upper().strip() == "M4":
            self.frame_param.grid_remove()
        else:
            if not self.frame_param.winfo_ismapped():
                self.frame_param.grid()

    def actualizar_vista(self) -> None:
        """Muestra/oculta secciones según modo actual."""
        modo = self.modo_control.get()
        for w in (
            self.frame_pid,
            self.boton_rampa,
            self.frame_mem,
            self.frame_param,
            self.btn_enviar_param_rampa,
            self.btn_toggle,
        ):
            w.grid_forget()
        if modo == "PID":
            self.frame_pid.grid(row=2, column=0, columnspan=2, pady=(4, 0), sticky="n")
            self.frame_mem.grid(row=3, column=0, columnspan=2, padx=5, pady=(6, 2), sticky="w")
            if self.memoria.get().upper().strip() != "M4":
                self.frame_param.grid(row=4, column=0, columnspan=2, padx=5, pady=(2, 2), sticky="w")
            self.btn_toggle.grid(row=5, column=0, columnspan=2, padx=5, pady=(6, 10), sticky="w")
        else:
            self.boton_rampa.grid(row=2, column=0, padx=5, pady=(8, 0), sticky="w")
            self.frame_mem.grid(row=3, column=0, columnspan=2, padx=5, pady=(6, 2), sticky="w")
            if self.memoria.get().upper().strip() != "M4":
                self.frame_param.grid(row=4, column=0, columnspan=2, padx=5, pady=(2, 2), sticky="w")
            self.btn_enviar_param_rampa.grid(row=5, column=0, padx=5, pady=(6, 0), sticky="w")
            self.btn_toggle.grid(row=6, column=0, columnspan=2, padx=5, pady=(6, 10), sticky="w")

    # ------------------------------------------------------------------
    # Lectura/validación de valores
    # ------------------------------------------------------------------
    def _sp_trunc_capped(self, value) -> int:
        """Convierte a int y trunca en [0..600]."""
        try:
            n = int(float(value))
        except Exception:
            return 0
        return 600 if n > 600 else (0 if n < 0 else n)

    def _guardar_setpoint_int(self, valor_float) -> None:
        sp = self._sp_trunc_capped(valor_float)
        self.setpoint_valor = sp
        self.entry_setpoint.delete(0, tk.END)
        self.entry_setpoint.insert(0, str(sp))

    def _leer_int(self, entry: ttk.Entry, default: int = 0) -> int:
        txt = entry.get().strip()
        if not txt:
            return default
        try:
            return int(float(txt))
        except Exception:
            return default

    def _leer_bp_escalada(self, entry: ttk.Entry) -> int:
        """Banda P llega en décimas → escala x10 para protocolo."""
        txt = entry.get().strip()
        if not txt:
            return 0
        try:
            val = float(txt)
            return int(round(val * 10))
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Envíos al Arduino
    # ------------------------------------------------------------------
    def enviar_pid_solo_sp(self) -> None:
        if self.setpoint_valor is None:
            txt = self.entry_setpoint.get().strip()
            if not txt:
                return
            self.setpoint_valor = self._sp_trunc_capped(txt)
        else:
            self.setpoint_valor = self._sp_trunc_capped(self.setpoint_valor)
        mensaje = f"$;2;{self.id_omega};2;1;{self.setpoint_valor};!"
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    def enviar_parametros(self) -> None:
        svn = self._leer_int(self.entry_svn, default=0)
        bp10 = self._leer_bp_escalada(self.entry_bp)
        ti = self._leer_int(self.entry_ti, default=0)
        td = self._leer_int(self.entry_td, default=0)
        mem_idx = self._indice_memoria()
        mensaje = f"$;2;{self.id_omega};2;4;{mem_idx};{svn};{bp10};{ti};{td};!"
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    def enviar_autotuning_directo(self) -> None:
        mem_idx = self._indice_memoria()
        sp_txt = self.entry_setpoint.get().strip()
        sp = self._sp_trunc_capped(sp_txt if sp_txt else "0")
        if sp == 0:
            messagebox.showwarning(
                "Setpoint faltante",
                "Debe ingresar un valor de Setpoint (>0) para iniciar el autotuning",
            )
            return
        mensaje = f"$;2;{self.id_omega};2;2;{mem_idx};{sp};!"
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)
        # Asegurar que queda en Run visualmente
        if not self.estado_omega.get():
            self.estado_omega.set(True)
            self.btn_toggle.configure(text=self._texto_toggle())

    # ------------------------------------------------------------------
    # Ventanas auxiliares
    # ------------------------------------------------------------------
    def abrir_ventana_autotuning(self) -> None:
        if VentanaAutotuning is None:
            messagebox.showinfo("Autotuning", "La ventana de Autotuning no está disponible en este proyecto.")
            return
        if getattr(self, "_auto_win", None) and self._auto_win.winfo_exists():
            self._auto_win.lift()
            return
        self._auto_win = VentanaAutotuning(self, self.id_omega, self.arduino)

    def abrir_ventana_rampa(self) -> None:
        if getattr(self, "_rampa_win", None) and self._rampa_win.winfo_exists():
            self._rampa_win.lift()
            return
        self._rampa_win = VentanaRampa(self, self.id_omega, self.arduino)
        app = getattr(self, "controlador", None)
        if app is not None:
            if not hasattr(app, "_rampa_wins"):
                app._rampa_wins = {}
            app._rampa_wins[self.id_omega] = self._rampa_win

    # ------------------------------------------------------------------
    # API pública para aplicar datos recibidos
    # ------------------------------------------------------------------
    def cargar_desde_arduino(self, modo, sp, mem, svn, p, i, d) -> None:
        """Carga estado desde 7 valores en el orden: modo, sp, mem, svn, p, i, d."""
        try:
            modo_str = "PID" if str(modo) in ("1", "PID") else "Rampa"
            self.modo_control.set(modo_str)
            self._ultimo_modo_enviado = modo_str  # no reenviar al cambiar vista
        except Exception:
            pass

        try:
            self.entry_setpoint.delete(0, tk.END)
            self.entry_setpoint.insert(0, str(int(float(sp))))
            self.setpoint_valor = self._sp_trunc_capped(sp)
        except Exception:
            pass

        try:
            m = f"M{int(mem)}" if str(mem).isdigit() else str(mem).upper()
            self.memoria.set(m)
            self.combo_mem.set(m)
            self._aplicar_visibilidad_parametros()
        except Exception:
            pass

        # Parámetros
        def _set(entry: ttk.Entry, val) -> None:
            try:
                entry.delete(0, tk.END)
                entry.insert(0, str(int(float(val))))
            except Exception:
                pass

        _set(self.entry_svn, svn)
        _set(self.entry_bp, float(p) / 10.0)  # banda P viene x10
        _set(self.entry_ti, i)
        _set(self.entry_td, d)

        # Actualizar layout según modo
        self.actualizar_vista()

    def aplicar_parametros(self, svn, p, i, d) -> None:
        """Aplica parámetros SVN/P/I/D en UI (P viene x10)."""
        def _set(entry: ttk.Entry, val) -> None:
            try:
                entry.delete(0, tk.END)
                entry.insert(0, str(int(float(val))))
            except Exception:
                pass
        _set(self.entry_svn, svn)
        _set(self.entry_bp, float(p) / 10.0)
        _set(self.entry_ti, i)
        _set(self.entry_td, d)
