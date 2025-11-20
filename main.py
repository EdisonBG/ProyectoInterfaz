import tkinter as tk
import sys
import os
import threading

try:
    import cv2
    print(cv2.__file__)
    print("OpenCV version:", cv2.__version__)
    CV_AVAILABLE = True
except ImportError as e:
    print("ERROR:", e)
    CV_AVAILABLE = False
print("===================")

from gui.app import Aplicacion
import time

def reproducir_video_splash(video_path="splash.mp4", duracion=6):
    """Reproduce un video MP4 de duracion fija como splash screen"""
    
    if not CV_AVAILABLE:
        print("ERROR: OpenCV no disponible para reproducir video")
        return False
    
    # NUEVO: convertir ruta relativa a ruta absoluta basada en este archivo
    if not os.path.isabs(video_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))  # carpeta de main.py
        video_path = os.path.join(base_dir, video_path)

    print(f"Usando ruta de video: {video_path}")

    # Verificar si el archivo de video existe
    if not os.path.exists(video_path):
        print(f"ERROR: Video no encontrado: {video_path}")
        return False
        
    try:
        print("Intentando abrir video...")
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            print(f"ERROR: No se pudo abrir el video: {video_path}")
            return False
            
        print("Creando ventana OpenCV...")
        # Crear ventana de OpenCV en pantalla completa
        cv2.namedWindow("Splash", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Splash", cv2.WND_PROP_FULLSCREEN, 1)
        
        print("Reproduciendo video splash...")
        start_time = time.time()
        
        while (time.time() - start_time) < duracion:
            ret, frame = cap.read()
            
            if not ret:
                # Si el video termina antes, reiniciarlo
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret:
                    break
                    
            cv2.imshow("Splash", frame)
            
            # Salir si se presiona ESC o pasa el tiempo
            if cv2.waitKey(25) & 0xFF == 27:  # Tecla ESC
                break
                
        cap.release()
        cv2.destroyAllWindows()
        print("Video splash completado")
        return True
        
    except Exception as e:
        print(f"ERROR reproduciendo video splash: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":

    app = Aplicacion()
    app.geometry("1024x600+0+0")  # si la usas

    # Iniciar splash en background
    threading.Thread(
        target=reproducir_video_splash,
        args=("video_inicial.mp4", 5),
        daemon=True
    ).start()

    # --- Solucion anticlick-through (RPi Bookworm/Wayland) ---

    app.update_idletasks()

    def _ensure_front_and_focus():
        try:
            app.lift()
            app.focus_force()
            # pulso de topmost (True -> False) para vencer al compositor
            app.attributes("-topmost", True)
            app.after(120, lambda: app.attributes("-topmost", False))
        except Exception:
            pass

    # 1) Mostrar con peque�o retraso: VS Code suelta foco
    def _show_after_withdraw():
        try:
            app.deiconify()
        except Exception:
            pass
        _ensure_front_and_focus()

    # ocultar 150 ms y luego mostrar al frente
    try:
        app.withdraw()
    except Exception:
        pass
    app.after(120, _show_after_withdraw)

    # 2) Ciclo corto de refuerzos (durante ~1.2 s)
    def _focus_cycle(n=0):
        _ensure_front_and_focus()
        if n < 9:  # 10 intentos cada 120 ms
            app.after(120, lambda: _focus_cycle(n+1))
    app.after(160, _focus_cycle)

    # 3) Si el primer click llega demasiado pronto, lo "tragamos" y pedimos foco
    _first_click_done = {"v": False}

    def _swallow_until_focused(ev=None):
        if not _first_click_done["v"]:
            _ensure_front_and_focus()
            _first_click_done["v"] = True
            return "break"  # evita que ese primer click llegue a VS Code
    app.bind_all("<ButtonPress-1>", _swallow_until_focused, add="+")
    # tambien al map/idle por si el WM ignora el primero
    app.bind("<Map>", lambda e: app.after(10, _ensure_front_and_focus))
    app.after_idle(_ensure_front_and_focus)

    # --- Pantalla completa gestionada + "recordar volver a fullscreen" ---
    app.attributes("-fullscreen", True)  # sin barra de t�tulo
    app._want_fullscreen = True          # bandera de preferencia

    def _reapply_fullscreen(_=None):
        # Al restaurar desde la barra de tareas, vuelve a fullscreen si as� se prefiri�
        if getattr(app, "_want_fullscreen", False):
            app.after(50, lambda: app.attributes("-fullscreen", True))

    # Cuando reaparece o toma foco (tras minimizar/restaurar)
    app.bind("<Map>", _reapply_fullscreen, add="+")
    app.bind("<FocusIn>", _reapply_fullscreen, add="+")

    # (Opcional) salir de fullscreen con ESC, y NO volver autom�ticamente
    def _exit_fs(_=None):
        app._want_fullscreen = False
        app.attributes("-fullscreen", False)
    app.bind("<Escape>", _exit_fs)

    app.mainloop()