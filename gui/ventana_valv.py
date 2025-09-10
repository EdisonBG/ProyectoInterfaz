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

    - Solenoide (ID 5):
      * Toggle manual (Abrir/Cerrar)  : $;3;5;1;{1|2};P;!
        (1=abierta, 2=cerrada; P = presion seguridad entera [bar], default 25, tope 25)
      * Presion automatica (al modificar entry): $;3;5;0;P;!
        (0=modo automatico; P entera [bar], default 25, tope 25)
      * El entry se actualiza visualmente al tope si excede 25.

    - Bombas peristalticas 1 y 2 (IDs 6 y 7):
      * Toggle ON/OFF: $;3;{6|7};1;{1|2};!  (1=ON, 2=OFF)

    Persistencia V1/V2 en valv_pos.csv
    """

    def __init__(self, master, controlador, arduino, *args, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # --- Persistencia de posiciones (V1/V2) ---
        self._pos_file = os.path.join(
            os.path.dirname(__file__), "valv_pos.csv")

        # Estados V1/V2: "A" o "B"
        self.v1_pos = tk.StringVar(value="A")   # Entrada
        self.v2_pos = tk.StringVar(value="A")   # Salida

        # Estado Solenoide (True=abierta, False=cerrada) y presion actual
        self.sol_abierta = tk.BooleanVar(value=False)
        self.sol_presion = 25  # por defecto 25 bar (entero)

        # Estados peristalticas: True=ON, False=OFF
        self.per1_on = tk.BooleanVar(value=False)
        self.per2_on = tk.BooleanVar(value=False)

        # Estilos
        self._configurar_estilos()

        # UI
        self.crear_widgets()

        # Cargar posiciones guardadas y aplicarlas visualmente
        self._cargar_posiciones()
        self._refrescar_botones("v1")
        self._refrescar_botones("v2")

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

        style.configure("ABSelected.TButton", padding=6,
                        background="#007acc", foreground="white")
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
        for r in (0, 1, 2, 3):  # 4 secciones verticales
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

        # ====== Solenoide (seguridad, ID 5) ======
        sec_sol = ttk.LabelFrame(panel, text="Valvula solenoide (seguridad)")
        sec_sol.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        sec_sol.grid_columnconfigure(0, weight=0)
        sec_sol.grid_columnconfigure(1, weight=1)

        # Toggle manual abrir/cerrar
        self.btn_sol_toggle = ttk.Button(
            sec_sol, text=self._texto_sol(), command=self._toggle_sol)
        self.btn_sol_toggle.grid(
            row=0, column=0, columnspan=2, padx=5, pady=(8, 12), sticky="w")

        # Entry de presion seguridad (entera, por defecto 25)
        ttk.Label(sec_sol, text="Presion de seguridad (bar):").grid(
            row=1, column=0, padx=5, pady=5, sticky="e"
        )
        self.entry_p_seg = ttk.Entry(sec_sol, width=10)
        self.entry_p_seg.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.entry_p_seg.insert(0, str(self.sol_presion))

        # Lanzar teclado y al cerrar actualizar + enviar auto
        self.entry_p_seg.bind(
            "<Button-1>",
            lambda e: TecladoNumerico(
                self, self.entry_p_seg,
                on_submit=lambda v: self._aplicar_presion_y_enviar_auto(v)
            )
        )
        # Tambien enviar cuando se pierda el foco (si se edita sin el teclado)
        self.entry_p_seg.bind(
            "<FocusOut>", lambda e: self._aplicar_presion_y_enviar_auto(self.entry_p_seg.get()))

        # ====== Bombas peristalticas ======
        sec_per = ttk.LabelFrame(panel, text="Bombas peristalticas")
        sec_per.grid(row=3, column=0, sticky="nsew", padx=8, pady=8)
        sec_per.grid_columnconfigure(0, weight=1)

        self.btn_per1 = ttk.Button(
            sec_per, text=self._texto_per1(), command=self._toggle_per1)
        self.btn_per1.grid(row=0, column=0, padx=6, pady=(6, 4), sticky="w")

        self.btn_per2 = ttk.Button(
            sec_per, text=self._texto_per2(), command=self._toggle_per2)
        self.btn_per2.grid(row=1, column=0, padx=6, pady=(4, 8), sticky="w")

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
            self.btn_v1_a.configure(
                style="ABSelected.TButton" if sel == "A" else "AB.TButton")
            self.btn_v1_b.configure(
                style="ABSelected.TButton" if sel == "B" else "AB.TButton")
        elif cual == "v2":
            sel = self.v2_pos.get()
            self.btn_v2_a.configure(
                style="ABSelected.TButton" if sel == "A" else "AB.TButton")
            self.btn_v2_b.configure(
                style="ABSelected.TButton" if sel == "B" else "AB.TButton")

    def _texto_sol(self) -> str:
        # True (abierta) => mostrar opcion de cerrar; False (cerrada) => mostrar abrir
        return "Cerrar valvula" if self.sol_abierta.get() else "Abrir valvula"

    def _texto_per1(self) -> str:
        return "Peristaltica 1: OFF ? ON" if not self.per1_on.get() else "Peristaltica 1: ON ? OFF"

    def _texto_per2(self) -> str:
        return "Peristaltica 2: OFF ? ON" if not self.per2_on.get() else "Peristaltica 2: ON ? OFF"

    # ================= Handlers V1/V2 =================
    def _seleccionar_posicion(self, cual: str, pos: str):
        """
        Boton Posicion A/B para V1 o V2:
         - Actualiza variable y estilo
         - Guarda CSV
         - Envia: $;3;{1|2};1;{1|2};!
        """
        if pos not in ("A", "B"):
            return

        if cual == "v1":
            self.v1_pos.set(pos)
            self._refrescar_botones("v1")
            id_valvula = "1"
        elif cual == "v2":
            self.v2_pos.set(pos)
            self._refrescar_botones("v2")
            id_valvula = "2"
        else:
            return

        self._guardar_posiciones()

        pos_code = "1" if pos == "A" else "2"
        mensaje = f"$;3;{id_valvula};1;{pos_code};!"
        print(f"[TX] Valvula {id_valvula} ->", mensaje)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    # ================= Solenoide (ID 5) =================
    def _leer_presion_entera_capada(self, v) -> int:
        """
        Devuelve presion entera en bar (capada a 25). Acepta str/int/float/None.
        Si no es valida -> 25 (default).
        """
        try:
            s = "25" if v is None else str(v).strip() or "25"
            p = int(float(s))      # truncado
        except Exception:
            p = 25
        if p > 25:
            p = 25
        return p

    def _aplicar_presion_y_enviar_auto(self, valor):
        """
        1) Aplica presion al Entry (cap 25)
        2) Actualiza self.sol_presion
        3) Envia AUTOMATICO: $;3;5;0;P;!
        """
        p = self._leer_presion_entera_capada(valor)
        self.sol_presion = p
        # reflejar visualmente (por si hubo capado)
        self.entry_p_seg.delete(0, tk.END)
        self.entry_p_seg.insert(0, str(p))

        msg = f"$;3;5;0;{p};!"
        print("[TX] Solenoide (auto, presion set):", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _toggle_sol(self):
        """
        Toggle manual de la solenoide:
         - Usa presion actual del entry (cap 25, default 25)
         - Cambia estado local y texto boton
         - Envia: $;3;5;1;{1|2};P;!
           (1=abierta, 2=cerrada)
        """
        p = self._leer_presion_entera_capada(self.entry_p_seg.get())
        self.sol_presion = p
        # reflejar entry (por si hubo capado)
        self.entry_p_seg.delete(0, tk.END)
        self.entry_p_seg.insert(0, str(p))

        nuevo = not self.sol_abierta.get()
        self.sol_abierta.set(nuevo)
        self.btn_sol_toggle.configure(text=self._texto_sol())

        estado = "1" if nuevo else "2"   # 1=abierta, 2=cerrada
        msg = f"$;3;5;1;{estado};{p};!"
        print("[TX] Solenoide (manual):", msg)
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
