# serial_manager.py
import threading
import queue
import time

try:
    import serial
except Exception:
    serial = None


class SerialManager:
    """
    Lector/escritor de puerto serie en hilos separados.

    - q_out: mensajes que la UI quiere enviar -> hilo TX los escribe
    - q_in:  mensajes recibidos del Arduino -> la UI los consume con .after() o polling
    - Protocolo: la app ya debe enviar tramas completas (p.ej. "$;1;...;!").
    """

    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.1,
                 start_char: str = "$", end_char: str = "!"):
        if serial is None:
            raise RuntimeError("pyserial no esta instalado. Ejecutar: pip install pyserial")

        # Puerto serie
        self.ser = serial.Serial(port, baudrate=baud, timeout=timeout)

        # Colas de comunicación
        self.q_out: "queue.Queue[str]" = queue.Queue()
        self.q_in: "queue.Queue[str]" = queue.Queue()

        # Control de hilos
        self._stop = threading.Event()
        self._tx = threading.Thread(target=self._writer, daemon=True)
        self._rx = threading.Thread(target=self._reader, daemon=True)

        # Delimitadores de trama (para parseo en RX)
        self.start_char = start_char
        self.end_char = end_char

    # ---------------------------------------------------------------------
    # Ciclo de vida
    # ---------------------------------------------------------------------
    def start(self) -> None:
        """Inicia los hilos de TX y RX."""
        self._tx.start()
        self._rx.start()

    def stop(self) -> None:
        """Detiene los hilos y cierra el puerto."""
        self._stop.set()
        # Espera breve para que los hilos salgan limpiamente
        try:
            if self._tx.is_alive():
                self._tx.join(timeout=0.3)
        except Exception:
            pass
        try:
            if self._rx.is_alive():
                self._rx.join(timeout=0.3)
        except Exception:
            pass
        try:
            self.ser.close()
        except Exception:
            pass

    # ---------------------------------------------------------------------
    # Envío (nombres compatibles)
    # ---------------------------------------------------------------------
    def send(self, msg: str) -> None:
        """Encola un mensaje para envío (no bloqueante)."""
        self.q_out.put(msg)

    # Alias para máxima compatibilidad con el GUI refactorizado y versiones previas:
    def enviar_a_arduino(self, msg: str) -> None:
        """Alias de send(); compatible con ventanas que llaman controlador.enviar_a_arduino()."""
        self.send(msg)

    def write(self, msg: str) -> None:
        """Alias de send(); por si alguna parte usaba write()."""
        self.send(msg)

    def enviar(self, msg: str) -> None:
        """Alias de send(); nombre genérico en español."""
        self.send(msg)

    # ---------------------------------------------------------------------
    # Recepción (helpers)
    # ---------------------------------------------------------------------
    def get(self, timeout: float | None = None) -> str | None:
        """
        Obtiene un mensaje recibido.
        - timeout=None -> bloquea hasta que haya dato.
        - timeout>0   -> espera hasta ese tiempo.
        - timeout=0   -> no bloquea, devuelve None si no hay dato.
        """
        try:
            if timeout is None:
                return self.q_in.get()  # bloqueante
            elif timeout == 0:
                return self.q_in.get_nowait()
            else:
                return self.q_in.get(timeout=timeout)
        except queue.Empty:
            return None

    def recv_nowait(self) -> list[str]:
        """
        Saca todos los mensajes actualmente en cola RX sin bloquear.
        Útil para sondear periódicamente desde el GUI con .after().
        """
        items: list[str] = []
        while True:
            try:
                items.append(self.q_in.get_nowait())
            except queue.Empty:
                break
        return items

    # ---------------------------------------------------------------------
    # Hilos internos
    # ---------------------------------------------------------------------
    def _writer(self) -> None:
        while not self._stop.is_set():
            try:
                msg = self.q_out.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                # Asegura newline; la app ya debe incluir $ y ! si su protocolo lo requiere.
                self.ser.write((msg + "\n").encode("utf-8"))
            except Exception as e:
                print("[TX ERROR]", e)

    def _reader(self) -> None:
        buf = ""
        start = self.start_char
        end = self.end_char

        while not self._stop.is_set():
            try:
                chunk = self.ser.read(256).decode("utf-8", errors="ignore")
                if not chunk:
                    continue
                buf += chunk

                # Extrae mensajes enmarcados por start...end
                while True:
                    i = buf.find(start)
                    if i == -1:
                        # No hay inicio -> descarta basura previa si crece demasiado
                        if len(buf) > 1024:
                            buf = ""
                        break
                    j = buf.find(end, i + 1)
                    if j == -1:
                        # No hay fin aún -> conserva desde el inicio detectado
                        if i > 0:
                            buf = buf[i:]
                        break

                    raw = buf[i:j + 1]   # incluye start/end
                    buf = buf[j + 1:]    # recorta buffer
                    self.q_in.put(raw)
            except Exception as e:
                print("[RX ERROR]", e)
                time.sleep(0.1)
