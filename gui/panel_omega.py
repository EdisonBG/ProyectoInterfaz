"""
Panel de control para un Omega – v3: usa LabeledEntryNum para Setpoint y PID.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from .ventana_rampa import VentanaRampa
from .teclado_numerico import TecladoNumerico
from .ventana_autotuning import VentanaAutotuning
from ui.widgets import TouchButton, LabeledEntryNum


class PanelOmega(ttk.Frame):
    def __init__(self, master, id_omega: int, controlador, arduino, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.id_omega = id_omega
        self.controlador = controlador
        self.arduino = arduino

        self.modo_control = tk.StringVar(value="PID")
        self.memoria = tk.StringVar(value="M0")
        self.setpoint_valor: int | None = None
        self.estado_omega = tk.BooleanVar(value=False)

        self._modo_inicializado = False
        self._ultimo_modo_enviado: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        ttk.Label(self, text=f"Omega {id_omega}", style="Heading.TLabel").grid(
            row=0, column=0, columnspan=2, pady=(6, 8)
        )

        selector = ttk.Frame(self)
        selector.grid(row=1, column=0, columnspan=2, pady=(0, 6))
        ttk.Radiobutton(selector, text="PID", variable=self.modo_control, value="PID", command=self._on_modo_cambiado).pack(side="left", padx=6)
        ttk.Radiobutton(selector, text="Rampa", variable=self.modo_control, value="Rampa", command=self._on_modo_cambiado).pack(side="left", padx=6)

        # PID: Setpoint + botones
        self.frame_pid = ttk.Frame(self)
        self.frame_pid.grid_columnconfigure(0, weight=1)
        self.frame_pid.grid_columnconfigure(1, weight=1)

        campo_sp = LabeledEntryNum(self.frame_pid, "Setpoint:", width=10)
        campo_sp.grid(row=0, column=0, columnspan=2, sticky="w")
        campo_sp.bind_numeric(
            lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
            on_submit=self._guardar_setpoint_int,
        )
        self.entry_setpoint = campo_sp.entry

        btns_pid = ttk.Frame(self.frame_pid)
        btns_pid.grid(row=1, column=0, columnspan=2, padx=5, pady=(8, 4), sticky="w")
        TouchButton(btns_pid, text="Enviar", command=self.enviar_pid_solo_sp).grid(row=0, column=0, padx=(0, 8), pady=0, sticky="w")
        TouchButton(btns_pid, text="Enviar parámetros", command=self.enviar_parametros).grid(row=0, column=1, padx=(0, 8), pady=0, sticky="w")
        TouchButton(btns_pid, text="Iniciar autotuning", command=self.enviar_autotuning_directo).grid(row=0, column=2, padx=(0, 8), pady=0, sticky="w")

        # Memoria
        self.frame_mem = ttk.Frame(self)
        self.frame_mem.grid_columnconfigure(0, weight=0)
        self.frame_mem.grid_columnconfigure(1, weight=1)
        ttk.Label(self.frame_mem, text="Memoria:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.combo_mem = ttk.Combobox(self.frame_mem, values=["M0", "M1", "M2", "M3", "M4"], textvariable=self.memoria, state="readonly", width=6)
        self.combo_mem.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.combo_mem.bind("<<ComboboxSelected>>", self._on_memoria_cambiada)

        # Parámetros PID (SVN, P, I, D)
        self.frame_param = ttk.Frame(self)
        self.frame_param.grid_columnconfigure(0, weight=1)
        self.frame_param.grid_columnconfigure(1, weight=1)

        campo_svn = LabeledEntryNum(self.frame_param, "SVN:", width=10)
        campo_svn.grid(row=0, column=0, columnspan=2, sticky="w")
        campo_svn.bind_numeric(lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit))
        self.entry_svn = campo_svn.entry

        campo_bp = LabeledEntryNum(self.frame_param, "Banda P:", width=10)
        campo_bp.grid(row=1, column=0, columnspan=2, sticky="w")
        campo_bp.bind_numeric(lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit))
        self.entry_bp = campo_bp.entry

        campo_ti = LabeledEntryNum(self.frame_param, "Tiempo I:", width=10)
        campo_ti.grid(row=2, column=0, columnspan=2, sticky="w")
        campo_ti.bind_numeric(lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit))
        self.entry_ti = campo_ti.entry

        campo_td = LabeledEntryNum(self.frame_param, "Tiempo D:", width=10)
        campo_td.grid(row=3, column=0, columnspan=2, sticky="w")
        campo_td.bind_numeric(lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit))
        self.entry_td = campo_td.entry

        # Rampa
        self.boton_rampa = TouchButton(self, text="Configurar rampa", command=self.abrir_ventana_rampa)
        self.btn_enviar_param_rampa = TouchButton(self, text="Enviar parámetros", command=self.enviar_parametros)

        # Toggle
        self.btn_toggle = TouchButton(self, text=self._texto_toggle(), command=self._toggle_omega)

        self.actualizar_vista()
        self._aplicar_visibilidad_parametros()
        self._modo_inicializado = True
        self._ultimo_modo_enviado = self.modo_control.get()

    # (resto de la clase: igual a v2, con los mismos métodos públicos y helpers)

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

    def _on_memoria_cambiada(self, _ev=None) -> None:
        self._aplicar_visibilidad_parametros()
        self._solicitar_parametros_memoria()

    def _solicitar_parametros_memoria(self) -> None:
        mem_idx = self._indice_memoria()
        msg = f"$;2;{self.id_omega};4;4;{mem_idx};!"
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _aplicar_visibilidad_parametros(self) -> None:
        if self.memoria.get().upper().strip() == "M4":
            self.frame_param.grid_remove()
        else:
            if not self.frame_param.winfo_ismapped():
                self.frame_param.grid()

    def actualizar_vista(self) -> None:
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

    def _indice_memoria(self) -> int:
        try:
            val = self.combo_mem.get().strip().upper()
            return int(val.replace("M", ""))
        except Exception:
            return 0

    def _sp_trunc_capped(self, value) -> int:
        try:
            n = int(float(value))
        except Exception:
            return 0
        return 600 if n > 600 else n

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
        txt = entry.get().strip()
        if not txt:
            return 0
        try:
            val = float(txt)
            return int(round(val * 10))
        except Exception:
            return 0

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
        if not self.estado_omega.get():
            self.estado_omega.set(True)
            self.btn_toggle.configure(text=self._texto_toggle())

    def abrir_ventana_autotuning(self) -> None:
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
