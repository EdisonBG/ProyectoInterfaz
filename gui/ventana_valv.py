import os
import csv
import tkinter as tk
from tkinter import ttk , messagebox
from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico
from ui.widgets import TouchButton, TouchEntry, LabeledEntryNum

# Constantes táctiles (anchos/fuentes). Si no existen, usa valores por defecto.
try:
    from ui import constants as C
except Exception:
    class _C_:
        FONT_BASE = ("Calibri", 14)
        ENTRY_WIDTH = 12
        COMBO_WIDTH = 12
    C = _C_()

# --- Título movible por píxeles y con fuente configurable (solo en modo absoluto) ---
# Posición del "título" dibujado manualmente dentro de cada sección (x, y).
TITLE_POS = {
    1: (8, 2),
    2: (8, 2),
    3: (8, 2),
    4: (8, 2),
}
# Fuente (familia, tamaño, estilo) por sección para el título.
TITLE_FONT = {
    "v1": ("Calibri", 14, "bold"),
    "v2": ("Calibri", 14, "bold"),
    "con": ("Calibri", 14, "bold"),
    "bp": ("Calibri", 14, "bold"),
    "sol": ("Calibri", 14, "bold"),
    "per": ("Calibri", 14, "bold"),
}

# Coordenadas por FRAME (horizontal, vertical) para cada ELEMENTO dentro del mismo.
POS = {
    "v1": {
        "btn_v1_a":   (52, 80),
        "btn_v1_b": (225,  80), 
    },
    "v2": {
        "btn_v2_a":   (52, 80),
        "btn_v2_b": (225,  80),    
    },
    "con": {
        # Sección vacía - solo se mantiene el frame
    },
    "bp": {
        # Sección vacía - solo se mantiene el frame
    },
    "sol": {
        "campo_presion_seguridad": (5,  38), 
        "presion_manual_lbl": (150,  88), 
        "btn_sol_toggle":   (10, 123),    
        "btn_sol2_toggle":  (215, 123),   
    },
    "per": {
        "campo_presion_limite": (5, 40),      # Movido a sección per
        "btn_enviar_presiones": (150, 100),    # Movido a sección per
    },
}

class VentanaValv(tk.Frame):
    """
    Ventana de válvulas y bombas (optimizada para 1024x600):

    - Válvula 1 (Entrada)  : A/B (mutuamente excluyentes)
    - Válvula 2 (Salida)   : A/B (mutuamente excluyentes)
      Mensaje normal: $;3;{1|2};1;{1|2};!

    - Conexión equipo 2 (toggle):
      * Al activar: deshabilita Válvula 2; Válvula 1 pasa a $;3;1;8;{1|2};!
        y se envía una vez $;3;0;8;!

    - Bypass (reemplaza Motor 1/2):
      * Toggle entre Bypass 1 ↔ Bypass 2
      * Mensaje: $;3;3;1;{1|2};!   (1=Bypass 1, 2=Bypass 2)
      * Persiste en valv_pos.csv con clave BYP=1|2
      * No se reenvía si no hay cambio

    - Solenoide 1 (ID 5):
      * Manual: $;3;5;1;{1|2};P;!
      * Auto al editar presión: $;3;5;0;P;!   (P=bar*10, máx 20.0)

    - Solenoide 2 (ID 8):
      * Manual: $;3;8;1;{1|2};P;!
      * Usa la misma presión que Solenoide 1

    Persistencia: V1/V2/BYP en valv_pos.csv (formato clave,valor)
    """

    # ------------- init -------------
    def __init__(self, master, controlador, arduino, *args, **kwargs):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Archivo persistencia (CSV sencillo)
        self._pos_file = os.path.join(os.path.dirname(__file__), "valv_pos.csv")

        # Estados V1/V2 (persisten)
        self.v1_pos = tk.StringVar(value="A")
        self.v2_pos = tk.StringVar(value="A")

        # Conexión equipo 2
        self.conexion_equipo2 = tk.BooleanVar(value=False)

        # Solenoide 1
        self.sol_abierta = tk.BooleanVar(value=False)
        self.sol_presion = 20.0  # bar

        # Solenoide 2 - Misma presion que Solenoide 1
        self.sol2_abierta = tk.BooleanVar(value=False)
        
        # Nueva variable para presión límite
        self.sol_presion_limite = 20.0  # bar

        # Bypass (1 o 2) – ahora también persiste (clave BYP)
        self.bypass_sel = tk.IntVar(value=1)  # 1=Bypass 1, 2=Bypass 2

        # Estilos / UI
        self._configurar_estilos()
        self._build_ui()

        # Cargar y reflejar V1/V2/BYP guardadas
        self._cargar_posiciones()
        self._refrescar_botones("v1")
        self._refrescar_botones("v2")

        # --- Notificar estado inicial de las flechas ---
        self._notificar_estado_actual_flechas()

        # para que barra_navegacion pueda acceder a esta instancia
        if hasattr(self.controlador, '_ventana_valv'):
            print("[DEBUG] VentanaValv ya existe en controlador")
        else:
            self.controlador._ventana_valv = self

    # ------------- Estilos -------------
    def _configurar_estilos(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("AB.TButton", padding=(16, 8), font=getattr(C, "FONT_BASE", ("Calibri", 16)))
        style.map("AB.TButton", background=[("!disabled", "#e6e6e6"), ("pressed", "#d0d0d0")])

        style.configure("ABSelected.TButton", padding=(16, 8), font=getattr(C, "FONT_BASE", ("Calibri", 16)), background="#bdbdbd")
        style.map("ABSelected.TButton",background=[("!disabled", "#bdbdbd"), ("pressed", "#9e9e9e")])
        
        RUN_COLOR = "#27ae60"
        STOP_COLOR = "#db4231"
        #boton de abrir/cerrar
        style.configure("AbrirBtn.TButton", padding=(12, 8), font=getattr(C, "FONT_BASE", ("Calibri", 16)))
        style.map("AbrirBtn.TButton", background=[("!disabled", RUN_COLOR), ("active", RUN_COLOR), ("pressed", RUN_COLOR)])
        style.configure("CerrarBtn.TButton", padding=(12, 8), font=getattr(C, "FONT_BASE", ("Calibri", 16)))
        style.map("CerrarBtn.TButton", background=[("!disabled", STOP_COLOR), ("active", STOP_COLOR), ("pressed", STOP_COLOR)])

    # ------------- UI -------------
    def _build_ui(self):
        # Layout raíz: barra izq + contenido der
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=140)
        self.grid_columnconfigure(1, weight=1)

        # Barra navegación
        barra = BarraNavegacion(self, self.controlador)
        barra.grid(row=0, column=0, sticky="nsw")

        # Contenedor derecho
        cont = ttk.Frame(self)
        cont.grid(row=0, column=1, sticky="nsew")  # sin padding para aprovechar ancho

        # Rejilla 2×3 para "tarjetas"
        for c in (0, 1):
            cont.grid_columnconfigure(c, weight=1, uniform="cols")
        for r in range(3):
            cont.grid_rowconfigure(r, weight=1, uniform="rows")

        # Definición de secciones (2 columnas × 3 filas)
        secciones = [
            ("v1", "Válvula de 4 vías 1 (Entrada)"),
            ("v2", "Válvula de 4 vías 2 (Salida)"),
            ("con", ""),
            ("bp",  ""),
            ("sol", "Control Backpressure"),
            ("per", "Presión Límite"),
        ]

        for idx, (sec_id, titulo) in enumerate(secciones, start=1):
            fila = (idx - 1) // 2
            col = (idx - 1) % 2
            frame = self._crear_seccion_valv(cont, sec_id, titulo)
            frame.grid(row=fila, column=col, padx=6, pady=6, sticky="nsew")

        # Estado inicial que ya tenías
        self._aplicar_estado_conexion()

    def _crear_seccion_valv(self, parent, sec_id: str, titulo: str) -> ttk.LabelFrame:
        """Crea una sección (tarjeta) según el identificador sec_id."""
        # Padding interno coherente con tu versión original

        frame = ttk.Frame(parent, borderwidth=2, relief="groove")
        title_lbl = ttk.Label(frame, text=titulo, font=TITLE_FONT.get(sec_id, ("Calibri", 20, "bold")))
        title_x, title_y = TITLE_POS.get(sec_id, (10, 8))
        title_lbl.place(x=title_x, y=title_y)

        if sec_id == "v1":
            # --- Tarjeta: Válvula 1 (Entrada) ---
            self.btn_v1_a = TouchButton(frame, text="Posición A", style="AB.TButton", command=lambda: self._seleccionar_posicion("v1", "A"))
            self.btn_v1_a.place(x=POS[sec_id]["btn_v1_a"][0], y=POS[sec_id]["btn_v1_a"][1])
        
            self.btn_v1_b = TouchButton(frame, text="Posición B", style="AB.TButton", command=lambda: self._seleccionar_posicion("v1", "B"))
            self.btn_v1_b.place(x=POS[sec_id]["btn_v1_b"][0], y=POS[sec_id]["btn_v1_b"][1])

        elif sec_id == "v2":
            # --- Tarjeta: Válvula 2 (Salida) ---
            self.btn_v2_a = TouchButton(frame, text="Posición A", style="AB.TButton", command=lambda: self._seleccionar_posicion("v2", "A"))
            self.btn_v2_a.place(x=POS[sec_id]["btn_v2_a"][0], y=POS[sec_id]["btn_v2_a"][1])
        
            self.btn_v2_b = TouchButton(frame, text="Posición B", style="AB.TButton", command=lambda: self._seleccionar_posicion("v2", "B"))
            self.btn_v2_b.place(x=POS[sec_id]["btn_v2_b"][0], y=POS[sec_id]["btn_v2_b"][1])

        elif sec_id == "con":
            # --- Tarjeta: Conexión equipo 2 ---
            # Sección vacía - solo título
            pass

        elif sec_id == "bp":
            # --- Tarjeta: Bypass ---
            # Sección vacía - solo título
            pass

        elif sec_id == "sol":
            # --- Tarjeta: Solenoide (seguridad) ---
            # Solenoide 1
            initial_style = "CerrarBtn.TButton" if self.sol_abierta.get() else "AbrirBtn.TButton"
            self.btn_sol_toggle = TouchButton(frame, text=self._texto_sol(), style=initial_style, command=self._toggle_sol)
            self.btn_sol_toggle.place(x=POS[sec_id]["btn_sol_toggle"][0], y=POS[sec_id]["btn_sol_toggle"][1])
            
            # Solenoide 2
            initial_style2 = "CerrarBtn.TButton" if self.sol2_abierta.get() else "AbrirBtn.TButton"
            self.btn_sol2_toggle = TouchButton(frame, text=self._texto_sol2(), style=initial_style2, command=self._toggle_sol2)
            self.btn_sol2_toggle.place(x=POS[sec_id]["btn_sol2_toggle"][0], y=POS[sec_id]["btn_sol2_toggle"][1])
            
            presion_manual_lbl = ttk.Label(frame, text="Modo manual", font=getattr(C, "FONT_BASE", ("Calibri", 14)))
            presion_manual_lbl.place(x=POS[sec_id]["presion_manual_lbl"][0], y=POS[sec_id]["presion_manual_lbl"][1])

            # Presion de seguridad (maximo 20.0bar) - AHORA SIN ENVÍO AUTOMÁTICO
            campo_presion_seguridad = LabeledEntryNum(frame, "Presión deseada (bar):",
            width=18,
            label_font=getattr(C, "FONT_BASE", ("Calibri", 14)),
            entry_ipady=7,
            )
        
            campo_presion_seguridad.place(x=POS[sec_id]["campo_presion_seguridad"][0], y=POS[sec_id]["campo_presion_seguridad"][1])
            self.entry_p_seg = campo_presion_seguridad.entry
            # Solo actualiza el valor, no envía
            campo_presion_seguridad.bind_numeric(
                lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
                on_submit=lambda v: self._actualizar_presion_seguridad(v),
            )

        elif sec_id == "per":
            # --- Tarjeta: Presión Límite ---
            # Campo para presión límite en sección per
            campo_presion_limite = LabeledEntryNum(frame, "Presión límite (bar):",
            width=18,
            label_font=getattr(C, "FONT_BASE", ("Calibri", 14)),
            entry_ipady=7,
            )
        
            campo_presion_limite.place(x=POS[sec_id]["campo_presion_limite"][0], y=POS[sec_id]["campo_presion_limite"][1])
            self.entry_p_lim = campo_presion_limite.entry
            campo_presion_limite.bind_numeric(
                lambda entry, on_submit: TecladoNumerico(self, entry, on_submit=on_submit),
                on_submit=lambda v: self._actualizar_presion_limite(v),
            )

            # Botón para enviar ambas presiones en sección per
            self.btn_enviar_presiones = TouchButton(frame, text="Enviar", style="AB.TButton", command=self._enviar_presiones)
            self.btn_enviar_presiones.place(x=POS[sec_id]["btn_enviar_presiones"][0], y=POS[sec_id]["btn_enviar_presiones"][1])

        return frame

    # ------------- Persistencia V1/V2/BYP -------------
    def _cargar_posiciones(self):
        if not os.path.exists(self._pos_file):
            return
        try:
            with open(self._pos_file, newline="", encoding="utf-8") as f:
                for nombre, pos in csv.reader(f):
                    key = (nombre or "").strip().upper()
                    val = (pos or "").strip().upper()
                    if key == "V1" and val in ("A", "B"):
                        self.v1_pos.set(val)
                    elif key == "V2" and val in ("A", "B"):
                        self.v2_pos.set(val)
                    elif key == "BYP" and val in ("1", "2"):
                        try:
                            self.bypass_sel.set(int(val))
                        except Exception:
                            self.bypass_sel.set(1)

            # --- Notificar después de cargar las posiciones ---
            self._notificar_estado_actual_flechas()

        except Exception as e:
            print(f"[WARN] No se pudo leer {self._pos_file}: {e}")

    def _guardar_posiciones(self):
        try:
            with open(self._pos_file, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["V1", self.v1_pos.get()])
                w.writerow(["V2", self.v2_pos.get()])
                w.writerow(["BYP", str(self.bypass_sel.get())])
        except Exception as e:
            print(f"[WARN] No se pudo escribir {self._pos_file}: {e}")

    def actualizar_desde_csv(self):
        """Función simple que actualiza TODO desde el CSV"""
        self._cargar_posiciones()
        self._refrescar_botones("v1")
        self._refrescar_botones("v2")

    # --- Para la visualización del sentido de flujo segun las V4vias -----
    def _notificar_estado_actual_flechas(self):
        """
        Notifica el estado actual de las válvulas para actualizar las flechas
        Se llama después de cargar las posiciones desde el CSV
        """
        if hasattr(self.controlador, 'notificar_cambio_flecha_valvula'):
            # Notificar el estado ACTUAL (que puede ser A o B según el CSV)
            self.controlador.notificar_cambio_flecha_valvula(1, self.v1_pos.get())
            self.controlador.notificar_cambio_flecha_valvula(2, self.v2_pos.get())

    # ------------- Helpers UI -------------
    def _refrescar_botones(self, cual: str):
        if cual == "v1":
            sel = self.v1_pos.get()
            self.btn_v1_a.configure(style="ABSelected.TButton" if sel == "A" else "AB.TButton")
            self.btn_v1_b.configure(style="ABSelected.TButton" if sel == "B" else "AB.TButton")
        elif cual == "v2":
            sel = self.v2_pos.get()
            self.btn_v2_a.configure(style="ABSelected.TButton" if sel == "A" else "AB.TButton")
            self.btn_v2_b.configure(style="ABSelected.TButton" if sel == "B" else "AB.TButton")

    def _texto_sol(self) -> str:
        txt = "Cerrar válvula 1" if self.sol_abierta.get() else "Abrir válvula 1"
        # Estilo según el texto (se aplica al final del ciclo actual)
        try:
            style = "AbrirBtn.TButton" if txt == "Abrir válvula 1" else "CerrarBtn.TButton"
            self.after(0, lambda: self.btn_sol_toggle.configure(style=style))
        except Exception:
            pass
        return txt

    # NUEVA FUNCIÓN para el texto del botón solenoide 2
    def _texto_sol2(self) -> str:
        txt = "Cerrar válvula 2" if self.sol2_abierta.get() else "Abrir válvula 2"
        # Estilo según el texto (se aplica al final del ciclo actual)
        try:
            style = "AbrirBtn.TButton" if txt == "Abrir válvula 2" else "CerrarBtn.TButton"
            self.after(0, lambda: self.btn_sol2_toggle.configure(style=style))
        except Exception:
            pass
        return txt

    # ------------- Handlers V1/V2 -------------
    def _seleccionar_posicion(self, cual: str, pos: str):
        if pos not in ("A", "B"):
            return
        pos_code = "1" if pos == "A" else "2"

        if cual == "v1":
            if self.v1_pos.get() == pos:
                self._refrescar_botones("v1")
                return
            self.v1_pos.set(pos)
            self._refrescar_botones("v1")
            mensaje = f"$;3;1;8;{pos_code};!" if self.conexion_equipo2.get() else f"$;3;1;1;{pos_code};!"
            self._guardar_posiciones()

            # --- Notificar cambio de flecha para válvula 1 ---
            if hasattr(self.controlador, 'notificar_cambio_flecha_valvula'):
                self.controlador.notificar_cambio_flecha_valvula(1, pos)

        elif cual == "v2":
            if self.conexion_equipo2.get():
                return  # V2 deshabilitada
            if self.v2_pos.get() == pos:
                self._refrescar_botones("v2")
                return
            self.v2_pos.set(pos)
            self._refrescar_botones("v2")
            mensaje = f"$;3;2;1;{pos_code};!"
            self._guardar_posiciones()

            # --- Notificar cambio de flecha para válvula 2 ---
            if hasattr(self.controlador, 'notificar_cambio_flecha_valvula'):
                self.controlador.notificar_cambio_flecha_valvula(2, pos)
        else:
            return

        print("[TX]", mensaje)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(mensaje)

    # ------------- Conexión equipo 2 -------------
    def _toggle_conexion(self):
        nuevo = not self.conexion_equipo2.get()
        self.conexion_equipo2.set(nuevo)

        if nuevo:
            # 1. Al activar conexión: ambas válvulas en posición A
            self.v1_pos.set("A")
            self.v2_pos.set("A")
            self._refrescar_botones("v1")
            self._refrescar_botones("v2")
            # --- Notificar cambio de flechas para ambas válvulas ---
            if hasattr(self.controlador, 'notificar_cambio_flecha_valvula'):
                self.controlador.notificar_cambio_flecha_valvula(1, "A")
                self.controlador.notificar_cambio_flecha_valvula(2, "A")

            self.controlador.set_equipo2_conectado(True)  # equipo 2 conectado
        else:
            # 2. Al desactivar conexión: v2 queda en la misma posición que v1
            self.v2_pos.set(self.v1_pos.get())
            self._refrescar_botones("v2")
            # --- Notificar cambio de flecha para válvula 2 ---
            if hasattr(self.controlador, 'notificar_cambio_flecha_valvula'):
                self.controlador.notificar_cambio_flecha_valvula(2, self.v1_pos.get())
            
            self.controlador.set_equipo2_conectado(False)  #equipo 2 desconectado

        self._guardar_posiciones()
        
        self._aplicar_estado_conexion()
        if nuevo:
            msg = "$;3;0;8;!"
            print("[TX] Conexión equipo 2 ACTIVADA:", msg)
            if hasattr(self.controlador, "enviar_a_arduino"):
                self.controlador.enviar_a_arduino(msg)

    def _aplicar_estado_conexion(self):
        on = self.conexion_equipo2.get()
        state_v2 = ("disabled" if on else "normal")
        self.btn_v2_a.configure(state=state_v2)
        self.btn_v2_b.configure(state=state_v2)
        self.btn_v1_a.configure(state="normal")
        self.btn_v1_b.configure(state="normal")

    # ------------- Nuevas funciones para manejar presiones -------------
    def _actualizar_presion_seguridad(self, valor):
        """Actualiza solo el campo de entrada, NO la variable interna"""
        p = self._leer_presion_float_capada(valor, es_presion_deseada=True)
        
        # NUEVA LÓGICA: Ajustar si la presión de seguridad es mayor que la límite
        # Solo si la presión límite es mayor que 0 (ya se ingresó un valor)
        if self.sol_presion_limite > 0 and p > self.sol_presion_limite:
            p = max(0, self.sol_presion_limite - 2.0)  # 2 bar por debajo, mínimo 0
        
        # Solo actualiza la interfaz, no la variable interna
        self.entry_p_seg.delete(0, tk.END)
        self.entry_p_seg.insert(0, f"{p:.1f}")

    def _actualizar_presion_limite(self, valor):
        """Actualiza la presión límite sin enviar automáticamente"""
        p = self._leer_presion_float_capada(valor, es_presion_deseada=False)
    
        # Solo actualiza la interfaz, no la variable interna
        self.entry_p_lim.delete(0, tk.END)
        self.entry_p_lim.insert(0, f"{p:.1f}")

    def _enviar_presiones(self):
        """Envía ambas presiones (seguridad y límite) al Arduino en un solo mensaje"""
        
        # NUEVA LÓGICA: Verificar qué campos están completos
        tiene_p_seg = bool(self.entry_p_seg.get())
        tiene_p_lim = bool(self.entry_p_lim.get())
        
        # Caso 1: Solo tiene presión límite -> ajustar presión deseada automáticamente
        if tiene_p_lim and not tiene_p_seg:
            p_lim = self._leer_presion_float_capada(self.entry_p_lim.get(), es_presion_deseada=False)
            p_seg = max(0, p_lim - 2.0)
            
            # Asegurar que la presión deseada no exceda 20 bar
            if p_seg > 20.0:
                p_seg = 20.0
                
            # Actualizar la interfaz
            self.entry_p_seg.delete(0, tk.END)
            self.entry_p_seg.insert(0, f"{p_seg:.1f}")
            
            # Ambas presiones están listas, continuar...
            tiene_p_seg = True
        
        # Caso 2: Solo tiene presión deseada -> mostrar error
        elif tiene_p_seg and not tiene_p_lim:
            messagebox.showerror("Error", "Es necesario ingresar ambas presiones")
            return
        
        # Caso 3: Ninguna presión ingresada -> mostrar error
        elif not tiene_p_seg and not tiene_p_lim:
            messagebox.showerror("Error", "Es necesario ingresar ambas presiones")
            return
        
        # Si llegamos aquí, ambas presiones están disponibles
        p_seg = self._leer_presion_float_capada(self.entry_p_seg.get(), es_presion_deseada=True)
        p_lim = self._leer_presion_float_capada(self.entry_p_lim.get(), es_presion_deseada=False)
        
        # Aplicar lógica de ajuste si es necesario
        if p_seg > p_lim:
            p_seg = max(0, p_lim - 2.0)
            # Actualizar también la entrada visual
            self.entry_p_seg.delete(0, tk.END)
            self.entry_p_seg.insert(0, f"{p_seg:.1f}")

        # Convertir a decibares
        p10_seg = int(round(p_seg * 10))
        p10_lim = int(round(p_lim * 10))

        # Enviar mensaje
        msg = f"$;3;5;0;{p10_seg};{p10_lim};!"
        print("[TX] Presiones (seguridad y límite):", msg)

        if hasattr(self.controlador, "enviar_a_arduino"):
            # SOLO ACTUALIZAMOS LAS VARIABLES INTERNAS SI EL ENVÍO ES EXITOSO
            try:
                self.controlador.enviar_a_arduino(msg)
                
                # AHORA SÍ ACTUALIZAMOS LAS VARIABLES INTERNAS
                self.sol_presion = p_seg
                self.sol_presion_limite = p_lim
                
                # Activar modo automático en la UI
                self._activar_control_presion_automatico(True)
                # Resetear botones de solenoides
                self._resetear_botones_solenoides()
                
            except Exception as e:
                messagebox.showerror("Error de comunicación", 
                                f"No se pudo enviar al Arduino: {str(e)}")

    # ------------- Solenoide (ID 5) -------------
    def _leer_presion_float_capada(self, v, es_presion_deseada=False) -> float:
        try:
            s = "20" if v is None else str(v).strip() or "20"
            p = float(s)
        except Exception:
            p = 20.0
        
        # Diferentes límites según el tipo de presión
        if es_presion_deseada:
            # Presión deseada: máximo 20.0 bar
            if p > 20.0:
                p = 20.0
        else:
            # Presión límite: máximo 24.0 bar
            if p > 24.0:
                p = 24.0
        
        return round(p, 1)


    def _resetear_botones_solenoides(self):
        """
        Resetea los botones de los solenoides a su estado inicial:
        - Texto: "Abrir válvula 1" y "Abrir válvula 2"
        - Estilo: verde (AbrirBtn.TButton)
        - Estado interno: False (cerradas)
        """
        # Resetear estado interno
        self.sol_abierta.set(False)
        self.sol2_abierta.set(False)
        
        # Actualizar textos y estilos de los botones
        self.btn_sol_toggle.configure(text="Abrir válvula 1", style="AbrirBtn.TButton")
        self.btn_sol2_toggle.configure(text="Abrir válvula 2", style="AbrirBtn.TButton")
        
    def _activar_control_presion_automatico(self, activar: bool):
        """
        Activa o desactiva el modo automático de control de presión
        y notifica a los indicadores
        """
        if activar:
            # --- Al activar modo automático, resetear botones ---
            self._resetear_botones_solenoides()

        if hasattr(self.controlador, 'notificar_cambio_estado_valvula'):
            # En modo automático, forzamos el estado a True para que se muestre AMARILLO
            # En modo manual, usamos el estado real de las válvulas
            estado_a_mostrar_sol1 = True if activar else self.sol_abierta.get()
            estado_a_mostrar_sol2 = True if activar else self.sol2_abierta.get()
            
            self.controlador.notificar_cambio_estado_valvula(
                "sol1", 
                estado_a_mostrar_sol1, 
                activar  # modo_auto = True cuando está en control automático
            )
            self.controlador.notificar_cambio_estado_valvula(
                "sol2", 
                estado_a_mostrar_sol2, 
                activar  # modo_auto = True cuando está en control automático
            )

    def _toggle_sol(self):
        # Leer directamente de los campos de entrada
        p_seg = self._leer_presion_float_capada(self.entry_p_seg.get(), es_presion_deseada=True)
        
        # Si no hay presión límite configurada en el campo, usar 24.0
        p_lim = self._leer_presion_float_capada(self.entry_p_lim.get(), es_presion_deseada=False)
        if not self.entry_p_lim.get() or p_lim == 0:
            p_lim = 24.0
            self.entry_p_lim.delete(0, tk.END)
            self.entry_p_lim.insert(0, "24.0")
        
        nuevo = not self.sol_abierta.get()
        self.sol_abierta.set(nuevo)
        self.btn_sol_toggle.configure(text=self._texto_sol())
        estado = "1" if nuevo else "2"
        p10 = int(round(p_seg * 10))
        p10_lim = int(round(self.sol_presion_limite * 10))  # Convertir límite a decibares
        
        # MODIFICADO: Incluir la presión límite en el mensaje
        msg = f"$;3;5;1;{estado};{p10};{p10_lim};!"
        print("[TX]", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
            
        self._activar_control_presion_automatico(False)

        # --- Notificar cambio de estado del solenoide 1 ---
        if hasattr(self.controlador, 'notificar_cambio_estado_valvula'):
            self.controlador.notificar_cambio_estado_valvula("sol1", nuevo, False)

    def _toggle_sol2(self):
        # Leer directamente de los campos de entrada
        p_seg = self._leer_presion_float_capada(self.entry_p_seg.get(), es_presion_deseada=True)
        
        # Si no hay presión límite configurada en el campo, usar 24.0
        p_lim = self._leer_presion_float_capada(self.entry_p_lim.get(), es_presion_deseada=False)
        if not self.entry_p_lim.get() or p_lim == 0:
            p_lim = 24.0
            self.entry_p_lim.delete(0, tk.END)
            self.entry_p_lim.insert(0, "24.0")
        
        nuevo = not self.sol2_abierta.get()
        self.sol2_abierta.set(nuevo)
        self.btn_sol2_toggle.configure(text=self._texto_sol2())
        estado = "1" if nuevo else "2"
        p10 = int(round(p_seg * 10))
        p10_lim = int(round(self.sol_presion_limite * 10))  # Convertir límite a decibares
        
        # MODIFICADO: Incluir la presión límite en el mensaje
        msg = f"$;3;8;1;{estado};{p10};{p10_lim};!"
        print("[TX]", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)

        self._activar_control_presion_automatico(False)

        # --- Notificar cambio de estado del solenoide 2 ---
        if hasattr(self.controlador, 'notificar_cambio_estado_valvula'):
            self.controlador.notificar_cambio_estado_valvula("sol2", nuevo, False)

    # ------------- Bypass (CMD 3; Valvs motor; manual; 1/2) -------------
    def _toggle_bypass(self):
        nuevo = 2 if self.bypass_sel.get() == 1 else 1
        if nuevo == self.bypass_sel.get():
            return  # sin cambio
        self.bypass_sel.set(nuevo)

        # Persistir BYP junto con V1/V2
        self._guardar_posiciones()

        mfc_win = getattr(self.controlador, "_ventana_mfc", None)
        if mfc_win is not None and hasattr(mfc_win, "_reload_bypass_and_refresh"):
            mfc_win._reload_bypass_and_refresh()

        # Enviar sólo si cambió
        msg = f"$;3;3;1;{nuevo};!"
        print("[TX] Bypass ->", msg)
        if hasattr(self.controlador, "enviar_a_arduino"):
            self.controlador.enviar_a_arduino(msg)
