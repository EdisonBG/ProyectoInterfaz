import os
import csv
import tkinter as tk
from tkinter import ttk
from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico


class VentanaValv(tk.Frame):
    """
    Ventana de válvulas y bombas.
    """

    def __init__(self, master, controlador, arduino, *args, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # --- Persistencia V1/V2 ---
        self._pos_file = os.path.join(os.path.dirname(__file__), "valv_pos.csv")

        # Estados
        self.v1_pos = tk.StringVar(value="A")
        self.v2_pos = tk.StringVar(value="A")
        self.conexion_equipo2 = tk.BooleanVar(value=False)
        self.sol_abierta = tk.BooleanVar(value=False)
        self.sol_presion = 20.0
        self.per1_on = tk.BooleanVar(value=False)
        self.per2_on = tk.BooleanVar(value=False)
        self.vm1_dir = tk.StringVar(value="D")
        self.vm2_dir = tk.StringVar(value="D")

        # Estilos
        self._configurar_estilos()

        # UI
        self.crear_widgets()

        # Estado inicial
        self._cargar_posiciones()
        self._refrescar_botones("v1")
        self._refrescar_botones("v2")
        self._refrescar_botones_vm("vm1")
        self._refrescar_botones_vm("vm2")

        # Forzar primer repintado (evita parches al primer cambio de pestaña)
        self.update_idletasks()

    # ================= UI / Estilos =================
    def _configurar_estilos(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass

        # Paleta
        self._BG = "#0f172a"
        self._SURFACE = "#111827"
        self._TEXT = "#e5e7eb"
        self._MUTED = "#9ca3af"
        self._BORDER = "#334155"
        self._PRIMARY = "#2563eb"
        self._PRIMARY_ACTIVE = "#1d4ed8"

        self.configure(bg=self._BG)
        self.option_add("*Font", ("TkDefaultFont", 12))
        self.option_add("*TButton.Font", ("TkDefaultFont", 12, "bold"))
        self.option_add("*Entry.Font", ("TkDefaultFont", 12))

        # Labels con fondo de tarjeta (evita rectángulos claros)
        st.configure("Valv.TLabel", background=self._SURFACE, foreground=self._TEXT)

        st.configure(
            "Valv.TEntry",
            fieldbackground=self._BG, foreground=self._TEXT,
            bordercolor=self._BORDER, lightcolor=self._PRIMARY,
            darkcolor=self._BORDER, padding=8
        )

        # Contenedores oscuros (clave para eliminar parches)
        st.configure("Valv.Container.TFrame", background=self._BG)
        st.configure("Valv.Inner.TFrame", background=self._SURFACE)

        # Botones base
        st.configure("Valv.TButton",
                     padding=(12, 10), relief="raised", borderwidth=2,
                     background=self._SURFACE, foreground=self._TEXT)
        st.map("Valv.TButton",
               background=[("active", self._BORDER)],
               relief=[("pressed", "sunken")])

        # Primarios
        st.configure("ValvPrimary.TButton",
                     padding=(12, 10), relief="raised", borderwidth=2,
                     background=self._PRIMARY, foreground="white")
        st.map("ValvPrimary.TButton",
               background=[("active", self._PRIMARY_ACTIVE)],
               relief=[("pressed", "sunken")])

        # Botones A/B (selección)
        st.configure("AB.TButton", padding=(10, 8), relief="raised", borderwidth=2,
                     background=self._SURFACE, foreground=self._TEXT)
        st.map("AB.TButton",
               background=[("active", self._BORDER)],
               relief=[("pressed", "sunken")])

        st.configure("ABSelected.TButton", padding=(10, 8), relief="raised", borderwidth=2,
                     background=self._PRIMARY, foreground="white")
        st.map("ABSelected.TButton",
               background=[("active", self._PRIMARY_ACTIVE)],
               relief=[("pressed", "sunken")])

    # ---------- Tarjeta con borde (solo GRID, sin mezclar pack) ----------
    def _card(self, parent, title, row, col, colspan=1):
        """
        Devuelve un frame 'content' con un borde persistente y título.
        """
        outer = tk.Frame(parent, bg=self._BG)  # fondo general
        outer.grid(row=row, column=col, columnspan=colspan,
                   sticky="nsew", padx=12, pady=8)
        outer.grid_columnconfigure(0, weight=1)

        # Línea superior (header)
        tk.Frame(outer, bg=self._BORDER, height=2).grid(row=0, column=0, sticky="ew")

        # Título
        tk.Label(outer, text=title, bg=self._BG, fg=self._TEXT,
                 font=("TkDefaultFont", 12, "bold"),
                 anchor="w", padx=10, pady=4).grid(row=1, column=0, sticky="ew")

        # Marco con borde
        border = tk.Frame(outer, bg=self._BORDER)
        border.grid(row=2, column=0, sticky="nsew")
        border.grid_columnconfigure(0, weight=1)
        border.grid_rowconfigure(0, weight=1)

        # Cuerpo
        inner = tk.Frame(border, bg=self._SURFACE)
        inner.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        inner.grid_columnconfigure(0, weight=1)

        # Contenido final (ttk.Frame con estilo oscuro explícito)
        content = ttk.Frame(inner, style="Valv.Inner.TFrame")
        content.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        content.grid_columnconfigure(0, weight=1)
        return content

    def crear_widgets(self):
        # Layout raíz
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación (ancho uniforme)
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="nsw")
        # asegura mismo ancho en todas las vistas
        self.grid_columnconfigure(0, minsize=getattr(BarraNavegacion, "ANCHO", 230))
        barra.grid_propagate(False)

        # Panel derecho (2 columnas) — estilo de contenedor oscuro
        panel = ttk.Frame(self, style="Valv.Container.TFrame")
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 10), pady=10)
        panel.grid_columnconfigure(0, weight=1, uniform="cards")
        panel.grid_columnconfigure(1, weight=1, uniform="cards")

        # ====== Válvula 1 (Entrada) ======
        sec_v1 = self._card(panel, "Válvula 1 (Entrada)", row=0, col=0)
        sec_v1.grid_columnconfigure((0, 1), weight=1)
        self.btn_v1_a = ttk.Button(sec_v1, text="Posición A", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v1", "A"))
        self.btn_v1_b = ttk.Button(sec_v1, text="Posición B", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v1", "B"))
        self.btn_v1_a.grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.btn_v1_b.grid(row=0, column=1, padx=8, pady=6, sticky="e")

        # ====== Válvula 2 (Salida) ======
        sec_v2 = self._card(panel, "Válvula 2 (Salida)", row=0, col=1)
        sec_v2.grid_columnconfigure((0, 1), weight=1)
        self.btn_v2_a = ttk.Button(sec_v2, text="Posición A", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v2", "A"))
        self.btn_v2_b = ttk.Button(sec_v2, text="Posición B", style="AB.TButton",
                                   command=lambda: self._seleccionar_posicion("v2", "B"))
        self.btn_v2_a.grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.btn_v2_b.grid(row=0, column=1, padx=8, pady=6, sticky="e")

        # ====== Conexión equipo 2 ======
        sec_con = self._card(panel, "Conexión equipo 2", row=1, col=0, colspan=2)
        self.btn_con_eq2 = ttk.Button(sec_con, text=self._texto_conexion(),
                                      style="ValvPrimary.TButton", command=self._toggle_conexion)
        self.btn_con_eq2.grid(row=0, column=0, padx=8, pady=6, sticky="w")

        # ====== Válvula motor 1 (Izq ↤ / Der ↦) ======
        sec_vm1 = self._card(panel, "Válvula motor 1", row=2, col=0)
        sec_vm1.grid_columnconfigure((0, 1), weight=1)
        self.btn_vm1_izq = ttk.Button(sec_vm1, text="← Izquierda", style="AB.TButton",
                                      command=lambda: self._seleccionar_motor("vm1", "I"))
        self.btn_vm1_der = ttk.Button(sec_vm1, text="Derecha →", style="AB.TButton",
                                      command=lambda: self._seleccionar_motor("vm1", "D"))
        self.btn_vm1_izq.grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.btn_vm1_der.grid(row=0, column=1, padx=8, pady=6, sticky="e")

        # ====== Válvula motor 2 ======
        sec_vm2 = self._card(panel, "Válvula motor 2", row=2, col=1)
        sec_vm2.grid_columnconfigure((0, 1), weight=1)
        self.btn_vm2_izq = ttk.Button(sec_vm2, text="← Izquierda", style="AB.TButton",
                                      command=lambda: self._seleccionar_motor("vm2", "I"))
        self.btn_vm2_der = ttk.Button(sec_vm2, text="Derecha →", style="AB.TButton",
                                      command=lambda: self._seleccionar_motor("vm2", "D"))
        self.btn_vm2_izq.grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.btn_vm2_der.grid(row=0, column=1, padx=8, pady=6, sticky="e")

        # ====== Solenoide ======
        sec_sol = self._card(panel, "Válvula solenoide (seguridad)", row=3, col=0, colspan=2)
        sec_sol.grid_columnconfigure(1, weight=1)
        self.btn_sol_toggle = ttk.Button(sec_sol, text=self._texto_sol(),
                                         style="ValvPrimary.TButton", command=self._toggle_sol)
        self.btn_sol_toggle.grid(row=0, column=0, columnspan=2, padx=8, pady=(6, 8), sticky="w")

        # Label de presión con mismo fondo de tarjeta
        tk.Label(
            sec_sol,
            text="Presión de seguridad (bar):",
            bg=self._SURFACE, fg=self._TEXT,
            padx=0, pady=0, bd=0, highlightthickness=0
        ).grid(row=1, column=0, padx=8, pady=6, sticky="e")

        self.entry_p_seg = ttk.Entry(sec_sol, width=10, style="Valv.TEntry")
        self.entry_p_seg.grid(row=1, column=1, padx=8, pady=6, sticky="w")
        self.entry_p_seg.insert(0, f"{self.sol_presion:.1f}")
        self.entry_p_seg.bind(
            "<Button-1>",
            lambda e: TecladoNumerico(self, self.entry_p_seg,
                                      on_submit=lambda v: self._aplicar_presion_y_enviar_auto(v))
        )
        self.entry_p_seg.bind(
            "<FocusOut>",
            lambda e: self._aplicar_presion_y_enviar_auto(self.entry_p_seg.get())
        )

        # ====== Bombas ======
        sec_per = self._card(panel, "Bombas peristálticas", row=4, col=0, colspan=2)
        self.btn_per1 = ttk.Button(sec_per, text=self._texto_per1(),
                                   style="Valv.TButton", command=self._toggle_per1)
        self.btn_per2 = ttk.Button(sec_per, text=self._texto_per2(),
                                   style="Valv.TButton", command=self._toggle_per2)
        self.btn_per1.grid(row=0, column=0, padx=8, pady=(6, 4), sticky="w")
        self.btn_per2.grid(row=1, column=0, padx=8, pady=(4, 8), sticky="w")

        # Aplicar estado conexión
        self._aplicar_estado_conexion()

    # ================= Persistencia/Helpers/Handlers =================
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

    def _refrescar_botones(self, cual: str):
        if cual == "v1":
            sel = self.v1_pos.get()
            self.btn_v1_a.configure(style="ABSelected.TButton" if sel == "A" else "AB.TButton",
                                    text=("✓ Posición A" if sel == "A" else "Posición A"))
            self.btn_v1_b.configure(style="ABSelected.TButton" if sel == "B" else "AB.TButton",
                                    text=("✓ Posición B" if sel == "B" else "Posición B"))
        elif cual == "v2":
            sel = self.v2_pos.get()
            self.btn_v2_a.configure(style="ABSelected.TButton" if sel == "A" else "AB.TButton",
                                    text=("✓ Posición A" if sel == "A" else "Posición A"))
            self.btn_v2_b.configure(style="ABSelected.TButton" if sel == "B" else "AB.TButton",
                                    text=("✓ Posición B" if sel == "B" else "Posición B"))

    def _refrescar_botones_vm(self, cual: str):
        if cual == "vm1":
            sel = self.vm1_dir.get()
            self.btn_vm1_izq.configure(style="ABSelected.TButton" if sel == "I" else "AB.TButton",
                                       text=("✓ ← Izquierda" if sel == "I" else "← Izquierda"))
            self.btn_vm1_der.configure(style="ABSelected.TButton" if sel == "D" else "AB.TButton",
                                       text=("✓ Derecha →" if sel == "D" else "Derecha →"))
        elif cual == "vm2":
            sel = self.vm2_dir.get()
            self.btn_vm2_izq.configure(style="ABSelected.TButton" if sel == "I" else "AB.TButton",
                                       text=("✓ ← Izquierda" if sel == "I" else "← Izquierda"))
            self.btn_vm2_der.configure(style="ABSelected.TButton" if sel == "D" else "AB.TButton",
                                       text=("✓ Derecha →" if sel == "D" else "Derecha →"))

    def _texto_sol(self) -> str:
        return "Cerrar válvula" if self.sol_abierta.get() else "Abrir válvula"

    def _texto_per1(self) -> str:
        return "Peristáltica 1: OFF → ON" if not self.per1_on.get() else "Peristáltica 1: ON → OFF"

    def _texto_per2(self) -> str:
        return "Peristáltica 2: OFF → ON" if not self.per2_on.get() else "Peristáltica 2: ON → OFF"

    def _texto_conexion(self) -> str:
        return "Conexión equipo 2: OFF" if not self.conexion_equipo2.get() else "Conexión equipo 2: ON"

    # --- Handlers (misma lógica de mensajes) ---
    def _seleccionar_posicion(self, cual: str, pos: str):
        if pos not in ("A", "B"):
            return
        pos_code = "1" if pos == "A" else "2"
        if cual == "v1":
            self.v1_pos.set(pos)
            self._refrescar_botones("v1")
            mensaje = f"$;3;1;8;{pos_code};!" if self.conexion_equipo2.get() else f"$;3;1;1;{pos_code};!"
            self._guardar_posiciones()
        elif cual == "v2":
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

    def _seleccionar_motor(self, cual: str, dir_code: str):
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
        pos_val = "1" if dir_code == "D" else "2"
        msg = f"$;3;{id_motor};1;{pos_val};!"
        print(f"[TX] {cual.upper()} ->", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _toggle_per1(self):
        nuevo = not self.per1_on.get()
        self.per1_on.set(nuevo)
        self.btn_per1.configure(text=self._texto_per1())
        estado = "1" if nuevo else "2"
        msg = f"$;3;6;1;{estado};!"
        print("[TX] Peristaltica 1:", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

    def _toggle_per2(self):
        nuevo = not self.per2_on.get()
        self.per2_on.set(nuevo)
        self.btn_per2.configure(text=self._texto_per2())
        estado = "1" if nuevo else "2"
        msg = f"$;3;7;1;{estado};!"
        print("[TX] Peristaltica 2:", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
