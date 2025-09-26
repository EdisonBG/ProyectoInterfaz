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
        self.geometry("1024x600")
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
        """
        Punto central para procesar mensajes que llegan del Arduino.
        """
        try:
            limpio = msg.strip()
            if not (limpio.startswith("$") and limpio.endswith("!")):
                return

            cuerpo = limpio[1:-1]
            partes = [p for p in cuerpo.split(";") if p != ""]
            if len(partes) < 3:
                return

            # ------------------------------------------------------------
            # 1) Rampa (respuesta a $;2;ID;4;3;!):
            #    $;2;ID;3;SP0..SP7;T0..T7;PASO;!  => total 20 campos
            # ------------------------------------------------------------
            if partes[0] == "2" and len(partes) == 20 and partes[2] == "3":
                try:
                    id_omega_rx = int(partes[1])
                except Exception:
                    id_omega_rx = None

                sp_list = partes[3:11]   # 8 SP
                t_list  = partes[11:19]  # 8 T
                paso    = partes[19]     # paso final

                attr = f"_rampa_win_{id_omega_rx}"
                win = getattr(self, attr, None)
                if win is not None and hasattr(win, "aplicar_rampa"):
                    win.aplicar_rampa(sp_list, t_list, paso)
                else:
                    print(f"[RX rampa] sin ventana activa para Omega {id_omega_rx}")
                return

            # ------------------------------------------------------------
            # 2) Autotuning (lectura de memorias)
            #    $;2;ID;2;sp0;sp1;sp2;sp3;!  => 7 campos
            # ------------------------------------------------------------
            if partes[0] == "2" and len(partes) == 7 and partes[2] == "2":
                try:
                    id_omega_rx = int(partes[1])
                except Exception:
                    id_omega_rx = None

                sp_list = partes[3:7]
                win = getattr(self, "_autotuning_win", None)
                if win is not None and getattr(win, "id_omega", None) == id_omega_rx:
                    win.actualizar_setpoints(sp_list)
                return

            # ------------------------------------------------------------
            # 3) Estado de temperatura de Omega1 y Omega2 (al entrar)
            #    $;2; m1; sp1; mem1; svn1; p1; i1; d1;  m2; sp2; mem2; svn2; p2; i2; d2; !
            #    => total 15 campos (1 cmd + 14 datos)
            # ------------------------------------------------------------
            if partes[0] == "2" and len(partes) == 15:
                data = partes[1:15]
                o1 = data[0:7]
                o2 = data[7:14]
                vo = self._ventanas.get("VentanaOmega")
                if vo is not None and hasattr(vo, "aplicar_estado_omegas"):
                    vo.aplicar_estado_omegas(o1, o2)
                else:
                    print("[INFO] Estado Omega recibido pero VentanaOmega no está instanciada")
                return

            # ------------------------------------------------------------
            # 4) Parámetros PID de una memoria
            #    $;2;ID;svn;p;i;d;!  => 6 campos
            # ------------------------------------------------------------
            if partes[0] == "2" and len(partes) == 6:
                try:
                    id_omega_rx = int(partes[1])
                except Exception:
                    id_omega_rx = None

                svn, p, i, d = partes[2], partes[3], partes[4], partes[5]
                vo = self._ventanas.get("VentanaOmega")
                if vo is not None and hasattr(vo, "actualizar_parametros_omega") and id_omega_rx is not None:
                    vo.actualizar_parametros_omega(id_omega_rx, svn, p, i, d)
                else:
                    print("[INFO] Parámetros PID recibidos pero VentanaOmega no está lista")
                return

            # ------------------------------------------------------------
            # 5) Variables de proceso (CMD=5) – VentanaPrincipal y VentanaGraph
            #    $;5;Tω1;Tω2;Th1;Th2;Tc1;Tc2;Pmez*10;Ph2*10;Psal*10;
            #        Q_O2;Q_CO2;Q_N2;Q_H2;PotW;HorasOn;!
            # ------------------------------------------------------------
            if partes[0] == "5" and len(partes) >= 16:
                # Ventana Principal
                vp = self._ventanas.get("VentanaPrincipal") if hasattr(self, "_ventanas") else None
                if vp is not None and hasattr(vp, "aplicar_datos_cmd5"):
                    vp.aplicar_datos_cmd5(partes)

                # Ventana Graph
                vg = getattr(self, "_ventana_graph", None)
                if vg is not None and hasattr(vg, "on_rx_cmd5"):
                    vg.on_rx_cmd5(partes)
                return

            # ------------------------------------------------------------
            # Otros comandos (válvulas=3, MFC=1, etc.)...
            # ------------------------------------------------------------
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
