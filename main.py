"""
Entry point for the GUI application on Raspberry Pi 4 Model B.

Responsibilities:
- Import and initialize the top-level application class.
- Start the Tkinter event loop.

Notes:
- Window sizing (1024x530 usable area) and UI theme should be centralized in the GUI layer
  (e.g., gui/theme.py) and applied by gui/app.py (Aplicacion).
- This module intentionally remains minimal to keep startup fast and maintain separation of concerns.
"""

from gui.app import Aplicacion


def main() -> None:
    """Create the application instance and start Tkinter's event loop.

    The Aplicacion class is expected to derive from tk.Tk (or manage a single Tk instance)
    and be responsible for:
    - Setting the window geometry to 1024x530 for the usable client area.
    - Applying the global ttk Style (fonts, colors, touch-friendly sizes).
    - Managing navigation between frames/windows.
    """
    app = Aplicacion()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        # Print any unhandled exception to stderr so it surfaces in system logs (e.g., journalctl).
        import sys

        print(f"[FATAL] Unhandled exception: {exc}", file=sys.stderr)
        raise
