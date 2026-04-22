"""
alert.ssz  –  Python implementation of the S-SIZE alert library.

In the original IKEMEN engine, alert() shows a pop-up message box.
In this cross-platform Python replica it prints to stdout,
with an optional --gui flag for a real dialog via tkinter.
"""
import sys


def _alert(message: str) -> None:
    """Display a message to the user."""
    try:
        # Try a simple Tk dialog first (works on most desktops)
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("SSZ Alert", str(message))
        root.destroy()
    except Exception:
        # Fall back to console output
        print(f"[ALERT] {message}")


def _alert_console(message: str) -> None:
    print(str(message))


def _dispatch_alert(message: str) -> None:
    """Dispatch to the current _alert implementation (allows monkey-patching in tests)."""
    import ssize.stdlib.alert as _self
    _self._alert(str(message))


def register(env, interpreter) -> None:
    """Called by the interpreter when loading this module."""
    env.define("alert",        _dispatch_alert)
    env.define("alertConsole", _alert_console)
