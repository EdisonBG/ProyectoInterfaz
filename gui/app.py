"""
Controlador principal de la interfaz (Tk) con viewport fijo 1024×530.

- Mantiene un *viewport* de tamaño útil constante (1024×530) donde se montan
  todas las ventanas para evitar recortes por la barra de título o bordes.
- Navegación por nombre con `mostrar_ventana(nombre)` usada desde la barra.
- Envío/recepción (no bloqueante) hacia Arduino mediante `SerialManager`.
- Ruteo básico de RX: CMD=5 → `VentanaGraph.on_rx_cmd5(partes)`; 
  se puede ampliar según necesidades.

Este archivo sustituye al `app.py` anterior. Mantiene compatibilidad con
las ventanas refactorizadas: `VentanaPrincipal`, `VentanaMfc`,
`VentanaOmega`, `VentanaValv`, `VentanaAuto`, `VentanaGraph`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import queue

# Ventanas
from .ventana_principal import VentanaPrincipal
from .ventana_mfc import VentanaMfc
from .ventana_omega import VentanaOmega
from .ventana_valv import VentanaValv
from .ventana_auto import VentanaAuto
from .ventana_graph import VentanaGraph

# Serial
from .serial_manager import SerialManager  # se asume provee `start()`, `stop()`, `send(str)` y `rx_queue`


class Aplicacion(tk.Tk):
    """Controlador principal de la interfaz gráfica."""

    def __init__(self, serial_port: str = "/dev/ttyACM0", baud: int = 115200):
        super().__init__()
        self.title("Interfaz Arduino-Raspberry")

        # --- Estado ---
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

        # --- Viewport fijo (área útil 1024×530) ---
        self._ajustar_tamano_ventana(1024, 530)

        # --- Serial no bloqueante ---
        self.serial = None
        self.rx_queue: queue.Queue[str] | None = None
        try:
            self.serial = SerialManager(port=serial_port, baud=baud)
            self.serial.start()
            self.rx_queue = self.serial.rx_queue
        except Exception as e:
            print(f"[WARN] No se pudo iniciar SerialManager: {e}")

        # --- Primer pantalla ---
        self.mostrar_ventana("VentanaPrincipal")

        # Poll de RX
        self.after(100, self._poll_rx)

        # Cierra ordenado
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ==============================================================
    # Viewport fijo 1024×530
    # ==============================================================
    def _ajustar_tamano_ventana(self, inner_w: int = 1024, inner_h: int = 530):
        """Ajusta el tamaño de la ventana para que el área *interna* útil
        sea exactamente `inner_w × inner_h`.
        Crea un frame `_viewport` donde se montan las ventanas.
        """
        try:
            # Escalado DPI a 96 (1.0) para evitar distorsiones en RPi
            self.tk.call('tk', 'scaling', '-displayof', '.', 1.0)
        except Exception:
            pass

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._viewport = ttk.Frame(self, width=inner_w, height=inner_h)
        self._viewport.grid(row=0, column=0, sticky="nsew")
        self._viewport.grid_propagate(False)  # clave: no permitir que los hijos cambien el tamaño

        # Ajuste de geometry para compensar decoraciones
        self.update_idletasks()
        outer_w = self.winfo_width()
        outer_h = self.winfo_height()
        view_w = self._viewport.winfo_width()
        view_h = self._viewport.winfo_height()
        if outer_w == 1 and outer_h == 1:
            # Primer pase (algunas WMs reportan 1x1 antes del layout)
            self.geometry(f"{inner_w+80}x{inner_h+120}")
            self.update_idletasks()
            outer_w = self.winfo_width(); outer_h = self.winfo_height()
            view_w = self._viewport.winfo_width(); view_h = self._viewport.winfo_height()
        deco_w = max(0, outer_w - view_w)
        deco_h = max(0, outer_h - view_h)
        self.geometry(f"{inner_w + deco_w}x{inner_h + deco_h}")

    def _montar_ventana_en_viewport(self, frame: tk.Frame):
        """Monta un Frame dentro del viewport fijo 1024×530 sin destruirlo.
        Se ocultan otros hijos y se levanta el objetivo."""
        # Asegurar que el viewport existe
        if not hasattr(self, "_viewport"):
            self._ajustar_tamano_ventana(1024, 530)

        # Ocultar cualquier otro hijo y dejar solo el objetivo
        for w in list(self._viewport.winfo_children()):
            if w is frame:
                continue
            try:
                w.grid_forget()
            except Exception:
                pass

        # En este proyecto las ventanas se crean con master=self._viewport
        # (Tk no permite reparentar dinámicamente un widget).
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
            frame = Clase(self._viewport, self, self.serial)  # (master, controlador, arduino)
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
        if self.serial and hasattr(self.serial, "send"):
            try:
                self.serial.send(msg)
                return
            except Exception as e:
                print(f"[SERIAL] Error enviando: {e}")
        print("[TX]", msg)

    def _poll_rx(self):
        """Consulta la cola RX sin bloquear y rutea mensajes a las ventanas."""
        try:
            if self.rx_queue is not None:
                while True:
                    line = self.rx_queue.get_nowait()
                    self._procesar_linea_rx(line)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_rx)

    def _procesar_linea_rx(self, line: str) -> None:
        line = (line or "").strip()
        if not line:
            return
        # protocolo: $;{cmd};...;!
        if not line.startswith("$") or not line.endswith("!"):
            return
        payload = line[2:-1] if line.startswith("$;") else line[1:-1]
        partes = payload.split(";") if payload else []
        if not partes:
            return
        cmd = partes[0]
        # CMD=5 → datos para gráfica
        if cmd == "5":
            # intentar enviar a la ventana de gráfica si existe
            v = self._ventanas.get("VentanaGraph")
            if v and hasattr(v, "on_rx_cmd5"):
                try:
                    v.on_rx_cmd5(partes)
                except Exception as e:
                    print(f"[Graph] Error en on_rx_cmd5: {e}")

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


# ---------------------------------------------------------------
# Arranque manual (si se ejecuta este módulo directamente)
# ---------------------------------------------------------------
if __name__ == "__main__":
    app = Aplicacion()
    app.mainloop()
