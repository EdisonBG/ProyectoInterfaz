import tkinter as tk
from tkinter import ttk, messagebox
from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico


class VentanaMfc(tk.Frame):
    """
    Control de 4 MFC con:
      - Combobox de gas por MFC (O2, N2, H2, CO2, CO, Aire)
      - Entry de flujo (capado 0..MAX según gas/MFC), leyenda min/max
      - Botones 'Abrir MFC' / 'Cerrar MFC' (mutuamente excluyentes) -> $;1;ID;2;1/2;!
      - Botón 'Enviar flujo' (excluyente con Abrir/Cerrar) -> $;1;ID;1;PWM;!  (PWM: 0..255)

    Máximos por gas:
      - Base (MFC1):      O2=10000, N2=10000, H2=10100, CO2=7370, CO=10000, Aire=10060
      - MFC2/3/4:         O2=9920 (especial), resto igual a Base
    """

    # Tabla base de máximos (aplicada tal cual a MFC1)
    BASE_MAX = {
        "O2": 10000,
        "N2": 10000,
        "H2": 10100,
        "CO2": 7370,
        "CO": 10000,
        "Aire": 10060,
    }

    # Máximos específicos por MFC (sobrescriben la BASE_MAX donde aplique)
    MFC_MAX = {
        1: {"O2": 10000, "N2": 10000, "H2": 10100, "CO2": 7370, "CO": 10000, "Aire": 10060},
        2: {"O2": 9920,  "N2": 10000, "H2": 10100, "CO2": 10000, "CO": 10000, "Aire": 10060},
        3: {"O2": 9920,  "N2": 10000, "H2": 10100, "CO2": 7370,  "CO": 10000, "Aire": 10060},
        4: {"O2": 9920,  "N2": 10000, "H2": 10000, "CO2": 7370,  "CO": 10000, "Aire": 10060},
    }

    GAS_LIST = ["O2", "N2", "H2", "CO2", "CO", "Aire"]
    DEFAULT_GAS = {1: "O2", 2: "CO2", 3: "N2", 4: "H2"}

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Valores por MFC (flujo actual como string normalizado)
        self.valores = {i: {"flujo": ""} for i in range(1, 5)}

        # Estado de botones Abrir/Cerrar: None / "open" / "close"
        self.estado_mfc = {i: None for i in range(1, 5)}

        # Referencias de widgets por MFC
        self.refs = {i: {} for i in range(1, 5)}

        self._configurar_estilos_compacto()
        self._crear_ui()

    # ------------------------ Estilos (compacto 1024×600) ------------------------
    def _configurar_estilos_compacto(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass

        # Paleta
        self._BG = "#0f172a"
        self._SURFACE = "#111827"
        self._BORDER = "#334155"
        self._TEXT = "#e5e7eb"
        self._MUTED = "#9ca3af"
        self._PRIMARY = "#22c55e"
        self._PRIMARY_ACTIVE = "#16a34a"
        self._TOGGLE_ON = "#2563eb"
        self._TOGGLE_ON_ACTIVE = "#1d4ed8"

        # Fuentes más pequeñas
        self.option_add("*Font", ("TkDefaultFont", 10))
        self.option_add("*TButton.Font", ("TkDefaultFont", 10, "bold"))
        self.option_add("*Entry.Font", ("TkDefaultFont", 10))
        self.option_add("*TCombobox*Listbox*Font", ("TkDefaultFont", 10))
        self.configure(background=self._BG)

        # Estilos base
        st.configure("TFrame", background=self._BG)
        st.configure("TLabel", background=self._SURFACE, foreground=self._TEXT)
        st.configure("Muted.TLabel", background=self._SURFACE, foreground=self._MUTED)

        st.configure("Card.TLabelframe", background=self._SURFACE,
                     foreground=self._TEXT, bordercolor=self._BORDER, relief="flat")
        st.configure("Card.TLabelframe.Label", background=self._SURFACE,
                     foreground=self._TEXT, font=("TkDefaultFont", 11, "bold"))

        st.configure("TButton", padding=(8, 6), relief="raised", borderwidth=2,
                     background=self._SURFACE, foreground=self._TEXT)
        st.map("TButton", background=[("active", self._BORDER)],
               relief=[("pressed", "sunken")])

        st.configure("Primary.TButton", padding=(8, 6), relief="raised", borderwidth=2,
                     background=self._PRIMARY, foreground="#052e16")
        st.map("Primary.TButton", background=[("active", self._PRIMARY_ACTIVE)],
               relief=[("pressed", "sunken")])

        st.configure("SelBtn.TButton", padding=(8, 6), relief="raised", borderwidth=2,
                     background=self._SURFACE, foreground=self._TEXT)
        st.map("SelBtn.TButton", background=[("active", self._BORDER)],
               relief=[("pressed", "sunken")])

        st.configure("SelBtnOn.TButton", padding=(8, 6), relief="raised", borderwidth=2,
                     background=self._TOGGLE_ON, foreground="white")
        st.map("SelBtnOn.TButton", background=[("active", self._TOGGLE_ON_ACTIVE)],
               relief=[("pressed", "sunken")])

        st.configure("TEntry", fieldbackground=self._BG, foreground=self._TEXT,
                     bordercolor=self._BORDER, lightcolor=self._TOGGLE_ON,
                     darkcolor=self._BORDER, padding=4)

        st.configure("TCombobox", fieldbackground=self._BG, background=self._SURFACE,
                     foreground=self._TEXT, selectbackground=self._TOGGLE_ON,
                     selectforeground="white", arrowcolor=self._TEXT)
        st.map("TCombobox",
               fieldbackground=[("readonly", self._BG), ("!disabled", self._BG)],
               foreground=[("readonly", self._TEXT), ("!disabled", self._TEXT)],
               selectbackground=[("readonly", self._TOGGLE_ON)],
               selectforeground=[("readonly", "white")])

        st.configure("TSeparator", background=self._BORDER)

    # ------------------------ UI ------------------------
    def _crear_ui(self):
        # Layout raíz: barra + panel
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación compacta
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="nsw")
        self.grid_columnconfigure(0, minsize=getattr(BarraNavegacion, "ANCHO", 170))

        # Contenedor principal (compacto)
        cont = ttk.Frame(self, padding=(10, 10, 10, 10))
        cont.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        cont.grid_columnconfigure(0, weight=1, uniform="mfc")
        cont.grid_columnconfigure(1, weight=1, uniform="mfc")
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_rowconfigure(1, weight=1)

        secciones = [
            (1, "MFC 1 (O₂)"),
            (2, "MFC 2 (CO₂)"),
            (3, "MFC 3 (N₂)"),
            (4, "MFC 4 (H₂)"),
        ]
        for idx, (mfc_id, titulo) in enumerate(secciones, start=1):
            fila = (idx - 1) // 2
            col = (idx - 1) % 2
            frame = self._crear_seccion_mfc(cont, mfc_id, titulo)
            frame.grid(row=fila, column=col, padx=8, pady=8, sticky="nsew")

    def _crear_seccion_mfc(self, parent, mfc_id: int, titulo: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text=titulo, style="Card.TLabelframe", padding=(10, 8))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        row = 0

        # Gas
        ttk.Label(frame, text="Gas:").grid(row=row, column=0, padx=6, pady=6, sticky="e")
        combo = ttk.Combobox(frame, values=self.GAS_LIST, state="readonly", width=10)
        combo.set(self.DEFAULT_GAS[mfc_id])
        combo.grid(row=row, column=1, padx=6, pady=6, sticky="ew")
        combo.bind("<<ComboboxSelected>>", lambda _e, m=mfc_id: self._on_cambio_gas(m))
        self.refs[mfc_id]["combo"] = combo
        row += 1

        # Flujo
        ttk.Label(frame, text="Flujo (mL/min):").grid(row=row, column=0, padx=6, pady=6, sticky="e")
        entry = ttk.Entry(frame, width=12)
        entry.grid(row=row, column=1, padx=6, pady=6, sticky="ew")
        entry.bind(
            "<Button-1>",
            lambda e, ent=entry, m=mfc_id: TecladoNumerico(
                self, ent, on_submit=lambda v, mm=m, en=ent: self._on_submit_flujo(mm, en, v)
            ),
        )
        self.refs[mfc_id]["entry"] = entry
        row += 1

        # Leyenda
        maxv = self._maximo_mfc_por_gas(mfc_id, combo.get())
        legend = ttk.Label(frame, text=f"min: 0   max: {maxv}", style="Muted.TLabel")
        legend.grid(row=row, column=0, columnspan=2, padx=6, pady=(0, 8), sticky="w")
        self.refs[mfc_id]["legend"] = legend
        row += 1

        # Abrir/Cerrar
        btn_open = ttk.Button(frame, text="Abrir MFC", style="SelBtn.TButton",
                              command=lambda m=mfc_id: self._btn_open(m))
        btn_close = ttk.Button(frame, text="Cerrar MFC", style="SelBtn.TButton",
                               command=lambda m=mfc_id: self._btn_close(m))
        btn_open.grid(row=row, column=0, padx=6, pady=6, sticky="ew")
        btn_close.grid(row=row, column=1, padx=6, pady=6, sticky="ew")
        self.refs[mfc_id]["btn_open"] = btn_open
        self.refs[mfc_id]["btn_close"] = btn_close
        row += 1

        # Enviar flujo
        ttk.Button(frame, text="Enviar flujo", style="Primary.TButton",
                   command=lambda m=mfc_id: self._enviar_flujo(m))\
            .grid(row=row, column=0, columnspan=2, padx=6, pady=(8, 6), sticky="ew")

        return frame

    # ------------------------ Lógica de máximos ------------------------
    def _maximo_mfc_por_gas(self, mfc_id: int, gas: str) -> int:
        gas = gas if gas in self.BASE_MAX else "O2"
        if mfc_id in self.MFC_MAX and gas in self.MFC_MAX[mfc_id]:
            return self.MFC_MAX[mfc_id][gas]
        return self.BASE_MAX[gas]

    # ------------------------ Handlers de UI ------------------------
    def _on_cambio_gas(self, mfc_id: int):
        gas = self.refs[mfc_id]["combo"].get()
        maxv = self._maximo_mfc_por_gas(mfc_id, gas)
        self.refs[mfc_id]["legend"].configure(text=f"min: 0   max: {maxv}")

        ent = self.refs[mfc_id]["entry"]
        txt = (ent.get() or "").strip()
        if txt:
            try:
                f = float(txt)
            except Exception:
                f = 0.0
            f = max(0.0, min(float(maxv), f))
            ent.delete(0, tk.END)
            ent.insert(0, str(int(f)) if f.is_integer() else str(f))
            self.valores[mfc_id]["flujo"] = ent.get().strip()

    def _on_submit_flujo(self, mfc_id: int, entry: ttk.Entry, valor):
        try:
            f = float(valor)
        except Exception:
            f = 0.0
        gas = self.refs[mfc_id]["combo"].get()
        maxv = self._maximo_mfc_por_gas(mfc_id, gas)
        f = max(0.0, min(float(maxv), f))

        entry.delete(0, tk.END)
        entry.insert(0, str(int(f)) if f.is_integer() else str(f))
        self.valores[mfc_id]["flujo"] = entry.get().strip()

    def _actualizar_estilos_on_off(self, mfc_id: int):
        refs = self.refs[mfc_id]
        est = self.estado_mfc[mfc_id]
        refs["btn_open"].configure(style="SelBtnOn.TButton" if est == "open" else "SelBtn.TButton")
        refs["btn_close"].configure(style="SelBtnOn.TButton" if est == "close" else "SelBtn.TButton")

    # ------------------------ Abrir/Cerrar ------------------------
    def _btn_open(self, mfc_id: int):
        self.estado_mfc[mfc_id] = "open"
        self._actualizar_estilos_on_off(mfc_id)
        self._enviar_mensaje(f"$;1;{mfc_id};2;1;!")

    def _btn_close(self, mfc_id: int):
        self.estado_mfc[mfc_id] = "close"
        self._actualizar_estilos_on_off(mfc_id)
        self._enviar_mensaje(f"$;1;{mfc_id};2;2;!")

    # ------------------------ Enviar flujo (SP -> PWM) ------------------------
    def _enviar_flujo(self, mfc_id: int):
        ent = self.refs[mfc_id]["entry"]
        txt = (ent.get() or "").strip()
        if not txt:
            self._alerta("Dato faltante", f"Ingrese el flujo para MFC {mfc_id}.")
            return

        try:
            f = float(txt)
        except Exception:
            f = 0.0

        gas = self.refs[mfc_id]["combo"].get()
        maxv = self._maximo_mfc_por_gas(mfc_id, gas)
        f = max(0.0, min(float(maxv), f))

        pwm = self._flujo_a_pwm(f, maxv)
        msg = f"$;1;{mfc_id};1;{pwm};!"
        self._enviar_mensaje(msg)

        # Exclusión con abrir/cerrar
        self.estado_mfc[mfc_id] = None
        self._actualizar_estilos_on_off(mfc_id)

    # ------------------------ Utilidades ------------------------
    def _flujo_a_pwm(self, flujo: float, max_flujo: float) -> int:
        if max_flujo <= 0:
            return 0
        pwm = int(round((flujo / max_flujo) * 255))
        return max(0, min(255, pwm))

    def _alerta(self, titulo: str, mensaje: str):
        messagebox.showerror(titulo, mensaje)

    def _enviar_mensaje(self, mensaje: str):
        print("[TX MFC]", mensaje)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)
