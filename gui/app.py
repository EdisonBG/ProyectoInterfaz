import tkinter as tk
import serial
from .ventana_principal import VentanaPrincipal
from .ventana_mfc import VentanaMfc
from .ventana_omega import VentanaOmega
from .ventana_valv import VentanaValv
from .ventana_auto import VentanaAuto
from .ventana_graph import VentanaGraph

from .serial_manager import SerialManager
import queue  # para Empty en el poll de RX


class Aplicacion(tk.Tk):
    def __init__(self, arduino=None, serial_port="/dev/ttyACM0", baud=115200, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title("Interfaz Arduino-Raspberry")
        self.geometry("1280x800")
        # Escalado general (fuentes/ttk). Subir/bajar entre 1.0 y 1.3 segun se sienta en tactil
        self.tk.call("tk", "scaling", 1.20)

        # === Comunicacion serie ===
        # Se intentara usar SerialManager (hilos RX/TX). Si falla, se intenta pyserial directo.
        self.serial = None     # SerialManager
        self.arduino = None    # pyserial.Serial directo (fallback)
        try:

            self.serial = SerialManager(serial_port, baud)
            self.serial.start()
            print(
                f"[INFO] Serial abierto en {serial_port} @ {baud} bps (SerialManager)")
        except Exception as e:
            print(f"[WARN] SerialManager no disponible: {e}")
            # Fallback a pyserial directo
            try:
                self.arduino = serial.Serial(
                    serial_port, baudrate=baud, timeout=1)
                print(
                    f"[INFO] Conectado a Arduino en {serial_port} @ {baud} bps (pyserial)")
            except Exception as e2:
                print(f"[WARN] No se pudo abrir puerto serial: {e2}")

        # Si se inyecta un objeto pyserial externo via parametro arduino, se respeta
        if arduino is not None:
            self.arduino = arduino

         # Para que el frame hijo se expanda
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Mapa de clases de ventanas
        self._clases = {
            "VentanaPrincipal": VentanaPrincipal,
            "VentanaMfc": VentanaMfc,
            "VentanaOmega": VentanaOmega,
            "VentanaValv": VentanaValv,
            "VentanaAuto": VentanaAuto,
            "VentanaGraph": VentanaGraph,
        }

        # Instancias creadas (cache)
        self._ventanas = {}
        self._ventana_activa = None

        # Mostrar ventana inicial
        self.mostrar_ventana("VentanaPrincipal")

        # Programar polling periodico de la cola RX del SerialManager (si existe)
        self.after(50, self._poll_serial)

        # Cierre limpio
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def enviar_a_arduino(self, mensaje: str):
        """
        Envia un mensaje al Arduino por serial si esta conectado.
        Siempre imprime el mensaje para debug.
        Prioriza SerialManager; si no esta disponible, usa pyserial directo.
        """
        print(f"[TX] {mensaje}")
        # Envio via SerialManager (no bloqueante)
        if self.serial is not None:
            try:
                self.serial.send(mensaje)
                return
            except Exception as e:
                print(f"[TX ERROR SerialManager] {e}")
        # Fallback a pyserial directo
        if self.arduino is not None:
            try:
                self.arduino.write((mensaje + "\n").encode("utf-8"))
                return
            except Exception as e:
                print(f"[TX ERROR pyserial] {e}")

    def _poll_serial(self):
        """
        Vaciar cola de entrada del SerialManager y procesar mensajes recibidos.
        No bloquear el hilo de UI. Reprogramar con after().
        """

        if self.serial is not None:

            try:
                while True:
                    msg = self.serial.q_in.get_nowait()
                    self._manejar_mensaje(msg)
                    print("encontre algo en serial")
                    print(msg)
            except queue.Empty:
                pass
        # Reprogramar el siguiente poll
        self.after(50, self._poll_serial)

    def _manejar_mensaje(self, msg: str):
        try:
            limpio = msg.strip()
            if not (limpio.startswith("$") and limpio.endswith("!")):
                return

            cuerpo = limpio[1:-1]
            partes = [p for p in cuerpo.split(";") if p != ""]
            if len(partes) < 3:
                return

            # ---------- Rampa ----------
            if partes[0] == "2" and len(partes) == 20 and partes[2] == "3":
                # ... (igual que tienes)
                return

            # ---------- Autotuning (memorias) ----------
            if partes[0] == "2" and len(partes) == 7 and partes[2] == "2":
                # ... (igual que tienes)
                return

            # ---------- Estado Omega 1 y 2 ----------
            if partes[0] == "2" and len(partes) == 15:
                # ... (igual que tienes)
                return

            # ---------- Parámetros PID de una memoria ----------
            if partes[0] == "2" and len(partes) == 6:
                # ... (igual que tienes)
                return

            # ---------- CMD 5: Variables de proceso (monitor + graph) ----------
            # Esperado: ['5', Tω1, Tω2, Th1, Th2, Tc1, Tc2, Pmez*10, Ph2*10, Psal*10,
            #                 Q_O2, Q_CO2, Q_N2, Q_H2, PotW, HorasOn]  => 16 tokens
            if partes[0] == "5":
                if len(partes) >= 16:
                    # 1) Ventana principal (si está abierta)
                    vp = self._ventanas.get("VentanaPrincipal") if hasattr(self, "_ventanas") else None
                    if vp is not None and hasattr(vp, "aplicar_datos_cmd5"):
                        vp.aplicar_datos_cmd5(partes)

                    # 2) Ventana de gráfico (si está abierta)
                    vg = getattr(self, "_ventana_graph", None)
                    if vg is not None and hasattr(vg, "on_rx_cmd5"):
                        vg.on_rx_cmd5(partes)

                    return  # ya ruteado a ambos
                else:
                    # Llega CMD=5 pero con longitud inesperada: log opcional
                    print(f"[RX CMD5] Longitud inesperada: {len(partes)} -> {partes}")
                    return

            # ---------- Otros comandos no ruteados ----------
            print("[RX NO RUTEADO]", partes)

        except Exception as e:
            print(f"[RX ERROR] {e}")


    def _on_close(self):
        """
        Cierre limpio de recursos (hilos y puerto).
        """
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

    def _obtener_ventana(self, nombre):
        """
        Crea la ventana si no existe y la devuelve desde cache.
        Todas las ventanas se gridean en la misma celda.
        """
        if nombre not in self._ventanas:
            Clase = self._clases[nombre]
            # (master, controlador, arduino)
            frame = Clase(self, self, self.arduino)
            # Coloca todas las ventanas en la misma celda del grid
            frame.grid(row=0, column=0, sticky="nsew")
            self._ventanas[nombre] = frame
        return self._ventanas[nombre]

    def mostrar_ventana(self, nombre):
        """
        Oculta las demas y trae al frente la seleccionada (sin destruir).
        """
        # Asegura que la ventana exista
        frame_objetivo = self._obtener_ventana(nombre)

        # Oculta todas (pero sin destruir)
        for n, frame in self._ventanas.items():
            if frame is not frame_objetivo:
                frame.grid_remove()

        # Muestra y trae al frente la que corresponde
        frame_objetivo.grid()       # vuelve a mostrar si estaba oculto
        frame_objetivo.tkraise()    # al frente

        self._ventana_activa = nombre

        # --- Enviar identificador al entrar a Temperatura ---
        if nombre == "VentanaOmega":
            try:
                self.enviar_a_arduino("$;2;9;!")
            except Exception as e:
                print(
                    f"[WARN] No se pudo enviar identificador de VentanaOmega: {e}")
