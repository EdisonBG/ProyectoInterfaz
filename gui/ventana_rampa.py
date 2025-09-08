import tkinter as tk
from tkinter import ttk
from .teclado_numerico import TecladoNumerico


class VentanaRampa(tk.Toplevel):
    """
    Configuracion de Rampa para un Omega (ID 1 o 2)

    UI:
      - 8 pasos (0..7): para cada paso, Setpoint y Tiempo (min)
      - Campo "Paso limite (0-7)"

    Envio al presionar "Enviar":
      $;2;ID_OMEGA;1;3;SP0;SP1;...;SP7;T0;T1;...;T7;PASO_LIM;!

    Reglas:
      - SP y T se envian como enteros por truncado (10.5 -> 10)
      - SP se limita a max 600
      - Si un campo esta vacio o no es numero -> 0
      - Paso limite vacio/invalido/fuera de 0..7 -> 0
    """

    def __init__(self, master, id_omega, arduino, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.arduino = arduino
        self.id_omega = id_omega
        self.title(f"Rampa - Omega {id_omega}")
        self.geometry("400x560")
        self.resizable(False, False)

        # envio centralizado si el master expone 'controlador'
        self.controlador = getattr(master, "controlador", None)

        # ventana modal, por encima del padre
        self.transient(master.winfo_toplevel())
        self.wait_visibility()
        self.lift()
        self.focus_force()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        ttk.Label(self, text=f"Configuracion de Rampa - Omega {id_omega}",
                  font=("Arial", 14, "bold")).pack(pady=10)

        # Contenedor scrollable
        cont = ttk.Frame(self)
        cont.pack(pady=5)

        self.campos = []  # Lista de (entry_sp, entry_tiempo) para pasos 0..7

        # pasos 0..7
        for i in range(8):
            frame_paso = ttk.Frame(cont)
            frame_paso.pack(pady=4, anchor="w")

            for c in (0, 1, 2, 3, 4):
                frame_paso.grid_columnconfigure(c, weight=0)

            ttk.Label(frame_paso, text=f"Paso {i}")\
                .grid(row=0, column=0, padx=5, sticky="w")

            ttk.Label(frame_paso, text="Setpoint:")\
                .grid(row=0, column=1, padx=5, sticky="e")
            entrada_sp = ttk.Entry(frame_paso, width=10)
            entrada_sp.grid(row=0, column=2)
            entrada_sp.bind("<Button-1>", lambda e, entry=entrada_sp: TecladoNumerico(
                self, entry, on_submit=lambda v, ent=entry: self._rampa_aplicar_sp(ent, v)))

            ttk.Label(frame_paso, text="Tiempo (min):")\
                .grid(row=0, column=3, padx=5, sticky="e")
            entrada_tiempo = ttk.Entry(frame_paso, width=10)
            entrada_tiempo.grid(row=0, column=4)
            entrada_tiempo.bind(
                "<Button-1>",
                lambda e, entry=entrada_tiempo: TecladoNumerico(
                    self, entry,
                    on_submit=lambda v, ent=entry: self._rampa_aplicar_t(
                        ent, v)
                )
            )

            self.campos.append((entrada_sp, entrada_tiempo))

        # paso limite (0..7)
        frame_lim = ttk.Frame(self)
        frame_lim.pack(pady=10)
        ttk.Label(frame_lim, text="Paso limite (0-7):").grid(row=0,
                                                             column=0, padx=5, sticky="e")
        self.entry_limite = ttk.Entry(frame_lim, width=6)
        self.entry_limite.grid(row=0, column=1, padx=5)
        self.entry_limite.bind(
            "<Button-1>",
            lambda e: TecladoNumerico(self, self.entry_limite)
        )

        # boton enviar
        botones = ttk.Frame(self)
        botones.pack(pady=15)
        ttk.Button(botones, text="Enviar", command=self.enviar_rampa)\
            .grid(row=0, column=0, padx=8)

        # atajos
        self.bind("<Return>", lambda e: self.enviar_rampa())
        self.bind("<Escape>", lambda e: self.destroy())

    # ----------------- helpers -----------------
    def _trunc_int(self, value):
        try:
            return int(float(value))
        except Exception:
            return 0

    def _rampa_aplicar_sp(self, entry, valor):
        n = self._trunc_int(valor)
        if n > 600:
            n = 600
        entry.delete(0, tk.END)
        entry.insert(0, str(n))

    def _rampa_aplicar_t(self, entry, valor):
        n = self._trunc_int(valor)
        entry.delete(0, tk.END)
        entry.insert(0, str(n))

    def _int_trunc_or_zero(self, s: str) -> int:
        """
        Convierte texto a entero por truncado (no redondeo).
        - "" o invalido -> 0
        - "10.9" -> 10 ; "-3.7" -> -3
        """
        s = (s or "").strip()
        if not s:
            return 0
        try:
            return int(float(s))  # int() trunca hacia 0
        except Exception:
            return 0

    def _sp_int_trunc_capped(self, s: str, max_sp: int = 600) -> int:
        """
        Setpoint entero por truncado y limitado a max_sp.
        - "" o invalido -> 0
        - valor > max_sp -> max_sp
        """
        n = self._int_trunc_or_zero(s)
        if n > max_sp:
            print(f"[INFO] SP {n} mayor que {max_sp}; se envia {max_sp}")
            return max_sp
        return n

    def _paso_limite_valido(self, s: str) -> int:
        """
        Paso limite entero en 0..7; si invalido -> 0
        """
        try:
            v = int(float((s or "").strip() or "0"))
            if 0 <= v <= 7:
                return v
            return 0
        except Exception:
            return 0

    # ----------------- envio -----------------

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

        # construir mensaje
        partes = ["$;2", str(self.id_omega), "1", "3"]
        # SP0..SP7
        partes.extend(str(v) for v in sp_list_int)
        # T0..T7
        partes.extend(str(v) for v in t_list_int)
        # paso limite
        partes.append(str(paso_lim))

        mensaje = ";".join(partes) + ";!"
        print("Mensaje Rampa:", mensaje)

        # envio centralizado
        if self.controlador and hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)
        elif self.arduino:
            try:
                self.arduino.write((mensaje + "\n").encode("utf-8"))
            except Exception as e:
                print("Error al enviar al Arduino:", e)

        self.destroy()
