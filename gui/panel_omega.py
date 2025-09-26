import tkinter as tk
from tkinter import ttk , messagebox
from .ventana_rampa import VentanaRampa
from .teclado_numerico import TecladoNumerico
from .ventana_autotuning import VentanaAutotuning


class PanelOmega(ttk.Frame):
    def __init__(self, master, id_omega, controlador, arduino, *args, **kwargs):
        super().__init__(master, *args, **kwargs)

        # === Identificacion y referencias ===
        self.id_omega = id_omega                 # Numero de Omega (1,2,..)
        self.controlador = controlador           # App para envio centralizado
        self.arduino = arduino                   # Fallback serial directo

        # === Estado interno ===
        self.modo_control = tk.StringVar(value="PID")  # 'PID' o 'Rampa'
        self.memoria = tk.StringVar(value="M0")        # M0..M4
        self.setpoint_valor = None
        self._ultimo_setpoint_enviado = None
        self.estado_omega = tk.BooleanVar(value=False)  # Run=False al inicio

        # Flag para no disparar envio de cambio de modo en la primera dibujada
        self._modo_inicializado = False
        self._ultimo_modo_enviado = None  # 'PID' o 'Rampa'

        # === Layout base ===
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # === Titulo ===
        ttk.Label(self, text=f"Omega {id_omega}", font=("Arial", 14, "bold"))\
            .grid(row=0, column=0, columnspan=2, pady=(6, 8))

        # selector PID/Rampa
        selector = ttk.Frame(self)
        selector.grid(row=1, column=0, columnspan=2, pady=(0, 6))
        ttk.Radiobutton(selector, text="PID", variable=self.modo_control,
                        value="PID", command=self._on_modo_cambiado).pack(side="left", padx=6)
        ttk.Radiobutton(selector, text="Rampa", variable=self.modo_control,
                        value="Rampa", command=self._on_modo_cambiado).pack(side="left", padx=6)

        # =================================================================
        # =================== CONTENEDOR PID (solo setpoint + botones) =====
        # =================================================================
        self.frame_pid = ttk.Frame(self)
        self.frame_pid.grid_columnconfigure(0, weight=0)
        self.frame_pid.grid_columnconfigure(1, weight=1)

        # Setpoint (solo en PID)
        ttk.Label(self.frame_pid, text="Setpoint:").grid(
            row=0, column=0, padx=5, pady=5, sticky="e")
        self.entry_setpoint = ttk.Entry(self.frame_pid, width=10)
        self.entry_setpoint.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.entry_setpoint.bind(
            "<Button-1>",
            lambda e: TecladoNumerico(
                self, self.entry_setpoint, on_submit=self._guardar_setpoint_int
            )
        )

        # Botones PID (Enviar SP, Enviar parametros, Iniciar autotuning)
        btns_pid = ttk.Frame(self.frame_pid)
        btns_pid.grid(row=1, column=0, columnspan=2,
                      padx=5, pady=(8, 4), sticky="w")

        self.btn_enviar_sp = ttk.Button(
            btns_pid, text="Enviar", command=self.enviar_pid_solo_sp)
        self.btn_enviar_sp.grid(
            row=0, column=0, padx=(0, 8), pady=0, sticky="w")

        self.btn_enviar_param = ttk.Button(
            btns_pid, text="Enviar parametros", command=self.enviar_parametros)
        self.btn_enviar_param.grid(
            row=0, column=1, padx=(0, 8), pady=0, sticky="w")

        self.btn_autotuning = ttk.Button(
            btns_pid, text="Iniciar autotuning", command=self.enviar_autotuning_directo)
        self.btn_autotuning.grid(
            row=0, column=2, padx=(0, 8), pady=0, sticky="w")

        # =================================================================
        # =========== MEMORIA + PARAMETROS (compartidos PID/Rampa) =========
        # =================================================================
        # Nota: ahora son hijos de self (no de frame_pid) para poder
        # colocarlos tanto en PID como en Rampa sin duplicacion.

        # Memoria (M0..M4)
        self.frame_mem = ttk.Frame(self)
        self.frame_mem.grid_columnconfigure(0, weight=0)
        self.frame_mem.grid_columnconfigure(1, weight=1)

        ttk.Label(self.frame_mem, text="Memoria:").grid(
            row=0, column=0, padx=5, pady=5, sticky="e")
        self.combo_mem = ttk.Combobox(
            self.frame_mem,
            values=["M0", "M1", "M2", "M3", "M4"],
            textvariable=self.memoria,
            state="readonly",
            width=6
        )

        self.combo_mem.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.combo_mem.bind("<<ComboboxSelected>>", self._on_memoria_cambiada)

        # Parametros PID (SVN, BP, TI, TD)
        self.frame_param = ttk.Frame(self)
        self.frame_param.grid_columnconfigure(0, weight=0)
        self.frame_param.grid_columnconfigure(1, weight=1)

        ttk.Label(self.frame_param, text="SVN:").grid(
            row=0, column=0, padx=5, pady=3, sticky="e")
        self.entry_svn = ttk.Entry(self.frame_param, width=10)
        self.entry_svn.grid(row=0, column=1, padx=5, pady=3, sticky="w")
        self.entry_svn.bind(
            "<Button-1>", lambda e: TecladoNumerico(self, self.entry_svn))

        ttk.Label(self.frame_param, text="Banda P:").grid(
            row=1, column=0, padx=5, pady=3, sticky="e")
        self.entry_bp = ttk.Entry(self.frame_param, width=10)
        self.entry_bp.grid(row=1, column=1, padx=5, pady=3, sticky="w")
        self.entry_bp.bind(
            "<Button-1>", lambda e: TecladoNumerico(self, self.entry_bp))

        ttk.Label(self.frame_param, text="Tiempo I:").grid(
            row=2, column=0, padx=5, pady=3, sticky="e")
        self.entry_ti = ttk.Entry(self.frame_param, width=10)
        self.entry_ti.grid(row=2, column=1, padx=5, pady=3, sticky="w")
        self.entry_ti.bind(
            "<Button-1>", lambda e: TecladoNumerico(self, self.entry_ti))

        ttk.Label(self.frame_param, text="Tiempo D:").grid(
            row=3, column=0, padx=5, pady=3, sticky="e")
        self.entry_td = ttk.Entry(self.frame_param, width=10)
        self.entry_td.grid(row=3, column=1, padx=5, pady=3, sticky="w")
        self.entry_td.bind(
            "<Button-1>", lambda e: TecladoNumerico(self, self.entry_td))

        # =================================================================
        # =================== MODO RAMPA ==================================
        # =================================================================
        self.boton_rampa = ttk.Button(
            self, text="Configurar Rampa", command=self.abrir_ventana_rampa)

        # Enviar parametros tambien disponible en Rampa
        self.btn_enviar_param_rampa = ttk.Button(
            self, text="Enviar parametros", command=self.enviar_parametros)

        # =================================================================
        # =================== TOGGLE RUN/STOP =============================
        # =================================================================
        self.btn_toggle = ttk.Button(
            self, text=self._texto_toggle(), command=self._toggle_omega)

        # Mostrar UI inicial
        self.actualizar_vista()
        # Ajustar visibilidad de parametros segun memoria
        self._aplicar_visibilidad_parametros()

        self._modo_inicializado = True
        self._ultimo_modo_enviado = self.modo_control.get()

    # ======= cambio PID/Rampa por el usuario =======
    def _on_modo_cambiado(self):
        """
        1) Reacomoda la UI.
        2) Envia el comando de cambio de modo SOLO si ya se inicializo y hay cambio real.
           $;2;ID_OMEGA;1|3;6;!
        """
        self.actualizar_vista()
        self._enviar_cambio_modo()  # centralizado con salvaguardas

    def _enviar_cambio_modo(self):
        """Envio protegido de cambio de modo (evita dobles y el primer armado)."""
        if not self._modo_inicializado:
            return
        modo_actual = self.modo_control.get()          # 'PID' o 'Rampa'
        if modo_actual == self._ultimo_modo_enviado:
            return
        modo_code = "1" if modo_actual == "PID" else "3"
        msg = f"$;2;{self.id_omega};{modo_code};6;!"
        print("[TX] Cambio de modo:", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
        self._ultimo_modo_enviado = modo_actual

    # ====================== Toggle Run/Stop ==========================
    def _texto_toggle(self) -> str:
        return "Run" if not self.estado_omega.get() else "Stop"

    def _toggle_omega(self):
        nuevo = not self.estado_omega.get()
        self.estado_omega.set(nuevo)
        self.btn_toggle.configure(text=self._texto_toggle())

        accion = "1" if nuevo else "0"
        mensaje = f"$;2;{self.id_omega};{accion};5;!"
        print("Mensaje toggle Omega:", mensaje)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    def ui_set_omega_started(self):
        if not self.estado_omega.get():
            self.estado_omega.set(True)
            self.btn_toggle.configure(text=self._texto_toggle())

    # =================== Memoria y parametros ========================
    def _on_memoria_cambiada(self, _ev=None):
        # Mostrar/ocultar bloque de parametros segun M4 o no
        self._aplicar_visibilidad_parametros()
        # Pedir al Arduino los parametros de la memoria recien seleccionada
        self._solicitar_parametros_memoria()

    def _solicitar_parametros_memoria(self):
        """
        Solicita al Arduino los parametros PID de la memoria seleccionada.
        Formato: $;2;ID_OMEGA;4;4;MEM;!
        """
        mem_idx = self._indice_memoria()
        msg = f"$;2;{self.id_omega};4;4;{mem_idx};!"
        print("Solicitando parametros PID:", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _aplicar_visibilidad_parametros(self):
        """
        Oculta los parametros si memoria=M4; los muestra en M0-M3.

        """
        if self.memoria.get().upper().strip() == "M4":
            self.frame_param.grid_remove()
        else:

            if not self.frame_param.winfo_ismapped():
                self.frame_param.grid()  # sera recolocado por actualizar_vista

    # =================== Cambio de modo (PID/Rampa) ==================
    def actualizar_vista(self):
        modo = self.modo_control.get()

        # Limpiar colocaciones previas
        for w in (self.frame_pid, self.boton_rampa, self.frame_mem,
                  self.frame_param, self.btn_enviar_param_rampa, self.btn_toggle):
            w.grid_forget()

        if modo == "PID":
            # PID: setpoint + botones propios
            self.frame_pid.grid(row=2, column=0, columnspan=2,
                                pady=(4, 0), sticky="n")
            # Memoria y parametros debajo del bloque PID
            self.frame_mem.grid(row=3, column=0, columnspan=2,
                                padx=5, pady=(6, 2), sticky="w")
            # Parametros (si memoria != M4)
            if self.memoria.get().upper().strip() != "M4":
                self.frame_param.grid(
                    row=4, column=0, columnspan=2, padx=5, pady=(2, 2), sticky="w")
            # Toggle al final
            self.btn_toggle.grid(row=5, column=0, columnspan=2,
                                 padx=5, pady=(6, 10), sticky="w")

        else:
            # Rampa: boton de configuracion
            self.boton_rampa.grid(row=2, column=0, padx=5,
                                  pady=(8, 0), sticky="w")
            # Memoria y parametros (mismos widgets, misma logica)
            self.frame_mem.grid(row=3, column=0, columnspan=2,
                                padx=5, pady=(6, 2), sticky="w")
            if self.memoria.get().upper().strip() != "M4":
                self.frame_param.grid(
                    row=4, column=0, columnspan=2, padx=5, pady=(2, 2), sticky="w")
            # Enviar parametros (rampa)
            self.btn_enviar_param_rampa.grid(
                row=5, column=0, padx=5, pady=(6, 0), sticky="w")
            # Toggle
            self.btn_toggle.grid(row=6, column=0, columnspan=2,
                                 padx=5, pady=(6, 10), sticky="w")

    # =================== Lectura de valores ==========================

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

    def _guardar_setpoint_int(self, valor_float):
        sp = self._sp_trunc_capped(valor_float)
        self.setpoint_valor = sp
        self.entry_setpoint.delete(0, tk.END)
        self.entry_setpoint.insert(0, str(sp))
        print(f"Omega {self.id_omega} SP -> {sp}")

    def _leer_int(self, entry, default=0) -> int:
        txt = entry.get().strip()
        if not txt:
            return default
        try:
            return int(float(txt))
        except Exception:
            return default

    def _leer_bp_escalada(self, entry) -> int:
        txt = entry.get().strip()
        if not txt:
            return 0
        try:
            val = float(txt)
            return int(round(val * 10))  # escala *10
        except Exception:
            return 0

    # =================== Envio de mensajes ===========================
    def enviar_pid_solo_sp(self):
        if self.setpoint_valor is None:
            txt = self.entry_setpoint.get().strip()
            if not txt:
                print("Setpoint no definido")
                return
            self.setpoint_valor = self._sp_trunc_capped(txt)
        else:
            self.setpoint_valor = self._sp_trunc_capped(self.setpoint_valor)

        # Modo 2 = Heat/Cold predeterminado (PID/AT)
        mensaje = f"$;2;{self.id_omega};2;1;{self.setpoint_valor};!"
        print("Mensaje PID (solo SP):", mensaje)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    def enviar_parametros(self):
        svn = self._leer_int(self.entry_svn, default=0)
        bp10 = self._leer_bp_escalada(self.entry_bp)
        ti = self._leer_int(self.entry_ti, default=0)
        td = self._leer_int(self.entry_td, default=0)

        # Incluimos la memoria en el mensaje (segun tu ajuste reciente)
        mem_idx = self._indice_memoria()

        mensaje = f"$;2;{self.id_omega};2;4;{mem_idx};{svn};{bp10};{ti};{td};!"
        print("Mensaje parametros PID:", mensaje)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    # =================== Ventanas hijas ==============================
    def abrir_ventana_autotuning(self):
        if getattr(self, "_auto_win", None) and self._auto_win.winfo_exists():
            self._auto_win.lift()
            return
        self._auto_win = VentanaAutotuning(self, self.id_omega, self.arduino)

    def abrir_ventana_rampa(self):
        """
        Abre (o levanta) la ventana de rampa.
        NOTA: La ventana, en su __init__, ya envia $;2;ID;4;3;! para solicitar datos.
        """
        if getattr(self, "_rampa_win", None) and self._rampa_win.winfo_exists():
            self._rampa_win.lift()
            return
        self._rampa_win = VentanaRampa(self, self.id_omega, self.arduino)
        # Registrar en la App para poder actualizarla cuando llegue la respuesta
        app = getattr(self, "controlador", None)
        if app is not None:
            if not hasattr(app, "_rampa_wins"):
                app._rampa_wins = {}
            app._rampa_wins[self.id_omega] = self._rampa_win

        # Registrar en la App para poder actualizarla cuando llegue la respuesta
        app = getattr(self, "controlador", None)
        if app is not None:
            # Diccionario por id_omega -> ventana
            if not hasattr(app, "_rampa_wins"):
                app._rampa_wins = {}
            app._rampa_wins[self.id_omega] = self._rampa_win

    def enviar_autotuning_directo(self):
        mem_idx = self._indice_memoria()
        sp_txt = self.entry_setpoint.get().strip()
        sp = self._sp_trunc_capped(sp_txt if sp_txt else "0")

        if sp == 0:
            messagebox.showwarning("Sepoint faltante","Debe ingresar un valor de Setpoint para iniciar el autotuning")
            return

        mensaje = f"$;2;{self.id_omega};2;2;{mem_idx};{sp};!"
        print("Mensaje autotuning:", mensaje)

        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

        # Poner boton en Run solo a nivel UI (Arduino hara su comprobacion)
        if not self.estado_omega.get():
            self.estado_omega.set(True)
            self.btn_toggle.configure(text=self._texto_toggle())

    # =================== Carga de estado desde Arduino ===================
    def cargar_desde_arduino(self, modo_num, sp_or_neg1, mem_idx, svn, p10, ti, td):
        """
        Actualiza la UI del panel con datos recibidos del Arduino.
        Parametros:
          - modo_num: 0 -> PID, 3 -> Rampa
          - sp_or_neg1: entero (SP si PID) o -1 si Rampa
          - mem_idx: 0..4 (M0..M4)
          - svn, p10, ti, td: enteros. 'p10' es P escalado *10 (mostrar p10/10 con 1 decimal)

        Efectos:
          - Cambia el modo (PID/Rampa) visualmente
          - Ajusta la memoria (M0..M4)
          - Rellena SVN, P, I, D
          - Si esta en PID y sp>=0, coloca el setpoint (con truncado/tope 600)
          - Refresca la disposicion (actualizar_vista) y visibilidad de parametros
        """
        # 1) Modo
        nuevo_modo = "PID" if int(modo_num) == 0 else "Rampa"
        if self.modo_control.get() != nuevo_modo:
            self.modo_control.set(nuevo_modo)

        # 2) Memoria
        try:
            mem_idx = int(mem_idx)
        except Exception:
            mem_idx = 0
        mem_idx = max(0, min(4, mem_idx))
        self.memoria.set(f"M{mem_idx}")

        # 3) Parametros
        try:
            svn = int(svn)
        except Exception:
            svn = 0
        try:
            ti = int(ti)
        except Exception:
            ti = 0
        try:
            td = int(td)
        except Exception:
            td = 0

        # p10 viene escalado *10; para mostrar, p = p10/10 con 1 decimal
        try:
            p10 = int(p10)
            p_mostrable = f"{p10 / 10:.1f}"
        except Exception:
            p10 = 0
            p_mostrable = "0.0"

        # Rellenar entries de parametros
        self.entry_svn.delete(0, tk.END)
        self.entry_svn.insert(0, str(svn))

        self.entry_bp.delete(0, tk.END)
        self.entry_bp.insert(0, p_mostrable)

        self.entry_ti.delete(0, tk.END)
        self.entry_ti.insert(0, str(ti))

        self.entry_td.delete(0, tk.END)
        self.entry_td.insert(0, str(td))

        # 4) Setpoint (solo si modo = PID y sp enviado >=0)
        try:
            sp_or_neg1 = int(sp_or_neg1)
        except Exception:
            sp_or_neg1 = -1

        if nuevo_modo == "PID" and sp_or_neg1 >= 0:
            sp_ok = self._sp_trunc_capped(sp_or_neg1)
            self.setpoint_valor = sp_ok
            self.entry_setpoint.delete(0, tk.END)
            self.entry_setpoint.insert(0, str(sp_ok))
        else:
            # En rampa ocultamos SP de PID (ya lo maneja actualizar_vista)
            self.setpoint_valor = None
            self.entry_setpoint.delete(0, tk.END)

        # 5) Refrescar UI (colocaciones y visibilidad de parametros)
        self.actualizar_vista()
        self._aplicar_visibilidad_parametros()

    def aplicar_parametros(self, svn, p, i, d):
        """
        Actualiza los entries SVN, P, I, D del panel con los valores recibidos.
        - svn, i, d se muestran como enteros
        - p se muestra con 1 decimal (si Arduino envia P*10, dividimos entre 10.0)
          Ajusta aqui si tu Arduino envia 'P' ya sin escalar.
        """
        try:
            svn_i = int(float(svn))
        except Exception:
            svn_i = 0

        # Asumimos que Arduino responde con P*10 (como nosotros lo enviamos)
        # Si tu Arduino responde P "real", cambia a: p_val = float(p)
        try:
            p10_i = int(float(p))
            p_val = p10_i / 10.0
        except Exception:
            p_val = 0.0

        try:
            i_i = int(float(i))
        except Exception:
            i_i = 0

        try:
            d_i = int(float(d))
        except Exception:
            d_i = 0

        # Rellenar entries (aunque esten ocultos si memoria=M4)
        self.entry_svn.delete(0, tk.END)
        self.entry_svn.insert(0, str(svn_i))

        self.entry_bp.delete(0, tk.END)
        self.entry_bp.insert(0, f"{p_val:.1f}")

        self.entry_ti.delete(0, tk.END)
        self.entry_ti.insert(0, str(i_i))

        self.entry_td.delete(0, tk.END)
        self.entry_td.insert(0, str(d_i))
