import tkinter as tk
from tkinter import ttk, messagebox


class TecladoNumerico(tk.Toplevel):
    """Teclado numérico táctil (popup modal) para editar un `Entry`.

    - Centra la ventana sobre el toplevel padre.
    - Botones grandes y accesibles en pantallas táctiles.
    - `on_submit(valor_float)` permite aplicar lógica adicional al confirmar.
    """

    def __init__(self, master, entry_destino, on_submit=None):
        super().__init__(master)
        self.title("Teclado Numérico")
        self.geometry("240x340")
        self.resizable(False, False)

        self.entry = entry_destino
        self.on_submit = on_submit

        # Modal/transiente sobre el toplevel
        self.transient(master.winfo_toplevel())
        self.wait_visibility()
        self.lift()
        self.focus_force()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._crear_teclas()

        # Atajos
        self.bind("<Return>", lambda e: self._enviar_valor())
        self.bind("<Escape>", lambda e: self.destroy())

        # Centrado aproximado sobre el padre
        try:
            parent = self.winfo_toplevel()
            self.update_idletasks()
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _crear_teclas(self):
        botones = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            (".", 3, 0), ("0", 3, 1), ("<-", 3, 2),
            ("Limpiar", 4, 0),
        ]
        for (texto, fila, col) in botones:
            colspan = 3 if texto == "Limpiar" else 1
            ttk.Button(
                self,
                text=texto,
                width=5 if texto != "Limpiar" else 16,
                command=lambda t=texto: self._presionar(t),
            ).grid(row=fila, column=col, columnspan=colspan, padx=5, pady=5)

        ttk.Button(self, text="Enviar", width=16, command=self._enviar_valor).grid(
            row=5, column=0, columnspan=3, pady=10
        )

    def _presionar(self, texto):
        if texto == "<-":
            actual = self.entry.get()
            self.entry.delete(0, tk.END)
            self.entry.insert(0, actual[:-1])
        elif texto == "Limpiar":
            self.entry.delete(0, tk.END)
        else:
            self.entry.insert(tk.END, texto)

    def _enviar_valor(self):
        texto = self.entry.get().strip()
        try:
            valor = float(texto)
        except ValueError:
            messagebox.showerror("Error", "Ingrese un número válido.", parent=self)
            self.entry.delete(0, tk.END)
            self.lift(); self.focus_force(); self.grab_set()
            return
        if self.on_submit:
            self.on_submit(valor)
        self.destroy()
