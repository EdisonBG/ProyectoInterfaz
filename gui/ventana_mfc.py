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

    Notas:
      - El PWM se calcula con round para mejor precisión efectiva.
      - Al enviar flujo se deseleccionan Abrir/Cerrar.
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
        1: {  # MFC1 (O2) -> ya era correcto: usa la base tal cual
            "O2": 10000, "N2": 10000, "H2": 10100, "CO2": 7370, "CO": 10000, "Aire": 10060,
        },
        2: {  # MFC2 (por defecto CO2) -> CO2 = 10000 (especial), O2 = 9920 (especial)
            "O2": 9920, "N2": 10000, "H2": 10100, "CO2": 10000, "CO": 10000, "Aire": 10060,
        },
        3: {  # MFC3 (por defecto N2) -> igual a base excepto O2 = 9920 (especial)
            "O2": 9920, "N2": 10000, "H2": 10100, "CO2": 7370, "CO": 10000, "Aire": 10060,
        },
        4: {  # MFC4 (por defecto H2) -> H2 = 10000 (especial), O2 = 9920 (especial)
            "O2": 9920, "N2": 10000, "H2": 10000, "CO2": 7370, "CO": 10000, "Aire": 10060,
        },
    }

    # Gases disponibles y orden para el combobox
    GAS_LIST = ["O2", "N2", "H2", "CO2", "CO", "Aire"]

    # Gas por defecto por MFC
    DEFAULT_GAS = {
        1: "O2",
        2: "CO2",
        3: "N2",
        4: "H2",
    }

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Valores por MFC (flujo actual como string normalizado)
        self.valores = {i: {"flujo": ""} for i in range(1, 5)}

        # Estado de botones Abrir/Cerrar: None / "open" / "close"
        self.estado_mfc = {i: None for i in range(1, 5)}

        # Referencias de widgets por MFC
        # refs[mfc_id] = {"combo": Combobox, "entry": Entry, "legend": Label, "btn_open": Button, "btn_close": Button}
        self.refs = {i: {} for i in range(1, 5)}

        self._configurar_estilos()
        self._crear_ui()

    # ------------------------ Estilos ------------------------
    def _configurar_estilos(self):
        st = ttk.Style(self)
        try:
            # [UI] Tema base “clam” (estable en Raspberry)
            st.theme_use("clam")
        except Exception:
            pass

        # [UI] ---- Tokens de color y tipografía (alto contraste) ----
        BG = "#0f172a"
        SURFACE = "#111827"
        CARD = "#111827"
        TEXT = "#e5e7eb"
        MUTED = "#9ca3af"
        BORDER = "#1f2937"
        PRIMARY = "#22c55e"
        PRIMARY_ACTIVE = "#16a34a"
        TOGGLE_ON = "#2563eb"
        TOGGLE_ON_ACTIVE = "#1d4ed8"

        # [UI] Tipografía base más grande para táctil
        self.option_add("*Font", ("TkDefaultFont", 12))            # texto general
        self.option_add("*TButton.Font", ("TkDefaultFont", 12, "bold"))
        self.option_add("*TCombobox*Listbox*Font", ("TkDefaultFont", 12))
        self.option_add("*Entry.Font", ("TkDefaultFont", 12))

        # [UI] Fondo raíz
        self.configure(background=BG)

        # [UI] Labels y frames
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=SURFACE, foreground=TEXT)
        st.configure("Muted.TLabel", background=SURFACE, foreground=MUTED)

        # [UI] Cards (LabelFrame) con mayor padding y título legible
        st.configure(
            "Card.TLabelframe",
            background=CARD,
            foreground=TEXT,
            bordercolor=BORDER,
            relief="flat"
        )
        st.configure(
            "Card.TLabelframe.Label",
            background=CARD,
            foreground=TEXT,
            font=("TkDefaultFont", 13, "bold")  # título de card más grande
        )

        # [UI] ====== BOTONES CON BORDE Y RELIEVE (sobresalidos) ======
        # Nota: ttk no tiene “3D” real, pero usamos relief + border + colores para simular.
        st.configure(
            "TButton",
            padding=(14, 12),             # altura táctil
            relief="raised",              # relieve elevado
            borderwidth=2,                # borde visible
            focusthickness=2,
            focuscolor=TOGGLE_ON,
            background=SURFACE,
            foreground=TEXT
        )
        st.map(
            "TButton",
            background=[("active", BORDER)],
            relief=[("pressed", "sunken")],  # hundido al presionar
        )

        # [UI] Botón primario (Enviar flujo) VERDE, elevado
        st.configure(
            "Primary.TButton",
            padding=(16, 14),
            relief="raised",
            borderwidth=2,
            focusthickness=2,
            focuscolor="#064e3b",
            background=PRIMARY,
            foreground="#052e16"
        )
        st.map(
            "Primary.TButton",
            background=[("active", PRIMARY_ACTIVE)],
            relief=[("pressed", "sunken")]
        )

        # [UI] Botones toggle Abrir/Cerrar (apagado/encendido)
        st.configure(
            "SelBtn.TButton",
            padding=(14, 12),
            relief="raised",
            borderwidth=2,
            background=SURFACE,
            foreground=TEXT
        )
        st.map(
            "SelBtn.TButton",
            background=[("active", BORDER)],
            relief=[("pressed", "sunken")]
        )

        st.configure(
            "SelBtnOn.TButton",
            padding=(14, 12),
            relief="raised",
            borderwidth=2,
            background=TOGGLE_ON,
            foreground="white"
        )
        st.map(
            "SelBtnOn.TButton",
            background=[("active", TOGGLE_ON_ACTIVE)],
            relief=[("pressed", "sunken")]
        )

        # [UI] Entradas y Combobox con campo oscuro y borde claro
        st.configure(
            "TEntry",
            fieldbackground=BG,
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=TOGGLE_ON,
            darkcolor=BORDER,
            padding=10
        )
        # [UI] Combobox con texto más legible (fondo oscuro, letra clara)
        st.configure(
            "TCombobox",
            fieldbackground=BG,      # fondo del campo
            background=SURFACE,      # fondo del widget completo
            foreground=TEXT,         # color del texto dentro del campo
            selectbackground=TOGGLE_ON,   # fondo al seleccionar
            selectforeground="white",     # letra al seleccionar
            arrowcolor=TEXT               # color de la flecha
        )
        st.map("TCombobox",
               fieldbackground=[("readonly", BG), ("!disabled", BG)],
               foreground=[("readonly", TEXT), ("!disabled", TEXT)],
               selectbackground=[("readonly", TOGGLE_ON)],
               selectforeground=[("readonly", "white")])

        

        # [UI] Separador
        st.configure("TSeparator", background=BORDER)

    # ------------------------ UI ------------------------
    def _crear_ui(self):
        # Layout raíz: barra + panel
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # [UI] Barra de navegación (sin tocar lógica)
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="nsw")
        self.grid_columnconfigure(0, minsize=BarraNavegacion.ANCHO)  # asegura mismo ancho


        # [UI] Contenedor principal con más padding para respirar
        cont = ttk.Frame(self, padding=(16, 16, 16, 16))
        cont.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
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
            # [UI] Gutter amplio para pantallas táctiles
            frame.grid(row=fila, column=col, padx=10, pady=10, sticky="nsew")

    def _crear_seccion_mfc(self, parent, mfc_id: int, titulo: str) -> ttk.LabelFrame:
        """Sección por MFC: gas (combo), flujo (entry + leyenda), Abrir/Cerrar, Enviar flujo."""
        # [UI] Card con buen padding
        frame = ttk.LabelFrame(parent, text=titulo, style="Card.TLabelframe", padding=(14, 12))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)  # [UI] ambas columnas expanden

        row = 0

        # Combobox gas
        ttk.Label(frame, text="Gas:").grid(row=row, column=0, padx=8, pady=8, sticky="e")
        combo = ttk.Combobox(frame, values=self.GAS_LIST, state="readonly", width=12, style="TCombobox")
        combo.set(self.DEFAULT_GAS[mfc_id])
        combo.grid(row=row, column=1, padx=8, pady=8, sticky="ew")  # [UI] que llene columna
        combo.bind("<<ComboboxSelected>>", lambda _e, m=mfc_id: self._on_cambio_gas(m))
        self.refs[mfc_id]["combo"] = combo
        row += 1

        # Entry de flujo
        ttk.Label(frame, text="Flujo (mL/min):").grid(row=row, column=0, padx=8, pady=8, sticky="e")
        entry = ttk.Entry(frame, width=14)  # [UI] más ancho
        entry.grid(row=row, column=1, padx=8, pady=8, sticky="ew")  # [UI] llenar columna
        entry.bind(
            "<Button-1>",
            lambda e, ent=entry, m=mfc_id: TecladoNumerico(
                self, ent, on_submit=lambda v, mm=m, en=ent: self._on_submit_flujo(mm, en, v)
            ),
        )
        self.refs[mfc_id]["entry"] = entry
        row += 1

        # Leyenda min/max
        maxv = self._maximo_mfc_por_gas(mfc_id, combo.get())
        legend = ttk.Label(frame, text=f"min: 0   max: {maxv}", style="Muted.TLabel")
        legend.grid(row=row, column=0, columnspan=2, padx=8, pady=(0, 10), sticky="w")
        self.refs[mfc_id]["legend"] = legend
        row += 1

        # Botones Abrir / Cerrar (mutuamente excluyentes)
        # [UI] ahora se ven elevados, con borde, y ocupan todo el ancho de su columna
        btn_open = ttk.Button(frame, text="Abrir MFC", style="SelBtn.TButton",
                              command=lambda m=mfc_id: self._btn_open(m))
        btn_close = ttk.Button(frame, text="Cerrar MFC", style="SelBtn.TButton",
                               command=lambda m=mfc_id: self._btn_close(m))
        btn_open.grid(row=row, column=0, padx=8, pady=8, sticky="ew")
        btn_close.grid(row=row, column=1, padx=8, pady=8, sticky="ew")
        self.refs[mfc_id]["btn_open"] = btn_open
        self.refs[mfc_id]["btn_close"] = btn_close
        row += 1

        # Botón Enviar flujo
        # [UI] botón primario grande, a todo el ancho del card
        ttk.Button(frame, text="Enviar flujo", style="Primary.TButton",
                   command=lambda m=mfc_id: self._enviar_flujo(m))\
            .grid(row=row, column=0, columnspan=2, padx=8, pady=(12, 6), sticky="ew")

        return frame

    # ------------------------ Lógica de máximos ------------------------
    def _maximo_mfc_por_gas(self, mfc_id: int, gas: str) -> int:
        """
        Devuelve el máximo permitido para (MFC, gas) usando la tabla específica MFC_MAX.
        Si el gas no está reconocido, cae a 'O2'. Si faltara la clave, cae a BASE_MAX como respaldo.
        """
        gas = gas if gas in self.BASE_MAX else "O2"
        # Intentar primero tabla específica por MFC
        if mfc_id in self.MFC_MAX and gas in self.MFC_MAX[mfc_id]:
            return self.MFC_MAX[mfc_id][gas]
        # Respaldo: base
        return self.BASE_MAX[gas]

    # ------------------------ Handlers de UI ------------------------
    def _on_cambio_gas(self, mfc_id: int):
        """Actualiza leyenda y capa el entry al cambiar gas."""
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
        """Normaliza y capa el flujo al confirmar con el teclado numérico, y guarda."""
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
        """Resalta el botón seleccionado en Abrir/Cerrar."""
        refs = self.refs[mfc_id]
        est = self.estado_mfc[mfc_id]
        refs["btn_open"].configure(style="SelBtnOn.TButton" if est == "open" else "SelBtn.TButton")
        refs["btn_close"].configure(style="SelBtnOn.TButton" if est == "close" else "SelBtn.TButton")

    # ------------------------ Abrir/Cerrar (mutuamente excluyentes) ------------------------
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
        """
        Envía SP como PWM:
          $;1;ID;1;PWM;!
        - PWM = round(flujo / MAX(mfc,gas) * 255) con clamp 0..255
        - Desmarca Abrir/Cerrar (los tres controles son excluyentes)
        """
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

        # Desmarcar Abrir/Cerrar (exclusión)
        self.estado_mfc[mfc_id] = None
        self._actualizar_estilos_on_off(mfc_id)

    # ------------------------ Utilidades ------------------------
    def _flujo_a_pwm(self, flujo: float, max_flujo: float) -> int:
        """Mapeo proporcional flujo->[0..255], redondeado y limitado."""
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
