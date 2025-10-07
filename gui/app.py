"""
Controlador principal de la interfaz (Tk) con viewport fijo 1024×530 + estilos táctiles.

- Usa constantes de ui/constants.py para tamaños y fuentes globales (táctil).
- Viewport 1024×530 (USABLE_WIDTH/USABLE_HEIGHT) que evita recortes.
- Estilos ttk globales: TButton/TEntry/TCombobox con fuentes “dedo friendly”.
- Serial no bloqueante con polling según POLL_MS.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox  # <-- agregado messagebox
import queue

# Constantes táctiles (obligatorias)
from ui.constants import (
    USABLE_WIDTH, USABLE_HEIGHT, TK_SCALING,
    FONT_BASE, FONT_HEADING,
    POLL_MS,
)

# Para leer opcionales sin romper si no existen
from ui import constants as _C

# Ventanas
from .ventana_principal import VentanaPrincipal
from .ventana_mfc import VentanaMfc
from .ventana_omega import VentanaOmega
from .ventana_valv import VentanaValv
from .ventana_auto import VentanaAuto
from .ventana_graph import VentanaGraph

# Serial (usa tu SerialManager con send()/enviar_a_arduino()/recv_nowait())
from .serial_manager import SerialManager


class Aplicacion(tk.Tk):
    """Controlador principal de la interfaz gráfica."""

    def __init__(self, serial_port: str = "/dev/ttyACM0", baud: int = 115200):
        super().__init__()
        self.title("Interfaz Arduino-Raspberry")

        # ---- Estilos globales “táctiles” ----
        self._configurar_estilos_tactiles()

        # ---- Estado ----
        self._ventanas: dict[str, tk.Frame] = {}
        self._clases: dict[str, type[tk.Frame]] = {
            "VentanaPrincipal": VentanaPrincipal,
            "VentanaMfc": VentanaMfc,
            "VentanaOmega": VentanaOmega,
            "VentanaValv": VentanaValv,
            "VentanaAuto": VentanaAuto,
            "VentanaGraph": VentanaGraph,
        }
        self._ventana_activa: str | None = None

        # ---- Viewport fijo (área útil USABLE_WIDTH × USABLE_HEIGHT) ----
        self._ajustar_tamano_ventana(USABLE_WIDTH, USABLE_HEIGHT)

        # ---- Serial no bloqueante ----
        self.serial: SerialManager | None = None
        try:
            self.serial = SerialManager(port=serial_port, baud=baud)
            self.serial.start()
        except Exception as e:
            print(f"[WARN] No se pudo iniciar SerialManager: {e}")
            self.serial = None  # sigue corriendo en modo “simulado”

        # ---- Primera pantalla ----
        self.mostrar_ventana("VentanaPrincipal")

        # Poll de RX (usa POLL_MS de constants)
        self.after(POLL_MS, self._poll_rx)

        # Cierra ordenado
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ==============================================================
    # Estilos ttk táctiles
    # ==============================================================
    def _configurar_estilos_tactiles(self):
        """Aplica escalado global y estilos base para widgets ttk."""

        # Escalado DPI (afecta métricas base de Tk, alturas de controles)
        try:
            self.tk.call('tk', 'scaling', '-displayof', '.', float(TK_SCALING))
        except Exception:
            pass

        style = ttk.Style(self)

        # Fuente por defecto para la mayoría de controles
        style.configure(".", font=FONT_BASE)

        # Botones estándar
        style.configure("TButton", font=FONT_BASE, padding=(12, 8))

        # Estilo específico “Touch” para botones grandes (opcionales)
        _btn_font = getattr(_C, "BUTTON_FONT", FONT_HEADING)
        _btn_pad = getattr(_C, "BTN_PAD", (14, 10))
        style.configure("Touch.TButton", font=_btn_font, padding=_btn_pad)

        # Entradas y combobox: la altura aumenta con la fuente base
        style.configure("TEntry", font=FONT_BASE)
        style.configure("TCombobox", font=FONT_BASE)

        # Labels de sección/títulos
        style.configure("Heading.TLabel", font=FONT_HEADING)

    # ==============================================================
    # Viewport fijo
    # ==============================================================
    def _ajustar_tamano_ventana(self, inner_w: int, inner_h: int):
        """Ajusta la ventana para que el área interna útil sea exactamente inner_w × inner_h."""
        # grid raíz
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Lienzo fijo donde se montan las ventanas
        self._viewport = ttk.Frame(self, width=inner_w, height=inner_h)
        self._viewport.grid(row=0, column=0, sticky="nsew")
        self._viewport.grid_propagate(False)

        # Ajuste de geometry para compensar decoraciones
        self.update_idletasks()
        outer_w = self.winfo_width()
        outer_h = self.winfo_height()
        view_w = self._viewport.winfo_width()
        view_h = self._viewport.winfo_height()
        if outer_w == 1 and outer_h == 1:
            self.geometry(f"{inner_w+80}x{inner_h+120}")
            self.update_idletasks()
            outer_w = self.winfo_width(); outer_h = self.winfo_height()
            view_w = self._viewport.winfo_width(); view_h = self._viewport.winfo_height()
        deco_w = max(0, outer_w - view_w)
        deco_h = max(0, outer_h - view_h)
        self.geometry(f"{inner_w + deco_w}x{inner_h + deco_h}")

    def _montar_ventana_en_viewport(self, frame: tk.Frame):
        """Monta un Frame dentro del viewport sin destruirlo."""
        if not hasattr(self, "_viewport"):
            self._ajustar_tamano_ventana(USABLE_WIDTH, USABLE_HEIGHT)

        for w in list(self._viewport.winfo_children()):  # oculta el resto
            if w is frame:
                continue
            try:
                w.grid_forget()
            except Exception:
                pass

        try:
            frame.grid(row=0, column=0, sticky="nsew")
            frame.tkraise()
        except Exception as e:
            print(f"[NAV] No se pudo montar la ventana: {e}")

        self._viewport.grid_rowconfigure(0, weight=1)
        self._viewport.grid_columnconfigure(0, weight=1)

    # ==============================================================
    # Navegación
    # ==============================================================
    def _obtener_ventana(self, nombre: str) -> tk.Frame:
        frame = self._ventanas.get(nombre)
        if frame is None:
            Clase = self._clases.get(nombre)
            if Clase is None:
                raise KeyError(f"No hay clase registrada para '{nombre}'.")
            # (master, controlador, arduino/serial)
            frame = Clase(self._viewport, self, self.serial)
            self._ventanas[nombre] = frame
        return frame

    def mostrar_ventana(self, nombre: str) -> None:
        frame = self._obtener_ventana(nombre)
        self._montar_ventana_en_viewport(frame)
        self._ventana_activa = nombre

        # Identificador al entrar a Temperatura (según necesidad original)
        if nombre == "VentanaOmega":
            try:
                self.enviar_a_arduino("$;2;9;!")
            except Exception as e:
                print(f"[WARN] No se pudo enviar identificador VentanaOmega: {e}")

    # ==============================================================
    # Serial I/O
    # ==============================================================
    def enviar_a_arduino(self, msg: str) -> None:
        """Encola `msg` para envío. Si no hay SerialManager, imprime por consola."""
        if self.serial and hasattr(self.serial, "enviar_a_arduino"):
            try:
                self.serial.enviar_a_arduino(msg)  # alias seguro hacia send()
                return
            except Exception as e:
                print(f"[SERIAL] Error enviando: {e}")
        print("[TX]", msg)

    def _poll_rx(self):
        """Consulta RX sin bloquear y rutea mensajes a las ventanas."""
        try:
            if self.serial:
                # Usa helper del SerialManager; si no existe, cae a q_in
                try:
                    lines = self.serial.recv_nowait()
                except AttributeError:
                    # compat: acceder a la cola q_in directamente
                    lines = []
                    try:
                        while True:
                            lines.append(self.serial.q_in.get_nowait())
                    except (queue.Empty, AttributeError):
                        pass

                for raw in lines:
                    self._procesar_linea_rx(raw)
        finally:
            self.after(POLL_MS, self._poll_rx)  # reprograma

    def _procesar_linea_rx(self, line: str) -> None:
        line = (line or "").strip()
        if not line:
            return
        # protocolo: $;{cmd};...;!
        if not (line.startswith("$") and line.endswith("!")):
            return

        # Extrae payload sin $ y !
        payload = line[2:-1] if line.startswith("$;") else line[1:-1]
        partes = payload.split(";") if payload else []
        if not partes:
            return

        cmd = partes[0]

        # ---- ALERTA DE PRESIÓN SEGURIDAD ----
        # Trama especificada: $;1;4;!
        if cmd == "1" and len(partes) >= 2 and partes[1] == "4":
            self._alerta_presion_superada()
            return  # tras atender alerta, no hace falta continuar

        # ---- CMD=5 → datos para gráfica ----
        if cmd == "5":
            v = self._ventanas.get("VentanaGraph")
            if v and hasattr(v, "on_rx_cmd5"):
                try:
                    v.on_rx_cmd5(partes)
                except Exception as e:
                    print(f"[Graph] Error en on_rx_cmd5: {e}")

        # Aquí puedes enrutar más comandos si los usas (CMD=1,2,3,4,...)

    # ==============================================================
    # Lógica de alerta y reseteo de SP de gas
    # ==============================================================
    def _alerta_presion_superada(self) -> None:
        """
        Muestra un popup de alerta y pone a 0 los setpoints de gas en los entries
        visibles (Auto y MFC cuando es posible). También puedes añadir aquí los
        comandos a Arduino para poner las salidas a 0 si lo requieres.
        """
        try:
            messagebox.showerror("Seguridad", "Presión de seguridad superada")
        except Exception:
            print("[ALERTA] Presión de seguridad superada")

        # 1) Intentar poner a 0 en VentanaAuto (tenemos acceso directo a los entries)
        va = self._ventanas.get("VentanaAuto")
        if va and hasattr(va, "cells"):
            try:
                for c in range(1, 9):
                    col = va.cells.get(c)
                    if not col:
                        continue
                    for key in ("m1_f", "m2_f", "m3_f", "m4_f"):
                        ent = col.get(key)
                        if ent:
                            try:
                                ent.delete(0, tk.END)
                                ent.insert(0, "0")
                            except Exception:
                                pass
                # si quieres además mandar comando inmediato a Arduino para cero PWM:
                for mfc_id in (1, 2, 3, 4):
                    self.enviar_a_arduino(f"$;1;{mfc_id};1;0;!")
            except Exception as e:
                print("[Auto] No se pudo forzar 0 en flujos:", e)

        # 2) Intentar poner a 0 en VentanaMfc (si expone algún método evidente)
        vmfc = self._ventanas.get("VentanaMfc")
        if vmfc:
            # Si tu VentanaMfc tiene un método explícito, úsalo:
            if hasattr(vmfc, "poner_gases_a_cero"):
                try:
                    vmfc.poner_gases_a_cero()
                except Exception:
                    pass
            elif hasattr(vmfc, "forzar_cero_flujos"):
                try:
                    vmfc.forzar_cero_flujos()
                except Exception:
                    pass
            else:
                # Fallback: recorre widgets buscando entries de flujo (heurístico seguro)
                try:
                    self._zero_numeric_entries(vmfc)
                except Exception as e:
                    print("[MFC] No se pudo forzar 0 en entradas:", e)

    def _zero_numeric_entries(self, root: tk.Misc) -> None:
        """
        Heurístico de respaldo: recorre el subárbol de widgets y pone a '0' cualquier Entry
        que contenga solo dígitos/float positivo. No toca campos vacíos ni de texto libre.
        Úsalo solo como fallback cuando la ventana no expone API propia.
        """
        try:
            import re
            num_re = re.compile(r"^\s*\d+(\.\d+)?\s*$")
        except Exception:
            num_re = None

        def visit(w: tk.Misc):
            for child in w.winfo_children():
                # ttk.Entry y tk.Entry
                if isinstance(child, (tk.Entry, ttk.Entry)):
                    try:
                        val = child.get()
                        if val is None:
                            continue
                        s = str(val).strip()
                        if not s:
                            continue
                        if num_re and num_re.match(s):
                            child.delete(0, tk.END)
                            child.insert(0, "0")
                    except Exception:
                        pass
                # recursión
                try:
                    visit(child)
                except Exception:
                    pass

        visit(root)

    # ==============================================================
    # Cierre
    # ==============================================================
    def _on_close(self):
        try:
            if self.serial and hasattr(self.serial, "stop"):
                self.serial.stop()
        except Exception:
            pass
        self.destroy()
