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
    - q_in:  mensajes recibidos del Arduino -> la UI los consume con .after()
    """

    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.1,
                 start_char: str = "$", end_char: str = "!"):
        if serial is None:
            raise RuntimeError(
                "pyserial no esta instalado. pip install pyserial")

        self.ser = serial.Serial(port, baudrate=baud, timeout=timeout)
        self.q_out = queue.Queue()
        self.q_in = queue.Queue()
        self._stop = threading.Event()
        self._tx = threading.Thread(target=self._writer, daemon=True)
        self._rx = threading.Thread(target=self._reader, daemon=True)
        self.start_char = start_char
        self.end_char = end_char

    def start(self):
        self._tx.start()
        self._rx.start()

    def stop(self):
        self._stop.set()
        try:
            self.ser.close()
        except Exception:
            pass

    def send(self, msg: str):
        """Llamar desde la UI para enviar un mensaje (sin bloquear)."""
        self.q_out.put(msg)

    # --- Hilos internos ---
    def _writer(self):
        while not self._stop.is_set():
            try:
                msg = self.q_out.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.ser.write((msg + "\n").encode("utf-8"))
            except Exception as e:
                print("[TX ERROR]", e)

    def _reader(self):
        buf = ""
        start = self.start_char
        end = self.end_char
        while not self._stop.is_set():
            try:
                chunk = self.ser.read(256).decode("utf-8", errors="ignore")
                if not chunk:
                    continue
                buf += chunk
                # extraer mensajes enmarcados por start...end
                while True:
                    i = buf.find(start)
                    if i == -1:
                        # no hay inicio, descartar basura previa
                        if len(buf) > 1024:
                            buf = ""
                        break
                    j = buf.find(end, i + 1)
                    if j == -1:
                        # no hay fin aun
                        # recortar basura al inicio si hubiera
                        if i > 0:
                            buf = buf[i:]
                        break
                    raw = buf[i:j+1]
                    buf = buf[j+1:]
                    self.q_in.put(raw)
            except Exception as e:
                print("[RX ERROR]", e)
                time.sleep(0.1)
