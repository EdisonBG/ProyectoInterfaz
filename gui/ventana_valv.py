import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox
from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico  # se mantiene por V3


class VentanaValv(tk.Frame):
    """
    Ventana de valvulas:
      - Valvula 1 (Entrada): botones Posicion A / Posicion B (mutuamente excluyentes)
      - Valvula 2 (Salida):  botones Posicion A / Posicion B (mutuamente excluyentes)
      - Valvula 3 (bypass/seguridad): manual + presion; mensaje separado
    Persistencia de posiciones (V1/V2) en valv_pos.csv
    Formato mensaje V1/V2 al presionar A/B: $;3;ID_VALVULA;POS;!
      ID_VALVULA: 1=Entrada, 2=Salida
      POS: 1=A, 2=B
    """

    def __init__(self, master, controlador, arduino, *args, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Ruta para CSV de posiciones
        self._pos_file = os.path.join(
            os.path.dirname(__file__), "valv_pos.csv")

        # Estado V1/V2: "A" o "B"
        self.v1_pos = tk.StringVar(value="A")  # Entrada
        self.v2_pos = tk.StringVar(value="A")  # Salida

        # Estado V3 (se mantiene)
        self.v3 = {
            "estado_manual": False,     # False=cerrada, True=abierta
            "presion_seguridad": None,  # umbral (float)
        }
        self.v3_estado = tk.BooleanVar(value=self.v3["estado_manual"])

        # Estilos para resaltar el boton seleccionado
        self._configurar_estilos()

        # UI
        self.crear_widgets()

        # Cargar posiciones guardadas y aplicarlas
        self._cargar_posiciones()
        self._aplicar_posiciones_iniciales()

    # ----------------- UI -----------------
    def _configurar_estilos(self):
        """Define estilos ttk para resaltar el boton seleccionado."""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("AB.TButton", padding=6)
        style.map(
            "AB.TButton",
            background=[("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")],
        )

        style.configure("ABSelected.TButton",
                        padding=6, background="#007acc", foreground="white")
        style.map(
            "ABSelected.TButton",
            background=[("!disabled", "#007acc"), ("pressed", "#0062a3")],
            foreground=[("!disabled", "white")]
        )

    def crear_widgets(self):
        # Layout raiz
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)  # barra
        self.grid_columnconfigure(1, weight=1)  # contenido

        # Barra de navegacion pegada al borde
        barra = BarraNavegacion(self, self.controlador)
        barra.configure(width=230)
        barra.grid(row=0, column=0, sticky="nsw")
        barra.grid_propagate(False)

        # Panel derecho
        panel = ttk.Frame(self)
        panel.grid(row=0, column=1, sticky="nsew", padx=(10, 10), pady=10)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        # ====== Valvula 1 (Entrada) ======
        sec_v1 = ttk.LabelFrame(panel, text="Valvula 1 (Entrada)")
        sec_v1.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        sec_v1.grid_columnconfigure(0, weight=1)
        self.btn_v1_a = ttk.Button(
            sec_v1, text="Posicion A", style="AB.TButton",
            command=lambda: self._seleccionar_posicion("v1", "A")
        )
        self.btn_v1_b = ttk.Button(
            sec_v1, text="Posicion B", style="AB.TButton",
            command=lambda: self._seleccionar_posicion("v1", "B")
        )
        self.btn_v1_a.grid(row=0, column=0, padx=6, pady=10, sticky="w")
        self.btn_v1_b.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        # ====== Valvula 2 (Salida) ======
        sec_v2 = ttk.LabelFrame(panel, text="Valvula 2 (Salida)")
        sec_v2.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        sec_v2.grid_columnconfigure(0, weight=1)
        self.btn_v2_a = ttk.Button(
            sec_v2, text="Posicion A", style="AB.TButton",
            command=lambda: self._seleccionar_posicion("v2", "A")
        )
        self.btn_v2_b = ttk.Button(
            sec_v2, text="Posicion B", style="AB.TButton",
            command=lambda: self._seleccionar_posicion("v2", "B")
        )
        self.btn_v2_a.grid(row=0, column=0, padx=6, pady=10, sticky="w")
        self.btn_v2_b.grid(row=0, column=1, padx=6, pady=10, sticky="w")

        # ====== Valvula 3 (bypass / seguridad) ======
        sec3 = ttk.LabelFrame(panel, text="Valvula 3 (bypass / seguridad)")
        sec3.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        sec3.grid_columnconfigure(0, weight=0)
        sec3.grid_columnconfigure(1, weight=1)

        self.btn_v3_manual = ttk.Button(
            sec3, text=self._texto_v3(), command=self._toggle_v3
        )
        self.btn_v3_manual.grid(
            row=0, column=0, columnspan=2, padx=5, pady=(8, 12), sticky="w")

        ttk.Label(sec3, text="Presion de seguridad (bar):").grid(
            row=1, column=0, padx=5, pady=5, sticky="e"
        )
        self.entry_p_seg = ttk.Entry(sec3, width=10)
        self.entry_p_seg.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.entry_p_seg.bind(
            "<Button-1>",
            lambda e: TecladoNumerico(
                self, self.entry_p_seg,
                on_submit=self._aplicar_presion_ui
            )
        )

        ttk.Button(sec3, text="Enviar (Valvula 3)", command=self._enviar_v3)\
            .grid(row=2, column=0, columnspan=2, padx=5, pady=(10, 6), sticky="w")

    # ----------------- Persistencia -----------------
    def _cargar_posiciones(self):
        """Lee valv_pos.csv si existe y coloca las posiciones guardadas en v1_pos/v2_pos."""
        if not os.path.exists(self._pos_file):
            return
        try:
            with open(self._pos_file, newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) != 2:
                        continue
                    nombre, pos = row[0].strip(), row[1].strip().upper()
                    if nombre == "V1" and pos in ("A", "B"):
                        self.v1_pos.set(pos)
                    elif nombre == "V2" and pos in ("A", "B"):
                        self.v2_pos.set(pos)
        except Exception as e:
            print(f"[WARN] No se pudo leer {self._pos_file}: {e}")

    def _guardar_posiciones(self):
        """Escribe las posiciones actuales en valv_pos.csv."""
        try:
            with open(self._pos_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["V1", self.v1_pos.get()])
                writer.writerow(["V2", self.v2_pos.get()])
        except Exception as e:
            print(f"[WARN] No se pudo escribir {self._pos_file}: {e}")

    def _aplicar_posiciones_iniciales(self):
        """Aplica estilos a los botones segun v1_pos/v2_pos leidos del archivo."""
        self._refrescar_botones("v1")
        self._refrescar_botones("v2")

    # ----------------- Helpers UI -----------------
    def _aplicar_presion_ui(self, valor):
        try:
            p = float(valor)
        except Exception:
            # si no es numero, no tocar el entry aqui; el envio lo bloqueara
            return
        if p > 25:
            p = 25.0
        # reflejar
        self.entry_p_seg.delete(0, tk.END)
        self.entry_p_seg.insert(0, str(int(p)) if p.is_integer() else str(p))
        # actualizar modelo
        self.v3["presion_seguridad"] = p

    def _refrescar_botones(self, cual: str):
        """Actualiza el estilo de los botones A/B para la valvula indicada."""
        if cual == "v1":
            sel = self.v1_pos.get()
            self.btn_v1_a.configure(
                style="ABSelected.TButton" if sel == "A" else "AB.TButton")
            self.btn_v1_b.configure(
                style="ABSelected.TButton" if sel == "B" else "AB.TButton")
        elif cual == "v2":
            sel = self.v2_pos.get()
            self.btn_v2_a.configure(
                style="ABSelected.TButton" if sel == "A" else "AB.TButton")
            self.btn_v2_b.configure(
                style="ABSelected.TButton" if sel == "B" else "AB.TButton")

    def _texto_v3(self) -> str:
        return "Cerrar valvula 3" if self.v3_estado.get() else "Abrir valvula 3"

    def _leer_presion_validada(self, max_bar=25.0):
        """
        Lee la presion desde entry (si hay), si no desde el modelo, si no usa el default 25.
        - Si no es numerica -> muestra error y retorna (False, None, None).
        - Si es numerica y > max_bar -> se capa a max_bar.
        - Actualiza el Entry para reflejar el valor final (capado o default).
        - Actualiza self.v3["presion_seguridad"] con el valor final.
        - Devuelve (True, presion_escalada_str, presion_float_final).
        presion_escalada_str = int(round(p_final * 10)) como string.
        """
        # 1) Origen del texto: entry -> modelo -> default (25)
        txt_entry = self.entry_p_seg.get().strip()
        if txt_entry:
            origen = txt_entry
        else:
            pres_modelo = self.v3.get("presion_seguridad")
            if pres_modelo is not None:
                origen = str(pres_modelo)
            else:
                origen = "25"  # default

        # 2) Intentar convertir
        try:
            p = float(origen)
        except Exception:
            from tkinter import messagebox
            messagebox.showerror("Error de presion",
                                 "Valor de presion invalido.")
            return False, None, None

        # 3) Capar a max_bar si excede
        if p > max_bar:
            print(f"[INFO] Presion {p} > {max_bar}; se usa {max_bar}")
            p = max_bar

        # 4) Reflejar el valor final en el Entry (sin .0 si es entero)
        self.entry_p_seg.delete(0, tk.END)
        self.entry_p_seg.insert(
            0, str(int(p)) if float(p).is_integer() else str(p))

        # 5) Guardar en el modelo el valor final
        self.v3["presion_seguridad"] = p

        # 6) Escalar x10 para enviar
        presion_int10 = int(round(p * 10))
        return True, str(presion_int10), p

    # ----------------- Callbacks -----------------
    def _seleccionar_posicion(self, cual: str, pos: str):
        """
        Click en A/B para V1 o V2:
          - Actualiza variable (A/B)
          - Refresca estilo de botones
          - Persiste en CSV
          - Construye y envia: $;3;ID_VALVULA;POS;!
            ID_VALVULA: 1=Entrada (V1), 2=Salida (V2)
            POS: 1=A, 2=B
        """
        if pos not in ("A", "B"):
            return

        if cual == "v1":
            self.v1_pos.set(pos)
            self._refrescar_botones("v1")
            id_valvula = "1"
        elif cual == "v2":
            self.v2_pos.set(pos)
            self._refrescar_botones("v2")
            id_valvula = "2"
        else:
            return

        # Guardar posiciones
        self._guardar_posiciones()

        # Construir y enviar mensaje
        pos_code = "1" if pos == "A" else "2"
        mensaje = f"$;3;{id_valvula};{pos_code};!"
        print(f"Mensaje {cual.upper()} ->", mensaje)
        self.controlador.enviar_a_arduino(mensaje)

    def _guardar_v3(self, clave: str, valor: float):
        self.v3[clave] = valor
        print(f"Valvula 3 {clave} -> {valor}")

    def _toggle_v3(self):
        """
        Cambia el estado manual de la valvula 3 solo si la presion es numerica.
        Si no es numerica -> no cambia ni envia.
        Si es numerica y >25 -> se capa a 25 y se envia esa (x10).
        """
        ok, _, _ = self._leer_presion_validada(max_bar=25.0)
        if not ok:
            return  # no cambiar estado ni enviar

        nuevo = not self.v3_estado.get()
        self.v3_estado.set(nuevo)
        self.v3["estado_manual"] = nuevo
        self.btn_v3_manual.configure(text=self._texto_v3())
        print(f"Valvula 3 estado_manual -> {nuevo}")
        self._enviar_v3()

    # ----------------- Envio V3 -----------------
    def _fmt_num(self, v):
        if v is None:
            return None
        try:
            if float(v).is_integer():
                return str(int(float(v)))
            return str(float(v))
        except Exception:
            return None

    def _enviar_v3(self):
        """
        $;3;2;ESTADO;PRESION;!
        - ESTADO: 1 abre, 0 cierra
        - PRESION: bar * 10 como entero; si >25 se capa a 25 (=> 250)
        """
        ok, presion_str, _ = self._leer_presion_validada(max_bar=25.0)
        if not ok:
            return  # no enviar

        estado_num = "1" if self.v3_estado.get() else "0"
        cmd_id = "3"
        grupo = "2"
        mensaje = f"$;{cmd_id};{grupo};{estado_num};{presion_str};!"
        print("Mensaje Valvula 3:", mensaje)
        self.controlador.enviar_a_arduino(mensaje)
