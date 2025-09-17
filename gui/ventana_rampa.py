import tkinter as tk
from tkinter import ttk
from .teclado_numerico import TecladoNumerico


class VentanaRampa(tk.Toplevel):
    """
    Configuracion de Rampa para un Omega (ID 1 o 2)

    UI:
      - 8 pasos (0..7): para cada paso, Setpoint y Tiempo (min)
      - Campo "Paso limite (0-7)"

    Solicitud al abrir:
      $;2;ID_OMEGA;4;3;!

    Envio al presionar "Enviar":
      $;2;ID_OMEGA;1;3;SP0;SP1;...;SP7;T0;T1;...;T7;PASO_LIM;!

    Reglas:
      - SP y T se envian como enteros por truncado (10.5 -> 10)
      - SP se limita a max 600
      - Si un campo esta vacio o no es numero -> 0
      - Paso limite vacio/invalido/fuera de 0..7 -> 0

      Integracion App:
      - La App puede volcar datos de rampa con: aplicar_rampa(sp_list, t_list, paso_lim)
    """

    def __init__(self, master, id_omega, arduino, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.arduino = arduino
        self.id_omega = id_omega
        self.title(f"Rampa - Omega {id_omega}")
        self.geometry("420x600")
        self.resizable(False, False)

        # Referencia al controlador (Aplicacion) si existe, para:
        # - Envio centralizado
        # - para que la App pueda encontrar esta ventana y actualizarla
        self.controlador = getattr(master, "controlador", None)
        if self.controlador is not None:
            setattr(self.controlador, f"_rampa_win_{self.id_omega}", self)

        # ventana modal, por encima del padre
        self.transient(master.winfo_toplevel())
        self.wait_visibility()
        self.lift()
        self.focus_force()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW",  self._on_close)

        # =========================
        # [UI] Tema / estilos ttk
        # =========================
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass

        # [UI] Tokens de color coherentes con el resto
        BG = "#0f172a"          # fondo ventana
        SURFACE = "#111827"     # paneles/frames
        TEXT = "#e5e7eb"        # texto
        MUTED = "#9ca3af"
        BORDER = "#1f2937"
        PRIMARY = "#22c55e"
        PRIMARY_ACTIVE = "#16a34a"

        # [UI] Fondo de la toplevel (tk.Toplevel no es ttk)
        self.configure(bg=BG)

        # [UI] Tipografías un poco más grandes para táctil
        self.option_add("*Font", ("TkDefaultFont", 12))
        self.option_add("*TButton.Font", ("TkDefaultFont", 12, "bold"))
        self.option_add("*Entry.Font", ("TkDefaultFont", 12))

        # [UI] Estilos base
        st.configure("Rampa.TFrame", background=SURFACE)
        st.configure("Rampa.TLabel", background=SURFACE, foreground=TEXT)
        st.configure("RampaMuted.TLabel", background=SURFACE, foreground=MUTED)

        st.configure(
            "Rampa.TEntry",
            fieldbackground=BG,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor="#2563eb",
            darkcolor=BORDER,
            padding=8
        )

        st.configure(
            "Rampa.TButton",
            padding=(12, 10),
            relief="raised",
            borderwidth=2,
            background=SURFACE,
            foreground=TEXT
        )
        st.map("Rampa.TButton",
               background=[("active", BORDER)],
               relief=[("pressed", "sunken")])

        st.configure(
            "RampaPrimary.TButton",
            padding=(14, 12),
            relief="raised",
            borderwidth=2,
            background=PRIMARY,
            foreground="#052e16"
        )
        st.map("RampaPrimary.TButton",
               background=[("active", PRIMARY_ACTIVE)],
               relief=[("pressed", "sunken")])

        # =========================
        # Cabecera
        # =========================
        header = ttk.Frame(self, style="Rampa.TFrame", padding=(14, 12))  # [UI]
        header.pack(fill="x")
        ttk.Label(
            header,
            text=f"Configuracion de Rampa - Omega {id_omega}",
            style="Rampa.TLabel",
            font=("Arial", 14, "bold")
        ).pack(anchor="center")

        # =========================
        # Contenido (scrollable simple)
        # =========================
        body = ttk.Frame(self, style="Rampa.TFrame", padding=(14, 12))  # [UI]
        body.pack(fill="both", expand=True)

        # [UI] contenedor de pasos
        cont = ttk.Frame(body, style="Rampa.TFrame")
        cont.pack(pady=6, fill="x")

        self.campos = []  # Lista de (entry_sp, entry_tiempo) para pasos 0..7

        # pasos 0..7
        for i in range(8):
            frame_paso = ttk.Frame(cont, style="Rampa.TFrame")  # [UI]
            frame_paso.pack(pady=4, anchor="w", fill="x")        # [UI]

            for c in (0, 1, 2, 3, 4):
                frame_paso.grid_columnconfigure(c, weight=1 if c in (2, 4) else 0)  # [UI] entradas expanden

            ttk.Label(frame_paso, text=f"Paso {i}", style="RampaMuted.TLabel")\
                .grid(row=0, column=0, padx=6, sticky="w")

            ttk.Label(frame_paso, text="Setpoint:", style="Rampa.TLabel")\
                .grid(row=0, column=1, padx=6, sticky="e")
            entrada_sp = ttk.Entry(frame_paso, width=10, style="Rampa.TEntry")  # [UI]
            entrada_sp.grid(row=0, column=2, sticky="ew")                        # [UI]
            entrada_sp.bind("<Button-1>", lambda e, entry=entrada_sp: TecladoNumerico(
                self, entry, on_submit=lambda v, ent=entry: self._rampa_aplicar_sp(ent, v)))

            ttk.Label(frame_paso, text="Tiempo (min):", style="Rampa.TLabel")\
                .grid(row=0, column=3, padx=6, sticky="e")
            entrada_tiempo = ttk.Entry(frame_paso, width=10, style="Rampa.TEntry")  # [UI]
            entrada_tiempo.grid(row=0, column=4, sticky="ew")                        # [UI]
            entrada_tiempo.bind(
                "<Button-1>",
                lambda e, entry=entrada_tiempo: TecladoNumerico(
                    self, entry, on_submit=lambda v, ent=entry: self._rampa_aplicar_t(ent, v)
                )
            )

            self.campos.append((entrada_sp, entrada_tiempo))

        # paso limite (0..7)
        frame_lim = ttk.Frame(body, style="Rampa.TFrame")  # [UI]
        frame_lim.pack(pady=10, fill="x")                  # [UI]
        frame_lim.grid_columnconfigure(1, weight=1)        # [UI] para alinear

        ttk.Label(frame_lim, text="Paso limite (0-7):", style="Rampa.TLabel")\
            .grid(row=0, column=0, padx=6, sticky="e")
        self.entry_limite = ttk.Entry(frame_lim, width=6, style="Rampa.TEntry")  # [UI]
        self.entry_limite.grid(row=0, column=1, padx=6, sticky="w")
        self.entry_limite.bind("<Button-1>", lambda e: TecladoNumerico(self, self.entry_limite))

        # boton enviar
        botones = ttk.Frame(body, style="Rampa.TFrame")    # [UI]
        botones.pack(pady=12, fill="x")                    # [UI]
        botones.grid_columnconfigure(0, weight=1)          # [UI]
        ttk.Button(
            botones, text="Enviar", command=self.enviar_rampa, style="RampaPrimary.TButton"  # [UI]
        ).grid(row=0, column=0, padx=8, sticky="ew")       # [UI]

        # atajos
        self.bind("<Return>", lambda e: self.enviar_rampa())
        self.bind("<Escape>", lambda e: self.destroy())

        # [UI] Forzar repintado con estilos ya aplicados (evita parches claros al abrir)
        self.update_idletasks()
        self.after_idle(self.update_idletasks)

        # === Al abrir, solicitar la rampa actual ===
        self._solicitar_rampa_actual()

    # ----------------- helpers -----------------
    def _trunc_int(self, value):
        try:
            return int(float(value))
        except Exception:
            return 0

    def _rampa_aplicar_sp(self, entry, valor):
        """Callback del teclado para SP: truncado y tope 600; refleja en el entry."""
        n = self._trunc_int(valor)
        if n > 600:
            n = 600
        entry.delete(0, tk.END)
        entry.insert(0, str(n))

    def _rampa_aplicar_t(self, entry, valor):
        """Callback del teclado para T: truncado; refleja en el entry."""
        n = self._trunc_int(valor)
        entry.delete(0, tk.END)
        entry.insert(0, str(n))

    def _int_trunc_or_zero(self, v) -> int:
        """
        Trunca hacia 0; vacio/invalido -> 0.
        Acepta str, int, float, None.
        """
        if v is None:
            return 0
        try:
            s = str(v).strip()
            if not s:
                return 0
            return int(float(s))
        except Exception:
            return 0

    def _sp_int_trunc_capped(self, v, max_sp: int = 600) -> int:
        """
        Entero truncado con tope max_sp para SP.
        Acepta str, int, float, None.
        """
        n = self._int_trunc_or_zero(v)
        return max_sp if n > max_sp else n

    def _paso_limite_valido(self, v) -> int:
        """
        Devuelve entero en 0..7; si invalido -> 0.
        Acepta str, int, float, None.
        """
        try:
            s = "0" if v is None else str(v).strip() or "0"
            val = int(float(s))
            return val if 0 <= val <= 7 else 0
        except Exception:
            return 0

    # ----------------- carga desde Arduino -----------------
    def aplicar_rampa(self, sp_list, t_list, paso_lim):
        """
        Carga en los entries los SP/T recibidos (listas o tuplas).
        Aplica las mismas reglas (truncado, tope 600).
        """
        try:
            for i in range(8):
                sp_val = sp_list[i] if i < len(sp_list) else 0
                t_val = t_list[i] if i < len(t_list) else 0
                sp = self._sp_int_trunc_capped(sp_val, 600)
                ti = self._int_trunc_or_zero(t_val)
                sp_entry, t_entry = self.campos[i]
                sp_entry.delete(0, tk.END)
                sp_entry.insert(0, str(sp))
                t_entry.delete(0, tk.END)
                t_entry.insert(0, str(ti))

            pl = self._paso_limite_valido(str(paso_lim))
            self.entry_limite.delete(0, tk.END)
            self.entry_limite.insert(0, str(pl))
        except Exception as e:
            print(f"[Rampa] Error al aplicar datos: {e}")

    # ----------------- solicitud/envio -----------------
    def _solicitar_rampa_actual(self):
        """Al abrir: $;2;ID_OMEGA;4;3;!"""
        msg = f"$;2;{self.id_omega};4;3;!"
        print("[TX] Solicitud rampa:", msg)
        if self.controlador and hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
        elif self.arduino:
            try:
                self.arduino.write((msg + "\n").encode("utf-8"))
            except Exception as e:
                print("Error al enviar solicitud rampa:", e)

    def enviar_rampa(self):
        """
        Construye y envia:
          $;2;ID_OMEGA;1;3;SP0;SP1;...;SP7;T0;T1;...;T7;PASO_LIM;!
        - SP/T siempre enteros por truncado
        - SP limitado a 600
        - Vacio/invalido -> 0
        """
        sp_list_int = []
        t_list_int = []

        # recolectar SP y T (truncados; SP con limite 600)
        for entry_sp, entry_t in self.campos:
            sp_list_int.append(self._sp_int_trunc_capped(
                entry_sp.get(), max_sp=600))
            t_list_int.append(self._int_trunc_or_zero(entry_t.get()))

        # paso limite
        paso_lim = self._paso_limite_valido(self.entry_limite.get())

        # construir mensaje EXACTO: $;2;ID;1;3;sp0..sp7;t0..t7;pasoLim;!
        partes = ["$;2", str(self.id_omega), "1", "3"]
        partes.extend(str(v) for v in sp_list_int)  # SP0..SP7
        partes.extend(str(v) for v in t_list_int)   # T0..T7
        partes.append(str(paso_lim))                # Paso limite
        mensaje = ";".join(partes) + ";!"           # cierre final ;!

        print("[TX] Mensaje Rampa:", mensaje)

        # envio centralizado
        if self.controlador and hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)
        elif self.arduino:
            try:
                self.arduino.write((mensaje + "\n").encode("utf-8"))
            except Exception as e:
                print("Error al enviar al Arduino:", e)

        self._on_close()

        # ----------------- cierre/limpieza -----------------
    def _on_close(self):
        # Desregistrar este handle en la App
        try:
            if self.controlador is not None:
                attr = f"_rampa_win_{self.id_omega}"
                if getattr(self.controlador, attr, None) is self:
                    setattr(self.controlador, attr, None)
        except Exception:
            pass
        self.destroy()
