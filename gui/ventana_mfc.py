# gui/ventana_mfc.py
import os
import csv
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
      - Etiqueta “% de mezcla” por MFC (esquina superior derecha)

    Reglas de % mezcla (se basa en el BYPASS persistido por VentanaValv en valv_pos.csv):
      BYPASS 1:
        * Mezcla: MFC 1, 2 y 3 → % = SPi / (SP1+SP2+SP3)
        * MFC 4: 100% si su SP > 0, si SP=0 → 0%
      BYPASS 2:
        * Mezcla A: MFC 1 y 4 → % relativo al par (SP1+SP4)
        * Mezcla B: MFC 2 y 3 → % relativo al par (SP2+SP3)
        * Si la suma del par es 0 → ambos 0%

    Nota: Se lee BYP del archivo en la creación de la ventana. Si cambias el bypass
    en la otra ventana mientras esta está abierta y quieres forzar recálculo,
    puedes llamar a _reload_bypass_and_refresh() desde tu controlador al volver a esta vista.
    """

    # Tabla base de máximos
    BASE_MAX = {
        "O2": 10000,
        "N2": 10000,
        "H2": 10100,
        "CO2": 7370,
        "CO": 10000,
        "Aire": 10060,
    }

    # Máximos específicos por MFC
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

        # Flujo actual como string normalizado
        self.valores = {i: {"flujo": ""} for i in range(1, 5)}
        # Estado botones abrir/cerrar
        self.estado_mfc = {i: None for i in range(1, 5)}
        # Refs de widgets por MFC
        self.refs = {i: {} for i in range(1, 5)}

        # Archivo de bypass (lo escribe VentanaValv)
        self._pos_file = os.path.join(os.path.dirname(__file__), "valv_pos.csv")
        self._bypass = self._leer_bypass_desde_csv()  # 1 o 2

        # 🔧 IMPORTANTE: inicializar bandera ANTES de crear la UI
        self._syncing_gas = False  # evita recursión cuando sincronizamos 1<->3

        self._configurar_estilos()
        self._crear_ui()

        # Exponer referencia en el controlador
        if hasattr(self.controlador, "__setattr__"):
            setattr(self.controlador, "_ventana_mfc", self)

    # ------------------------ Estilos ------------------------
    def _configurar_estilos(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("SelBtn.TButton", padding=6)
        st.map("SelBtn.TButton",
               background=[("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")])
        st.configure("SelBtnOn.TButton", padding=6, background="#007acc", foreground="white")
        st.map("SelBtnOn.TButton",
               background=[("!disabled", "#007acc"), ("pressed", "#0062a3")],
               foreground=[("!disabled", "white")])

    # ------------------------ UI ------------------------
    def _crear_ui(self):
        # Layout raíz: barra + panel
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra de navegación sin márgenes para aprovechar espacio
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=95)
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        cont = ttk.Frame(self)
        cont.grid(row=0, column=1, sticky="nsew")
        cont.grid_columnconfigure(0, weight=1, uniform="mfc")
        cont.grid_columnconfigure(1, weight=1, uniform="mfc")

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

        # Recalcular % inicial
        self._recalc_mix_percentages()

        # Si BYPASS=2 al abrir, igualar gas de MFC3 al de MFC1 (o viceversa)
        if self._bypass == 2:
            self._sync_gases_if_needed(1)  # toma el gas de MFC1 como referencia

    def _crear_seccion_mfc(self, parent, mfc_id: int, titulo: str) -> ttk.LabelFrame:
        """Sección por MFC: gas (combo), flujo (entry + leyenda), Abrir/Cerrar, Enviar flujo, % mezcla."""
        frame = ttk.LabelFrame(parent, text=titulo)
        # 3 columnas: etiqueta/controles, valor, %mezcla a la derecha
        frame.grid_columnconfigure(0, weight=0)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=0)

        row = 0

        # Etiqueta % mezcla (arriba derecha)
        mix_lbl = ttk.Label(frame, text="% de mezcla: 0.0 %")
        mix_lbl.grid(row=row, column=2, padx=(4, 6), pady=(6, 0), sticky="ne")
        self.refs[mfc_id]["mix_lbl"] = mix_lbl

        # Combobox gas
        ttk.Label(frame, text="Gas:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
        combo = ttk.Combobox(frame, values=self.GAS_LIST, state="readonly", width=10)
        combo.set(self.DEFAULT_GAS[mfc_id])
        combo.grid(row=row, column=1, padx=5, pady=5, sticky="w")
        combo.bind("<<ComboboxSelected>>", lambda _e, m=mfc_id: self._on_cambio_gas(m))
        self.refs[mfc_id]["combo"] = combo
        row += 1

        # Entry de flujo
        ttk.Label(frame, text="Flujo (mL/min):").grid(row=row, column=0, padx=5, pady=5, sticky="e")
        entry = ttk.Entry(frame, width=10)
        entry.grid(row=row, column=1, padx=5, pady=5, sticky="w")
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
        legend = ttk.Label(frame, text=f"min: 0   max: {maxv}")
        legend.grid(row=row, column=0, columnspan=2, padx=5, pady=(0, 6), sticky="w")
        self.refs[mfc_id]["legend"] = legend
        row += 1

        # Botones Abrir / Cerrar
        btn_open = ttk.Button(frame, text="Abrir MFC", style="SelBtn.TButton",
                              command=lambda m=mfc_id: self._btn_open(m))
        btn_close = ttk.Button(frame, text="Cerrar MFC", style="SelBtn.TButton",
                               command=lambda m=mfc_id: self._btn_close(m))
        btn_open.grid(row=row, column=0, padx=6, pady=6, sticky="w")
        btn_close.grid(row=row, column=1, padx=6, pady=6, sticky="w")
        self.refs[mfc_id]["btn_open"] = btn_open
        self.refs[mfc_id]["btn_close"] = btn_close
        row += 1

        # Botón Enviar flujo
        ttk.Button(frame, text="Enviar flujo", command=lambda m=mfc_id: self._enviar_flujo(m))\
            .grid(row=row, column=0, columnspan=2, padx=6, pady=(8, 4))

        return frame

    # ------------------------ Bypass (leer/recargar) ------------------------
    def _leer_bypass_desde_csv(self) -> int:
        """Lee la clave BYP de valv_pos.csv. Devuelve 1 o 2 (default 1 si no existe)."""
        try:
            if os.path.exists(self._pos_file):
                with open(self._pos_file, newline="", encoding="utf-8") as f:
                    for nombre, pos in csv.reader(f):
                        if (nombre or "").strip().upper() == "BYP":
                            v = (pos or "").strip()
                            return 2 if v == "2" else 1
        except Exception:
            pass
        return 1

    def _reload_bypass_and_refresh(self):
        """Llamable externamente si cambia el bypass en la otra ventana y vuelve a esta."""
        prev = self._bypass
        self._bypass = self._leer_bypass_desde_csv()
        # Si acabamos de entrar a BYPASS=2, igualar gases 1↔3
        if self._bypass == 2 and prev != 2:
            self._sync_gases_if_needed(1)  # usa MFC1 como referencia
        self._recalc_mix_percentages()

    # ------------------------ Lógica de máximos ------------------------
    def _maximo_mfc_por_gas(self, mfc_id: int, gas: str) -> int:
        gas = gas if gas in self.BASE_MAX else "O2"
        if mfc_id in self.MFC_MAX and gas in self.MFC_MAX[mfc_id]:
            return self.MFC_MAX[mfc_id][gas]
        return self.BASE_MAX[gas]

    # ------------------------ Handlers de UI ------------------------
    def _on_cambio_gas(self, mfc_id: int):
        """Actualiza leyenda (cap del entry si corresponde). No afecta % mezcla."""
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

        # Si BYPASS=2 y es MFC1 o MFC3, igualar el otro
        self._sync_gases_if_needed(mfc_id)

    def _on_submit_flujo(self, mfc_id: int, entry: ttk.Entry, valor):
        """Normaliza/capa el flujo y recalcula % mezcla."""
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

        # Recalcular % mezcla por cambio de SP
        self._recalc_mix_percentages()

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

        # Desmarcar Abrir/Cerrar
        self.estado_mfc[mfc_id] = None
        self._actualizar_estilos_on_off(mfc_id)

    # ------------------------ % Mezcla ------------------------
    def _sp_val(self, mfc_id: int) -> float:
        """Lee el SP actual del entry (float, 0 si vacío)."""
        ent = self.refs[mfc_id]["entry"]
        try:
            return float((ent.get() or "0").strip())
        except Exception:
            return 0.0

    def _set_mix_percent(self, mfc_id: int, percent: float):
        lbl = self.refs[mfc_id]["mix_lbl"]
        lbl.configure(text=f"% de mezcla: {percent:.1f} %")

    def _recalc_mix_percentages(self):
        """Recalcula y pinta los % de mezcla en función del BYPASS y los SP."""
        bypass = self._bypass or 1

        sp1 = self._sp_val(1)
        sp2 = self._sp_val(2)
        sp3 = self._sp_val(3)
        sp4 = self._sp_val(4)

        if bypass == 1:
            # Mezcla de 1-2-3
            s = sp1 + sp2 + sp3
            if s > 0:
                p1 = 100.0 * sp1 / s
                p2 = 100.0 * sp2 / s
                p3 = 100.0 * sp3 / s
            else:
                p1 = p2 = p3 = 0.0
            # MFC4 puro: 100% si hay caudal, si no 0%
            p4 = 100.0 if sp4 > 0 else 0.0

            self._set_mix_percent(1, p1)
            self._set_mix_percent(2, p2)
            self._set_mix_percent(3, p3)
            self._set_mix_percent(4, p4)

        else:
            # BYPASS 2: pares (1,4) y (2,3)
            s14 = sp1 + sp4
            if s14 > 0:
                p1 = 100.0 * sp1 / s14
                p4 = 100.0 * sp4 / s14
            else:
                p1 = p4 = 0.0

            s23 = sp2 + sp3
            if s23 > 0:
                p2 = 100.0 * sp2 / s23
                p3 = 100.0 * sp3 / s23
            else:
                p2 = p3 = 0.0

            self._set_mix_percent(1, p1)
            self._set_mix_percent(2, p2)
            self._set_mix_percent(3, p3)
            self._set_mix_percent(4, p4)

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

    def _sync_gases_if_needed(self, changed_id: int):
        """
        Si BYPASS=2 y cambió el gas de MFC1 o MFC3, iguala el otro.
        Usa una bandera para evitar loops de eventos.
        """
        if self._bypass != 2:
            return
        if changed_id not in (1, 3):
            return
        if self._syncing_gas:
            return

        other = 3 if changed_id == 1 else 1
        gas = self.refs[changed_id]["combo"].get()

        # Sincronizar el combobox del otro MFC
        try:
            self._syncing_gas = True
            self.refs[other]["combo"].set(gas)
            # Actualizar leyenda y capar entry del otro MFC según su nuevo gas
            self._on_cambio_gas(other)
        finally:
            self._syncing_gas = False

    def reset_flujos_a_cero(self):
        """
        Pone en '0' los entries de flujo de los 4 MFC SIN enviar ningún mensaje.
        """
        try:
            for mid in (1, 2, 3, 4):
                ent = self.refs[mid]["entry"] if "entry" in self.refs[mid] else self.refs[mid]["ent"]
                ent.delete(0, tk.END)
                ent.insert(0, "0")
        except Exception as e:
            print(f"[MFC] No se pudieron poner en 0 los flujos: {e}")

    
        if hasattr(self, "_recalc_mix_percentages"):
            try:
                self._recalc_mix_percentages()
            except Exception:
                pass

    def reset_flujos_a_cero(self):
        """
        Pone los 4 entries de flujo en '0' sin enviar nada al Arduino.
        """
        try:
            for i in range(1, 5):
                ent = self.refs[i].get("entry")
                if ent is not None:
                    ent.delete(0, tk.END)
                    ent.insert(0, "0")
        except Exception as e:
            print(f"[MFC] No se pudieron resetear los flujos: {e}")