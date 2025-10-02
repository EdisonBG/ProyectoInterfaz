"""
Ventana de control de 4 MFC (Mass Flow Controllers) – v2 con LabeledEntryNum.
"""

from __future__ import annotations

import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox

from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico
from ui.widgets import TouchButton, TouchEntry, LabeledEntryNum


class VentanaMfc(tk.Frame):
    """Vista de control para cuatro MFC con selección de gas, setpoint y % de mezcla."""

    # Máximos base por gas (mL/min)
    BASE_MAX = {
        "O2": 10000,
        "N2": 10000,
        "H2": 10100,
        "CO2": 7370,
        "CO": 10000,
        "Aire": 10060,
    }

    # Máximos específicos por MFC (mL/min)
    MFC_MAX = {
        1: {"O2": 10000, "N2": 10000, "H2": 10100, "CO2": 7370,  "CO": 10000, "Aire": 10060},
        2: {"O2":  9920, "N2": 10000, "H2": 10100, "CO2": 10000, "CO": 10000, "Aire": 10060},
        3: {"O2":  9920, "N2": 10000, "H2": 10100, "CO2": 7370,  "CO": 10000, "Aire": 10060},
        4: {"O2":  9920, "N2": 10000, "H2": 10000, "CO2": 7370,  "CO": 10000, "Aire": 10060},
    }

    GAS_LIST = ["O2", "N2", "H2", "CO2", "CO", "Aire"]
    DEFAULT_GAS = {1: "O2", 2: "CO2", 3: "N2", 4: "H2"}

    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Estados y referencias por MFC
        self.valores: dict[int, dict[str, str]] = {i: {"flujo": ""} for i in range(1, 5)}
        self.estado_mfc: dict[int, str | None] = {i: None for i in range(1, 5)}
        self.refs: dict[int, dict[str, tk.Widget]] = {i: {} for i in range(1, 5)}

        # BYPASS persistido por VentanaValv
        self._pos_file = os.path.join(os.path.dirname(__file__), "valv_pos.csv")
        self._bypass = self._leer_bypass_desde_csv()  # 1 o 2

        # Bandera para sincronización 1↔3 con BYPASS=2
        self._syncing_gas = False

        self._configurar_estilos_locales()
        self._crear_ui()

        # Exponer referencia en el controlador
        if hasattr(self.controlador, "__setattr__"):
            setattr(self.controlador, "_ventana_mfc", self)

        # Cálculo inicial de porcentajes y sincronización inicial si aplica
        self._recalc_mix_percentages()
        if self._bypass == 2:
            self._sync_gases_if_needed(1)

    # ------------------------------------------------------------------
    # Estilos locales (resaltado Abrir/Cerrar)
    # ------------------------------------------------------------------
    def _configurar_estilos_locales(self) -> None:
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("SelBtn.TButton", padding=(16, 12))
        st.map("SelBtn.TButton", background=[("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")])
        st.configure("SelBtnOn.TButton", padding=(16, 12), background="#bdbdbd")
        st.map("SelBtnOn.TButton", background=[("!disabled", "#bdbdbd"), ("pressed", "#9e9e9e")])

    # ------------------------------------------------------------------
    # Construcción de UI
    # ------------------------------------------------------------------
    def _crear_ui(self) -> None:
        # Raíz: barra izquierda fija + panel contenido
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=140)
        self.grid_columnconfigure(1, weight=1)

        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="nsw")

        cont = ttk.Frame(self)
        cont.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        for c in range(2):
            cont.grid_columnconfigure(c, weight=1, uniform="mfc")
        for r in range(2):
            cont.grid_rowconfigure(r, weight=1)

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
        frame = ttk.LabelFrame(parent, text=titulo)
        frame.grid_columnconfigure(0, weight=0)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=0)

        row = 0

        # % mezcla (arriba derecha)
        mix_lbl = ttk.Label(frame, text="% de mezcla: 0.0 %")
        mix_lbl.grid(row=row, column=2, padx=(4, 6), pady=(6, 0), sticky="ne")
        self.refs[mfc_id]["mix_lbl"] = mix_lbl

        # Gas
        ttk.Label(frame, text="Gas:").grid(row=row, column=0, padx=5, pady=5, sticky="e")
        combo = ttk.Combobox(frame, values=self.GAS_LIST, state="readonly", width=10)
        combo.set(self.DEFAULT_GAS[mfc_id])
        combo.grid(row=row, column=1, padx=5, pady=5, sticky="w")
        combo.bind("<<ComboboxSelected>>", lambda _e, m=mfc_id: self._on_cambio_gas(m))
        self.refs[mfc_id]["combo"] = combo
        row += 1

        # Flujo (LabeledEntryNum + teclado numérico)
        campo_flujo = LabeledEntryNum(frame, "Flujo (mL/min):", width=10)
        campo_flujo.grid(row=row, column=0, columnspan=2, sticky="w")
        campo_flujo.bind_numeric(
            lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
            on_submit=lambda v, m=mfc_id: self._on_submit_flujo(m, campo_flujo.entry, v),
        )
        self.refs[mfc_id]["entry"] = campo_flujo.entry
        row += 1

        # Leyenda min/max
        maxv = self._maximo_mfc_por_gas(mfc_id, combo.get())
        legend = ttk.Label(frame, text=f"min: 0   max: {maxv}")
        legend.grid(row=row, column=0, columnspan=2, padx=5, pady=(0, 6), sticky="w")
        self.refs[mfc_id]["legend"] = legend
        row += 1

        # Botones Abrir / Cerrar
        btn_open = TouchButton(frame, text="Abrir MFC", style="SelBtn.TButton",
                               command=lambda m=mfc_id: self._btn_open(m))
        btn_close = TouchButton(frame, text="Cerrar MFC", style="SelBtn.TButton",
                                command=lambda m=mfc_id: self._btn_close(m))
        btn_open.grid(row=row, column=0, padx=6, pady=6, sticky="w")
        btn_close.grid(row=row, column=1, padx=6, pady=6, sticky="w")
        self.refs[mfc_id]["btn_open"] = btn_open
        self.refs[mfc_id]["btn_close"] = btn_close
        row += 1

        # Botón Enviar flujo
        TouchButton(frame, text="Enviar flujo", command=lambda m=mfc_id: self._enviar_flujo(m))\
            .grid(row=row, column=0, columnspan=2, padx=6, pady=(8, 4))

        return frame

    # ------------------------------------------------------------------
    # BYPASS (leer/recargar)
    # ------------------------------------------------------------------
    def _leer_bypass_desde_csv(self) -> int:
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

    def _reload_bypass_and_refresh(self) -> None:
        prev = self._bypass
        self._bypass = self._leer_bypass_desde_csv()
        if self._bypass == 2 and prev != 2:
            self._sync_gases_if_needed(1)
        self._recalc_mix_percentages()

    # ------------------------------------------------------------------
    # Lógica de máximos
    # ------------------------------------------------------------------
    def _maximo_mfc_por_gas(self, mfc_id: int, gas: str) -> int:
        gas = gas if gas in self.BASE_MAX else "O2"
        if mfc_id in self.MFC_MAX and gas in self.MFC_MAX[mfc_id]:
            return self.MFC_MAX[mfc_id][gas]
        return self.BASE_MAX[gas]

    # ------------------------------------------------------------------
    # Handlers de UI
    # ------------------------------------------------------------------
    def _on_cambio_gas(self, mfc_id: int) -> None:
        gas = self.refs[mfc_id]["combo"].get()
        maxv = self._maximo_mfc_por_gas(mfc_id, gas)
        self.refs[mfc_id]["legend"].configure(text=f"min: 0   max: {maxv}")

        ent: ttk.Entry = self.refs[mfc_id]["entry"]  # type: ignore[assignment]
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

    def _on_submit_flujo(self, mfc_id: int, entry: ttk.Entry, valor) -> None:
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

        self._recalc_mix_percentages()

    def _actualizar_estilos_on_off(self, mfc_id: int) -> None:
        refs = self.refs[mfc_id]
        est = self.estado_mfc[mfc_id]
        refs["btn_open"].configure(style="SelBtnOn.TButton" if est == "open" else "SelBtn.TButton")
        refs["btn_close"].configure(style="SelBtnOn.TButton" if est == "close" else "SelBtn.TButton")

    # ------------------------------------------------------------------
    # Abrir/Cerrar MFC
    # ------------------------------------------------------------------
    def _btn_open(self, mfc_id: int) -> None:
        self.estado_mfc[mfc_id] = "open"
        self._actualizar_estilos_on_off(mfc_id)
        self._enviar_mensaje(f"$;1;{mfc_id};2;1;!")

    def _btn_close(self, mfc_id: int) -> None:
        self.estado_mfc[mfc_id] = "close"
        self._actualizar_estilos_on_off(mfc_id)
        self._enviar_mensaje(f"$;1;{mfc_id};2;2;!")

    # ------------------------------------------------------------------
    # Enviar flujo (SP → PWM)
    # ------------------------------------------------------------------
    def _enviar_flujo(self, mfc_id: int) -> None:
        ent: ttk.Entry = self.refs[mfc_id]["entry"]  # type: ignore[assignment]
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

        # Limpiar estado Abrir/Cerrar
        self.estado_mfc[mfc_id] = None
        self._actualizar_estilos_on_off(mfc_id)

    # ------------------------------------------------------------------
    # % de mezcla
    # ------------------------------------------------------------------
    def _sp_val(self, mfc_id: int) -> float:
        ent: ttk.Entry = self.refs[mfc_id]["entry"]  # type: ignore[assignment]
        try:
            return float((ent.get() or "0").strip())
        except Exception:
            return 0.0

    def _set_mix_percent(self, mfc_id: int, percent: float) -> None:
        self.refs[mfc_id]["mix_lbl"].configure(text=f"% de mezcla: {percent:.1f} %")

    def _recalc_mix_percentages(self) -> None:
        bypass = self._bypass or 1

        sp1 = self._sp_val(1)
        sp2 = self._sp_val(2)
        sp3 = self._sp_val(3)
        sp4 = self._sp_val(4)

        if bypass == 1:
            # Mezcla de 1-2-3; 4 es línea pura
            s = sp1 + sp2 + sp3
            p1 = (100.0 * sp1 / s) if s > 0 else 0.0
            p2 = (100.0 * sp2 / s) if s > 0 else 0.0
            p3 = (100.0 * sp3 / s) if s > 0 else 0.0
            p4 = 100.0 if sp4 > 0 else 0.0
        else:
            # BYPASS 2: pares (1,4) y (2,3)
            s14 = sp1 + sp4
            s23 = sp2 + sp3
            p1 = (100.0 * sp1 / s14) if s14 > 0 else 0.0
            p4 = (100.0 * sp4 / s14) if s14 > 0 else 0.0
            p2 = (100.0 * sp2 / s23) if s23 > 0 else 0.0
            p3 = (100.0 * sp3 / s23) if s23 > 0 else 0.0

        self._set_mix_percent(1, p1)
        self._set_mix_percent(2, p2)
        self._set_mix_percent(3, p3)
        self._set_mix_percent(4, p4)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _flujo_a_pwm(self, flujo: float, max_flujo: float) -> int:
        if max_flujo <= 0:
            return 0
        pwm = int(round((flujo / max_flujo) * 255))
        return max(0, min(255, pwm))

    def _alerta(self, titulo: str, mensaje: str) -> None:
        messagebox.showerror(titulo, mensaje)

    def _enviar_mensaje(self, mensaje: str) -> None:
        print("[TX MFC]", mensaje)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    def _sync_gases_if_needed(self, changed_id: int) -> None:
        """Si BYPASS=2 y cambió gas de MFC1 o MFC3, iguala el otro evitando recursión."""
        if self._bypass != 2 or changed_id not in (1, 3) or self._syncing_gas:
            return
        other = 3 if changed_id == 1 else 1
        gas = self.refs[changed_id]["combo"].get()
        try:
            self._syncing_gas = True
            self.refs[other]["combo"].set(gas)
            self._on_cambio_gas(other)
        finally:
            self._syncing_gas = False
