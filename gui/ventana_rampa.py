import tkinter as tk
from tkinter import ttk, messagebox
from .teclado_numerico import TecladoNumerico


class VentanaRampa(tk.Toplevel):
    """Configuración de rampas (hasta 8 pasos de SP y tiempo) para un Omega.

    Notas:
    - Limita SP a 600 y paso límite entre 0 y 7.
    - Envío/solicitud de datos por protocolo $;2;...;! (integrado con App/Arduino).
    """

    def __init__(self, master, id_omega, arduino, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.arduino = arduino
        self.id_omega = id_omega
        self.title(f"Rampa - Omega {id_omega}")
        self.geometry("400x560")
        self.resizable(False, False)

        # Referencia al controlador (si el padre es un panel con atributo controlador)
        self.controlador = getattr(master, "controlador", None)
        if self.controlador is not None:
            setattr(self.controlador, f"_rampa_win_{self.id_omega}", self)

        # Modal/transiente
        self.transient(master.winfo_toplevel())
        self.wait_visibility(); self.lift(); self.focus_force(); self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        ttk.Label(self, text=f"Configuración de Rampa - Omega {id_omega}",
                  font=("Calibri", 14, "bold")).pack(pady=10)

        cont = ttk.Frame(self); cont.pack(pady=5)
        self.campos = []  # lista de (entry_sp, entry_t)
        for i in range(8):
            f = ttk.Frame(cont); f.pack(pady=4, anchor="w")
            ttk.Label(f, text=f"Paso {i}").grid(row=0, column=0, padx=5, sticky="w")
            ttk.Label(f, text="Setpoint:").grid(row=0, column=1, padx=5, sticky="e")
            e_sp = ttk.Entry(f, width=10); e_sp.grid(row=0, column=2)
            e_sp.bind("<Button-1>", lambda e, ent=e_sp:
                      TecladoNumerico(self, ent,
                                      on_submit=lambda v, en=ent: self._aplicar_sp(en, v)))
            ttk.Label(f, text="Tiempo (min):").grid(row=0, column=3, padx=5, sticky="e")
            e_t = ttk.Entry(f, width=10); e_t.grid(row=0, column=4)
            e_t.bind("<Button-1>", lambda e, ent=e_t:
                     TecladoNumerico(self, ent,
                                     on_submit=lambda v, en=ent: self._aplicar_t(en, v)))
            self.campos.append((e_sp, e_t))

        frl = ttk.Frame(self); frl.pack(pady=10)
        ttk.Label(frl, text="Paso límite (0-7):").grid(row=0, column=0, padx=5, sticky="e")
        self.entry_limite = ttk.Entry(frl, width=6); self.entry_limite.grid(row=0, column=1, padx=5)
        self.entry_limite.bind("<Button-1>", lambda e: TecladoNumerico(self, self.entry_limite))

        ttk.Button(self, text="Enviar", command=self.enviar_rampa).pack(pady=15)
        self.bind("<Return>", lambda e: self.enviar_rampa())
        self.bind("<Escape>", lambda e: self.destroy())

        self._solicitar_rampa()

    # --------------------------------------------------
    # Callbacks desde teclado numérico
    # --------------------------------------------------
    def _aplicar_sp(self, entry, valor):
        n = self._int_trunc(valor); n = min(n, 600)
        entry.delete(0, tk.END); entry.insert(0, str(n))

    def _aplicar_t(self, entry, valor):
        n = self._int_trunc(valor)
        entry.delete(0, tk.END); entry.insert(0, str(n))

    # --------------------------------------------------
    # Helpers numéricos
    # --------------------------------------------------
    def _int_trunc(self, v):
        try: return int(float(v))
        except Exception: return 0

    def _paso_lim_val(self, v):
        try:
            n = int(float(v))
            return n if 0 <= n <= 7 else 0
        except Exception:
            return 0

    # --------------------------------------------------
    # Integración con app/arduino
    # --------------------------------------------------
    def aplicar_rampa(self, sp_list, t_list, paso_lim):
        try:
            for i, (ent_sp, ent_t) in enumerate(self.campos):
                sp = self._int_trunc(sp_list[i]) if i < len(sp_list) else 0
                t = self._int_trunc(t_list[i]) if i < len(t_list) else 0
                ent_sp.delete(0, tk.END); ent_sp.insert(0, str(min(sp, 600)))
                ent_t.delete(0, tk.END); ent_t.insert(0, str(t))
            pl = self._paso_lim_val(paso_lim)
            self.entry_limite.delete(0, tk.END); self.entry_limite.insert(0, str(pl))
        except Exception as e:
            print("[Rampa] Error aplicando datos:", e)

    def _solicitar_rampa(self):
        msg = f"$;2;{self.id_omega};4;3;!"
        print("[TX] Solicitud rampa:", msg)
        if self.controlador and hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
        elif self.arduino:
            try:
                self.arduino.write((msg + "\n").encode("utf-8"))
            except Exception as e:
                print("Error al enviar solicitud rampa:", e)

    def enviar_rampa(self):
        sp_list = [min(self._int_trunc(sp.get()), 600) for sp, _ in self.campos]
        t_list = [self._int_trunc(t.get()) for _, t in self.campos]
        paso_lim = self._paso_lim_val(self.entry_limite.get())

        partes = ["$;2", str(self.id_omega), "1", "3"]
        partes.extend(str(v) for v in sp_list)
        partes.extend(str(v) for v in t_list)
        partes.append(str(paso_lim))
        msg = ";".join(partes) + ";!"
        print("[TX] Rampa:", msg)
        if self.controlador and hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
        elif self.arduino:
            try:
                self.arduino.write((msg + "\n").encode("utf-8"))
            except Exception as e:
                print("Error al enviar rampa:", e)
        self._on_close()

    def _on_close(self):
        try:
            if self.controlador is not None:
                attr = f"_rampa_win_{self.id_omega}"
                if getattr(self.controlador, attr, None) is self:
                    setattr(self.controlador, attr, None)
        except Exception:
            pass
        self.destroy()
