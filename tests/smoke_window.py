"""The window has to come up. Run by CI; not a pytest file.

Deliberately not inside the pytest suite: this is the check that the packaged
app opens at all, and it should fail loudly on its own rather than skip.
"""

import sys
import tkinter as tk

from overleaf_comments_export.gui import App

root = tk.Tk()
App(root)
root.update_idletasks()
w, h = root.winfo_reqwidth(), root.winfo_reqheight()
root.destroy()

print(f"the window asks for {w} x {h}")
if w < 400 or h < 300:
    sys.exit(f"the window came up empty at {w} x {h}")
