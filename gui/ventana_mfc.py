import tkinter as tk
from tkinter import ttk, messagebox
from .barra_navegacion import BarraNavegacion
from .teclado_numerico import TecladoNumerico


class VentanaMfc(tk.Frame):
    def __init__(self, master, controlador, arduino):
        super().__init__(master)
        self.controlador = controlador
        self.arduino = arduino

        # Estructura de almacenamiento:
        # self.valores[id_mfc] = {"flujo": float, "factor": float(opcional)}
        # id_mfc: 1=O2, 2=CO2, 3=N2, 4=H2
        self.valores = {i: {} for i in range(1, 5)}

        self.crear_widgets()

    def crear_widgets(self):
        # Layout raiz: barra izquierda fija y panel derecho expansible
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Barra de navegacion (alineada al borde, sin padding)
        BarraNavegacion(self, self.controlador).grid(
            row=0, column=0, sticky="nsw"
        )

        # === Contenedor derecho ===
        contenedor = ttk.Frame(self)
        contenedor.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        # 2 columnas uniformes para ubicar 4 secciones (2x2)
        contenedor.grid_columnconfigure(0, weight=1, uniform="mfc")
        contenedor.grid_columnconfigure(1, weight=1, uniform="mfc")

        # Definicion de secciones: (id, titulo, incluye_factor)
        secciones = [
            (1, "O2", True),
            (2, "CO2", False),
            (3, "N2", False),
            (4, "H2", False),
        ]

        # Crear 4 secciones en grilla 2x2
        for idx, (mfc_id, titulo, con_factor) in enumerate(secciones, start=1):
            fila = (idx - 1) // 2
            col = (idx - 1) % 2
            self._crear_seccion_gas(contenedor, mfc_id, titulo, con_factor).grid(
                row=fila, column=col, padx=8, pady=8, sticky="nsew"
            )

    def _crear_seccion_gas(self, parent, mfc_id: int, titulo: str, con_factor: bool) -> ttk.LabelFrame:
        """
        Crea una seccion (LabelFrame) para un gas MFC con sus entradas y boton Enviar.
        mfc_id: 1=O2, 2=CO2, 3=N2, 4=H2
        con_factor: True solo para O2 (flujo + factor). El resto solo flujo.
        """
        frame = ttk.LabelFrame(parent, text=titulo)
        frame.grid_columnconfigure(0, weight=0)
        frame.grid_columnconfigure(1, weight=1)

        # --- Flujo ---
        ttk.Label(frame, text="Flujo (mL/min):").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )
        entrada_flujo = ttk.Entry(frame, width=10)
        entrada_flujo.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        entrada_flujo.bind(
            "<Button-1>",
            lambda e, entry=entrada_flujo, m=mfc_id: TecladoNumerico(
                self,
                entry,
                on_submit=lambda valor, mm=m: self.guardar_valor_mfc(
                    mm, "flujo", valor)
            )
        )

        current_row = 1

        # --- Factor de conversion (solo para O2) ---
        if con_factor:
            ttk.Label(frame, text="Factor conversion:").grid(
                row=current_row, column=0, padx=5, pady=5, sticky="e"
            )
            entrada_factor = ttk.Entry(frame, width=10)
            entrada_factor.grid(row=current_row, column=1,
                                padx=5, pady=5, sticky="w")
            entrada_factor.bind(
                "<Button-1>",
                lambda e, entry=entrada_factor, m=mfc_id: TecladoNumerico(
                    self,
                    entry,
                    on_submit=lambda valor, mm=m: self.guardar_valor_mfc(
                        mm, "factor", valor)
                )
            )
            current_row += 1

        # --- Boton Enviar ---
        btn = ttk.Button(
            frame,
            text="Enviar",
            command=lambda m=mfc_id: self._enviar_mfc(m)
        )
        btn.grid(row=current_row, column=0, columnspan=2, pady=(8, 4))

        return frame

    # ================= auxiliares =================
    def guardar_valor_mfc(self, mfc_id: int, clave: str, valor):
        """
        Guarda un valor numerico en self.valores para el MFC indicado.
        Estructura: self.valores[mfc_id][clave] = valor
        """
        self.valores.setdefault(mfc_id, {})[clave] = valor
        print(f"MFC {mfc_id} {clave}: {valor}")

    def _alerta(self, titulo: str, mensaje: str):
        """Muestra una ventana de alerta modal simple."""
        messagebox.showerror(titulo, mensaje)

    def _enviar_mfc(self, mfc_id: int):
        """
        Construye y envia el mensaje segun el gas:
        - O2 (id=1): $;1;1;flujo;factor;!
            * Si falta factor, se envia 0.
            * Si falta flujo, se alerta y no se envia.
        - CO2/N2/H2 (id=2/3/4): $;1;id;flujo;!
            * Si falta flujo, se alerta y no se envia.
        """
        datos = self.valores.get(mfc_id, {})
        flujo = datos.get("flujo", None)

        # Validacion: flujo es obligatorio para todos
        if flujo is None:
            self._alerta(
                "Dato faltante", f"Debe ingresar el flujo para {self._nombre_mfc(mfc_id)}.")
            return

        if mfc_id == 1:
            # O2: factor opcional, si no hay -> usar 0
            factor = datos.get("factor", 0)
            if factor is None:
                factor = 0
            # mensaje = f"$;1;1;{flujo};{factor};!"
            mensaje = f"$;2;9;!"

        else:
            # CO2/N2/H2
            mensaje = f"$;1;{mfc_id};{flujo};!"

        print("Mensaje MFC:", mensaje)
        # Envio centralizado
        self.controlador.enviar_a_arduino(mensaje)

    def _nombre_mfc(self, mfc_id: int) -> str:
        """Devuelve el nombre legible del MFC segun su id."""
        return {1: "O2", 2: "CO2", 3: "N2", 4: "H2"}.get(mfc_id, f"MFC {mfc_id}")
