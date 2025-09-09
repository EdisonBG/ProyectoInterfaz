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
        """
        Punto central para procesar mensajes que llegan del Arduino.
        Formato general esperado: $;...;!
        Ejemplo AT (respuesta con 4 setpoints):
        $;2;ID_OMEGA;2;sp0;sp1;sp2;sp3;!
        """
        try:
            # normaliza espacios/nuevas lineas
            limpio = msg.strip()
            if not (limpio.startswith("$") and limpio.endswith("!")):
                # si no respeta el enmarcado, ignorar
                return

            # quita delimitadores $ y !
            cuerpo = limpio[1:-1]

            # separa por ; y elimina tokens vacios (por el ; despues de $)
            partes = [p for p in cuerpo.split(";") if p != ""]

            # si no hay lo minimo, salir
            if len(partes) < 3:
                return

            # ------------------------------------------------------------
            # Ruteo por comando. partes[0] suele ser el "ID de comando".
            # Para Omega (2) y subcomando 2 (autotuning data esperada):
            # esperado: ['2', 'ID_OMEGA', '2', 'sp0', 'sp1', 'sp2', 'sp3']
            # ------------------------------------------------------------

            # === Caso 1: Autotuning (lectura de memorias) ===
            # esperado: ['2', 'ID_OMEGA', '2', 'sp0', 'sp1', 'sp2', 'sp3']
            if partes[0] == "2" and partes[2] == "2" and len(partes) == 7:
                # parsea id de omega
                try:
                    id_omega_rx = int(partes[1])
                except Exception:
                    id_omega_rx = None

                sp_list = partes[3:7]

                # si hay ventana de autotuning abierta y corresponde al id, actualizarla
                win = getattr(self, "_autotuning_win", None)
                print("actualizar setpoints memorias")
                if win is not None and getattr(win, "id_omega", None) == id_omega_rx:
                    win.actualizar_setpoints(sp_list)
                return

                # === Caso 2: Estado de temperatura para Omega 1 y 2 (al entrar a ventana) ===
            # esperado:
            # ['2',
            #   m1, sp1, mem1, svn1, p1, i1, d1,
            #   m2, sp2, mem2, svn2, p2, i2, d2]
            # donde mX es 0 (PID) o 3 (Rampa). En PID spX >= 0; en Rampa spX == -1.
            elif partes[0] == "2" and len(partes) >= 15:
                # tomar exactamente 14 campos para robustez
                data = partes[1:15]
                o1 = data[0:7]
                o2 = data[7:14]

                # opcion: validacion rapida de modo (no bloquear si viene raro)
                # si no es 0/3 igual intentamos actualizar
                # aplicar en la ventana si existe
                vo = self._ventanas.get("VentanaOmega")
                if vo is not None and hasattr(vo, "aplicar_estado_omegas"):
                    vo.aplicar_estado_omegas(o1, o2)
                else:
                    # si la ventana aun no existe, puedes cachear aqui si lo deseas
                    # por ahora, solo se informa para debug
                    print(
                        "[INFO] Estado Omega recibido pero VentanaOmega no esta instanciada")
                return

            # === Caso 3: Respuesta parametros PID de una memoria ===
            # esperado: ['2', 'ID_OMEGA', 'svn', 'P', 'I', 'D']
            elif partes[0] == "2" and len(partes) == 6:
                try:
                    id_omega_rx = int(partes[1])
                except Exception:
                    id_omega_rx = None

                svn, p, i, d = partes[2], partes[3], partes[4], partes[5]

                vo = self._ventanas.get("VentanaOmega")
                if vo is not None and hasattr(vo, "actualizar_parametros_omega") and id_omega_rx is not None:
                    vo.actualizar_parametros_omega(id_omega_rx, svn, p, i, d)
                else:
                    print(
                        "[INFO] Parametros PID recibidos pero VentanaOmega no esta lista")
                return

            # --- Ruteo rampa: $;2;ID;3;SPx8;Tx8;PASO;!
            elif partes[0] == "2" and partes[2] == "3" and len(partes) >= 20:
                try:
                    id_omega_rx = int(partes[1])
                except Exception:
                    id_omega_rx = None

                # sp0..sp7 estan en [3:11], t0..t7 en [11:19], paso en [19]
                sp_list = partes[3:11]
                t_list = partes[11:19]
                paso = partes[19]

                # Si hay una VentanaRampa abierta para ese ID -> actualizarla
                attr = f"_rampa_win_{id_omega_rx}"
                win = getattr(self, attr, None)
                if win is not None and hasattr(win, "aplicar_rampa"):
                    win.aplicar_rampa(sp_list, t_list, paso)
                    return

                # Si no hay ventana rampa abierta, no es error: el usuario puede abrirla luego.
                print("[RX rampa] Datos recibidos para Omega",
                      id_omega_rx, "sin ventana activa")
                return

            # ------------------------------------------------------------
            # TODO: agregar aqui otros ruteos para distintos comandos:
            # if partes[0] == "3": ...  (valvulas)
            # if partes[0] == "1": ...  (MFC)
            # etc.
            # ------------------------------------------------------------

            # Si llega algo no reconocido, mostrarlo para debug
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
