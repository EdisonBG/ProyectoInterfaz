import tkinter as tk
from tkinter import ttk, messagebox
import serial
from .ventana_principal import VentanaPrincipal
from .ventana_mfc import VentanaMfc
from .ventana_omega import VentanaOmega
from .ventana_valv import VentanaValv
from .ventana_auto import VentanaAuto
from .ventana_graph import VentanaGraph

from .barra_navegacion import BarraNavegacion
from .serial_manager import SerialManager
import queue  # para Empty en el poll de RX
import glob
import os

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
        self._alert_windows = {}  # dict: clave_alerta -> Toplevel
        
        # --- Callbacks para estado de MFCs ---
        self._callbacks_estado_mfc = {1: [], 2: [], 3: [], 4: []}

        # --- Callbacks para válvulas y bomba ---
        self._callbacks_estado_valvulas = {"sol1": [], "sol2": [], "per1": []}

        # --- Callbacks para flechas de válvulas ---
        self._callbacks_flechas_valvulas = {1: [], 2: []}

        self._callback_presion_etapa_auto = None

        # --- variable para verificar la conexion al equipo 2 ---
        self.equipo2_conectado = False  # Variable nueva

        # --- Variable para verificar si se encuentra en modo AUTO, y la posicion de ambas valvulas de 4 vas en este modo ---
        self.auto_modo_activo = False  # Variable para modo auto on/off
        self.posicion_valvulas_auto = "A"  # Posicion en modo auto (A o B)

        # --- Variables para modo especial (mensaje $;6;1;X;!) ---
        self.modo_especial_activo = False  # True cuando llega $;6;1;X;!
        self.posicion_modo_especial = None  # "A" o "B" según el último mensaje

        if not os.path.exists(serial_port):
            nuevo_puerto = self._buscar_puerto_arduino()
            if nuevo_puerto is not None:
                print(f"[INFO] Puerto serie detectado autom�ticamente: {nuevo_puerto}")
                serial_port = nuevo_puerto
            else:
                print("[WARN] No se encontr� ning�n puerto serie disponible")

        try:

            self.serial = SerialManager(serial_port, baud)
            self.serial.start()
            print(
                f"[INFO] Serial abierto en {serial_port} @ {baud} bps (SerialManager)")
        except Exception as e:
            print(f"[WARN] SerialManager no disponible: {e}")
            # Fallback a pyserial directo
            self._intentar_conectar_serialmanager(serial_port, baud)

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

    def _intentar_conectar_serialmanager(self, serial_port, baud):
        """Intenta crear y arrancar SerialManager. Si falla, reintenta hasta lograrlo."""
        try:
            self.serial = SerialManager(serial_port, baud)
            self.serial.start()
            print(f"[INFO] Serial abierto en {serial_port} @ {baud} bps (SerialManager)")
        except Exception as e:
            print(f"[WARN] SerialManager no disponible: {e}")
            # Reintentar conexi�n m�s adelante
            self.after(1000, lambda: self._intentar_conectar_serialmanager(serial_port, baud))

    def _buscar_puerto_arduino(self):
        """Busca un puerto /dev/ttyACM* o /dev/ttyUSB* disponible."""
        candidatos = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
        for puerto in sorted(candidatos):
            try:
                s = serial.Serial(puerto, baudrate=9600, timeout=0.5)
                s.close()
                return puerto
            except Exception:
                continue
        return None
    
    # -- metodo para saber la conexion al equipo 2 ---
    def set_equipo2_conectado(self, estado):
        """Cambia el estado de conexi�n del equipo 2"""
        self.equipo2_conectado = estado
        
    def get_equipo2_conectado(self):
        """Obtiene el estado actual de conexi�n del equipo 2"""
        return self.equipo2_conectado
    
    def actualizar_botones_modo_especial(self):
        """Actualiza los botones de todas las barras de navegaci�n seg�n el modo especial actual"""
        for ventana in self._ventanas.values():
            try:
                # Buscar cualquier frame hijo que sea una BarraNavegacion
                for widget in ventana.winfo_children():
                    if isinstance(widget, BarraNavegacion):
                        widget._actualizar_modo_especial(self.modo_especial_activo)
            except Exception as e:
                print(f"[ERROR] Actualizando barra en {ventana}: {e}")
        
        # Tambi�n actualizar la barra de la ventana activa actual si existe
        if hasattr(self, '_ventana_activa') and self._ventana_activa in self._ventanas:
            ventana_activa = self._ventanas[self._ventana_activa]
            for widget in ventana_activa.winfo_children():
                if isinstance(widget, BarraNavegacion):
                    widget._actualizar_modo_especial(self.modo_especial_activo)
    
    # --- Metodos para cuando el equipo se encuentra en modo auto --
    def set_auto_modo_activo(self, estado):
        """Cambia el estado del modo auto"""
        self.auto_modo_activo = estado
        
    def set_posicion_valvulas_auto(self, posicion):
        """Cambia la posici�n de las v�lvulas en modo auto (A o B)"""
        self.posicion_valvulas_auto = posicion
        self.notificar_cambio_flecha_valvula(1, posicion)

    def registrar_callback_presion_etapa_auto(self, callback):
        """Registra un callback para cambios de presi�n en modo auto"""
        self._callback_presion_etapa_auto = callback

    def notificar_cambio_presion_etapa_auto(self, presion):
        """Notifica el cambio de presi�n en modo auto"""
        if self._callback_presion_etapa_auto is not None:
            try:
                self._callback_presion_etapa_auto(presion)
            except Exception as e:
                print(f"Error en callback presi�n etapa auto: {e}")
    # --- Métodos para manejar callbacks de estado MFC ---
    def registrar_callback_estado_mfc(self, mfc_id, callback):
        """Registra un callback para cambios de estado de un MFC"""
        if mfc_id in self._callbacks_estado_mfc:
            self._callbacks_estado_mfc[mfc_id].append(callback)

    def notificar_cambio_estado_mfc(self, mfc_id, estado):
        """Notifica a todos los callbacks registrados sobre un cambio de estado"""
        for callback in self._callbacks_estado_mfc.get(mfc_id, []):
            try:
                callback(mfc_id, estado)
            except Exception as e:
                print(f"Error en callback estado MFC{mfc_id}: {e}")
    
    # --- Métodos para manejar callbacks de estado válvulas solenoides BackPressure y bomba peristáltica ---

    def registrar_callback_estado_valvula(self, clave, callback):
        """Registra un callback para cambios de estado de válvulas/bomba"""
        if clave in self._callbacks_estado_valvulas:
            self._callbacks_estado_valvulas[clave].append(callback)

    def notificar_cambio_estado_valvula(self, clave, estado, modo_auto=False):
        """Notifica a todos los callbacks registrados sobre un cambio de estado"""
        for callback in self._callbacks_estado_valvulas.get(clave, []):
            try:
                callback(clave, estado, modo_auto)
            except Exception as e:
                print(f"Error en callback {clave}: {e}")

    # --- Métodos para flechas de válvulas ---
    def registrar_callback_flecha_valvula(self, valvula_id, callback):
        """Registra un callback para cambios de posición de una válvula de 4 vías"""
        if valvula_id in self._callbacks_flechas_valvulas:
            self._callbacks_flechas_valvulas[valvula_id].append(callback)

    def notificar_cambio_flecha_valvula(self, valvula_id, pos):
        """Notifica a todos los callbacks registrados sobre un cambio de posición"""
        for callback in self._callbacks_flechas_valvulas.get(valvula_id, []):
            try:
                callback(valvula_id, pos)
            except Exception as e:
                print(f"Error en callback flecha válvula {valvula_id}: {e}")

    # --- Métodos para obtener estado actual de las válvulas ---
    def obtener_estado_actual_valvulas(self):
        """
        Retorna el estado actual de las válvulas V1 y V2
        Si VentanaValv no existe, retorna (None, None)
        """
        vvalv = self._ventanas.get("VentanaValv")
        if vvalv is not None:
            return vvalv.v1_pos.get(), vvalv.v2_pos.get()
        return None, None

    def obtener_estado_valvula(self, valvula_id):
        """
        Retorna el estado actual de una válvula específica
        """
        vvalv = self._ventanas.get("VentanaValv")
        if vvalv is not None:
            if valvula_id == 1:
                return vvalv.v1_pos.get()
            elif valvula_id == 2:
                return vvalv.v2_pos.get()
        return None
        
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


            # ---------------- conexion al equipo 2 ----------------
            if len(partes) == 3 and partes[0] == "6":
                print(f"[RX] Mensaje especial recibido: {partes}")
                
                # Guardar estado en el controlador
                self.modo_especial_activo = (partes[1] == "1")
                
                # Si es mensaje de activación ($;6;1;X;!), guardar posición
                if self.modo_especial_activo:
                    self.posicion_modo_especial = "A" if partes[2] == "1" else "B"
                    self._actualizar_csv_directo(self.posicion_modo_especial)

                self.actualizar_botones_modo_especial()
                self._ultimo_estado_modo_especial = self.modo_especial_activo
                
                for ventana in self._ventanas.values():
                    if hasattr(ventana, 'barra_navegacion'):
                        ventana.barra_navegacion._actualizar_modo_especial(self.modo_especial_activo)
            # Notificar a ventana valv (si existe)
                vvalv = self._ventanas.get("VentanaValv")
                if vvalv is not None:
                    self.after(0, vvalv._manejar_mensaje_especial, partes)
                return
        
            # ---------------- Presión de seguridad superada ----------------
            # Formato exacto: $;1;4;!
            if len(partes) == 2 and partes[0] == "1" and partes[1] == "4":
                # Pop-up único (no modal, cerrable por el usuario)
                self._show_alert_popup(
                    key="pressure_security",
                    title="Alerta de presión",
                    body="Se superó la presión de seguridad."
                )

                # Poner entries de MFC a 0 (si ventana existe)
                vmfc = getattr(self, "_ventanas", {}).get("VentanaMfc") if hasattr(self, "_ventanas") else None
                if vmfc is not None and hasattr(vmfc, "reset_flujos_a_cero"):
                    try:
                        vmfc.reset_flujos_a_cero()
                    except Exception as e:
                        print(f"[WARN] No se pudieron resetear los MFC: {e}")
                return

            # ---------------- Error de sensor de presión ----------------
            # Formato: $;3;4;N;!  con N en {1,2,3,4}
            if len(partes) == 3 and partes[0] == "3" and partes[1] == "4":
                sensor = partes[2]
                if sensor in ("1", "2", "3", "4"):
                    self._show_alert_popup(
                        key=f"sensor_{sensor}",
                        title="Error de sensor",
                        body=f"Un sensor de presión está desconectado o fallando.\n\nSensor: {sensor}"
                    )
                    return


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

    def _notificar_modo_especial(self, modo_activo):
        """
        Notifica a barra navegación sobre el modo especial
        """
        # Buscar barra navegación en todas las ventanas
        for ventana in self._ventanas.values():
        # Si la ventana tiene una barra de navegaci�n, actualizarla
            if hasattr(ventana, 'barra_navegacion'):
                ventana.barra_navegacion._actualizar_modo_especial(modo_activo)
        # Tambi�n notificar a la barra de navegaci�n de la ventana principal si existe
        if hasattr(self, '_ventana_principal') and hasattr(self._ventana_principal, 'barra_navegacion'):
            self._ventana_principal.barra_navegacion._actualizar_modo_especial(modo_activo)                

    def _actualizar_csv_directo(self, posicion):
        """Actualiza el CSV de válvulas directamente (cuando ventana_valv no existe)"""
        import csv
        import os
        
        # Ruta al archivo CSV (misma que en ventana_valv)
        #csv_path = os.path.join(os.path.dirname(__file__), "ventana_valv", "valv_pos.csv")
        csv_path = os.path.join(os.path.dirname(__file__), "valv_pos.csv")
        
        try:
            # Leer archivo existente
            data = {}
            if os.path.exists(csv_path):
                with open(csv_path, newline="", encoding="utf-8") as f:
                    for nombre, pos in csv.reader(f):
                        key = (nombre or "").strip().upper()
                        val = (pos or "").strip().upper()
                        data[key] = val
            
            # Actualizar ambas válvulas con la nueva posición
            data["V1"] = posicion
            data["V2"] = posicion
            
            # Guardar archivo
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["V1", data["V1"]])
                w.writerow(["V2", data["V2"]])
                if "BYP" in data:
                    w.writerow(["BYP", data["BYP"]])
            
            print(f"[INFO] CSV actualizado directamente con posición {posicion}")
            
        except Exception as e:
            print(f"[ERROR] No se pudo actualizar CSV directamente: {e}")

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

            # Si estamos en modo especial y es la ventana de v�lvulas o auto, actualizar estado
            if hasattr(self, 'modo_especial_activo') and self.modo_especial_activo:
                if nombre == "VentanaValv" and hasattr(frame, '_aplicar_estado_conexion'):
                    frame.v1_pos.set(self.posicion_modo_especial)
                    frame.v2_pos.set(self.posicion_modo_especial)
                    frame._refrescar_botones("v1")
                    frame._refrescar_botones("v2")
                # Luego aplicar estado
                frame._aplicar_estado_conexion()
                

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

        if hasattr(frame_objetivo, 'barra_navegacion') and hasattr(self, 'modo_especial_activo'):
            frame_objetivo.barra_navegacion._actualizar_modo_especial(self.modo_especial_activo)

        # --- Enviar identificador al entrar a Temperatura ---
        if nombre == "VentanaOmega":
            try:
                self.enviar_a_arduino("$;2;9;!")
            except Exception as e:
                print(
                    f"[WARN] No se pudo enviar identificador de VentanaOmega: {e}")
                
    def _show_alert_popup(self, key: str, title: str, body: str):
        """
        Muestra (o enfoca) un Toplevel de alerta no modal, único por 'key'.
        - No bloquea la UI.
        - El usuario puede cerrarlo.
        - Si ya existe, solo lo trae al frente y actualiza el texto.
        """
        # Si ya existe y sigue viva, solo enfócala y actualiza:
        win = self._alert_windows.get(key)
        if win is not None and win.winfo_exists():
            # Actualizar texto si cambió y traer al frente
            try:
                lbl = getattr(win, "_lbl_body", None)
                if lbl is not None:
                    lbl.configure(text=body)
            except Exception:
                pass
            try:
                win.deiconify()
                win.lift()
                win.focus_force()
            except Exception:
                pass
            return

        # Crear nueva ventana
        win = tk.Toplevel(self)
        self._alert_windows[key] = win

        # Configuración básica
        win.title(title)
        win.attributes("-topmost", True)  # mantener arriba sin bloquear
        win.resizable(False, False)

        # Cerrar: borrar del registro
        def _on_close():
            try:
                if key in self._alert_windows:
                    del self._alert_windows[key]
            except Exception:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)

        # Contenido simple
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=title, font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 6))
        lbl_body = ttk.Label(frm, text=body, justify="left", wraplength=360)
        lbl_body.pack(anchor="w")
        win._lbl_body = lbl_body  # guardar referencia para actualizaciones

        ttk.Button(frm, text="Cerrar", command=_on_close).pack(anchor="e", pady=(12, 0))

        # Posicionar cerca del centro de la app
        try:
            win.update_idletasks()
            x = self.winfo_rootx() + max(20, (self.winfo_width() - win.winfo_width()) // 2)
            y = self.winfo_rooty() + max(20, (self.winfo_height() - win.winfo_height()) // 3)
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass
        