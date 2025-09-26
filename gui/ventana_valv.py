import os
import csv
import tkinter as tk
from tkinter import ttk
from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico


class VentanaValv(tk.Frame):
    """
    Ventana de válvulas y bombas (optimizada para 1024x600):

    - Válvula 1 (Entrada)  : A/B (mutuamente excluyentes)
    - Válvula 2 (Salida)   : A/B (mutuamente excluyentes)
      Mensaje normal: $;3;{1|2};1;{1|2};!

    - Conexión equipo 2 (toggle):
      * Al activar: deshabilita Válvula 2; Válvula 1 pasa a $;3;1;8;{1|2};!
        y se envía una vez $;3;0;8;!
      * Al desactivar: Válvula 1 vuelve a $;3;1;1;{1|2};!

    - Bypass (reemplaza Motor 1/2):
      * Toggle entre Bypass 1 ↔ Bypass 2
      * Mensaje: $;3;3;1;{1|2};!   (1=Bypass 1, 2=Bypass 2)
      * Persiste en valv_pos.csv con clave BYP=1|2
      * No se reenvía si no hay cambio

    - Solenoide (ID 5):
      * Manual: $;3;5;1;{1|2};P;!
      * Auto al editar presión: $;3;5;0;P;!   (P=bar*10, máx 20.0)

    - Peristálticas (IDs 6 y 7): $;3;{6|7};1;{1|2};! (ON/OFF)

    Persistencia: V1/V2/BYP en valv_pos.csv (formato clave,valor)
    """

    # ------------- init -------------
    def __init__(self, master, controlador, arduino, *args, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Archivo persistencia (CSV sencillo)
        self._pos_file = os.path.join(os.path.dirname(__file__), "valv_pos.csv")

        # Estados V1/V2 (persisten)
        self.v1_pos = tk.StringVar(value="A")
        self.v2_pos = tk.StringVar(value="A")

        # Conexión equipo 2
        self.conexion_equipo2 = tk.BooleanVar(value=False)

        # Solenoide
        self.sol_abierta = tk.BooleanVar(value=False)
        self.sol_presion = 20.0  # bar

        # Peristálticas
        self.per1_on = tk.BooleanVar(value=False)
        self.per2_on = tk.BooleanVar(value=False)

        # Bypass (1 o 2) – ahora también persiste (clave BYP)
        self.bypass_sel = tk.IntVar(value=1)  # 1=Bypass 1, 2=Bypass 2

        # Estilos / UI
        self._configurar_estilos()
        self._build_ui()

        # Cargar y reflejar V1/V2/BYP guardadas
        self._cargar_posiciones()
        self._refrescar_botones("v1")
        self._refrescar_botones("v2")
        # Refrescar texto del botón BYP según persistencia
        self.btn_bypass.configure(text=self._texto_bypass())

    # ------------- Estilos -------------
    def _configurar_estilos(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("AB.TButton", padding=6)
        style.map("AB.TButton",
                  background=[("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")])

        style.configure("ABSelected.TButton",
                        padding=6, background="#007acc", foreground="white")
        style.map("ABSelected.TButton",
                  background=[("!disabled", "#007acc"), ("pressed", "#0062a3")],
                  foreground=[("!disabled", "white")])

    # ------------- UI -------------
    def _build_ui(self):
        # Layout raíz: barra izq + contenido der
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # Barra de navegación SIN márgenes
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=230)
        barra.grid(row=0, column=0, sticky="ns")   # sin padx/pady
        barra.grid_propagate(False)

        # Contenedor derecho
        wrap = ttk.Frame(self)
        wrap.grid(row=0, column=1, sticky="nsew")  # sin padding para aprovechar ancho
        # Rejilla 2×N para "tarjetas"
        for c in (0, 1):
            wrap.grid_columnconfigure(c, weight=1, uniform="cols")
        for r in range(4):
            wrap.grid_rowconfigure(r, weight=1, uniform="rows")

        card_pad = dict(padx=6, pady=6)
        in_padx, in_pady = 6, 8

        # --- Tarjeta: Válvula 1 (Entrada) ---
        card_v1 = ttk.LabelFrame(wrap, text="Válvula 1 (Entrada)")
        card_v1.grid(row=0, column=0, sticky="nsew", **card_pad)
        card_v1.grid_columnconfigure(0, weight=1)
        ttk.Label(card_v1, text="Posición:").grid(row=0, column=0, padx=in_padx, pady=(in_pady, 4), sticky="w")
        btns_v1 = ttk.Frame(card_v1)
        btns_v1.grid(row=1, column=0, padx=in_padx, pady=(0, in_pady), sticky="w")
        self.btn_v1_a = ttk.Button(btns_v1, text="A", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v1", "A"))
        self.btn_v1_b = ttk.Button(btns_v1, text="B", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v1", "B"))
        self.btn_v1_a.grid(row=0, column=0, padx=(0, 6))
        self.btn_v1_b.grid(row=0, column=1, padx=(6, 0))

        # --- Tarjeta: Válvula 2 (Salida) ---
        card_v2 = ttk.LabelFrame(wrap, text="Válvula 2 (Salida)")
        card_v2.grid(row=0, column=1, sticky="nsew", **card_pad)
        card_v2.grid_columnconfigure(0, weight=1)
        ttk.Label(card_v2, text="Posición:").grid(row=0, column=0, padx=in_padx, pady=(in_pady, 4), sticky="w")
        btns_v2 = ttk.Frame(card_v2)
        btns_v2.grid(row=1, column=0, padx=in_padx, pady=(0, in_pady), sticky="w")
        self.btn_v2_a = ttk.Button(btns_v2, text="A", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v2", "A"))
        self.btn_v2_b = ttk.Button(btns_v2, text="B", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v2", "B"))
        self.btn_v2_a.grid(row=0, column=0, padx=(0, 6))
        self.btn_v2_b.grid(row=0, column=1, padx=(6, 0))

        # --- Tarjeta: Conexión equipo 2 ---
        card_con = ttk.LabelFrame(wrap, text="Conexión equipo 2")
        card_con.grid(row=1, column=0, sticky="nsew", **card_pad)
        self.btn_con_eq2 = ttk.Button(card_con, text=self._texto_conexion(),
                                      command=self._toggle_conexion)
        self.btn_con_eq2.grid(row=0, column=0, padx=in_padx, pady=in_pady, sticky="w")

        # --- Tarjeta: Bypass ---
        card_bp = ttk.LabelFrame(wrap, text="Bypass")
        card_bp.grid(row=1, column=1, sticky="nsew", **card_pad)
        card_bp.grid_columnconfigure(0, weight=1)
        self.btn_bypass = ttk.Button(
            card_bp, text=self._texto_bypass(), command=self._toggle_bypass, width=18
        )
        self.btn_bypass.grid(row=0, column=0, padx=in_padx, pady=in_pady, sticky="w")

        # --- Tarjeta: Solenoide (seguridad) ---
        card_sol = ttk.LabelFrame(wrap, text="Válvula solenoide (seguridad)")
        card_sol.grid(row=2, column=0, sticky="nsew", **card_pad)
        card_sol.grid_columnconfigure(1, weight=1)
        self.btn_sol_toggle = ttk.Button(card_sol, text=self._texto_sol(), command=self._toggle_sol)
        self.btn_sol_toggle.grid(row=0, column=0, columnspan=2, padx=in_padx, pady=(in_pady, 6), sticky="w")

        ttk.Label(card_sol, text="Presión de seguridad (bar):").grid(
            row=1, column=0, padx=in_padx, pady=6, sticky="e"
        )
        self.entry_p_seg = ttk.Entry(card_sol, width=10)
        self.entry_p_seg.grid(row=1, column=1, padx=(4, in_padx), pady=6, sticky="w")
        self.entry_p_seg.insert(0, f"{self.sol_presion:.1f}")
        self.entry_p_seg.bind("<Button-1>", lambda e: TecladoNumerico(
            self, self.entry_p_seg, on_submit=lambda v: self._aplicar_presion_y_enviar_auto(v)))
        self.entry_p_seg.bind("<FocusOut>", lambda _e: self._aplicar_presion_y_enviar_auto(self.entry_p_seg.get()))

        # --- Tarjeta: Peristálticas ---
        card_per = ttk.LabelFrame(wrap, text="Bombas peristálticas")
        card_per.grid(row=2, column=1, sticky="nsew", **card_pad)
        self.btn_per1 = ttk.Button(card_per, text=self._texto_per1(), command=self._toggle_per1, width=20)
        self.btn_per2 = ttk.Button(card_per, text=self._texto_per2(), command=self._toggle_per2, width=20)
        self.btn_per1.grid(row=0, column=0, padx=in_padx, pady=(in_pady, 6), sticky="w")
        self.btn_per2.grid(row=1, column=0, padx=in_padx, pady=(0, in_pady), sticky="w")

        # Establecer estado inicial de conexión
        self._aplicar_estado_conexion()

    # ------------- Persistencia V1/V2/BYP -------------
    def _cargar_posiciones(self):
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
                    elif key == "BYP" and val in ("1", "2"):
                        try:
                            self.bypass_sel.set(int(val))
                        except Exception:
                            self.bypass_sel.set(1)
        except Exception as e:
            print(f"[WARN] No se pudo leer {self._pos_file}: {e}")

    def _guardar_posiciones(self):
        try:
            with open(self._pos_file, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["V1", self.v1_pos.get()])
                w.writerow(["V2", self.v2_pos.get()])
                w.writerow(["BYP", str(self.bypass_sel.get())])
        except Exception as e:
            print(f"[WARN] No se pudo escribir {self._pos_file}: {e}")

    # ------------- Helpers UI -------------
    def _refrescar_botones(self, cual: str):
        if cual == "v1":
            sel = self.v1_pos.get()
            self.btn_v1_a.configure(style="ABSelected.TButton" if sel == "A" else "AB.TButton")
            self.btn_v1_b.configure(style="ABSelected.TButton" if sel == "B" else "AB.TButton")
        elif cual == "v2":
            sel = self.v2_pos.get()
            self.btn_v2_a.configure(style="ABSelected.TButton" if sel == "A" else "AB.TButton")
            self.btn_v2_b.configure(style="ABSelected.TButton" if sel == "B" else "AB.TButton")

    def _texto_sol(self) -> str:
        return "Cerrar válvula" if self.sol_abierta.get() else "Abrir válvula"

    def _texto_per1(self) -> str:
        return "Peristáltica 1: OFF → ON" if not self.per1_on.get() else "Peristáltica 1: ON → OFF"

    def _texto_per2(self) -> str:
        return "Peristáltica 2: OFF → ON" if not self.per2_on.get() else "Peristáltica 2: ON → OFF"

    def _texto_conexion(self) -> str:
        return "Conexión equipo 2: OFF" if not self.conexion_equipo2.get() else "Conexión equipo 2: ON"

    def _texto_bypass(self) -> str:
        return f"Bypass {self.bypass_sel.get()}  (cambiar)"

    # ------------- Handlers V1/V2 -------------
    def _seleccionar_posicion(self, cual: str, pos: str):
        if pos not in ("A", "B"):
            return
        pos_code = "1" if pos == "A" else "2"

        if cual == "v1":
            if self.v1_pos.get() == pos:
                self._refrescar_botones("v1")
                return
            self.v1_pos.set(pos)
            self._refrescar_botones("v1")
            mensaje = f"$;3;1;8;{pos_code};!" if self.conexion_equipo2.get() else f"$;3;1;1;{pos_code};!"
            self._guardar_posiciones()

        elif cual == "v2":
            if self.conexion_equipo2.get():
                return  # V2 deshabilitada
            if self.v2_pos.get() == pos:
                self._refrescar_botones("v2")
                return
            self.v2_pos.set(pos)
            self._refrescar_botones("v2")
            mensaje = f"$;3;2;1;{pos_code};!"
            self._guardar_posiciones()
        else:
            return

        print("[TX]", mensaje)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    # ------------- Conexión equipo 2 -------------
    def _toggle_conexion(self):
        nuevo = not self.conexion_equipo2.get()
        self.conexion_equipo2.set(nuevo)
        self.btn_con_eq2.configure(text=self._texto_conexion())
        self._aplicar_estado_conexion()
        if nuevo:
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

    # ------------- Solenoide (ID 5) -------------
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
        print("[TX]", msg)
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
        print("[TX]", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    # ------------- Bypass (CMD 3; Valvs motor; manual; 1/2) -------------
    def _toggle_bypass(self):
        nuevo = 2 if self.bypass_sel.get() == 1 else 1
        if nuevo == self.bypass_sel.get():
            return  # sin cambio
        self.bypass_sel.set(nuevo)
        self.btn_bypass.configure(text=self._texto_bypass())

        # Persistir BYP junto con V1/V2
        self._guardar_posiciones()

        mfc_win = getattr(self.controlador, "_ventana_mfc", None)
        if mfc_win is not None and hasattr(mfc_win, "_reload_bypass_and_refresh"):
            mfc_win._reload_bypass_and_refresh()

        # Enviar sólo si cambió
        msg = f"$;3;3;1;{nuevo};!"
        print("[TX] Bypass ->", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    # ------------- Peristálticas (6/7) -------------
    def _toggle_per1(self):
        nuevo = not self.per1_on.get()
        self.per1_on.set(nuevo)
        self.btn_per1.configure(text=self._texto_per1())
        estado = "1" if nuevo else "2"
        msg = f"$;3;6;1;{estado};!"
        print("[TX]", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _toggle_per2(self):
        nuevo = not self.per2_on.get()
        self.per2_on.set(nuevo)
        self.btn_per2.configure(text=self._texto_per2())
        estado = "1" if nuevo else "2"
        msg = f"$;3;7;1;{estado};!"
        print("[TX]", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
