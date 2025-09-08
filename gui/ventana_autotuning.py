import tkinter as tk
from tkinter import ttk
from .teclado_numerico import TecladoNumerico


class VentanaAutotuning(tk.Toplevel):
    """
    Ventana modal para configurar y lanzar el Autotuning de un Omega.

    Envio:
      $;2;ID_OMEGA;1;2;MEM;SP;!

    Donde:
      2        -> CMD Temperatura
      ID_OMEGA -> 1 o 2
      1        -> modo heat/hot
      2        -> autotuning
      MEM      -> 0..3 (M0..M3)
      SP       -> setpoint entero (truncado), tope 600

    Lectura SP memorias (ejemplo; ajusta al firmware si es diferente):
      Enviar: $;2;ID_OMEGA;4;2;!
      Recibir: $;2;ID_OMEGA;2;sp0;sp1;sp2;sp3;!
      Luego la App debe llamar: _autotuning_win.actualizar_setpoints([...])
    """

    def __init__(self, master, id_omega, arduino, on_started=None, *args, **kwargs):
        """
        on_started: callback opcional (sin argumentos) que el Panel pasara para
                    reflejar en UI que el Omega queda 'iniciado' tras lanzar el AT.
        """
        super().__init__(master, *args, **kwargs)
        self.title(f"Autotuning - Omega {id_omega}")
        self.geometry("300x250")
        self.resizable(False, False)

        # Identidad y referencias
        self.id_omega = id_omega
        self.arduino = arduino
        self.on_started = on_started  # <--- callback que actualiza el toggle en PanelOmega

        # Intentar obtener el controlador (Aplicacion) desde el padre (PanelOmega)
        self.controlador = getattr(master, "controlador", None)
        if self.controlador is not None:
            # Registrar esta ventana en la App para que la App pueda actualizarla
            setattr(self.controlador, "_autotuning_win", self)

        # Estado local
        self.memoria_seleccionada = tk.StringVar(value="M0")  # M0..M3
        # SP por memoria (vector recibido desde Arduino)
        self.setpoints = [0, 0, 0, 0]
        # ultimo valor editado por el usuario (int)
        self.setpoint_valor = None
        self._cargando = True          # bloquear UI hasta recibir los SP iniciales

        # Ventana modal, por encima del padre
        self.transient(master.winfo_toplevel())
        self.wait_visibility()
        self.lift()
        self.focus_force()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- UI ----
        ttk.Label(self, text=f"Autotuning - Omega {id_omega}",
                  font=("Arial", 14, "bold")).pack(pady=10)

        # Selector de memoria PID (M0..M3)
        frame_mem = ttk.Frame(self)
        frame_mem.pack(pady=10)
        ttk.Label(frame_mem, text="Memoria PID:").pack(side="left", padx=5)
        self.combo_memorias = ttk.Combobox(
            frame_mem,
            values=["M0", "M1", "M2", "M3"],
            textvariable=self.memoria_seleccionada,
            state="readonly",  # readonly cuando habilitado
            width=5
        )
        self.combo_memorias.pack(side="left")
        self.combo_memorias.bind("<<ComboboxSelected>>", self._cambio_memoria)

        # Campo de setpoint (editable con el teclado numerico)
        ttk.Label(self, text="Setpoint:").pack(pady=5)
        self.entry_setpoint = ttk.Entry(self, width=10)
        self.entry_setpoint.pack()
        self.entry_setpoint.bind(
            "<Button-1>",
            lambda e: TecladoNumerico(
                self,
                self.entry_setpoint,
                on_submit=self._guardar_setpoint_int
            )
        )

        # Boton para iniciar el autotuning
        self.btn_iniciar = ttk.Button(self, text="Iniciar Autotuning",
                                      command=self.enviar_autotuning)
        self.btn_iniciar.pack(pady=15)

        # Atajos utiles
        self.bind("<Return>", lambda e: self.enviar_autotuning())
        self.bind("<Escape>", lambda e: self._on_close())

        # Deshabilitar UI mientras cargan SP desde Arduino
        self._set_ui_habilitada(False)

        # Solicitar los 4 setpoints al abrir la ventana
        self._solicitar_setpoints()

        # Mostrar M0 en el entry (mientras llega la respuesta, se ve 0)
        self._refrescar_entry_desde_vector()

    # ================= helpers de memoria / entry =================
    def _set_ui_habilitada(self, habilitar: bool):
        """Habilita o deshabilita los controles de interaccion del usuario."""
        estado_combo = "readonly" if habilitar else "disabled"
        self.combo_memorias.configure(state=estado_combo)
        estado_btn = "normal" if habilitar else "disabled"
        self.btn_iniciar.configure(state=estado_btn)

    def _indice_memoria(self) -> int:
        """Convierte M0..M3 a un indice 0..3. Si falla, retorna 0."""
        mem = self.memoria_seleccionada.get().strip().upper()
        try:
            return int(mem.replace("M", ""))
        except Exception:
            return 0

    def _refrescar_entry_desde_vector(self):
        idx = self._indice_memoria()
        try:
            sp = int(float(self.setpoints[idx]))
        except Exception:
            sp = 0
        self.entry_setpoint.delete(0, tk.END)
        self.entry_setpoint.insert(0, str(sp))

    def _cambio_memoria(self, _event=None):
        """Callback al cambiar M0..M3: actualizar el entry."""
        self._refrescar_entry_desde_vector()

    def _guardar_setpoint_int(self, valor_float):
        """
        Trunca a int (no redondea), aplica tope 600, refleja en entry
        y actualiza vector local para la memoria seleccionada.
        """
        try:
            sp = int(float(valor_float))  # truncado
        except Exception:
            print("Setpoint invalido")
            return

        if sp > 600:
            sp = 600

        self.setpoint_valor = sp
        self.entry_setpoint.delete(0, tk.END)
        self.entry_setpoint.insert(0, str(sp))
        self.setpoints[self._indice_memoria()] = sp
        print(
            f"AT Omega {self.id_omega} {self.memoria_seleccionada.get()} -> SP={sp}")

    # ================= solicitud/actualizacion desde Arduino =================
    def _solicitar_setpoints(self):
        """
        Pide los cuatro setpoints actuales de autotuning para este Omega.
        Respuesta esperada:
          $;2;ID_OMEGA;2;sp0;sp1;sp2;sp3;!
        """
        if self.controlador is None:
            return
        msg = f"$;2;{self.id_omega};4;2;!"
        print("Solicitando setpoints AT:", msg)
        self.controlador.enviar_a_arduino(msg)

    def actualizar_setpoints(self, lista_sp):
        """
        Llamado por la App al recibir la respuesta con sp0..sp3.
        """
        try:
            vals = [int(float(x)) for x in lista_sp]  # truncado
            if len(vals) != 4:
                raise ValueError("se esperaban 4 valores")
            # Tope coherente (600)
            self.setpoints = [min(v, 600) for v in vals]
            self._refrescar_entry_desde_vector()
            self._cargando = False
            self._set_ui_habilitada(True)
            print(
                f"AT Omega {self.id_omega} setpoints recibidos: {self.setpoints}")
        except Exception as e:
            print("Error al actualizar setpoints AT:", e)

     # ---------- envio de inicio de autotuning ----------
    def enviar_autotuning(self):
        """
        Construye y envia:
          $;2;ID_OMEGA;1;2;MEM;SP;!

        Despues de enviar:
        - Invoca on_started() si fue provisto por el Panel para reflejar
          que el Omega queda 'iniciado' (solo UI, no reenvia comandos extra).
        - Cierra la ventana.
        """
        mem_idx = self._indice_memoria()

        # Obtener SP (trunc + tope 600)
        if self.setpoint_valor is None:
            txt = self.entry_setpoint.get().strip()
            if not txt:
                print("Setpoint no definido")
                return
            try:
                sp = int(float(txt))
            except Exception:
                print("Setpoint invalido")
                return
        else:
            try:
                sp = int(float(self.setpoint_valor))
            except Exception:
                print("Setpoint invalido")
                return

        if sp > 600:
            sp = 600

        # Reflejar en entry
        self.setpoint_valor = sp
        self.entry_setpoint.delete(0, tk.END)
        self.entry_setpoint.insert(0, str(sp))

        # Mensaje
        mensaje = f"$;2;{self.id_omega};1;2;{mem_idx};{self.setpoint_valor};!"
        print("Mensaje autotuning:", mensaje)

        # Envio centralizado (preferente) o fallback al serial directo
        app = self.controlador
        if app is not None and hasattr(app, "enviar_a_arduino"):
            try:
                app.enviar_a_arduino(mensaje)
            except Exception as e:
                print(f"Error al usar enviar_a_arduino: {e}")
        elif self.arduino:
            try:
                self.arduino.write((mensaje + "\n").encode("utf-8"))
            except Exception as e:
                print("Error al enviar al Arduino:", e)

        # Reflejar en la UI del panel que el omega quedo 'iniciado' (solo si nos pasaron callback)
        if callable(self.on_started):
            try:
                self.on_started()
            except Exception:
                pass

        # Cerrar ventana
        self._on_close()
    # ---- cierre ----

    def _on_close(self):
        try:
            if getattr(self.controlador, "_autotuning_win", None) is self:
                setattr(self.controlador, "_autotuning_win", None)
        except Exception:
            pass
        self.destroy()
