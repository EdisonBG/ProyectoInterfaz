import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

class TecladoNumerico(tk.Toplevel):
    def __init__(self, master, entry_destino, on_submit=None):
        super().__init__(master)
        self.title("Teclado Numerico")
        self.geometry("227x350")
        self.resizable(False, False)

        self._font = tkfont.Font(family="Calibri", size=14)
        
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        
        bg_theme = st.lookup("TFrame", "background")
        if not bg_theme:
            bg_theme = self.cget("bg")
        self.configure(bg=bg_theme)

        self.entry = entry_destino
        self.on_submit = on_submit
        
        # Guardar el valor original y configurar para reemplazo
        self._valor_original = self.entry.get()
        self._texto_seleccionado = True  # Indicar que el texto debería estar seleccionado
        self._primera_tecla = True  # Para saber si es la primera tecla presionada
        
        # Configurar el entry para que tenga el texto seleccionado
        self.entry.select_range(0, tk.END)
        self.entry.icursor(tk.END)

        self.transient(master.winfo_toplevel())
        self.crear_teclas()

        self.wait_visibility()
        self.lift()
        self.focus_force()
        self.grab_set()

        self.bind("<Return>", lambda e: self.enviar_valor())
        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def crear_teclas(self):
        botones = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            (".", 3, 0), ("0", 3, 1), ("<-", 3, 2),
            ("Enviar", 4, 0),
        ]
        
        for (texto, fila, col) in botones:
            colspan = 3 if texto in ("Limpiar", "Enviar") else 1
            boton = tk.Button(
                self,
                text=texto,
                font=self._font,
                width=5 if texto not in ("Limpiar", "Enviar") else 16,
                command=self.enviar_valor if texto == "Enviar" else (lambda t=texto: self.presionar(t))
            )
            boton.grid(row=fila, column=col,
                    columnspan=colspan, padx=10, pady=10)

        # Botón "Limpiar"
        tk.Button(self, text="Limpiar", font=self._font, width=16,
                command=lambda: self.presionar("Limpiar"))\
            .grid(row=5, column=0, columnspan=3, pady=10)

    def presionar(self, texto):
        # Si es la primera tecla después de abrir y no es una tecla especial,
        # reemplazar el contenido completo
        if self._primera_tecla and texto not in ["<-", "Limpiar", "Enviar"]:
            self.entry.delete(0, tk.END)
            self.entry.insert(0, texto)
            self._primera_tecla = False
        elif texto == "<-":
            actual = self.entry.get()
            self.entry.delete(0, tk.END)
            self.entry.insert(0, actual[:-1])
            self._primera_tecla = False
        elif texto == "Limpiar":
            self.entry.delete(0, tk.END)
            self._primera_tecla = False
        else:
            # Para teclas subsiguientes, insertar normalmente
            self.entry.insert(tk.END, texto)
            self._primera_tecla = False

    def enviar_valor(self):
        texto = self.entry.get().strip()
        try:
            valor = float(texto)
        except ValueError:
            messagebox.showerror(
                "Error", "Ingrese un numero valido.", parent=self)
            self.entry.delete(0, tk.END)
            self.entry.insert(0, self._valor_original)  # Restaurar valor original
            self.lift()
            self.focus_force()
            self.grab_set()
            return

        if self.on_submit:
            self.on_submit(valor)
        self.destroy()
        
    def destroy(self):
        # Si se cierra sin enviar, restaurar el valor original
        if hasattr(self, '_valor_original'):
            current_val = self.entry.get()
            # Solo restaurar si el usuario no modificó nada
            if current_val == self._valor_original or not current_val:
                self.entry.delete(0, tk.END)
                self.entry.insert(0, self._valor_original)
        super().destroy()