import os
import csv
import tkinter as tk
from tkinter import ttk
from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico


class VentanaValv(tk.Frame):
    """
    Ventana de valvulas y bombas:

    - Valvula 1 (Entrada)  : Botones Posicion A / Posicion B (mutuamente excluyentes)
    - Valvula 2 (Salida)   : Botones Posicion A / Posicion B (mutuamente excluyentes)
      -> Mensaje al presionar A/B: $;3;{1|2};1;{1|2};!
         3=CMD valvulas, {1|2}=ID (entrada/salida), 1=modo manual, {1|2}=A/B

    - Conexión equipo 2 (toggle):
      * Al activar: deshabilita Válvula 2; Válvula 1 pasa a enviar $;3;1;8;{1|2};!
        y se envía una vez $;3;0;8;!
      * Al desactivar: habilita Válvula 2; Válvula 1 vuelve a $;3;1;1;{1|2};!

    - Válvulas motor 1 y 2:
      * Dos botones excluyentes: Izquierda / Derecha
      * Mensaje: $;3;{3|4};1;{1|2};!   (1=derecha, 2=izquierda)

    - Solenoide (ID 5):
      * Toggle manual (Abrir/Cerrar)  : $;3;5;1;{1|2};P;!
        (1=abierta, 2=cerrada; P = presion seguridad *10 [bar*10], default 20.0, tope 20.0)
      * Presion automatica (al modificar entry): $;3;5;0;P;!
        (0=modo automatico; P [bar*10], default 20.0, tope 20.0)

    - Bombas peristalticas 1 y 2 (IDs 6 y 7):
      * Toggle ON/OFF: $;3;{6|7};1;{1|2};!  (1=ON, 2=OFF)

    Persistencia V1/V2 en valv_pos.csv
    """

    def __init__(self, master, controlador, arduino, *args, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # --- Persistencia de posiciones (V1/V2) ---
        self._pos_file = os.path.join(os.path.dirname(__file__), "valv_pos.csv")

        # Estados V1/V2: "A" o "B"
        self.v1_pos = tk.StringVar(value="A")   # Entrada
        self.v2_pos = tk.StringVar(value="A")   # Salida

        # Estado Conexión equipo 2
        self.conexion_equipo2 = tk.BooleanVar(value=False)

        # Estado Solenoide (True=abierta, False=cerrada) y presion actual (float)
        self.sol_abierta = tk.BooleanVar(value=False)
        self.sol_presion = 20.0  # por defecto 20.0 bar

        # Estados peristalticas: True=ON, False=OFF
        self.per1_on = tk.BooleanVar(value=False)
        self.per2_on = tk.BooleanVar(value=False)

        # Estados válvulas motor (D/I)
        self.vm1_dir = tk.StringVar(value="D")  # D=derecha, I=izquierda
        self.vm2_dir = tk.StringVar(value="D")

        # Estilos
        self._configurar_estilos()

        # UI
        self.crear_widgets()

        # Cargar posiciones guardadas y aplicarlas visualmente
        self._cargar_posiciones()
        self._refrescar_botones("v1")
        self._refrescar_botones("v2")
        self._refrescar_botones_vm("vm1")
        self._refrescar_botones_vm("vm2")

    # ================= UI / Estilos =================
    def _configurar_estilos(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Botones A/B estandar y resaltado
        style.configure("AB.TButton", padding=6)
        style.map(
            "AB.TButton",
            background=[("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")],
        )

        style.configure("ABSelected.TButton", padding=6, background="#007acc", foreground="white")
        style.map(
            "ABSelected.TButton",
            background=[("!disabled", "#007acc"), ("pressed", "#0062a3")],
            foreground=[("!disabled", "white")],
        )

    def crear_widgets(self):
        # Layout raiz: barra izq + contenido der
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegacion
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=230)
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        # Panel derecho
        panel = ttk.Frame(self)
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 10), pady=10)
        panel.grid_columnconfigure(0, weight=1)
        for r in range(6):  # más filas para secciones adicionales
            panel.grid_rowconfigure(r, weight=1)

        # ====== Valvula 1 (Entrada) ======
        sec_v1 = ttk.LabelFrame(panel, text="Valvula 1 (Entrada)")
        sec_v1.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        sec_v1.grid_columnconfigure(0, weight=1)

        self.btn_v1_a = ttk.Button(
            sec_v1, text="Posicion A", style="AB.TButton",
            command=lambda: self._seleccionar_posicion("v1", "A")
        )
        self.btn_v1_b = ttk.Button(
            sec_v1, text="Posicion B", style="AB.TButton",
            command=lambda: self._seleccionar_posicion("v1", "B")
        )
        self.btn_v1_a.grid(row=0, column=0, padx=6, pady=10, sticky="w")
        self.btn_v1_b.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        # ====== Valvula 2 (Salida) ======
        sec_v2 = ttk.LabelFrame(panel, text="Valvula 2 (Salida)")
        sec_v2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        sec_v2.grid_columnconfigure(0, weight=1)

        self.btn_v2_a = ttk.Button(
            sec_v2, text="Posicion A", style="AB.TButton",
            command=lambda: self._seleccionar_posicion("v2", "A")
        )
        self.btn_v2_b = ttk.Button(
            sec_v2, text="Posicion B", style="AB.TButton",
            command=lambda: self._seleccionar_posicion("v2", "B")
        )
        self.btn_v2_a.grid(row=0, column=0, padx=6, pady=10, sticky="w")
        self.btn_v2_b.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        # ====== Conexión equipo 2 (toggle) ======
        sec_con = ttk.LabelFrame(panel, text="Conexión equipo 2")
        sec_con.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        self.btn_con_eq2 = ttk.Button(
            sec_con, text=self._texto_conexion(), command=self._toggle_conexion
        )
        self.btn_con_eq2.grid(row=0, column=0, padx=6, pady=10, sticky="w")

        # ====== Válvula Motor 1 ======
        sec_vm1 = ttk.LabelFrame(panel, text="Válvula motor 1")
        sec_vm1.grid(row=3, column=0, sticky="nsew", padx=8, pady=8)
        sec_vm1.grid_columnconfigure(0, weight=1)

        self.btn_vm1_der = ttk.Button(
            sec_vm1, text="Derecha", style="AB.TButton",
            command=lambda: self._seleccionar_motor("vm1", "D")
        )
        self.btn_vm1_izq = ttk.Button(
            sec_vm1, text="Izquierda", style="AB.TButton",
            command=lambda: self._seleccionar_motor("vm1", "I")
        )
        self.btn_vm1_der.grid(row=0, column=0, padx=6, pady=10, sticky="w")
        self.btn_vm1_izq.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        # ====== Válvula Motor 2 ======
        sec_vm2 = ttk.LabelFrame(panel, text="Válvula motor 2")
        sec_vm2.grid(row=4, column=0, sticky="nsew", padx=8, pady=8)
        sec_vm2.grid_columnconfigure(0, weight=1)

        self.btn_vm2_der = ttk.Button(
            sec_vm2, text="Derecha", style="AB.TButton",
            command=lambda: self._seleccionar_motor("vm2", "D")
        )
        self.btn_vm2_izq = ttk.Button(
            sec_vm2, text="Izquierda", style="AB.TButton",
            command=lambda: self._seleccionar_motor("vm2", "I")
        )
        self.btn_vm2_der.grid(row=0, column=0, padx=6, pady=10, sticky="w")
        self.btn_vm2_izq.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        # ====== Solenoide (seguridad, ID 5) ======
        sec_sol = ttk.LabelFrame(panel, text="Valvula solenoide (seguridad)")
        sec_sol.grid(row=5, column=0, sticky="nsew", padx=8, pady=8)
        sec_sol.grid_columnconfigure(0, weight=0)
        sec_sol.grid_columnconfigure(1, weight=1)

        # Toggle manual abrir/cerrar
        self.btn_sol_toggle = ttk.Button(
            sec_sol, text=self._texto_sol(), command=self._toggle_sol)
        self.btn_sol_toggle.grid(row=0, column=0, columnspan=2, padx=5, pady=(8, 12), sticky="w")

        # Entry de presion seguridad (float, default 20.0, tope 20.0)
        ttk.Label(sec_sol, text="Presion de seguridad (bar):").grid(
            row=1, column=0, padx=5, pady=5, sticky="e"
        )
        self.entry_p_seg = ttk.Entry(sec_sol, width=10)
        self.entry_p_seg.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.entry_p_seg.insert(0, f"{self.sol_presion:.1f}")

        # Lanzar teclado y al cerrar actualizar + enviar auto
        self.entry_p_seg.bind(
            "<Button-1>",
            lambda e: TecladoNumerico(
                self, self.entry_p_seg,
                on_submit=lambda v: self._aplicar_presion_y_enviar_auto(v)
            )
        )
        # Enviar al perder foco
        self.entry_p_seg.bind("<FocusOut>", lambda e: self._aplicar_presion_y_enviar_auto(self.entry_p_seg.get()))

        # ====== Bombas peristalticas ======
        sec_per = ttk.LabelFrame(panel, text="Bombas peristalticas")
        sec_per.grid(row=6, column=0, sticky="nsew", padx=8, pady=8)
        sec_per.grid_columnconfigure(0, weight=1)

        self.btn_per1 = ttk.Button(sec_per, text=self._texto_per1(), command=self._toggle_per1)
        self.btn_per1.grid(row=0, column=0, padx=6, pady=(6, 4), sticky="w")

        self.btn_per2 = ttk.Button(sec_per, text=self._texto_per2(), command=self._toggle_per2)
        self.btn_per2.grid(row=1, column=0, padx=6, pady=(4, 8), sticky="w")

        # asegúrate de aplicar estado inicial de conexión
        self._aplicar_estado_conexion()

    # ================= Persistencia V1/V2 =================
    def _cargar_posiciones(self):
        if not os.path.exists(self._pos_file):
            return
        try:
            with open(self._pos_file, newline="", encoding="utf-8") as f:
                for nombre, pos in csv.reader(f):
                    pos = (pos or "").strip().upper()
                    if nombre == "V1" and pos in ("A", "B"):
                        self.v1_pos.set(pos)
                    elif nombre == "V2" and pos in ("A", "B"):
                        self.v2_pos.set(pos)
        except Exception as e:
            print(f"[WARN] No se pudo leer {self._pos_file}: {e}")

    def _guardar_posiciones(self):
        try:
            with open(self._pos_file, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["V1", self.v1_pos.get()])
                w.writerow(["V2", self.v2_pos.get()])
        except Exception as e:
            print(f"[WARN] No se pudo escribir {self._pos_file}: {e}")

    # ================= Helpers UI =================
    def _refrescar_botones(self, cual: str):
        if cual == "v1":
            sel = self.v1_pos.get()
            self.btn_v1_a.configure(style="ABSelected.TButton" if sel == "A" else "AB.TButton")
            self.btn_v1_b.configure(style="ABSelected.TButton" if sel == "B" else "AB.TButton")
        elif cual == "v2":
            sel = self.v2_pos.get()
            self.btn_v2_a.configure(style="ABSelected.TButton" if sel == "A" else "AB.TButton")
            self.btn_v2_b.configure(style="ABSelected.TButton" if sel == "B" else "AB.TButton")

    def _refrescar_botones_vm(self, cual: str):
        if cual == "vm1":
            sel = self.vm1_dir.get()  # 'D'/'I'
            self.btn_vm1_der.configure(style="ABSelected.TButton" if sel == "D" else "AB.TButton")
            self.btn_vm1_izq.configure(style="ABSelected.TButton" if sel == "I" else "AB.TButton")
        elif cual == "vm2":
            sel = self.vm2_dir.get()
            self.btn_vm2_der.configure(style="ABSelected.TButton" if sel == "D" else "AB.TButton")
            self.btn_vm2_izq.configure(style="ABSelected.TButton" if sel == "I" else "AB.TButton")

    def _texto_sol(self) -> str:
        # True (abierta) => mostrar opcion de cerrar; False (cerrada) => mostrar abrir
        return "Cerrar valvula" if self.sol_abierta.get() else "Abrir valvula"

    def _texto_per1(self) -> str:
        return "Peristaltica 1: OFF ? ON" if not self.per1_on.get() else "Peristaltica 1: ON ? OFF"

    def _texto_per2(self) -> str:
        return "Peristaltica 2: OFF ? ON" if not self.per2_on.get() else "Peristaltica 2: ON ? OFF"

    def _texto_conexion(self) -> str:
        return "Conexión equipo 2: OFF" if not self.conexion_equipo2.get() else "Conexión equipo 2: ON"

    # ================= Handlers V1/V2 =================
    def _seleccionar_posicion(self, cual: str, pos: str):
        """
        Boton Posicion A/B para V1 o V2:
         - Actualiza variable y estilo
         - Guarda CSV (solo V1/V2)
         - Envia:
            * Modo normal:
                V1 -> $;3;1;1;{1|2};!
                V2 -> $;3;2;1;{1|2};!
            * Conexión equipo 2 (activo):
                V1 -> $;3;1;8;{1|2};!
                (V2 está deshabilitada)
        """
        if pos not in ("A", "B"):
            return

        pos_code = "1" if pos == "A" else "2"

        if cual == "v1":
            self.v1_pos.set(pos)
            self._refrescar_botones("v1")

            if self.conexion_equipo2.get():
                mensaje = f"$;3;1;8;{pos_code};!"
            else:
                mensaje = f"$;3;1;1;{pos_code};!"

            self._guardar_posiciones()

        elif cual == "v2":
            # si conexión ON, V2 está deshabilitada (no debería llamarse)
            if self.conexion_equipo2.get():
                return
            self.v2_pos.set(pos)
            self._refrescar_botones("v2")
            mensaje = f"$;3;2;1;{pos_code};!"
            self._guardar_posiciones()

        else:
            return

        print(f"[TX] {cual.upper()} ->", mensaje)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    # ================ Conexión equipo 2 =================
    def _toggle_conexion(self):
        nuevo = not self.conexion_equipo2.get()
        self.conexion_equipo2.set(nuevo)
        self.btn_con_eq2.configure(text=self._texto_conexion())
        self._aplicar_estado_conexion()

        if nuevo:
            # al activar, enviar $;3;0;8;!
            msg = "$;3;0;8;!"
            print("[TX] Conexión equipo 2 ACTIVADA:", msg)
            if hasattr(self.controlador, "enviar_a_arduino"):
                self.controlador.enviar_a_arduino(msg)

    def _aplicar_estado_conexion(self):
        on = self.conexion_equipo2.get()
        # V2 deshabilitada en conexión ON
        state_v2 = ("disabled" if on else "normal")
        self.btn_v2_a.configure(state=state_v2)
        self.btn_v2_b.configure(state=state_v2)
        # V1 permanece habilitada, pero cambia el mensaje en _seleccionar_posicion
        self.btn_v1_a.configure(state="normal")
        self.btn_v1_b.configure(state="normal")

    # ================= Solenoide (ID 5) =================
    def _leer_presion_float_capada(self, v) -> float:
        """
        Devuelve presión float con 1 decimal, capada a 20.0.
        Acepta str/int/float/None. Si no es válida -> 20.0 (default).
        """
        try:
            s = "20" if v is None else str(v).strip() or "20"
            p = float(s)
        except Exception:
            p = 20.0
        if p > 20.0:
            p = 20.0
        # redondear a 1 decimal
        return round(p, 1)

    def _aplicar_presion_y_enviar_auto(self, valor):
        """
        1) Aplica presion al Entry (cap 20.0)
        2) Actualiza self.sol_presion
        3) Envia AUTOMATICO: $;3;5;0;P;!   (P = bar*10 entero)
        """
        p = self._leer_presion_float_capada(valor)
        self.sol_presion = p
        # reflejar con un decimal
        self.entry_p_seg.delete(0, tk.END)
        self.entry_p_seg.insert(0, f"{p:.1f}")

        # escalar ×10 al enviar
        p10 = int(round(p * 10))
        msg = f"$;3;5;0;{p10};!"
        print("Solenoide (auto, presion set):", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _toggle_sol(self):
        """
        Toggle manual de la solenoide:
         - Usa presion actual del entry (cap 20.0, default 20.0)
         - Cambia estado local y texto boton
         - Envia: $;3;5;1;{1|2};P;!  (1=abierta, 2=cerrada; P = bar*10)
        """
        p = self._leer_presion_float_capada(self.entry_p_seg.get())
        self.sol_presion = p
        self.entry_p_seg.delete(0, tk.END)
        self.entry_p_seg.insert(0, f"{p:.1f}")

        nuevo = not self.sol_abierta.get()
        self.sol_abierta.set(nuevo)
        self.btn_sol_toggle.configure(text=self._texto_sol())

        estado = "1" if nuevo else "2"   # 1=abierta, 2=cerrada
        p10 = int(round(p * 10))
        msg = f"$;3;5;1;{estado};{p10};!"
        print("Solenoide (manual):", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    # ================= Válvulas motor (IDs 3 y 4) =================
    def _seleccionar_motor(self, cual: str, dir_code: str):
        """
        Botones Izquierda/Derecha (mutuamente excluyentes) para VM1/VM2:
          - cual: 'vm1' o 'vm2'
          - dir_code: 'D' (derecha) o 'I' (izquierda)
        Envia:
          VM1: $;3;3;1;{1|2};!
          VM2: $;3;4;1;{1|2};!
        """
        if cual not in ("vm1", "vm2") or dir_code not in ("D", "I"):
            return

        if cual == "vm1":
            self.vm1_dir.set(dir_code)
            self._refrescar_botones_vm("vm1")
            id_motor = "3"
        else:
            self.vm2_dir.set(dir_code)
            self._refrescar_botones_vm("vm2")
            id_motor = "4"

        pos_val = "1" if dir_code == "D" else "2"  # 1=derecha, 2=izquierda
        msg = f"$;3;{id_motor};1;{pos_val};!"
        print(f"[TX] {cual.upper()} ->", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    # ================= Peristalticas (IDs 6 y 7) =================
    def _toggle_per1(self):
        """
        Toggle ON/OFF peristaltica 1:
          $;3;6;1;{1|2};!
        """
        nuevo = not self.per1_on.get()
        self.per1_on.set(nuevo)
        self.btn_per1.configure(text=self._texto_per1())

        estado = "1" if nuevo else "2"   # 1=ON, 2=OFF
        msg = f"$;3;6;1;{estado};!"
        print("[TX] Peristaltica 1:", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _toggle_per2(self):
        """
        Toggle ON/OFF peristaltica 2:
          $;3;7;1;{1|2};!
        """
        nuevo = not self.per2_on.get()
        self.per2_on.set(nuevo)
        self.btn_per2.configure(text=self._texto_per2())

        estado = "1" if nuevo else "2"   # 1=ON, 2=OFF
        msg = f"$;3;7;1;{estado};!"
        print("[TX] Peristaltica 2:", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
