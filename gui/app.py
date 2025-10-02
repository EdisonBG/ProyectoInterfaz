"""
Clase principal de la aplicación Tkinter para Raspberry Pi 4.

Cambios clave de esta versión:
- Geometría fija tomada de ui/constants.py (1024x530).
- Estilo/tema centralizados en gui/theme.apply_theme.
- Polling serie usando POLL_MS desde ui/constants.py.
- Navegación con caché de instancias y limpieza de recursos.
"""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, Optional, Type

import serial  # pyserial

# Tema y constantes centralizadas
from ui.constants import USABLE_WIDTH, USABLE_HEIGHT, POLL_MS
from gui.theme import apply_theme

# Importaciones de ventanas (mantener según proyecto)
from .ventana_principal import VentanaPrincipal
from .ventana_mfc import VentanaMfc
from .ventana_omega import VentanaOmega
from .ventana_valv import VentanaValv
from .ventana_auto import VentanaAuto
from .ventana_graph import VentanaGraph

from .serial_manager import SerialManager


class Aplicacion(tk.Tk):
    """Ventana raíz de la aplicación.

    Gestiona estilo, geometría, comunicación serie y navegación entre subventanas.
    """

    # Conservado solo por compatibilidad interna; el estilo real vive en gui/theme.py
    TK_SCALING: float = 1.20

    # Activar/desactivar trazas internas ligeras
    DEBUG: bool = False

    def __init__(
        self,
        arduino: Optional[serial.Serial] = None,
        serial_port: str = "/dev/ttyACM0",
        baud: int = 115200,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        # --- Configuración de ventana raíz ---
        self.title("Interfaz Arduino-Raspberry")
        self.geometry(f"{USABLE_WIDTH}x{USABLE_HEIGHT}")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Estilo y tema centralizados ---
        apply_theme(self)

        # --- Comunicación serie ---
        self.serial: Optional[SerialManager] = None
        self.arduino: Optional[serial.Serial] = None

        try:
            self.serial = SerialManager(serial_port, baud)
            self.serial.start()
            self._log_debug(f"Serial abierto en {serial_port} @ {baud} bps (SerialManager)")
        except Exception as e:
            self._log_debug(f"SerialManager no disponible: {e}")
            try:
                self.arduino = serial.Serial(serial_port, baudrate=baud, timeout=1)
                self._log_debug(f"Conectado a Arduino en {serial_port} @ {baud} bps (pyserial)")
            except Exception as e2:
                print(f"[WARN] No se pudo abrir puerto serial: {e2}")

        if arduino is not None:
            self.arduino = arduino

        # --- Registro de clases de ventanas e instancias ---
        self._clases: Dict[str, Type[tk.Frame]] = {
            "VentanaPrincipal": VentanaPrincipal,
            "VentanaMfc": VentanaMfc,
            "VentanaOmega": VentanaOmega,
            "VentanaValv": VentanaValv,
            "VentanaAuto": VentanaAuto,
            "VentanaGraph": VentanaGraph,
        }
        self._ventanas: Dict[str, tk.Frame] = {}
        self._ventana_activa: Optional[str] = None

        # Mostrar ventana inicial
        self.mostrar_ventana("VentanaPrincipal")

        # Polling RX no bloqueante
        self.after(POLL_MS, self._poll_serial)

        # Cierre limpio
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------------
    # Comunicación serie
    # ---------------------------------------------------------------------
    def enviar_a_arduino(self, mensaje: str) -> None:
        """Envía un mensaje al Arduino por el canal disponible.

        Prioriza SerialManager; si no está disponible, usa pyserial directo.
        Siempre termina las líneas con "\n" en envío directo.
        """
        self._log_debug(f"[TX] {mensaje}")
        if self.serial is not None:
            try:
                self.serial.send(mensaje)
                return
            except Exception as e:
                print(f"[TX ERROR SerialManager] {e}")
        if self.arduino is not None:
            try:
                self.arduino.write((mensaje + "\n").encode("utf-8"))
            except Exception as e:
                print(f"[TX ERROR pyserial] {e}")

    def _poll_serial(self) -> None:
        """Sondea la cola RX de SerialManager y procesa los mensajes disponibles."""
        if self.serial is not None:
            try:
                while True:
                    msg = self.serial.q_in.get_nowait()
                    self._manejar_mensaje(msg)
            except queue.Empty:
                pass
            except Exception as e:
                print(f"[RX ERROR poll] {e}")
        self.after(POLL_MS, self._poll_serial)

    def _manejar_mensaje(self, msg: str) -> None:
        """Punto central para procesar mensajes recibidos del Arduino.

        Formato esperado: "$;...;!". Mensajes inválidos se descartan silenciosamente.
        """
        try:
            limpio = msg.strip()
            if not (limpio.startswith("$") and limpio.endswith("!")):
                return

            cuerpo = limpio[1:-1]
            partes = [p for p in cuerpo.split(";") if p != ""]
            if len(partes) < 2:
                return

            # 1) Rampa (respuesta a $;2;ID;4;3;!)
            #    $;2;ID;3;SP0..SP7;T0..T7;PASO;!  => total 20 campos
            if partes[0] == "2" and len(partes) == 20 and partes[2] == "3":
                id_omega_rx = _safe_int(partes[1])
                sp_list = partes[3:11]
                t_list = partes[11:19]
                paso = partes[19]

                attr = f"_rampa_win_{id_omega_rx}"
                win = getattr(self, attr, None)
                if win is not None and hasattr(win, "aplicar_rampa"):
                    win.aplicar_rampa(sp_list, t_list, paso)
                else:
                    self._log_debug(f"[RX rampa] sin ventana activa para Omega {id_omega_rx}")
                return

            # 2) Autotuning (lectura de memorias)
            #    $;2;ID;2;sp0;sp1;sp2;sp3;!  => 7 campos
            if partes[0] == "2" and len(partes) == 7 and partes[2] == "2":
                id_omega_rx = _safe_int(partes[1])
                sp_list = partes[3:7]
                win = getattr(self, "_autotuning_win", None)
                if win is not None and getattr(win, "id_omega", None) == id_omega_rx:
                    win.actualizar_setpoints(sp_list)
                return

            # 3) Estado de temperatura de Omega1 y Omega2 (al entrar)
            #    $;2; m1; sp1; mem1; svn1; p1; i1; d1;  m2; sp2; mem2; svn2; p2; i2; d2; !
            #    => total 15 campos (1 cmd + 14 datos)
            if partes[0] == "2" and len(partes) == 15:
                data = partes[1:15]
                o1 = data[0:7]
                o2 = data[7:14]
                vo = self._ventanas.get("VentanaOmega")
                if vo is not None and hasattr(vo, "aplicar_estado_omegas"):
                    vo.aplicar_estado_omegas(o1, o2)
                else:
                    self._log_debug("[INFO] Estado Omega recibido pero VentanaOmega no está instanciada")
                return

            # 4) Parámetros PID de una memoria
            #    $;2;ID;svn;p;i;d;!  => 6 campos
            if partes[0] == "2" and len(partes) == 6:
                id_omega_rx = _safe_int(partes[1])
                svn, p, i, d = partes[2], partes[3], partes[4], partes[5]
                vo = self._ventanas.get("VentanaOmega")
                if vo is not None and hasattr(vo, "actualizar_parametros_omega") and id_omega_rx is not None:
                    vo.actualizar_parametros_omega(id_omega_rx, svn, p, i, d)
                else:
                    self._log_debug("[INFO] Parámetros PID recibidos pero VentanaOmega no está lista")
                return

            # 5) Variables de proceso (CMD=5) – VentanaPrincipal y VentanaGraph
            #    $;5;Tω1;Tω2;Th1;Th2;Tc1;Tc2;Pmez*10;Ph2*10;Psal*10; Q_O2;Q_CO2;Q_N2;Q_H2;PotW;HorasOn;!
            if partes[0] == "5" and len(partes) >= 16:
                vp = self._ventanas.get("VentanaPrincipal") if hasattr(self, "_ventanas") else None
                if vp is not None and hasattr(vp, "aplicar_datos_cmd5"):
                    vp.aplicar_datos_cmd5(partes)

                vg = getattr(self, "_ventana_graph", None)
                if vg is not None and hasattr(vg, "on_rx_cmd5"):
                    vg.on_rx_cmd5(partes)
                return

            self._log_debug(f"[RX NO RUTEADO] {partes}")

        except Exception as e:
            print(f"[RX ERROR] {e}")

    # ---------------------------------------------------------------------
    # Navegación entre ventanas
    # ---------------------------------------------------------------------
    def _obtener_ventana(self, nombre: str) -> tk.Frame:
        """Crea (si es necesario) y devuelve la instancia de la ventana."""
        if nombre not in self._ventanas:
            Clase = self._clases[nombre]
            frame = Clase(self, self, self.arduino)  # (master, controlador, arduino)
            frame.grid(row=0, column=0, sticky="nsew")
            self._ventanas[nombre] = frame
        return self._ventanas[nombre]

    def mostrar_ventana(self, nombre: str) -> None:
        """Oculta las demás y trae al frente la ventana seleccionada sin destruirla."""
        frame_objetivo = self._obtener_ventana(nombre)

        for frame in self._ventanas.values():
            if frame is not frame_objetivo:
                frame.grid_remove()

        frame_objetivo.grid()
        frame_objetivo.tkraise()
        self._ventana_activa = nombre

        # Enviar identificador al entrar a VentanaOmega
        if nombre == "VentanaOmega":
            try:
                self.enviar_a_arduino("$;2;9;!")
            except Exception as e:
                print(f"[WARN] No se pudo enviar identificador de VentanaOmega: {e}")

    # ---------------------------------------------------------------------
    # Cierre limpio
    # ---------------------------------------------------------------------
    def _on_close(self) -> None:
        """Libera recursos de comunicación y destruye la ventana raíz."""
        try:
            if self.serial is not None:
                self.serial.stop()
        except Exception:
            pass
        try:
            if self.arduino is not None:
                self.arduino.close()
        except Exception:
            pass
        self.destroy()

    # ---------------------------------------------------------------------
    # Utilidades internas
    # ---------------------------------------------------------------------
    def _log_debug(self, msg: str) -> None:
        """Escribe una traza ligera si DEBUG está activo."""
        if self.DEBUG:
            print(msg, file=sys.stderr)


# -------------------------------------------------------------------------
# Funciones auxiliares
# -------------------------------------------------------------------------

def _safe_int(texto: str) -> Optional[int]:
    """Convierte a int devolviendo None en caso de error."""
    try:
        return int(texto)
    except Exception:
        return None
