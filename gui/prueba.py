import tkinter as tk
from tkinter import ttk


class Prueba(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Prueba layout")
        self.geometry("800x600")
        self.configure(bg="lightgray")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("BotonAzul.TButton",
                        font=("Arial", 12, "bold"),
                        foreground="white",
                        background="#007acc",
                        padding=10)

        boton = ttk.Button(self, text="HOME", style="BotonAzul.TButton")
        boton.place(x=0, y=0, width=120, height=40)
        boton = ttk.Button(self, text="HOME", style="BotonAzul.TButton")
        boton.place(x=120, y=0, width=120, height=40)

        etiqueta = tk.Label(self, text="PRUEBA", bg="red", fg="white")
        etiqueta.place(x=10, y=100, width=100, height=30)


if __name__ == "__main__":
    app = Prueba()
    app.mainloop()
