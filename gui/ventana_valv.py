import os
import csv
import tkinter as tk
from tkinter import ttk
from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico


class VentanaValv(tk.Frame):
    """
    Ventana de valvulas y bombas (con persistencia de posiciones V1, V2, VM1, VM2):

    - Válvula 1 (Entrada)  : A/B (mutuamente excluyentes)
    - Válvula 2 (Salida)   : A/B (mutuamente excluyentes)
      Mensaje normal: $;3;{1|2};1;{1|2};!

    - Conexión equipo 2 (toggle):
      * Al activar: deshabilita Válvula 2; Válvula 1 pasa a enviar $;3;1;8;{1|2};!
        y se envía $;3;0;8;! una vez.
      * Al desactivar: Válvula 1 vuelve a $;3;1;1;{1|2};!

    - Válvulas motor 1 y 2 (VM1=ID3, VM2=ID4):
      * Dos botones excluyentes: Izquierda / Derecha
      * Mensaje: $;3;{3|4};1;{1|2};!   (1=derecha, 2=izquierda)
      * Persisten su última posición en valv_pos.csv (claves: VM1, VM2).
      * Si se pulsa la misma posición que ya está activa, NO se envía el mensaje.

    - Solenoide (ID 5):
      * Toggle manual (Abrir/Cerrar): $;3;5;1;{1|2};P;!
      * Presión automática al editar entry: $;3;5;0;P;!   (P = bar*10, máx 20.0)

    - Peristálticas (IDs 6 y 7): toggle ON/OFF: $;3;{6|7};1;{1|2};!
    """

    def __init__(self, master, controlador, arduino, *args, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Archivo de persistencia (CSV sencillo)
        self._pos_file = os.path.join(os.path.dirname(__file__), "valv_pos.csv")

        # Estados V1/V2: "A" o "B"
        self.v1_pos = tk.StringVar(value="A")
        self.v2_pos = tk.StringVar(value="A")

        # Estado Conexión equipo 2
        self.conexion_equipo2 = tk.BooleanVar(value=False)

        # Estado Solenoide (True=abierta, False=cerrada) y presión actual
        self.sol_abierta = tk.BooleanVar(value=False)
        self.sol_presion = 20.0  # bar

        # Estados peristálticas
        self.per1_on = tk.BooleanVar(value=False)
        self.per2_on = tk.BooleanVar(value=False)

        # Estados válvulas motor (D/I). Persisten en el mismo CSV (claves: VM1, VM2)
        self.vm1_dir = tk.StringVar(value="D")  # D=derecha, I=izquierda
        self.vm2_dir = tk.StringVar(value="D")

        # Estilos y UI
        self._configurar_estilos()
        self.crear_widgets()

        # Cargar posiciones guardadas y reflejarlas
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
        for r in range(6):
            panel.grid_rowconfigure(r, weight=1)

        # ====== Válvula 1 (Entrada) ======
        sec_v1 = ttk.LabelFrame(panel, text="Válvula 1 (Entrada)")
        sec_v1.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        sec_v1.grid_columnconfigure(0, weight=1)

        self.btn_v1_a = ttk.Button(sec_v1, text="Posición A", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v1", "A"))
        self.btn_v1_b = ttk.Button(sec_v1, text="Posición B", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v1", "B"))
        self.btn_v1_a.grid(row=0, column=0, padx=6, pady=10, sticky="w")
        self.btn_v1_b.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        # ====== Válvula 2 (Salida) ======
        sec_v2 = ttk.LabelFrame(panel, text="Válvula 2 (Salida)")
        sec_v2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        sec_v2.grid_columnconfigure(0, weight=1)

        self.btn_v2_a = ttk.Button(sec_v2, text="Posición A", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v2", "A"))
        self.btn_v2_b = ttk.Button(sec_v2, text="Posición B", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v2", "B"))
        self.btn_v2_a.grid(row=0, column=0, padx=6, pady=10, sticky="w")
        self.btn_v2_b.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        # ====== Conexión equipo 2 ======
        sec_con = ttk.LabelFrame(panel, text="Conexión equipo 2")
        sec_con.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        self.btn_con_eq2 = ttk.Button(sec_con, text=self._texto_conexion(), command=self._toggle_conexion)
        self.btn_con_eq2.grid(row=0, column=0, padx=6, pady=10, sticky="w")

        # ====== Válvula motor 1 ======
        sec_vm1 = ttk.LabelFrame(panel, text="Válvula motor 1")
        sec_vm1.grid(row=3, column=0, sticky="nsew", padx=8, pady=8)
        sec_vm1.grid_columnconfigure(0, weight=1)

        self.btn_vm1_der = ttk.Button(sec_vm1, text="Derecha", style="AB.TButton",
                                      command=lambda: self._seleccionar_motor("vm1", "D"))
        self.btn_vm1_izq = ttk.Button(sec_vm1, text="Izquierda", style="AB.TButton",
                                      command=lambda: self._seleccionar_motor("vm1", "I"))
        self.btn_vm1_der.grid(row=0, column=0, padx=6, pady=10, sticky="w")
        self.btn_vm1_izq.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        # ====== Válvula motor 2 ======
        sec_vm2 = ttk.LabelFrame(panel, text="Válvula motor 2")
        sec_vm2.grid(row=4, column=0, sticky="nsew", padx=8, pady=8)
        sec_vm2.grid_columnconfigure(0, weight=1)

        self.btn_vm2_der = ttk.Button(sec_vm2, text="Derecha", style="AB.TButton",
                                      command=lambda: self._seleccionar_motor("vm2", "D"))
        self.btn_vm2_izq = ttk.Button(sec_vm2, text="Izquierda", style="AB.TButton",
                                      command=lambda: self._seleccionar_motor("vm2", "I"))
        self.btn_vm2_der.grid(row=0, column=0, padx=6, pady=10, sticky="w")
        self.btn_vm2_izq.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        # ====== Solenoide (seguridad) ======
        sec_sol = ttk.LabelFrame(panel, text="Válvula solenoide (seguridad)")
        sec_sol.grid(row=5, column=0, sticky="nsew", padx=8, pady=8)
        sec_sol.grid_columnconfigure(0, weight=0)
        sec_sol.grid_columnconfigure(1, weight=1)

        self.btn_sol_toggle = ttk.Button(sec_sol, text=self._texto_sol(), command=self._toggle_sol)
        self.btn_sol_toggle.grid(row=0, column=0, columnspan=2, padx=5, pady=(8, 12), sticky="w")

        ttk.Label(sec_sol, text="Presión de seguridad (bar):").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.entry_p_seg = ttk.Entry(sec_sol, width=10)
        self.entry_p_seg.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.entry_p_seg.insert(0, f"{self.sol_presion:.1f}")
        self.entry_p_seg.bind("<Button-1>", lambda e: TecladoNumerico(
            self, self.entry_p_seg, on_submit=lambda v: self._aplicar_presion_y_enviar_auto(v)))
        self.entry_p_seg.bind("<FocusOut>", lambda _e: self._aplicar_presion_y_enviar_auto(self.entry_p_seg.get()))

        # ====== Peristálticas ======
        sec_per = ttk.LabelFrame(panel, text="Bombas peristálticas")
        sec_per.grid(row=6, column=0, sticky="nsew", padx=8, pady=8)
        sec_per.grid_columnconfigure(0, weight=1)

        self.btn_per1 = ttk.Button(sec_per, text=self._texto_per1(), command=self._toggle_per1)
        self.btn_per1.grid(row=0, column=0, padx=6, pady=(6, 4), sticky="w")

        self.btn_per2 = ttk.Button(sec_per, text=self._texto_per2(), command=self._toggle_per2)
        self.btn_per2.grid(row=1, column=0, padx=6, pady=(4, 8), sticky="w")

        # Aplicar estado inicial de conexión
        self._aplicar_estado_conexion()

    # ================= Persistencia =================
    def _cargar_posiciones(self):
        """
        Lee valv_pos.csv. Soporta filas: V1, V2, VM1, VM2.
        Valores válidos:
          - V1/V2: 'A'/'B'
          - VM1/VM2: 'D'/'I'
        """
        if not os.path.exists(self._pos_file):
            return
        try:
            with open(self._pos_file, newline="", encoding="utf-8") as f:
                for nombre, pos in csv.reader(f):
                    key = (nombre or "").strip().upper()
                    val = (pos or "").strip().upper()
                    if key == "V1" and val in ("A", "B"):
                        self.v1_pos.set(val)
                    elif key == "V2" and val in ("A", "B"):
                        self.v2_pos.set(val)
                    elif key == "VM1" and val in ("D", "I"):
                        self.vm1_dir.set(val)
                    elif key == "VM2" and val in ("D", "I"):
                        self.vm2_dir.set(val)
        except Exception as e:
            print(f"[WARN] No se pudo leer {self._pos_file}: {e}")

    def _guardar_posiciones(self):
        """
        Escribe todas las posiciones (V1, V2, VM1, VM2) en el CSV.
        """
        try:
            with open(self._pos_file, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["V1", self.v1_pos.get()])
                w.writerow(["V2", self.v2_pos.get()])
                w.writerow(["VM1", self.vm1_dir.get()])
                w.writerow(["VM2", self.vm2_dir.get()])
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
        return "Cerrar válvula" if self.sol_abierta.get() else "Abrir válvula"

    def _texto_per1(self) -> str:
        return "Peristáltica 1: OFF → ON" if not self.per1_on.get() else "Peristáltica 1: ON → OFF"

    def _texto_per2(self) -> str:
        return "Peristáltica 2: OFF → ON" if not self.per2_on.get() else "Peristáltica 2: ON → OFF"

    def _texto_conexion(self) -> str:
        return "Conexión equipo 2: OFF" if not self.conexion_equipo2.get() else "Conexión equipo 2: ON"

    # ================= Handlers V1/V2 =================
    def _seleccionar_posicion(self, cual: str, pos: str):
        if pos not in ("A", "B"):
            return

        pos_code = "1" if pos == "A" else "2"

        if cual == "v1":
            if self.v1_pos.get() == pos:
                # Ya está en esa posición; no reenviar
                self._refrescar_botones("v1")
                return

            self.v1_pos.set(pos)
            self._refrescar_botones("v1")
            if self.conexion_equipo2.get():
                mensaje = f"$;3;1;8;{pos_code};!"
            else:
                mensaje = f"$;3;1;1;{pos_code};!"
            self._guardar_posiciones()

        elif cual == "v2":
            if self.conexion_equipo2.get():
                return  # V2 deshabilitada en conexión ON
            if self.v2_pos.get() == pos:
                self._refrescar_botones("v2")
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
        state_v2 = ("disabled" if on else "normal")
        self.btn_v2_a.configure(state=state_v2)
        self.btn_v2_b.configure(state=state_v2)
        self.btn_v1_a.configure(state="normal")
        self.btn_v1_b.configure(state="normal")

    # ================= Solenoide (ID 5) =================
    def _leer_presion_float_capada(self, v) -> float:
        try:
            s = "20" if v is None else str(v).strip() or "20"
            p = float(s)
        except Exception:
            p = 20.0
        if p > 20.0:
            p = 20.0
        return round(p, 1)

    def _aplicar_presion_y_enviar_auto(self, valor):
        p = self._leer_presion_float_capada(valor)
        self.sol_presion = p
        self.entry_p_seg.delete(0, tk.END)
        self.entry_p_seg.insert(0, f"{p:.1f}")

        p10 = int(round(p * 10))
        msg = f"$;3;5;0;{p10};!"
        print("Solenoide (auto, presion set):", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _toggle_sol(self):
        p = self._leer_presion_float_capada(self.entry_p_seg.get())
        self.sol_presion = p
        self.entry_p_seg.delete(0, tk.END)
        self.entry_p_seg.insert(0, f"{p:.1f}")

        nuevo = not self.sol_abierta.get()
        self.sol_abierta.set(nuevo)
        self.btn_sol_toggle.configure(text=self._texto_sol())

        estado = "1" if nuevo else "2"
        p10 = int(round(p * 10))
        msg = f"$;3;5;1;{estado};{p10};!"
        print("Solenoide (manual):", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    # ================= Válvulas motor (IDs 3 y 4) =================
    def _seleccionar_motor(self, cual: str, dir_code: str):
        """
        VM1/VM2: 'D' (derecha) o 'I' (izquierda).
        - No reenvía si se elige la misma dirección que ya está activa.
        - Persiste en valv_pos.csv las claves VM1 / VM2.
        """
        if cual not in ("vm1", "vm2") or dir_code not in ("D", "I"):
            return

        # Si no hay cambio, no envíes
        if cual == "vm1" and self.vm1_dir.get() == dir_code:
            self._refrescar_botones_vm("vm1")
            return
        if cual == "vm2" and self.vm2_dir.get() == dir_code:
            self._refrescar_botones_vm("vm2")
            return

        if cual == "vm1":
            self.vm1_dir.set(dir_code)
            self._refrescar_botones_vm("vm1")
            id_motor = "3"
        else:
            self.vm2_dir.set(dir_code)
            self._refrescar_botones_vm("vm2")
            id_motor = "4"

        # Guardar persistencia (incluye V1/V2 actuales también)
        self._guardar_posiciones()

        pos_val = "1" if dir_code == "D" else "2"  # 1=derecha, 2=izquierda
        msg = f"$;3;{id_motor};1;{pos_val};!"
        print(f"[TX] {cual.upper()} ->", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    # ================= Peristálticas (IDs 6 y 7) =================
    def _toggle_per1(self):
        nuevo = not self.per1_on.get()
        self.per1_on.set(nuevo)
        self.btn_per1.configure(text=self._texto_per1())

        estado = "1" if nuevo else "2"
        msg = f"$;3;6;1;{estado};!"
        print("[TX] Peristáltica 1:", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _toggle_per2(self):
        nuevo = not self.per2_on.get()
        self.per2_on.set(nuevo)
        self.btn_per2.configure(text=self._texto_per2())

        estado = "1" if nuevo else "2"
        msg = f"$;3;7;1;{estado};!"
        print("[TX] Peristáltica 2:", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
