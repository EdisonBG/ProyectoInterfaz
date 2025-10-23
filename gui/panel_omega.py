import tkinter as tk
from tkinter import ttk , messagebox
from .ventana_rampa import VentanaRampa
from .teclado_numerico import TecladoNumerico
from .ventana_autotuning import VentanaAutotuning
from ui.widgets import TouchButton, TouchEntry, LabeledEntryNum

# Constantes táctiles (anchos/fuentes). Si no existen, usa valores por defecto.
try:
    from ui import constants as C
except Exception:
    class _C_:
        FONT_BASE = ("Calibri", 14)
        ENTRY_WIDTH = 12
        COMBO_WIDTH = 12
    C = _C_()


# Coordenadas por MFC (horizontal, vertical) para cada control dentro de su LabelFrame.
# Nota: "entry" posiciona el contenedor LabeledEntryNum completo (label+entry).
POS = {
    1: {
        "campo_setpoint": (23, 1),
        "btn_enviar_sp": (30, 60), "boton_rampa":(30, 60), "btn_toggle": (233, 60),
        "memoria_lbl": (96, 126),   "combo":    (212, 126),
        "btn_autotuning": (97, 172),
        "campo_svn":(45, 1),
        "campo_proporcional": (40, 47),
        "campo_integral":(40, 93),
        "campo_derivativo":(40, 137),
        "btn_enviar_param": (103, 190),
    },
    2: {
        "campo_setpoint": (23, 1),
        "btn_enviar_sp": (30, 60), "boton_rampa":(30, 60), "btn_toggle": (233, 60),    
        "memoria_lbl": (96, 126),   "combo":    (212, 126),  
        "btn_autotuning": (97, 172),
        "campo_svn":(45, 1), 
        "campo_proporcional": (40, 47),
        "campo_integral":(40, 93),
        "campo_derivativo":(40, 137),
        "btn_enviar_param": (103, 190),      
    },
}

class PanelOmega(ttk.Frame):
    MEMORIAS=["M0", "M1", "M2", "M3", "Auto"]
    

    def __init__(self, master, id_omega, controlador, arduino, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        # === Identificacion y referencias ===
        self.id_omega = id_omega                 # Numero de Omega (1,2,..)
        self.controlador = controlador           # App para envio centralizado
        self.arduino = arduino                   # Fallback serial directo
        self._configurar_estilos() 
        self.refs = {}  # almacena referencias como en MFC
        self.sp_area2 = None

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
        ttk.Label(self, text=f"Controlador {id_omega}", font=("Calibri", 16, "bold"))\
            .grid(row=0, column=0, columnspan=2, pady=(6, 8))

        # selector PID/Rampa
        selector = ttk.Frame(self)
        selector.grid(row=1, column=0, columnspan=2, pady=(0, 6))
        ttk.Radiobutton(selector, text="PID", variable=self.modo_control,
                        value="PID", command=self._on_modo_cambiado, style="BigRadio.TRadiobutton").pack(side="left", padx=6)
        ttk.Radiobutton(selector, text="RAMPA", variable=self.modo_control,
                        value="Rampa", command=self._on_modo_cambiado, style="BigRadio.TRadiobutton").pack(side="left", padx=6)

        # =================================================================
        # ================== CONTENEDOR SUPERIOR (setpoint + botones) =====
        # =================================================================
        self.frame_pid = ttk.Frame(self)
        self.frame_pid.grid_columnconfigure(0, weight=0)
        self.frame_pid.grid_columnconfigure(1, weight=1)
        
        # mismo fondo pero sin borde/relieve: contenedor para ubicar elementos en la parte superior
        sp_area = ttk.Frame(self.frame_pid, style="Omega.TFrame")
        sp_area.grid(row=0, column=0, columnspan=2, sticky="nw")
        sp_area.configure(width=400, height=290)  # tamaño del área
        sp_area.grid_propagate(False)             # respeta el tamaño
        # sin relieve
        sp_area.configure(borderwidth=0, relief="flat")

        # Setpoint 
        self.campo_setpoint = LabeledEntryNum(sp_area, "Setpoint temperatura (°C):",
            width=18,  # más largo
            label_font=getattr(C, "FONT_BASE", ("Calibri", 14)),  # label más grande
            entry_ipady=7,
            # entry_font opcional si quieres cambiar también la fuente del entry:
            # entry_font=(getattr(C, "FONT_BASE", ("Calibri", 16))[0], 16),
            )
        
        self.campo_setpoint.place(x=POS[id_omega]["campo_setpoint"][0], y=POS[id_omega]["campo_setpoint"][1])
        self.entry_setpoint = self.campo_setpoint.entry
        self.campo_setpoint.bind_numeric( lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
            on_submit=lambda v: self._guardar_setpoint_int(v),)
        self.refs["campo_setpoint"] = self.campo_setpoint.entry

        ###### Botones PID (Enviar SP, toggle RUN/STOP, Iniciar autotuning) ###############
        btns_pid = ttk.Frame(self.frame_pid)
        btns_pid.grid(row=1, column=0, columnspan=2,
                      padx=5, pady=(8, 4), sticky="w")

        self.btn_enviar_sp = TouchButton(sp_area, text="Enviar setpoint", style="SelBtn.TButton",
                                command=self.enviar_pid_solo_sp)
        self.btn_enviar_sp.place(x=POS[id_omega]["btn_enviar_sp"][0], y=POS[id_omega]["btn_enviar_sp"][1])
        self.refs["btn_enviar_sp"] = self.btn_enviar_sp
        self.btn_enviar_sp._base_style = self.btn_enviar_sp.cget("style")  # <--- guardamos el estilo claro

        initial_style = "StopBtn.TButton" if self.estado_omega.get() else "RunBtn.TButton"
        self.btn_toggle = TouchButton(sp_area, text=self._texto_toggle(), style=initial_style,
                                command=self._toggle_omega)
        self.btn_toggle.place(x=POS[id_omega]["btn_toggle"][0], y=POS[id_omega]["btn_toggle"][1])
        self.refs["btn_toggle"] = self.btn_toggle
        
        btn_autotuning = TouchButton(sp_area, text="Iniciar autotuning", style="SelBtn.TButton",
                                command=self.enviar_autotuning_directo)
        btn_autotuning.place(x=POS[id_omega]["btn_autotuning"][0], y=POS[id_omega]["btn_autotuning"][1])
        self.refs["btn_enviar_sp"] = btn_autotuning
        btn_autotuning._base_style = btn_autotuning.cget("style")  # <--- guardamos el estilo claro
        
        ###### Memorias PID: Label + COMBO ################
        memoria_lbl = ttk.Label(sp_area, text="Memoria:", font=getattr(C, "FONT_BASE", ("Calibri", 14)))
        memoria_lbl.place(x=POS[id_omega]["memoria_lbl"][0], y=POS[id_omega]["memoria_lbl"][1])

        combo = ttk.Combobox(
            sp_area,
            values=self.MEMORIAS,
            state="readonly",
            width=getattr(C, "COMBO_WIDTH", 10),
            height=130,
            font=getattr(C, "FONT_BASE", ("Calibri", 14)),
        )
        family = getattr(C, "FONT_BASE", ("Calibri", 14))[0]
        combo.option_add("*TCombobox*Listbox.font", (family, 14))

        combo.place(x=POS[id_omega]["combo"][0], y=POS[id_omega]["combo"][1])
        combo.bind("<<ComboboxSelected>>", self._on_memoria_cambiada)
        self.refs["combo"] = combo

        # =================================================================
        # =================== MODO RAMPA ==================================
        # =================================================================

        self.boton_rampa = TouchButton(sp_area, text="Configurar Rampa", style="SelBtn.TButton",
                                command=self.abrir_ventana_rampa)
        self.refs["boton_rampa"] = self.boton_rampa
        self.boton_rampa._base_style = self.boton_rampa.cget("style")  # <--- guardamos el estilo claro
        
        # Mostrar UI inicial
        self.actualizar_vista()
        # Ajustar visibilidad de parametros segun memoria
        self._aplicar_visibilidad_parametros()

        self._modo_inicializado = True
        self._ultimo_modo_enviado = self.modo_control.get()

    def set_contenedor_inferior(self, parent): 
        
        self._contenedor_inferior = parent
        self.sp_area2 = ttk.Frame(self._contenedor_inferior, style="Omega.TFrame")
        self.sp_area2.grid(row=0, column=0, sticky="nw")
        self.sp_area2.configure(width=397, height=242)  # tamaño del área
        self.sp_area2.grid_propagate(False)             # respeta el tamaño
        # sin relieve
        self.sp_area2.configure(borderwidth=0, relief="flat")
        
        # =================================================================
        # ============== CONTENEDOR INFERIOR (constantes PID + boton) =====
        # =================================================================
        campo_svn = LabeledEntryNum(self.sp_area2, "Temperatura °C (Svn):",
            width=18,  # más largo
            label_font=getattr(C, "FONT_BASE", ("Calibri", 14)),  # label más grande
            entry_ipady=7,
            # entry_font opcional si quieres cambiar también la fuente del entry:
            # entry_font=(getattr(C, "FONT_BASE", ("Calibri", 16))[0], 16),
            )
        
        campo_svn.place(x=POS[self.id_omega]["campo_svn"][0], y=POS[self.id_omega]["campo_svn"][1])
        self.entry_svn = campo_svn.entry
        campo_svn.bind_numeric( lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
            on_submit=lambda v:  self.entry_svn,)
        self.refs["campo_svn"] = campo_svn.entry

        campo_proporcional = LabeledEntryNum(self.sp_area2, "Banda Proporcional (Pb):",
            width=18,  # más largo
            label_font=getattr(C, "FONT_BASE", ("Calibri", 14)),  # label más grande
            entry_ipady=7,
            # entry_font opcional si quieres cambiar también la fuente del entry:
            # entry_font=(getattr(C, "FONT_BASE", ("Calibri", 16))[0], 16),
            )
        
        campo_proporcional.place(x=POS[self.id_omega]["campo_proporcional"][0], y=POS[self.id_omega]["campo_proporcional"][1])
        self.entry_bp = campo_proporcional.entry
        campo_proporcional.bind_numeric( lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
            on_submit=lambda v:  self.entry_bp,)
        self.refs["campo_proporcional"] = campo_proporcional.entry

        campo_integral = LabeledEntryNum(self.sp_area2, "Tiempo Integral (Ti):",
            width=18,  # más largo
            label_font=getattr(C, "FONT_BASE", ("Calibri", 14)),  # label más grande
            entry_ipady=7,
            # entry_font opcional si quieres cambiar también la fuente del entry:
            # entry_font=(getattr(C, "FONT_BASE", ("Calibri", 16))[0], 16),
            )
        
        campo_integral.place(x=POS[self.id_omega]["campo_integral"][0], y=POS[self.id_omega]["campo_integral"][1])
        self.entry_ti = campo_integral.entry
        campo_integral.bind_numeric( lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
            on_submit=lambda v:  self.entry_ti,)
        self.refs["campo_integral"] = campo_integral.entry

        campo_derivativo = LabeledEntryNum(self.sp_area2, "Tiempo Derivativo (Td):",
            width=18,  # más largo
            label_font=getattr(C, "FONT_BASE", ("Calibri", 14)),  # label más grande
            entry_ipady=7,
            # entry_font opcional si quieres cambiar también la fuente del entry:
            # entry_font=(getattr(C, "FONT_BASE", ("Calibri", 16))[0], 16),
            )
        
        campo_derivativo.place(x=POS[self.id_omega]["campo_derivativo"][0], y=POS[self.id_omega]["campo_derivativo"][1])
        self.entry_td = campo_derivativo.entry
        campo_derivativo.bind_numeric( lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
            on_submit=lambda v:  self.entry_td,)
        self.refs["campo_derivativo"] = campo_derivativo.entry

        btn_enviar_param = TouchButton(self.sp_area2, text="Enviar parametros", style="SelBtn.TButton",
                                command=self.enviar_parametros)
        btn_enviar_param.place(x=POS[self.id_omega]["btn_enviar_param"][0], y=POS[self.id_omega]["btn_enviar_param"][1])
        self.refs["btn_enviar_param"] = btn_enviar_param
        btn_enviar_param._base_style = btn_enviar_param.cget("style")  # <--- guardamos el estilo claro

    def _configurar_estilos(self):
        st = ttk.Style(self)
        
        try:
            st.theme_use("clam")  # ya lo usas en otras vistas
        except Exception:
            pass

        st.configure(
            "BigRadio.TRadiobutton",
            font=("Calibri", 13),    # <-- tamaño del texto
            padding=(12, 8)          # <-- más área clicable alrededor
        )
        # Label grande
        st.configure("Big.TLabel", font=("Calibri", 18))

        # Entry grande (alto y ancho visual crecen con la fuente y el padding)
        st.configure("Big.TEntry", font=("Calibri", 18), padding=(10, 8))
        
        RUN_COLOR = "#27ae60"
        STOP_COLOR = "#db4231"
        # boton de send/enviar_flujo
        st.configure("SelBtn.TButton", padding=(16, 8), font=getattr(C, "FONT_BASE", ("Calibri", 16)))
        st.map("SelBtn.TButton", background=[("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")])
        st.configure("SelBtnOn.TButton", padding=(16, 8), font=getattr(C, "FONT_BASE", ("Calibri", 16)), background="#bdbdbd")
        st.map("SelBtnOn.TButton", background=[("!disabled", "#bdbdbd"), ("pressed", "#9e9e9e")])

        #boton de run/stop
        st.configure("RunBtn.TButton", padding=(16, 8), font=getattr(C, "FONT_BASE", ("Calibri", 16)))
        st.map("RunBtn.TButton", background=[("!disabled", RUN_COLOR), ("active", RUN_COLOR), ("pressed", RUN_COLOR)])
        st.configure("StopBtn.TButton", padding=(16, 8), font=getattr(C, "FONT_BASE", ("Calibri", 16)))
        st.map("StopBtn.TButton", background=[("!disabled", STOP_COLOR), ("active", STOP_COLOR), ("pressed", STOP_COLOR)])

        # Estilo para Entry deshabilitado
        st.configure("Disabled.TEntry", fieldbackground="#d0d0d0")   # gris del fondo
        st.map("Disabled.TEntry", fieldbackground=[("disabled", "#d0d0d0")],
       foreground=[("disabled", "#555")])
        
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
        txt = "Run" if not self.estado_omega.get() else "Stop"
        # Estilo según el texto (se aplica al final del ciclo actual)
        try:
            style = "RunBtn.TButton" if txt == "Run" else "StopBtn.TButton"
            self.after(0, lambda: self.btn_toggle.configure(style=style))
        except Exception:
            pass
        return txt


    def _toggle_omega(self):
        nuevo = not self.estado_omega.get()
        self.estado_omega.set(nuevo)
        self.btn_toggle.configure(text=self._texto_toggle())

        accion = "1" if nuevo else "0"
        #self.btn_toggle.configure(style="StopBtn.TButton" if self.estado_omega.get() else "RunBtn.TButton")
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
        Oculta el contenedor inferior (sp_area2) si memoria=M4; lo muestra en M0–M3.
        Requiere que set_contenedor_inferior(...) haya creado y grideado self.sp_area2.
        """
        area = getattr(self, "sp_area2", None)
        if area is None:
            return  # aún no se llamó set_contenedor_inferior
        
        mem = self.refs["combo"].get()
        #print("Memoria seleccionada:", mem)
        if mem == "Auto":
            area.grid_remove()
        else:
            if not area.winfo_ismapped():
                area.grid()  # vuelve a mostrar con su grid original

    # =================== Cambio de modo (PID/Rampa) ==================
    def actualizar_vista(self):
        modo = self.modo_control.get()

         # Oculta ambos botones primero
        self.btn_enviar_sp.place_forget()
        self.boton_rampa.place_forget()
       
        if modo == "PID":
            # Dibuja todos los elementos de sp_area = contenedor superior
            self.frame_pid.grid()  
            # Dibuja el botón enviar setpoint. Es el único que se modifica en modo rampa
            self.btn_enviar_sp.place(x=POS[self.id_omega]["btn_enviar_sp"][0], y=POS[self.id_omega]["btn_enviar_sp"][1])
            # Parametros (si memoria != M4)
            if self.refs["combo"].get() != "Auto" and self.sp_area2 is not None:
                self.sp_area2.grid()
            #habilita el entry del setpint
            e = self.entry_setpoint
            e.state(["!disabled"])             # reactivar
            e.configure(style="TEntry")        # estilo normal por defecto

            # Re-vincula el teclado numérico (se pierde con el unbind)
            self.campo_setpoint.bind_numeric( lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
            on_submit=lambda v: self._guardar_setpoint_int(v),)
            #vuelve el color normal al label
            self.campo_setpoint.label.configure(foreground="")

        else:
            # Rampa: boton de configuracion
            self.boton_rampa.place(x=POS[self.id_omega]["boton_rampa"][0], y=POS[self.id_omega]["boton_rampa"][1])
            # Memoria y parametros (mismos widgets, misma logica)
            #self.frame_mem.grid(row=3, column=0, columnspan=2, padx=5, pady=(6, 2), sticky="w")
            if self.refs["combo"].get() != "Auto" and self.sp_area2 is not None:
                self.sp_area2.grid()
            #Deshabilita el ingresar el setpoint:entry
            e = self.entry_setpoint
            e.state(["disabled"])
            e.configure(style="Disabled.TEntry")
            # Evita que se abra el teclado numérico (por si el bind sigue activo)
            e.unbind("<Button-1>")

            #  apaga visual del label
            self.campo_setpoint.label.configure(foreground="#777")

    # =================== Lectura de valores ==========================

    def _indice_memoria(self) -> int:
        val = self.refs["combo"].get()
        if val == "Auto":
            return 4
        
        try:
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
