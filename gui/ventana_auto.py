# gui/ventana_auto.py
import os
import csv
import time
import tkinter as tk
from tkinter import ttk, messagebox

from .barra_navegacion import BarraNavegacion

# Teclado numerico (si existe)
try:
    from .teclado_numerico import TecladoNumerico
    _HAS_TECLADO = True
except Exception:
    _HAS_TECLADO = False


# ========================= Utiles de MFC / PWM =========================
def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def flujo_a_pwm(flujo: int, max_flujo: int) -> int:
    """
    Convierte flujo [0..max_flujo] a PWM [0..255] de forma lineal.
    Saturado y redondeado.
    """
    mf = max(1, int(max_flujo))  # evitar div/0
    f = clamp(int(flujo), 0, mf)
    return int(round(f * 255.0 / mf))


# Gases soportados
GASES = ["O2", "N2", "H2", "CO2", "CO", "Aire"]

# Tablas de máximos por MFC (según acordado)
MFC_MAX = {
    1: {"O2": 10000, "N2": 10000, "H2": 10100, "CO2": 7370,  "CO": 10000, "Aire": 10060},  # defecto O2
    2: {"O2": 9920,  "N2": 10000, "H2": 10100, "CO2": 10000, "CO": 10000, "Aire": 10060},  # defecto CO2
    3: {"O2": 9920,  "N2": 10000, "H2": 10100, "CO2": 7370,  "CO": 10000, "Aire": 10060},  # defecto N2
    4: {"O2": 9920,  "N2": 10000, "H2": 10000, "CO2": 7370,  "CO": 10000, "Aire": 10060},  # defecto H2
}

MFC_DEF_GAS = {1: "O2", 2: "CO2", 3: "N2", 4: "H2"}


# ========================= Panel de una Etapa =========================
class _EtapaPanel(ttk.LabelFrame):
    """
    Panel de configuración de una etapa:
      - Tiempo de proceso (min)
      - Válvulas: Pos inicial (A/B), Tiempo en A/B (min), Presión (1 decimal máx 25.0)
        Peristálticas 1/2: ON/OFF + tiempo (min, habilitado si ON)
      - MFC 1..4: combo gas + flujo + leyenda min/max (según gas/MFC)
      - Temperatura: Horno1 (SP, Mem M0..M4), Horno2 (SP, Mem M0..M4)
    """
    def __init__(self, master, idx: int):
        super().__init__(master, text=f"Etapa {idx}")
        self.idx = idx

        # ---- Grilla base
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        row = 0

        # ===== Tiempo de proceso =====
        frm_t = ttk.Frame(self)
        frm_t.grid(row=row, column=0, columnspan=2, sticky="ew", padx=6, pady=(6, 4))
        ttk.Label(frm_t, text="Tiempo de proceso (min):").grid(row=0, column=0, sticky="e")
        self.ent_tiempo = ttk.Entry(frm_t, width=8)
        self.ent_tiempo.grid(row=0, column=1, sticky="w", padx=4)
        if _HAS_TECLADO:
            self.ent_tiempo.bind("<Button-1>", lambda e: TecladoNumerico(self, self.ent_tiempo))

        row += 1

        # ===== Válvulas =====
        frm_v = ttk.LabelFrame(self, text="Válvulas")
        frm_v.grid(row=row, column=0, sticky="ew", padx=6, pady=6)
        frm_v.grid_columnconfigure(1, weight=1)

        ttk.Label(frm_v, text="Posición inicial:").grid(row=0, column=0, sticky="e")
        self.cmb_pos_ini = ttk.Combobox(frm_v, values=["A", "B"], state="readonly", width=5)
        self.cmb_pos_ini.set("A")
        self.cmb_pos_ini.grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(frm_v, text="Tiempo en A (min):").grid(row=1, column=0, sticky="e")
        self.ent_tA = ttk.Entry(frm_v, width=8)
        self.ent_tA.grid(row=1, column=1, sticky="w", padx=4)

        ttk.Label(frm_v, text="Tiempo en B (min):").grid(row=2, column=0, sticky="e")
        self.ent_tB = ttk.Entry(frm_v, width=8)
        self.ent_tB.grid(row=2, column=1, sticky="w", padx=4)

        if _HAS_TECLADO:
            self.ent_tA.bind("<Button-1>", lambda e: TecladoNumerico(self, self.ent_tA))
            self.ent_tB.bind("<Button-1>", lambda e: TecladoNumerico(self, self.ent_tB))

        ttk.Label(frm_v, text="Presión seguridad (bar, máx 25.0):").grid(row=3, column=0, sticky="e")
        self.ent_pres = ttk.Entry(frm_v, width=8)
        self.ent_pres.grid(row=3, column=1, sticky="w", padx=4)
        ttk.Label(frm_v, text="* 1 decimal, tope 25.0").grid(row=4, column=0, columnspan=2, sticky="w", padx=2)
        if _HAS_TECLADO:
            self.ent_pres.bind("<Button-1>", lambda e: TecladoNumerico(self, self.ent_pres))

        # Peristálticas
        ttk.Separator(frm_v, orient="horizontal").grid(row=5, column=0, columnspan=2, sticky="ew", pady=6)

        self.peri1_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm_v, text="Peristáltica 1 ON", variable=self.peri1_var,
                        command=self._toggle_p1).grid(row=6, column=0, sticky="w", columnspan=2)
        ttk.Label(frm_v, text="Tiempo P1 (min):").grid(row=7, column=0, sticky="e")
        self.ent_p1_t = ttk.Entry(frm_v, width=8, state="disabled")
        self.ent_p1_t.grid(row=7, column=1, sticky="w", padx=4)
        if _HAS_TECLADO:
            self.ent_p1_t.bind("<Button-1>", lambda e: TecladoNumerico(self, self.ent_p1_t))

        self.peri2_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm_v, text="Peristáltica 2 ON", variable=self.peri2_var,
                        command=self._toggle_p2).grid(row=8, column=0, sticky="w", columnspan=2)
        ttk.Label(frm_v, text="Tiempo P2 (min):").grid(row=9, column=0, sticky="e")
        self.ent_p2_t = ttk.Entry(frm_v, width=8, state="disabled")
        self.ent_p2_t.grid(row=9, column=1, sticky="w", padx=4)
        if _HAS_TECLADO:
            self.ent_p2_t.bind("<Button-1>", lambda e: TecladoNumerico(self, self.ent_p2_t))

        # ===== MFC =====
        frm_m = ttk.LabelFrame(self, text="MFC (flujo mL/min)")
        frm_m.grid(row=row, column=1, sticky="ew", padx=6, pady=6)
        frm_m.grid_columnconfigure(1, weight=1)

        self.mfc_vars = {}
        for mfc_id, base_row in zip((1, 2, 3, 4), (0, 3, 6, 9)):
            ttk.Label(frm_m, text=f"MFC{mfc_id} Gas:").grid(row=base_row, column=0, sticky="e")
            gas_var = tk.StringVar(value=MFC_DEF_GAS[mfc_id])
            cmb = ttk.Combobox(frm_m, values=GASES, textvariable=gas_var, state="readonly", width=8)
            cmb.grid(row=base_row, column=1, sticky="w")

            ttk.Label(frm_m, text=f"MFC{mfc_id} Flujo:").grid(row=base_row+1, column=0, sticky="e")
            ent = ttk.Entry(frm_m, width=10)
            ent.grid(row=base_row+1, column=1, sticky="w", padx=2)
            if _HAS_TECLADO:
                ent.bind("<Button-1>", lambda e, entry=ent: TecladoNumerico(self, entry))

            ley = ttk.Label(frm_m, text=self._leyenda_mfc(mfc_id, gas_var.get()))
            ley.grid(row=base_row+2, column=0, columnspan=2, sticky="w", padx=2)

            def on_gas_change(_ev=None, _m=mfc_id, _var=gas_var, _ley=ley):
                _ley.configure(text=self._leyenda_mfc(_m, _var.get()))

            cmb.bind("<<ComboboxSelected>>", on_gas_change)
            self.mfc_vars[mfc_id] = {"gas": gas_var, "entry": ent, "ley": ley}

        row += 1

        # ===== Temperatura =====
        frm_t2 = ttk.LabelFrame(self, text="Temperatura")
        frm_t2.grid(row=row, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 8))
        for c in range(4):
            frm_t2.grid_columnconfigure(c, weight=1)

        # Horno 1
        ttk.Label(frm_t2, text="Horno 1 SP:").grid(row=0, column=0, sticky="e")
        self.ent_sp1 = ttk.Entry(frm_t2, width=8)
        self.ent_sp1.grid(row=0, column=1, sticky="w", padx=3)
        ttk.Label(frm_t2, text="Mem:").grid(row=0, column=2, sticky="e")
        self.cmb_mem1 = ttk.Combobox(frm_t2, values=[f"M{i}" for i in range(5)], state="readonly", width=5)
        self.cmb_mem1.set("M0")
        self.cmb_mem1.grid(row=0, column=3, sticky="w")
        if _HAS_TECLADO:
            self.ent_sp1.bind("<Button-1>", lambda e: TecladoNumerico(self, self.ent_sp1))

        # Horno 2
        ttk.Label(frm_t2, text="Horno 2 SP:").grid(row=1, column=0, sticky="e")
        self.ent_sp2 = ttk.Entry(frm_t2, width=8)
        self.ent_sp2.grid(row=1, column=1, sticky="w", padx=3)
        ttk.Label(frm_t2, text="Mem:").grid(row=1, column=2, sticky="e")
        self.cmb_mem2 = ttk.Combobox(frm_t2, values=[f"M{i}" for i in range(5)], state="readonly", width=5)
        self.cmb_mem2.set("M0")
        self.cmb_mem2.grid(row=1, column=3, sticky="w")
        if _HAS_TECLADO:
            self.ent_sp2.bind("<Button-1>", lambda e: TecladoNumerico(self, self.ent_sp2))

    def _toggle_p1(self):
        self.ent_p1_t.configure(state="normal" if self.peri1_var.get() else "disabled")

    def _toggle_p2(self):
        self.ent_p2_t.configure(state="normal" if self.peri2_var.get() else "disabled")

    def _leyenda_mfc(self, mfc_id: int, gas: str) -> str:
        maxv = MFC_MAX[mfc_id].get(gas, 10000)
        return f"min: 0   max: {maxv}"

    # ----- Lectura y validación de la etapa -----
    def _int_pos(self, entry, *, minv=0, allow_zero=True, name=""):
        txt = (entry.get() or "").strip()
        try:
            v = int(float(txt))
        except Exception:
            raise ValueError(f"{name}: valor entero inválido")
        if (not allow_zero and v <= 0) or (v < minv):
            raise ValueError(f"{name}: debe ser >= {minv + (0 if allow_zero else 1)}")
        return v

    def _float_1dec_cap(self, entry, *, cap=25.0, name=""):
        txt = (entry.get() or "").strip()
        try:
            v = float(txt)
        except Exception:
            raise ValueError(f"{name}: valor numérico inválido")
        if v < 0:
            raise ValueError(f"{name}: no puede ser negativo")
        if v > cap:
            v = cap
        entry.delete(0, tk.END)
        entry.insert(0, f"{v:.1f}")
        return round(v, 1)

    def _read_sp_trunc600(self, entry, name="SP"):
        txt = (entry.get() or "").strip()
        try:
            v = int(float(txt))
        except Exception:
            raise ValueError(f"{name}: entero requerido")
        if v < 0:
            raise ValueError(f"{name}: no puede ser negativo")
        if v > 600:
            v = 600
            entry.delete(0, tk.END)
            entry.insert(0, str(v))
        return v

    def _read_mem_idx(self, combo):
        try:
            return int(combo.get().strip().upper().replace("M", ""))
        except Exception:
            return 0

    def _leer_mfc_pwm(self, mfc_id: int):
        gas = self.mfc_vars[mfc_id]["gas"].get()
        maxv = MFC_MAX[mfc_id].get(gas, 10000)
        txt = (self.mfc_vars[mfc_id]["entry"].get() or "").strip()
        if not txt:
            flujo = 0
        else:
            try:
                flujo = int(float(txt))
            except Exception:
                raise ValueError(f"MFC{mfc_id} Flujo inválido")
        flujo = clamp(flujo, 0, maxv)
        # reflejar clamp si cambió
        self.mfc_vars[mfc_id]["entry"].delete(0, tk.END)
        self.mfc_vars[mfc_id]["entry"].insert(0, str(flujo))
        return flujo_a_pwm(flujo, maxv)

    def leer_y_validar(self) -> dict:
        data = {}
        data["tmin"] = self._int_pos(self.ent_tiempo, minv=1, allow_zero=False, name="Tiempo de proceso")

        pos = self.cmb_pos_ini.get().strip().upper()
        data["pos_ini"] = 1 if pos == "A" else 2
        data["tA"] = self._int_pos(self.ent_tA, minv=1, allow_zero=False, name="Tiempo en A")
        data["tB"] = self._int_pos(self.ent_tB, minv=1, allow_zero=False, name="Tiempo en B")
        pres = self._float_1dec_cap(self.ent_pres, cap=25.0, name="Presión seguridad")
        data["pres_x10"] = int(round(pres * 10))

        data["p1_on"] = 1 if self.peri1_var.get() else 0
        data["p1_t"] = self._int_pos(self.ent_p1_t, minv=0, allow_zero=True, name="Tiempo P1") if data["p1_on"] else 0
        data["p2_on"] = 1 if self.peri2_var.get() else 0
        data["p2_t"] = self._int_pos(self.ent_p2_t, minv=0, allow_zero=True, name="Tiempo P2") if data["p2_on"] else 0

        data["mfc1_pwm"] = self._leer_mfc_pwm(1)
        data["mfc2_pwm"] = self._leer_mfc_pwm(2)
        data["mfc3_pwm"] = self._leer_mfc_pwm(3)
        data["mfc4_pwm"] = self._leer_mfc_pwm(4)

        data["sp1"]  = self._read_sp_trunc600(self.ent_sp1, "Horno1 SP")
        data["mem1"] = self._read_mem_idx(self.cmb_mem1)
        data["sp2"]  = self._read_sp_trunc600(self.ent_sp2, "Horno2 SP")
        data["mem2"] = self._read_mem_idx(self.cmb_mem2)

        return data

    # ----- CSV helpers -----
    def to_row(self):
        gas1 = self.mfc_vars[1]["gas"].get()
        gas2 = self.mfc_vars[2]["gas"].get()
        gas3 = self.mfc_vars[3]["gas"].get()
        gas4 = self.mfc_vars[4]["gas"].get()
        return [
            (self.ent_tiempo.get() or "").strip(),
            self.cmb_pos_ini.get(), (self.ent_tA.get() or "").strip(), (self.ent_tB.get() or "").strip(),
            (self.ent_pres.get() or "").strip(),
            "1" if self.peri1_var.get() else "0", (self.ent_p1_t.get() or "").strip(),
            "1" if self.peri2_var.get() else "0", (self.ent_p2_t.get() or "").strip(),
            gas1, (self.mfc_vars[1]["entry"].get() or "").strip(),
            gas2, (self.mfc_vars[2]["entry"].get() or "").strip(),
            gas3, (self.mfc_vars[3]["entry"].get() or "").strip(),
            gas4, (self.mfc_vars[4]["entry"].get() or "").strip(),
            (self.ent_sp1.get() or "").strip(), self.cmb_mem1.get(),
            (self.ent_sp2.get() or "").strip(), self.cmb_mem2.get(),
        ]

    def from_row(self, row):
        if len(row) < 22:
            return
        it = iter(row)
        self.ent_tiempo.delete(0, tk.END); self.ent_tiempo.insert(0, next(it, ""))
        self.cmb_pos_ini.set(next(it, "A"))
        self.ent_tA.delete(0, tk.END); self.ent_tA.insert(0, next(it, ""))
        self.ent_tB.delete(0, tk.END); self.ent_tB.insert(0, next(it, ""))
        self.ent_pres.delete(0, tk.END); self.ent_pres.insert(0, next(it, ""))

        self.peri1_var.set(next(it, "0") == "1"); self._toggle_p1()
        self.ent_p1_t.delete(0, tk.END); self.ent_p1_t.insert(0, next(it, ""))

        self.peri2_var.set(next(it, "0") == "1"); self._toggle_p2()
        self.ent_p2_t.delete(0, tk.END); self.ent_p2_t.insert(0, next(it, ""))

        for mfc_id in (1, 2, 3, 4):
            gas = next(it, MFC_DEF_GAS[mfc_id])
            self.mfc_vars[mfc_id]["gas"].set(gas)
            self.mfc_vars[mfc_id]["ley"].configure(text=self._leyenda_mfc(mfc_id, gas))
            flow = next(it, "")
            self.mfc_vars[mfc_id]["entry"].delete(0, tk.END)
            self.mfc_vars[mfc_id]["entry"].insert(0, flow)

        self.ent_sp1.delete(0, tk.END); self.ent_sp1.insert(0, next(it, ""))
        self.cmb_mem1.set(next(it, "M0"))
        self.ent_sp2.delete(0, tk.END); self.ent_sp2.insert(0, next(it, ""))
        self.cmb_mem2.set(next(it, "M0"))


# ========================= Runner preciso (no bloqueante) =========================
class _StageRunner:
    """
    Coordina el envío de etapas y los timers internos (válvulas A/B, peristálticas) con precisión:
    - Usa time.monotonic() para calcular residuales al pausar y reanudar exactamente.
    - Exposición de estado para el monitor.
    """
    def __init__(self, scheduler_widget, enviar_func, get_stage_data_func, total_stages: int, on_state=lambda *_: None):
        self.sched = scheduler_widget
        self.enviar = enviar_func
        self.get_data = get_stage_data_func
        self.n = total_stages
        self.on_state = on_state   # callback (stage, pos, remain_stage_s, remain_seg_s, p1_on, p2_on)

        # Estado de ejecución
        self.current = 1
        self.running = False
        self.paused = False

        # IDs de after y temporizadores absolutos (monotonic)
        self._after_ids = []

        # Tiempos absolutos (segundos monotonic hasta evento)
        self._t_end_stage = None
        self._t_end_segment = None
        self._t_p1_off = None
        self._t_p2_off = None

        # Parametros actuales
        self._pos_actual = None  # 1=A, 2=B
        self._dur_A = 0
        self._dur_B = 0
        self._p1_on = 0
        self._p2_on = 0

        # Monitor tick
        self._tick_id = None

    # ---- control público ----
    def start(self):
        if self.running:
            return
        self.running = True
        self.paused = False
        self.current = 1
        self._start_stage(self.current)

    def pause(self):
        if not self.running or self.paused:
            return
        self.paused = True
        self._cancel_all()

        now = time.monotonic()
        # Guardar residuales (en segundos) para reprogramar luego
        self._res_stage = max(0.0, (self._t_end_stage - now)) if self._t_end_stage else 0.0
        self._res_seg   = max(0.0, (self._t_end_segment - now)) if self._t_end_segment else 0.0
        self._res_p1    = max(0.0, (self._t_p1_off - now)) if (self._t_p1_off and self._p1_on) else None
        self._res_p2    = max(0.0, (self._t_p2_off - now)) if (self._t_p2_off and self._p2_on) else None

        self._t_end_stage = None
        self._t_end_segment = None
        self._t_p1_off = None
        self._t_p2_off = None

    def resume(self):
        if not self.running or not self.paused:
            return
        self.paused = False

        now = time.monotonic()
        # Reprogramar fin de etapa y segmento con residuales exactos
        if getattr(self, "_res_stage", 0.0) > 0:
            self._t_end_stage = now + self._res_stage
            self._after_ids.append(self.sched.after(int(self._res_stage * 1000), self._end_stage))
        if getattr(self, "_res_seg", 0.0) > 0:
            self._t_end_segment = now + self._res_seg
            self._after_ids.append(self.sched.after(int(self._res_seg * 1000), self._toggle_valvula))

        # Peristálticas: reprogramar sus OFF si estaban pendientes
        if self._p1_on and self._res_p1 is not None and self._res_p1 > 0:
            self._t_p1_off = now + self._res_p1
            self._after_ids.append(self.sched.after(int(self._res_p1 * 1000), self._peristaltica_off, 6))
        if self._p2_on and self._res_p2 is not None and self._res_p2 > 0:
            self._t_p2_off = now + self._res_p2
            self._after_ids.append(self.sched.after(int(self._res_p2 * 1000), self._peristaltica_off, 7))

        # Relanzar el tick del monitor
        self._schedule_tick()

    def stop(self):
        self.running = False
        self.paused = False
        self._cancel_all()
        # Reset estado para monitor
        self.on_state(0, 0, 0, 0, 0, 0)

    # ---- helpers after ----
    def _cancel_all(self):
        for aid in self._after_ids:
            try:
                self.sched.after_cancel(aid)
            except Exception:
                pass
        self._after_ids.clear()

        if self._tick_id is not None:
            try:
                self.sched.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None

    # ---- etapa ----
    def _start_stage(self, idx: int):
        if not self.running:
            return

        data = self.get_data(idx)  # validado por la ventana

        # Mensaje de cabecera de etapa
        msg = f"$;4;{idx};{data['tmin']};{data['pos_ini']};{data['tA']};{data['tB']};{data['pres_x10']};" \
              f"{data['p1_on']};{data['p1_t']};{data['p2_on']};{data['p2_t']};" \
              f"{data['mfc1_pwm']};{data['mfc2_pwm']};{data['mfc3_pwm']};{data['mfc4_pwm']};" \
              f"{data['sp1']};{data['mem1']};{data['sp2']};{data['mem2']}!"
        self.enviar(msg)

        # Inicializar tiempos absolutos
        now = time.monotonic()
        self._t_end_stage = now + data['tmin'] * 60.0

        # Posiciones y segmentos
        self._pos_actual = data['pos_ini']  # 1=A, 2=B
        self._dur_A = data['tA']
        self._dur_B = data['tB']
        seg_min = self._dur_A if self._pos_actual == 1 else self._dur_B
        seg_s = min(seg_min * 60.0, data['tmin'] * 60.0)  # no exceder etapa
        self._t_end_segment = now + seg_s

        # Enviar posición inicial (modo auto = 0)
        self.enviar(f"$;3;1;0;{self._pos_actual};!")

        # Peristálticas (modo 0 auto)
        self._p1_on = data['p1_on']
        self._p2_on = data['p2_on']
        if self._p1_on:
            self.enviar("$;3;6;0;1;!")  # ON
            t_off = min(data['p1_t'], data['tmin'])
            self._t_p1_off = now + t_off * 60.0
            self._after_ids.append(self.sched.after(int(t_off * 60_000), self._peristaltica_off, 6))
        else:
            self._t_p1_off = None

        if self._p2_on:
            self.enviar("$;3;7;0;1;!")  # ON
            t_off = min(data['p2_t'], data['tmin'])
            self._t_p2_off = now + t_off * 60.0
            self._after_ids.append(self.sched.after(int(t_off * 60_000), self._peristaltica_off, 7))
        else:
            self._t_p2_off = None

        # Programar fin de segmento y fin de etapa
        self._after_ids.append(self.sched.after(int(seg_s * 1000), self._toggle_valvula))
        self._after_ids.append(self.sched.after(int(data['tmin'] * 60_000), self._end_stage))

        # Lanzar monitor tick
        self._schedule_tick()
        self._push_state()

    def _peristaltica_off(self, which_id: int):
        # OFF (modo auto 0)
        self.enviar(f"$;3;{which_id};0;2;!")
        if which_id == 6:
            self._p1_on = 0
            self._t_p1_off = None
        else:
            self._p2_on = 0
            self._t_p2_off = None
        self._push_state()

    def _toggle_valvula(self):
        if not self.running or self.paused:
            return

        now = time.monotonic()
        # Si la etapa ya terminó, no alternar (lo hará _end_stage)
        if self._t_end_stage and now >= self._t_end_stage:
            return

        # Cambiar posición
        self._pos_actual = 2 if self._pos_actual == 1 else 1
        self.enviar(f"$;3;1;0;{self._pos_actual};!")

        # Calcular siguiente segmento respetando fin de etapa
        seg_min = self._dur_A if self._pos_actual == 1 else self._dur_B
        seg_s = seg_min * 60.0
        # recortar si excede el fin de etapa
        if self._t_end_stage:
            max_seg = max(0.0, self._t_end_stage - now)
            seg_s = min(seg_s, max_seg)

        self._t_end_segment = now + seg_s
        self._after_ids.append(self.sched.after(int(seg_s * 1000), self._toggle_valvula))
        self._push_state()

    def _end_stage(self):
        if not self.running:
            return

        # Apagar peristálticas que sigan ON
        if self._p1_on:
            self.enviar("$;3;6;0;2;!")
            self._p1_on = 0
        if self._p2_on:
            self.enviar("$;3;7;0;2;!")
            self._p2_on = 0

        self.current += 1
        if self.current > self.n:
            # Termina la secuencia
            self.stop()
            return

        # Siguiente etapa
        self._start_stage(self.current)

    # ---- Monitor ----
    def _schedule_tick(self):
        # Actualiza el monitor cada 1s
        if self._tick_id is not None:
            try:
                self.sched.after_cancel(self._tick_id)
            except Exception:
                pass
        self._tick_id = self.sched.after(1000, self._tick)

    def _tick(self):
        if not self.running or self.paused:
            self._tick_id = None
            return
        self._push_state()
        self._schedule_tick()

    def _push_state(self):
        now = time.monotonic()
        remain_stage = max(0, int(round((self._t_end_stage - now))) if self._t_end_stage else 0)
        remain_seg   = max(0, int(round((self._t_end_segment - now))) if self._t_end_segment else 0)
        self.on_state(self.current, self._pos_actual or 0, remain_stage, remain_seg, self._p1_on, self._p2_on)


# ========================= Ventana Auto =========================
class VentanaAuto(tk.Frame):
    """
    Ventana de configuración y ejecución automática (6 etapas fijas).
    Barra de navegación a la IZQUIERDA y panel principal a la DERECHA.
    """
    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Programador: prioriza el de controlador si tiene after/after_cancel
        self._scheduler = controlador if hasattr(controlador, "after") else self

        self._build_ui()

        # Runner preciso (todo igual que antes)
        self.runner = _StageRunner(
            scheduler_widget=self._scheduler,
            enviar_func=self._enviar_a_arduino,
            get_stage_data_func=self._get_stage_data_validated,
            total_stages=6,
            on_state=self._monitor_update
        )

    def _build_ui(self):
        # ====== grilla raíz: 2 columnas (barra izquierda fija | panel derecho expansible) ======
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)   # barra
        self.grid_columnconfigure(1, weight=1)   # panel derecho

        # ----- Barra de navegación a la IZQUIERDA -----
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=230)                   # ancho fijo como en otras ventanas
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)                  # evita que se encoja

        # ----- Panel derecho con acciones + monitor + zona scrollable -----
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        right.grid_rowconfigure(1, weight=1)         # la zona scroll ocupa el resto
        right.grid_columnconfigure(0, weight=1)

        # === fila 0: Acciones + Monitor (horizontal) ===
        top = ttk.Frame(right)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=1)

        # Acciones a la izquierda
        acciones = ttk.Frame(top)
        acciones.grid(row=0, column=0, sticky="w")
        ttk.Button(acciones, text="Validar", command=self._validar_todo).pack(side="left", padx=(0, 6))
        self.btn_start  = ttk.Button(acciones, text="Iniciar", command=self._iniciar)
        self.btn_pause  = ttk.Button(acciones, text="Pausar", command=self._pausar, state="disabled")
        self.btn_resume = ttk.Button(acciones, text="Reanudar", command=self._reanudar, state="disabled")
        self.btn_stop   = ttk.Button(acciones, text="Detener", command=self._detener, state="disabled")
        self.btn_start.pack(side="left", padx=(0, 6))
        self.btn_pause.pack(side="left", padx=(0, 6))
        self.btn_resume.pack(side="left", padx=(0, 6))
        self.btn_stop.pack(side="left", padx=(0, 6))
        ttk.Button(acciones, text="Guardar preset", command=self._guardar_csv).pack(side="left", padx=(16, 6))
        ttk.Button(acciones, text="Cargar preset", command=self._cargar_csv).pack(side="left")

        # Monitor a la derecha
        monitor = ttk.LabelFrame(top, text="Monitor")
        monitor.grid(row=0, column=1, sticky="e")
        for c in range(4):
            monitor.grid_columnconfigure(c, weight=1)
        ttk.Label(monitor, text="Etapa:").grid(row=0, column=0, sticky="e")
        self.lbl_m_stage = ttk.Label(monitor, text="-")
        self.lbl_m_stage.grid(row=0, column=1, sticky="w")
        ttk.Label(monitor, text="Posición:").grid(row=0, column=2, sticky="e")
        self.lbl_m_pos = ttk.Label(monitor, text="-")
        self.lbl_m_pos.grid(row=0, column=3, sticky="w")
        ttk.Label(monitor, text="Restante etapa:").grid(row=1, column=0, sticky="e")
        self.lbl_m_rest_stage = ttk.Label(monitor, text="-")
        self.lbl_m_rest_stage.grid(row=1, column=1, sticky="w")
        ttk.Label(monitor, text="Restante segmento:").grid(row=1, column=2, sticky="e")
        self.lbl_m_rest_seg = ttk.Label(monitor, text="-")
        self.lbl_m_rest_seg.grid(row=1, column=3, sticky="w")
        ttk.Label(monitor, text="P1:").grid(row=2, column=0, sticky="e")
        self.lbl_m_p1 = ttk.Label(monitor, text="-")
        self.lbl_m_p1.grid(row=2, column=1, sticky="w")
        ttk.Label(monitor, text="P2:").grid(row=2, column=2, sticky="e")
        self.lbl_m_p2 = ttk.Label(monitor, text="-")
        self.lbl_m_p2.grid(row=2, column=3, sticky="w")

        # === fila 1: Área scrollable (etapas) ===
        scroll_area = ttk.Frame(right)
        scroll_area.grid(row=1, column=0, sticky="nsew")
        scroll_area.grid_rowconfigure(0, weight=1)
        scroll_area.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(scroll_area, highlightthickness=0)
        vscroll = ttk.Scrollbar(scroll_area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vscroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")

        # Frame interior dentro del canvas
        self.inner = ttk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # 6 etapas (igual que antes)
        self.etapas = []
        for i in range(1, 7):
            p = _EtapaPanel(self.inner, i)
            p.grid(row=i-1, column=0, sticky="ew", padx=8, pady=6)
            self.etapas.append(p)

        # Rueda del mouse para scroll
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)   # Windows
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)     # Linux
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)     # Linux


    # ---- Scroll helpers ----
    def _on_inner_configure(self, _ev=None):
        # Actualiza el scrollregion al tamaño del frame interior
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, ev):
        # Ajusta el ancho del inner al ancho visible del canvas
        self.canvas.itemconfigure(self.inner_id, width=ev.width)

    def _on_mousewheel(self, event):
        # Normaliza para distintos sistemas
        if event.num == 4:       # Linux scroll up
            delta = -120
        elif event.num == 5:     # Linux scroll down
            delta = 120
        else:
            delta = -1 * int(event.delta)

        self.canvas.yview_scroll(int(delta / 120), "units")

    # ---- Envío centralizado ----
    def _enviar_a_arduino(self, msg: str):
        print("[TX AUTO]", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
        elif self.arduino:
            try:
                self.arduino.write((msg + "\n").encode("utf-8"))
            except Exception as e:
                print("Error al enviar al Arduino:", e)

    # ---- Validación global ----
    def _validar_todo(self):
        errores = []
        self._clear_errors()

        for i, etapa in enumerate(self.etapas, start=1):
            try:
                etapa.leer_y_validar()
            except Exception as e:
                errores.append(f"Etapa {i}: {e}")
                self._mark_error(etapa)

        if errores:
            messagebox.showerror("Errores de validación", "\n".join(errores))
        else:
            messagebox.showinfo("Validación", "Todos los datos son válidos.")

    def _clear_errors(self):
        for p in self.etapas:
            p.configure(style="TLabelframe")

    def _mark_error(self, etapa_panel: _EtapaPanel):
        try:
            style = ttk.Style(self)
            style.configure("Err.TLabelframe", foreground="red")
            etapa_panel.configure(style="Err.TLabelframe")
        except Exception:
            pass

    # ---- Acciones ----
    def _get_stage_data_validated(self, idx: int) -> dict:
        return self.etapas[idx-1].leer_y_validar()

    def _iniciar(self):
        # Validar antes de iniciar
        self._clear_errors()
        errores = []
        for i, etapa in enumerate(self.etapas, start=1):
            try:
                etapa.leer_y_validar()
            except Exception as e:
                errores.append(f"Etapa {i}: {e}")
                self._mark_error(etapa)
        if errores:
            messagebox.showerror("Errores de validación", "\n".join(errores))
            return

        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal")
        self.btn_resume.configure(state="disabled")
        self.btn_stop.configure(state="normal")

        self.runner.start()

    def _pausar(self):
        self.runner.pause()
        self.btn_pause.configure(state="disabled")
        self.btn_resume.configure(state="normal")

    def _reanudar(self):
        self.runner.resume()
        self.btn_pause.configure(state="normal")
        self.btn_resume.configure(state="disabled")

    def _detener(self):
        self.runner.stop()
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled")
        self.btn_resume.configure(state="disabled")
        self.btn_stop.configure(state="disabled")
        # Poner monitor en neutro
        self._monitor_update(0, 0, 0, 0, 0, 0)

    # ---- CSV ----
    def _preset_path(self):
        base = os.path.dirname(__file__)
        return os.path.join(base, "auto_preset.csv")

    def _guardar_csv(self):
        path = self._preset_path()
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "tmin", "pos_ini", "tA", "tB", "pres",
                    "p1_on", "p1_t", "p2_on", "p2_t",
                    "mfc1_gas", "mfc1_f", "mfc2_gas", "mfc2_f",
                    "mfc3_gas", "mfc3_f", "mfc4_gas", "mfc4_f",
                    "sp1", "mem1", "sp2", "mem2"
                ])
                for p in self.etapas:
                    w.writerow(p.to_row())
            messagebox.showinfo("Preset", f"Preset guardado en {path}")
        except Exception as e:
            messagebox.showerror("Preset", f"No se pudo guardar:\n{e}")

    def _cargar_csv(self):
        path = self._preset_path()
        if not os.path.exists(path):
            messagebox.showerror("Preset", f"No existe el archivo:\n{path}")
            return
        try:
            with open(path, newline="", encoding="utf-8") as f:
                r = csv.reader(f)
                header = next(r, None)
                for i, row in enumerate(r, start=1):
                    if i > len(self.etapas):
                        break
                    self.etapas[i-1].from_row(row)
            messagebox.showinfo("Preset", "Preset cargado.")
        except Exception as e:
            messagebox.showerror("Preset", f"No se pudo cargar:\n{e}")

    # ---- Monitor (callback desde runner) ----
    def _monitor_update(self, stage, pos, remain_stage_s, remain_seg_s, p1_on, p2_on):
        self.lbl_m_stage.configure(text=str(stage) if stage > 0 else "-")
        self.lbl_m_pos.configure(text=("A" if pos == 1 else ("B" if pos == 2 else "-")))
        self.lbl_m_rest_stage.configure(text=self._fmt_s(remain_stage_s))
        self.lbl_m_rest_seg.configure(text=self._fmt_s(remain_seg_s))
        self.lbl_m_p1.configure(text=("ON" if p1_on else "OFF"))
        self.lbl_m_p2.configure(text=("ON" if p2_on else "OFF"))

    @staticmethod
    def _fmt_s(seconds: int) -> str:
        if not seconds or seconds <= 0:
            return "00:00"
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"
