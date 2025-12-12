import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

class TecladoNumerico(tk.Toplevel):
    def __init__(self, master, entry_destino=None, on_submit=None):
        super().__init__(master)
       
        self.title("Teclado Numerico")
        self.geometry("300x320")
        self.resizable(False, False)
       
        # Configuraci�n visual
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

        # Inicializar referencias
        self._current_entry = entry_destino
        self._current_on_submit = on_submit
        self._valor_original = ""
        self._primera_tecla = True
       
        self.transient(master.winfo_toplevel())
        self.crear_teclas()
       
        # Configurar eventos
        self.bind("<Return>", lambda e: self.enviar_valor())
        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
       
        # Si se proporcion� un entry, configurarlo
        if self._current_entry is not None:
            self._valor_original = self._current_entry.get()
            self._primera_tecla = True
           
            # Seleccionar texto en el entry
            self._current_entry.select_range(0, tk.END)
            self._current_entry.icursor(tk.END)
           
        # Mostrar y posicionar el teclado
        self.deiconify()
        self.lift()
        self.focus_force()
        self.grab_set()
       
        # Forzar actualizaci�n de la UI
        self.update_idletasks()
   
    def crear_teclas(self):
        botones = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            (".", 3, 0), ("0", 3, 1), ("<-", 3, 2),
            ("Enviar", 4, 0),
        ]
       
        for (texto, fila, col) in botones:
            colspan = 3 if texto == "Enviar" else 1
            boton = tk.Button(
                self,
                text=texto,
                font=self._font,
                width=5 if texto != "Enviar" else 16,
                command=self.enviar_valor if texto == "Enviar" else (lambda t=texto: self.presionar(t))
            )
            boton.grid(row=fila, column=col, columnspan=colspan, padx=10, pady=10)

        tk.Button(self, text="Limpiar", font=self._font, width=16,
                 command=lambda: self.presionar("Limpiar"))\
            .grid(row=5, column=0, columnspan=3, pady=10)
        
    def presionar(self, texto):
        if self._current_entry is None:
            return
           
        if self._primera_tecla and texto not in ["<-", "Limpiar", "Enviar"]:
            self._current_entry.delete(0, tk.END)
            self._current_entry.insert(0, texto)
            self._primera_tecla = False
        elif texto == "<-":
            actual = self._current_entry.get()
            self._current_entry.delete(0, tk.END)
            self._current_entry.insert(0, actual[:-1])
            self._primera_tecla = False
        elif texto == "Limpiar":
            self._current_entry.delete(0, tk.END)
            self._primera_tecla = False
        else:
            self._current_entry.insert(tk.END, texto)
            self._primera_tecla = False
   
    def enviar_valor(self):
        if self._current_entry is None:
            return
           
        texto = self._current_entry.get().strip()
        try:
            valor = float(texto)
        except ValueError:
            messagebox.showerror("Error", "Ingrese un numero valido.", parent=self)
            self._current_entry.delete(0, tk.END)
            self._current_entry.insert(0, self._valor_original)
            return

        if self._current_on_submit:
            self._current_on_submit(valor)
        
        # Liberar recursos antes de destruir
        self.grab_release()
        self.destroy()