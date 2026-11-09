"""
Duplicator 4 Studio - printer software for the Wanhao Duplicator 4 (Sailfish, USB).

    python tools/d4_gui.py        (or double-click D4_Control.bat)

Tabs
  Printer  - live temperatures + chart, limit switches, move/home, extruders,
             filament load/unload, motor test
  Prepare  - create a print without the command line (vase, square, R+L cubes,
             air demo), see a 3D preview and the safety-check result
  Print    - file library with preview/time/filament/check, pre-print checklist,
             live print view (progress, time left, height, filament, temps)

Safety: EMERGENCY STOP (button / Esc), heater watchdog, bed heating blocked
while the bed sensor is faulty, files that fail the checker cannot be printed.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import collections
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

try:                                   # Windows-11 style theme (pip install sv-ttk)
    import sv_ttk
except ImportError:
    sv_ttk = None

import d4_paths
import render_preview as rp
import s3g_link as s3g
from d4_paths import LOGFILE, OUT, PREV, TOOLS, run_tool
from d4_worker import Worker
CHART_SPAN_S = 300
COLD_EXTRUDE_C = 170

# Google Material colours (light = Google Workspace, dark = Google dark theme tints)
PALETTES = {
    "light": {"page": "#f1f3f4", "border": "#dadce0", "bg": "#ffffff", "panel": "#ffffff", "fg": "#202124", "dim": "#5f6368",
              "r": "#ea4335", "l": "#1a73e8", "bed": "#f9ab00", "ok": "#34a853",
              "off": "#dadce0", "warn": "#e37400", "grid": "#e8eaed", "accent": "#1a73e8",
              "accent2": "#1765cc", "on_accent": "#ffffff", "tonal": "#e8f0fe", "tonal_fg": "#1967d2",
              "danger": "#d93025", "danger2": "#b3261e", "field": "#f1f3f4", "btn": "#ffffff",
              "btn_active": "#f1f3f4", "btn_dis": "#f1f3f4", "dis_fg": "#9aa0a6",
              "canvas": "#ffffff", "trough": "#e8eaed", "status": "#ffffff"},
    "dark": {"page": "#202124", "border": "#3c4043", "bg": "#2d2e31", "panel": "#2d2e31", "fg": "#e8eaed", "dim": "#9aa0a6",
             "r": "#f28b82", "l": "#8ab4f8", "bed": "#fdd663", "ok": "#81c995",
             "off": "#5f6368", "warn": "#fcad70", "grid": "#3c4043", "accent": "#8ab4f8",
             "accent2": "#aecbfa", "on_accent": "#202124", "tonal": "#394457", "tonal_fg": "#d2e3fc",
             "danger": "#d93025", "danger2": "#b3261e", "field": "#303134", "btn": "#303134",
             "btn_active": "#3c4043", "btn_dis": "#2a2b2e", "dis_fg": "#5f6368",
             "canvas": "#2d2e31", "trough": "#3c4043", "status": "#2d2e31"},
}
SETTINGS = d4_paths.SETTINGS


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_settings(**kw):
    s = load_settings()
    s.update(kw)
    with open(SETTINGS, "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=2)


def windows_uses_light_theme():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 1
    except OSError:
        return False


THEME_CHOICE = load_settings().get("theme", "System")          # System / Light / Dark
THEME = ("light" if windows_uses_light_theme() else "dark") if THEME_CHOICE == "System"     else THEME_CHOICE.lower()
COL = dict(PALETTES.get(THEME, PALETTES["dark"]))

# ---- objects the Prepare tab can make ---------------------------------------------
# param: (cli flag, label, default, min, max, step)
OBJECTS = {
    "📦 Your 3D model (STL / 3MF / OBJ)": {
        "script": "slice_model.py", "name": "MODEL", "extruder": True, "model": True, "fixed": [],
        "desc": "Any 3D design (Paint 3D, Tinkercad, Thingiverse …) sliced by the PrusaSlicer "
                "engine with the Duplicator 4 profile. Layer 0.1 fine · 0.2 normal · 0.3 draft. "
                "Squish: negative = first layer closer to the bed. Colour Z: above this height "
                "the OTHER extruder prints (two colours, 0 = off). Fast 1: ~40 % quicker for "
                "simple parts like boxes and brackets (keep 0 for detailed figures). "
                "🔍 Fit check: will it print well (3-D report). 🧩 Assembly: do several parts "
                "(e.g. a box + the boards inside) collide?",
        "params": [("layer-height", "Layer (mm)", 0.2, 0.1, 0.3, 0.05),
                   ("infill", "Infill (%)", 20, 0, 100, 5),
                   ("walls", "Walls", 3, 1, 6, 1),
                   ("supports", "Supports 0/1", 0, 0, 1, 1),
                   ("brim", "Brim (mm)", 5, 0, 15, 1),
                   ("scale", "Scale (%)", 100, 10, 500, 5),
                   ("temp", "Nozzle °C", 210, 180, 240, 5),
                   ("first-temp", "1st layer °C", 220, 180, 240, 5),
                   ("z-offset", "Squish (mm)", -0.05, -0.3, 0.3, 0.02),
                   ("color-z", "Colour Z (mm)", 0, 0, 140, 0.1),
                   ("fast", "Fast 0/1", 0, 0, 1, 1)]},
    "Twisted flower vase": {
        "script": "make_vase.py", "name": "TWIST_VASE", "extruder": False, "fixed": [],
        "desc": "6-lobed vase that twists and bulges. Brim + solid spiral base, then one "
                "continuous spiral wall. Left extruder. Looks great, ~15-20 min.",
        "params": [("height", "Height (mm)", 25, 5, 60, 1), ("radius", "Radius (mm)", 14, 6, 30, 1),
                   ("twist", "Twist (°)", 60, 0, 360, 10), ("lobes", "Lobes", 6, 3, 12, 1),
                   ("temp", "Nozzle °C", 210, 180, 240, 5),
                   ("first-temp", "1st layer °C", 220, 180, 240, 5),
                   ("brim", "Brim rings", 6, 0, 15, 1),
                   ("z-offset", "Squish (mm)", -0.08, -0.3, 0.3, 0.02)]},
    "Square block": {
        "script": "make_dual_sample.py", "name": "SQUARE", "extruder": True, "fixed": ["--slow-z"],
        "desc": "Solid square block in the middle of the bed, one extruder. Quick test print.",
        "params": [("size", "Size (mm)", 15, 5, 40, 1), ("height", "Height (mm)", 2, 0.5, 20, 0.5),
                   ("temp", "Nozzle temp (C)", 210, 180, 240, 5)]},
    "Two-colour cubes (R + L)": {
        "script": "make_dual_sample.py", "name": "RL_CUBES", "extruder": False,
        "fixed": ["--slow-z", "--only", "both"],
        "desc": "One cube per extruder, layers alternate R/L. Needs filament in BOTH extruders.",
        "params": [("size", "Cube size (mm)", 10, 5, 25, 1), ("height", "Height (mm)", 2, 0.5, 20, 0.5),
                   ("temp", "Nozzle temp (C)", 210, 180, 240, 5)]},
    "Air demo (left, bed not used)": {
        "script": "make_left_demo.py", "name": "DEMO_LEFT", "extruder": False, "fixed": [],
        "fixed_name": True,
        "desc": "Left nozzle heats and draws a spiral in the air. Bed never moves. "
                "Good quick check that the left extruder feeds.",
        "params": [("temp", "Nozzle temp (C)", 210, 180, 240, 5)]},
}


class Card(tk.Frame):
    """Google-style card: title on the grey page, white body with a thin border.
    Children go into the card body; pack()/grid() place the whole card."""

    def __init__(self, parent, title):
        self.outer = tk.Frame(parent, bg=COL["page"])
        tk.Label(self.outer, text=title, bg=COL["page"], fg=COL["fg"], anchor="w",
                 font=("Segoe UI Semibold", 11)).pack(fill="x", padx=4, pady=(0, 4))
        super().__init__(self.outer, bg=COL["bg"], highlightthickness=1,
                         highlightbackground=COL["border"], highlightcolor=COL["border"],
                         padx=14, pady=12)

    def pack(self, **kw):
        self.outer.pack(**kw)
        tk.Frame.pack(self, fill="both", expand=True)

    def grid(self, **kw):
        self.outer.grid(**kw)
        tk.Frame.pack(self, fill="both", expand=True)


class ScrollFrame(tk.Frame):
    """Page that fills the window when it is big enough and gets scrollbars when the window
    is made smaller than its content (so the window can be resized freely)."""
    _NO_WHEEL = ("Text", "Treeview", "TSpinbox", "TCombobox", "Spinbox", "Listbox")

    def __init__(self, master):
        super().__init__(master, bg=COL["page"])
        self.canvas = tk.Canvas(self, bg=COL["page"], highlightthickness=0, bd=0, width=300, height=200)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        self.inner = tk.Frame(self.canvas, bg=COL["page"])
        self.win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", self._fit)
        self.inner.bind("<Configure>", self._fit)

    MIN_W, MIN_H = 1100, 500        # the layout squeezes nicely down to this; below it, scroll

    def _fit(self, _e=None):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        rw = min(self.inner.winfo_reqwidth(), self.MIN_W)
        rh = min(self.inner.winfo_reqheight(), self.MIN_H)
        w, h = max(cw, rw), max(ch, rh)
        self.canvas.itemconfigure(self.win, width=w, height=h)
        self.canvas.configure(scrollregion=(0, 0, w, h))
        if rh > ch + 1:
            self.vsb.grid(row=0, column=1, sticky="ns")
        else:
            self.vsb.grid_remove()
            self.canvas.yview_moveto(0)
        if rw > cw + 1:
            self.hsb.grid(row=1, column=0, sticky="ew")
        else:
            self.hsb.grid_remove()
            self.canvas.xview_moveto(0)

    @classmethod
    def on_wheel(cls, e):
        """App-wide mouse wheel: scroll the page under the pointer (if it has a scrollbar)."""
        w = e.widget
        try:
            if w.winfo_class() in cls._NO_WHEEL:
                return                              # lists/log/number boxes keep their own wheel
        except (AttributeError, tk.TclError):
            return
        while w is not None and not isinstance(w, ScrollFrame):
            w = getattr(w, "master", None)
        if w is not None and w.vsb.winfo_ismapped():
            w.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")


class GBar(tk.Canvas):
    """Flat, rounded Material progress bar."""

    def __init__(self, master, color=None, height=8, **kw):
        super().__init__(master, height=height + 2, highlightthickness=0, bd=0,
                         bg=kw.pop("bg", COL["bg"]), **kw)
        self.color = color or COL["accent"]
        self.h = height
        self.frac = 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value, maximum=1.0, color=None):
        self.frac = 0.0 if not maximum else max(0.0, min(1.0, float(value) / maximum))
        if color:
            self.color = color
        self._draw()

    def _draw(self):
        self.delete("all")
        w, y, r = self.winfo_width(), self.h / 2 + 1, self.h / 2
        if w < 4:
            return
        self.create_line(r + 1, y, w - r - 1, y, fill=COL["trough"], width=self.h, capstyle="round")
        if self.frac > 0:
            x = r + 1 + (w - 2 * r - 2) * self.frac
            self.create_line(r + 1, y, max(r + 1.5, x), y, fill=self.color, width=self.h,
                             capstyle="round")


class GButton(tk.Button):
    """Flat Google-style button (filled / tonal / danger) with hover and ttk-like state()."""
    KINDS = {"filled": ("accent", "on_accent", "accent2"), "tonal": ("tonal", "tonal_fg", "grid"),
             "danger": ("danger", None, "danger2")}

    def __init__(self, master, text, command, kind="filled", size=11, **kw):
        bg, fg, hover = self.KINDS[kind]
        self._bg, self._hover = COL[bg], COL[hover]
        fgc = COL[fg] if fg else "#ffffff"
        super().__init__(master, text=text, command=command, bg=self._bg, fg=fgc,
                         activebackground=self._hover, activeforeground=fgc, relief="flat", bd=0,
                         padx=kw.pop("padx", 20), pady=kw.pop("pady", 8), cursor="hand2",
                         font=("Segoe UI Semibold", size), disabledforeground=COL["dis_fg"], **kw)
        self.bind("<Enter>", lambda e: self["state"] != "disabled" and self.configure(bg=self._hover))
        self.bind("<Leave>", lambda e: self["state"] != "disabled" and self.configure(bg=self._bg))

    def state(self, spec):
        off = "disabled" in spec
        self.configure(state="disabled" if off else "normal", bg=COL["btn_dis"] if off else self._bg,
                       cursor="arrow" if off else "hand2")

    def instate(self, spec):
        return ("disabled" in spec) == (self["state"] == "disabled")


def fmt_min(s):
    s = max(0, int(s))
    return "%d:%02d" % (s // 60, s % 60) if s < 3600 else "%dh %02dm" % (s // 3600, s % 3600 // 60)


# =============================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Duplicator 4 Studio")
        self.configure(bg=COL["page"])
        self.minsize(760, 500)                       # small enough to really resize; pages scroll
        # normal (not maximised) size: fits the screen with room to spare
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(1280, sw - 80), min(780, sh - 120)
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, (sw - w) // 2), max(0, (sh - h) // 3)))
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        os.makedirs(PREV, exist_ok=True)
        self.events = queue.Queue()
        self.worker = Worker(self.events)
        self.worker.start()
        self.hist = collections.deque()
        self.es_last, self.es_changes = None, collections.deque()
        self.connected = False
        self.printing = False
        self.print_stats = None
        self.user_disconnected = False
        self._connecting_until = 0.0
        self._last_temps = {}
        self._last_pos = [0.0] * 5
        self._controls = []
        self._stats_cache = {}          # path -> (mtime, stats)
        self._check_cache = {}          # path -> (mtime, ok, text)
        self._preview_img = None
        self._gen_img = None
        self.ui = load_settings().get("ui", {})          # remembered UI state from last time
        self._obj_params = dict(self.ui.get("obj_params", {}))
        self._style()
        self._build()
        self.bind("<Escape>", lambda e: self.estop())
        for seq in ("<Control-Shift-A>", "<Control-Shift-a>"):     # hidden "about"
            self.bind(seq, lambda e: self.show_about())
        self.bind_all("<MouseWheel>", ScrollFrame.on_wheel, add="+")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_ports(autoconnect=True)
        self.refresh_library(select=self.ui.get("last_file"))
        self._restore_ui()
        self.after(100, self.pump)
        self.after(3000, self.watch_ports)
        self.after(15000, self._autosave)

    # ---- remember settings between sessions --------------------------------------
    def _restore_ui(self):
        u = self.ui
        try:
            if u.get("geometry") and u.get("window_state") != "zoomed":
                self.state("normal")
                # never restore a size/position that no longer fits this screen
                try:
                    size, _, pos = u["geometry"].partition("+")
                    gw, gh = (int(v) for v in size.split("x"))
                    sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
                    gw, gh = max(760, min(gw, sw)), max(500, min(gh, sh - 40))
                    gx, gy = (int(v) for v in pos.split("+")) if pos else (40, 20)
                    gx, gy = max(0, min(gx, sw - 200)), max(0, min(gy, sh - 200))
                    self.geometry("%dx%d+%d+%d" % (gw, gh, gx, gy))
                except (ValueError, TypeError):
                    pass
            for key in ("r", "l", "bed"):
                if key in u.get("temps", {}):
                    self.t_entry[key].set(u["temps"][key])
            if "step" in u:
                self.step.set(u["step"])
            if "move_mm" in u:
                self.e_amt.set(u["move_mm"])
            if "load_temp" in u:
                self.fil_temp.set(u["load_temp"])
            self.keep_hot.set(bool(u.get("keep_hot", False)))
            # bed_ok is deliberately NOT restored: bed heating stays blocked at every start
            if u.get("object") in OBJECTS:
                self.obj_var.set(u["object"])
                self._build_params()
            tabs = {"printer": self.tab_printer, "prepare": self.tab_prepare, "print": self.tab_print}
            if u.get("tab") in tabs:
                self.nb.select(tabs[u["tab"]])
        except (tk.TclError, ValueError, TypeError) as e:
            self.log("Could not restore some saved settings: %s" % e)

    def _remember_params(self):
        """Store the current object's settings so each object type keeps its own values."""
        obj = getattr(self, "_params_for", None)
        if not obj or not getattr(self, "param_widgets", None):
            return
        vals = {flag: sb.get() for flag, (sb, lo, hi) in self.param_widgets.items()}
        vals["_extruder"] = self.ext_var.get()
        if OBJECTS[obj].get("model"):
            vals["_model"] = self.model_var.get()
        if not OBJECTS[obj].get("fixed_name"):
            vals["_name"] = self.gen_name.get()
        self._obj_params[obj] = vals

    def _collect_ui(self):
        self._remember_params()
        tab = {str(self.tab_printer): "printer", str(self.tab_prepare): "prepare",
               str(self.tab_print): "print"}.get(self.nb.select(), "printer")
        sel = self.tree.selection() if hasattr(self, "tree") else ()
        return {
            "tab": tab,
            "window_state": self.state(),
            "geometry": self.geometry() if self.state() == "normal" else self.ui.get("geometry", ""),
            "temps": {k: self.t_entry[k].get() for k in ("r", "l", "bed")},
            "step": self.step.get(),
            "move_mm": self.e_amt.get(),
            "load_temp": self.fil_temp.get(),
            "keep_hot": bool(self.keep_hot.get()),
            "object": self.obj_var.get(),
            "obj_params": self._obj_params,
            "last_file": sel[0] if sel else self.ui.get("last_file"),
        }

    def save_ui(self):
        try:
            self.ui = self._collect_ui()
            save_settings(ui=self.ui)
        except (OSError, tk.TclError, ValueError):
            pass

    def _autosave(self):
        self.save_ui()
        self.after(15000, self._autosave)

    # ---- styling ---------------------------------------------------------------
    def _style(self):
        s = ttk.Style(self)
        if sv_ttk:
            sv_ttk.set_theme(THEME)                     # Windows 11 look, light or dark
        else:
            s.theme_use("clam")
            s.configure(".", background=COL["panel"], foreground=COL["fg"], fieldbackground=COL["field"],
                        bordercolor=COL["grid"])
            s.configure("TButton", background=COL["btn"], padding=(8, 4))
            s.map("TButton", background=[("active", COL["btn_active"]), ("disabled", COL["btn_dis"])],
                  foreground=[("disabled", COL["dis_fg"])])
            s.configure("Accent.TButton", background=COL["accent"], foreground="white")
            s.map("Accent.TButton", background=[("active", COL["accent2"])])
        base = ("Segoe UI", 10)
        s.configure(".", font=base, background=COL["bg"], foreground=COL["fg"])
        s.configure("Page.TFrame", background=COL["page"])
        s.configure("Page.TLabel", background=COL["page"])
        for st in ("TFrame", "TLabel", "TLabelframe", "TCheckbutton", "TRadiobutton",
                   "Switch.TCheckbutton", "TNotebook"):
            s.configure(st, background=COL["bg"])
        s.configure("TLabelframe.Label", background=COL["bg"])
        s.configure("TNotebook", background=COL["page"])
        s.configure("Treeview", background=COL["canvas"], fieldbackground=COL["canvas"],
                    foreground=COL["fg"])
        s.map("Treeview", background=[("selected", COL["tonal"])],
              foreground=[("selected", COL["tonal_fg"])])
        s.configure("TLabelframe.Label", font=("Segoe UI Semibold", 11), foreground=COL["fg"])
        s.configure("Dim.TLabel", foreground=COL["dim"])
        s.configure("Big.TLabel", font=("Segoe UI Semibold", 20))
        s.configure("Huge.TLabel", font=("Segoe UI Semibold", 24))
        s.configure("Value.TLabel", font=("Segoe UI Semibold", 14))
        s.configure("Accent.TButton", font=("Segoe UI Semibold", 11), padding=(14, 7))
        s.configure("TNotebook.Tab", font=("Segoe UI Semibold", 11), padding=(18, 8))
        s.configure("Treeview", rowheight=32)
        s.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))
        s.configure("Temp.Horizontal.TProgressbar", thickness=6)

    def show_about(self):
        messagebox.showinfo("About", "Duplicator 4 Studio\n\nDeveloped by ARUN\n%s\n\n"
                                     "Slicing engine: PrusaSlicer (open source)" % __copyright__)

    def _scroll_page(self, tab):
        """Put a scrollable page into a notebook tab; the tab content is built inside it."""
        sf = ScrollFrame(tab)
        sf.pack(fill="both", expand=True)
        return sf.inner

    def _bg_of(self, m):
        """Background colour of a container (tk frames know it; ttk frames use their style)."""
        if isinstance(m, tk.Frame):
            return m.cget("bg")
        try:
            if str(m.cget("style")) == "Page.TFrame":
                return COL["page"]
        except tk.TclError:
            pass
        return COL["bg"]

    def _fix_bg(self, w=None):
        """Give every ttk label the exact background of what it sits on (no grey boxes)."""
        w = w or self
        for c in w.winfo_children():
            if isinstance(c, ttk.Label):
                try:
                    c.configure(background=self._bg_of(c.master))
                except tk.TclError:
                    pass
            self._fix_bg(c)

    def _panel(self, parent, title):
        return Card(parent, title)

    def _btn(self, parent, text, cmd, style=None):
        b = ttk.Button(parent, text=text, command=cmd, style=style) if style else \
            ttk.Button(parent, text=text, command=cmd)
        self._controls.append(b)
        return b

    # ---- layout ------------------------------------------------------------------
    def _build(self):
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        title = tk.Label(top, text="Duplicator 4 Studio", bg=COL["bg"], fg=COL["fg"],
                         font=("Segoe UI", 14, "bold"))
        title.pack(side="left", padx=(0, 16))
        title.bind("<Double-Button-1>", lambda e: self.show_about())
        ttk.Label(top, text="Port", style="Bg.TLabel").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(top, textvariable=self.port_var, width=20, state="readonly")
        self.port_box.pack(side="left", padx=6)
        ttk.Button(top, text="↻", width=3, command=self.refresh_ports).pack(side="left")
        self.conn_btn = ttk.Button(top, text="Connect", command=self.toggle_connect)
        self.conn_btn.pack(side="left", padx=6)
        self.conn_lbl = tk.Label(top, text="● Disconnected", bg=COL["bg"], fg=COL["dim"],
                                 font=("Segoe UI", 11, "bold"))
        self.conn_lbl.pack(side="left", padx=10)
        self.board_lbl = tk.Label(top, text="", bg=COL["bg"], fg=COL["dim"])
        self.board_lbl.pack(side="left")
        GButton(top, "\u26d4  EMERGENCY STOP  (Esc)", self.estop, kind="danger", size=12,
                padx=18, pady=7).pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=0)
        self.tab_printer = ttk.Frame(self.nb, padding=(10, 12), style="Page.TFrame")
        self.tab_prepare = ttk.Frame(self.nb, padding=(10, 12), style="Page.TFrame")
        self.tab_print = ttk.Frame(self.nb, padding=(10, 12), style="Page.TFrame")
        self.nb.add(self.tab_printer, text="🖨  Printer")
        self.nb.add(self.tab_prepare, text="🧩  Prepare")
        self.nb.add(self.tab_print, text="📂  Print")

        self._build_printer_tab(self._scroll_page(self.tab_printer))
        self._build_prepare_tab(self._scroll_page(self.tab_prepare))
        self._build_print_tab(self._scroll_page(self.tab_print))

        tk.Frame(self, bg=COL["border"], height=1).pack(fill="x", side="bottom")
        sb = tk.Frame(self, bg=COL["status"])
        sb.pack(fill="x", side="bottom")
        self.status_lbl = tk.Label(sb, text="Ready", bg=COL["status"], fg=COL["dim"], anchor="w",
                                   font=("Segoe UI", 9))
        self.status_lbl.pack(side="left", padx=10, pady=3)
        self.status_temps = tk.Label(sb, text="", bg=COL["status"], fg=COL["dim"], font=("Consolas", 9))
        self.theme_var = tk.StringVar(value=THEME_CHOICE)
        tb = ttk.Combobox(sb, textvariable=self.theme_var, values=("System", "Light", "Dark"),
                          state="readonly", width=8)
        tb.bind("<<ComboboxSelected>>", lambda e: self.change_theme())
        tb.pack(side="right", padx=(4, 10), pady=3)
        tk.Label(sb, text="Theme", bg=COL["status"], fg=COL["dim"], font=("Segoe UI", 9)).pack(side="right")
        self.status_temps.pack(side="right", padx=14)
        self.set_controls(False)
        self._fix_bg()

    # ======================= PRINTER TAB ===========================================
    def _build_printer_tab(self, tab):
        for c in range(3):
            tab.columnconfigure(c, weight=1, uniform="col")
        tab.rowconfigure(0, weight=1)
        left, mid, right = (tk.Frame(tab, bg=COL["page"]) for _ in range(3))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        mid.grid(row=0, column=1, sticky="nsew", padx=6)
        right.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        self._build_temps(left)
        self._build_switches(mid)
        self._build_jog(mid)
        self._build_extruders(right)
        self._build_log(right)

    def _build_temps(self, parent):
        f = self._panel(parent, "Temperatures")
        f.pack(fill="x")
        f.columnconfigure(1, weight=1)
        self.t_lbl, self.t_tgt, self.t_entry, self.t_bar = {}, {}, {}, {}
        rows = (("r", "Right", 210), ("l", "Left", 210), ("bed", "Bed", 0))
        for i, (key, name, default) in enumerate(rows):
            r0 = i * 2
            tk.Label(f, text="●", fg=COL[key], bg=COL["panel"], font=("Segoe UI", 14)).grid(
                row=r0, column=0, sticky="w", padx=(0, 6))
            nm = ttk.Frame(f)
            nm.grid(row=r0, column=1, sticky="w")
            ttk.Label(nm, text=name, font=("Segoe UI Semibold", 10)).pack(anchor="w")
            self.t_tgt[key] = ttk.Label(nm, text="off", style="Dim.TLabel")
            self.t_tgt[key].pack(anchor="w")
            self.t_lbl[key] = ttk.Label(f, text="---°", style="Big.TLabel", width=4, anchor="e")
            self.t_lbl[key].grid(row=r0, column=2, padx=(4, 10))
            e = ttk.Spinbox(f, from_=0, to=(240 if key != "bed" else 110), width=4, increment=5)
            e.set(default)
            e.grid(row=r0, column=3, padx=2)
            self.t_entry[key] = e
            ttk.Button(f, text="Set", width=4, command=lambda k=key: self.set_heater(k)).grid(row=r0, column=4, padx=2)
            ttk.Button(f, text="Off", width=4, command=lambda k=key: self.set_heater(k, 0)).grid(row=r0, column=5)
            bar = GBar(f, color=COL[key], height=6)
            bar.grid(row=r0 + 1, column=1, columnspan=5, sticky="ew", pady=(2, 10))
            self.t_bar[key] = bar
        self.bed_ok = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Bed sensor repaired (allow bed heating)", variable=self.bed_ok,
                        style="Switch.TCheckbutton" if sv_ttk else "TCheckbutton").grid(
            row=6, column=0, columnspan=6, sticky="w", pady=(2, 0))
        bb = ttk.Frame(f)
        bb.grid(row=7, column=0, columnspan=6, sticky="w", pady=(10, 0))
        ttk.Button(bb, text="🔥 PLA: both 210 °C", command=lambda: self.preset(210)).pack(side="left")
        ttk.Button(bb, text="❄ All heaters off", command=lambda: self.worker.submit("heaters_off")).pack(side="left", padx=8)
        c = self._panel(parent, "Temperature history (5 min)")
        c.pack(fill="both", expand=True, pady=(10, 0))
        self.chart = tk.Canvas(c, bg=COL["canvas"], highlightthickness=0, height=160)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda e: self.draw_chart())

    def _build_switches(self, parent):
        f = self._panel(parent, "Limit switches  &  position")
        f.pack(fill="x")
        f.columnconfigure(1, weight=1)
        self.sw = {}
        rows = ((1, "X", "X axis", "\u2192|  head at the right end"),
                (3, "Y", "Y axis", "\u2191|  head at the back"),
                (4, "Z", "Z axis", "\u2191  bed at the top"))
        for i, (bit, letter, name, where) in enumerate(rows):
            cv = tk.Canvas(f, width=30, height=30, bg=COL["panel"], highlightthickness=0)
            cv.grid(row=i, column=0, padx=(0, 10), pady=3)
            circle = cv.create_oval(2, 2, 28, 28, fill=COL["off"], outline="")
            txt = cv.create_text(15, 15, text=letter, fill=COL["dim"], font=("Segoe UI Semibold", 11))
            info = ttk.Frame(f)
            info.grid(row=i, column=1, sticky="w")
            ttk.Label(info, text=name, font=("Segoe UI Semibold", 10)).pack(anchor="w")
            ttk.Label(info, text=where, style="Dim.TLabel", font=("Segoe UI", 9)).pack(anchor="w")
            pill = tk.Label(f, text="", font=("Segoe UI Semibold", 9), padx=10, pady=2)
            pill.grid(row=i, column=2, sticky="e")
            self.sw[bit] = (cv, circle, txt, pill, letter, name)
            self._sw_text(bit, False)
        self.sw_warn = ttk.Label(f, text="", foreground=COL["warn"])
        self.sw_warn.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        tk.Frame(f, bg=COL["border"], height=1).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 6))
        self.pos_lbl = ttk.Label(f, text="X ---   Y ---   Z ---", font=("Consolas", 10))
        self.pos_lbl.grid(row=5, column=0, columnspan=3, sticky="w")
        self.homed_lbl = ttk.Label(f, text="Not homed", style="Dim.TLabel")
        self.homed_lbl.grid(row=6, column=0, columnspan=3, sticky="w")

    def _sw_text(self, bit, on):
        cv, circle, txt, pill, letter, name = self.sw[bit]
        cv.itemconfigure(circle, fill=COL["ok"] if on else COL["off"])
        cv.itemconfigure(txt, fill=COL["on_accent"] if on else COL["dim"])
        if on:
            pill.configure(text="\u25cf  PRESSED", bg=COL["ok"], fg=COL["on_accent"])
        else:
            pill.configure(text="\u25cb  open", bg=COL["field"], fg=COL["dim"])

    def _build_jog(self, parent):
        f = self._panel(parent, "Move")
        f.pack(fill="both", expand=True, pady=(10, 0))
        self.step = tk.DoubleVar(value=10.0)
        sf = ttk.Frame(f, style="Panel.TFrame")
        sf.pack(fill="x")
        ttk.Label(sf, text="Step").pack(side="left")
        for v in (0.1, 1, 10, 50):
            ttk.Radiobutton(sf, text="%g mm" % v, value=v, variable=self.step).pack(side="left", padx=4)

        g = ttk.Frame(f, style="Panel.TFrame")
        g.pack(fill="x", pady=(8, 4))
        for c in (0, 1, 2, 4):
            g.columnconfigure(c, weight=1, uniform="jog")
        g.columnconfigure(3, minsize=14)
        ttk.Label(g, text="Head  (X / Y)", style="Dim.TLabel").grid(row=0, column=0, columnspan=3)
        ttk.Label(g, text="Bed  (Z)", style="Dim.TLabel").grid(row=0, column=4)

        def B(text, cmd, r, c, kind=None):
            if kind:
                b = GButton(g, text, cmd, kind=kind, size=10, padx=6, pady=5)
                self._controls.append(b)
            else:
                b = self._btn(g, text, cmd)
            b.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
            return b
        # direction pad: arrows point the way the HEAD moves; centre = home X/Y
        B("\u25b2  Back", lambda: self.jog(1, +1), 1, 1)
        B("\u25c4  Left", lambda: self.jog(0, -1), 2, 0)
        B("\u2302  Home XY", lambda: self.worker.submit("home_xy"), 2, 1, kind="tonal")
        B("Right  \u25ba", lambda: self.jog(0, +1), 2, 2)
        B("\u25bc  Front", lambda: self.jog(1, -1), 3, 1)
        # Z column: the BED moves (up = towards the nozzles)
        B("\u25b2  Up", lambda: self.jog(2, -1), 1, 4)
        B("\u2302  Home Z", self.home_z, 2, 4, kind="tonal")
        B("\u25bc  Down", lambda: self.jog(2, +1), 3, 4)

        h = ttk.Frame(f, style="Panel.TFrame")
        h.pack(fill="x", pady=(8, 0))
        for c in range(3):
            h.columnconfigure(c, weight=1, uniform="home")
        self._btn(h, "\u2302  Home all", self.home_all).grid(row=0, column=0, sticky="ew", padx=2)
        self._btn(h, "\u2298  Motors off", lambda: self.worker.submit("motors_off")).grid(
            row=0, column=1, sticky="ew", padx=2)
        self._btn(h, "\u2699  Motor test", self.motor_test).grid(row=0, column=2, sticky="ew", padx=2)

    def _build_extruders(self, parent):
        e = self._panel(parent, "Extruders / filament")
        e.pack(fill="x")
        for c in range(1, 5):
            e.columnconfigure(c, weight=1, uniform="ext")
        top = ttk.Frame(e)
        top.grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 6))
        ttk.Label(top, text="Move").pack(side="left")
        self.e_amt = ttk.Spinbox(top, from_=1, to=100, width=4, increment=5)
        self.e_amt.set(10)
        self.e_amt.pack(side="left", padx=(6, 2))
        ttk.Label(top, text="mm", style="Dim.TLabel").pack(side="left", padx=(0, 12))
        ttk.Label(top, text="Load temp").pack(side="left")
        self.fil_temp = ttk.Spinbox(top, from_=170, to=240, width=4, increment=5)
        self.fil_temp.set(210)
        self.fil_temp.pack(side="left", padx=(6, 2))
        ttk.Label(top, text="°C", style="Dim.TLabel").pack(side="left")
        for i, (tool, name) in enumerate(((0, "Right"), (1, "Left"))):
            ttk.Label(e, text=name).grid(row=1 + i, column=0, sticky="w", pady=2)
            self._btn(e, "Retract", lambda t=tool: self.extrude(t, -1)).grid(row=1 + i, column=1, padx=2, sticky="ew")
            self._btn(e, "Extrude", lambda t=tool: self.extrude(t, +1)).grid(row=1 + i, column=2, padx=2, sticky="ew")
            self._btn(e, "⬇ Load", lambda t=tool: self.filament(t, "load")).grid(row=1 + i, column=3, padx=2, sticky="ew")
            self._btn(e, "⬆ Unload", lambda t=tool: self.filament(t, "unload")).grid(row=1 + i, column=4, padx=2, sticky="ew")
        self.keep_hot = tk.BooleanVar(value=False)
        ttk.Checkbutton(e, text="Keep nozzle hot afterwards", variable=self.keep_hot, style="Switch.TCheckbutton" if sv_ttk else "TCheckbutton").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self._btn(e, "■ Stop filament", lambda: self.worker.submit("stop_motion")).grid(
            row=3, column=3, columnspan=2, sticky="ew", padx=2, pady=(4, 0))

    def _build_log(self, parent):
        f = self._panel(parent, "Log")
        f.pack(fill="both", expand=True, pady=(10, 0))
        self.logbox = tk.Text(f, bg=COL["canvas"], fg=COL["fg"], relief="flat", height=10,
                              font=("Consolas", 9), wrap="word", state="disabled")
        self.logbox.pack(fill="both", expand=True)
        self.logbox.tag_configure("alarm", foreground=COL["danger"], font=("Consolas", 9, "bold"))
        self.logbox.tag_configure("ok", foreground=COL["ok"])

    # ======================= PREPARE TAB ===========================================
    def _build_prepare_tab(self, tab):
        tab.columnconfigure(0, weight=2, uniform="p")
        tab.columnconfigure(1, weight=3, uniform="p")
        tab.rowconfigure(0, weight=1)
        left = tk.Frame(tab, bg=COL["page"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = tk.Frame(tab, bg=COL["page"])
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        f = self._panel(left, "1. Choose an object")
        f.pack(fill="x")
        self.obj_var = tk.StringVar(value=list(OBJECTS)[0])
        cb = ttk.Combobox(f, textvariable=self.obj_var, values=list(OBJECTS), state="readonly",
                          font=("Segoe UI", 11))
        cb.pack(fill="x")
        cb.bind("<<ComboboxSelected>>", lambda e: self._build_params())
        self.obj_desc = ttk.Label(f, text="", style="Dim.TLabel", wraplength=430, justify="left")
        self.obj_desc.pack(fill="x", pady=(6, 0))

        self.param_panel = self._panel(left, "2. Settings")
        self.param_panel.pack(fill="x", pady=(10, 0))

        g = self._panel(left, "3. Generate")
        g.pack(fill="x", pady=(10, 0))
        nr = ttk.Frame(g, style="Panel.TFrame")
        nr.pack(fill="x")
        ttk.Label(nr, text="File name").pack(side="left")
        self.gen_name = ttk.Entry(nr, width=16)
        self.gen_name.pack(side="left", padx=6)
        ttk.Label(nr, text=".x3g", style="Dim.TLabel").pack(side="left")
        # Generate sits on the same row as the file name (fits small screens)
        self.gen_btn = GButton(nr, "\u2699  Generate", self.generate, padx=18)
        self.gen_btn.pack(side="right")
        p = self._panel(right, "Preview")
        p.pack(fill="both", expand=True)
        # result line + "Open in Print tab" live under the preview (always on screen)
        res = ttk.Frame(p)
        res.pack(side="bottom", fill="x", pady=(8, 0))
        self.gen_to_print = GButton(res, "📂  Open in Print tab", self._goto_print_generated,
                                    kind="tonal", size=10, padx=14, pady=6)
        self.gen_status = ttk.Label(res, text="", style="Dim.TLabel", wraplength=640, justify="left")
        self.gen_status.pack(side="left", fill="x", expand=True)
        self.gen_preview = tk.Label(p, bg=COL["canvas"], text="Generate an object to see its preview",
                                    fg=COL["dim"], font=("Segoe UI", 11))
        self.gen_preview.pack(fill="both", expand=True)
        self.gen_preview.bind("<Configure>", lambda e: self._show_image(self.gen_preview, "_gen_src"))
        self._build_params()

    def _build_params(self):
        self._remember_params()                        # keep the previous object's values
        for w in self.param_panel.winfo_children():
            w.destroy()
        name = self.obj_var.get()
        obj = OBJECTS[name]
        saved = self._obj_params.get(name, {})
        self._params_for = name
        self.obj_desc.configure(text=obj["desc"])
        self.param_widgets = {}
        pp = self.param_panel
        r0 = 0
        self.model_var = tk.StringVar(value=saved.get("_model", ""))
        if obj.get("model"):
            # the model file comes first: it is what the user picks before anything else
            ttk.Label(pp, text="3D model file", font=("Segoe UI Semibold", 10)).grid(
                row=0, column=0, sticky="w", pady=(0, 6))
            mf = ttk.Frame(pp)
            mf.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=(0, 6))
            ttk.Entry(mf, textvariable=self.model_var).pack(side="left", fill="x", expand=True)
            GButton(mf, "📂 Browse…", self.pick_model, kind="tonal", size=10, padx=12, pady=4).pack(
                side="left", padx=(6, 0))
            GButton(mf, "🔍 Fit check", self.fit_check, kind="tonal", size=10, padx=12, pady=4).pack(
                side="left", padx=(6, 0))
            GButton(mf, "🧩 Assembly…", self.fit_check_assembly, kind="tonal", size=10, padx=12, pady=4).pack(
                side="left", padx=(6, 0))
            r0 = 1
        params = obj["params"]
        two_col = len(params) > 5                       # long lists: two columns, no range hints
        for i, (flag, label, default, lo, hi, step) in enumerate(params):
            r, c = (r0 + i // 2, (i % 2) * 2) if two_col else (r0 + i, 0)
            ttk.Label(pp, text=label).grid(row=r, column=c, sticky="w", pady=3,
                                           padx=(0 if c == 0 else 16, 0))
            sb = ttk.Spinbox(pp, from_=lo, to=hi, increment=step, width=6 if two_col else 8)
            sb.set(saved.get(flag, default))
            sb.grid(row=r, column=c + 1, sticky="w", padx=8, pady=3)
            if not two_col:
                ttk.Label(pp, text="%g … %g" % (lo, hi), style="Dim.TLabel").grid(row=r, column=2, sticky="w")
            self.param_widgets[flag] = (sb, lo, hi)
        row = r0 + ((len(params) + 1) // 2 if two_col else len(params))
        self.ext_var = tk.StringVar(value=saved.get("_extruder", "left"))
        if obj["extruder"]:
            ttk.Label(pp, text="Extruder").grid(row=row, column=0, sticky="w", pady=3)
            ef = ttk.Frame(pp, style="Panel.TFrame")
            ef.grid(row=row, column=1, columnspan=3, sticky="w", padx=8)
            ttk.Radiobutton(ef, text="Left", value="left", variable=self.ext_var).pack(side="left")
            ttk.Radiobutton(ef, text="Right", value="right", variable=self.ext_var).pack(side="left", padx=8)
        pp.columnconfigure(3, weight=1)
        self._fix_bg(self.param_panel)
        self.gen_name.configure(state="normal")
        self.gen_name.delete(0, "end")
        self.gen_name.insert(0, saved.get("_name", obj["name"]))
        if obj.get("fixed_name"):
            self.gen_name.configure(state="disabled")

    def pick_model(self):
        p = filedialog.askopenfilename(
            title="Choose a 3D model",
            initialdir=os.path.dirname(self.model_var.get()) if self.model_var.get() else d4_paths.MODELS,
            filetypes=[("3D models", "*.stl *.3mf *.obj *.amf"), ("All files", "*.*")])
        if p:
            self.model_var.set(os.path.normpath(p))
            base = os.path.splitext(os.path.basename(p))[0].upper()
            base = "".join(ch for ch in base if ch.isalnum() or ch in "_-")[:24] or "MODEL"
            self.gen_name.delete(0, "end")
            self.gen_name.insert(0, base)

    # ---- fit check: printability of one design, or collisions between assembled parts --------
    def fit_check(self, files=None):
        if not files:
            m = self.model_var.get().strip().strip('"')
            if not os.path.isfile(m):
                messagebox.showinfo("Fit check", "Choose a 3D model file first (📂 Browse…).\n\n"
                                    "To check several parts together (for example a box and the boards "
                                    "inside it), use 🧩 Assembly….")
                return
            files = [m]
        args = list(files)
        if len(files) == 1:                             # check with the settings shown on screen
            for flag in ("supports", "brim", "scale"):
                if flag in self.param_widgets:
                    try:
                        args += ["--" + flag, "%g" % float(self.param_widgets[flag][0].get())]
                    except ValueError:
                        pass
        args.append("--no-open")
        what = os.path.basename(files[0]) if len(files) == 1 else "%d parts" % len(files)
        self.gen_status.configure(text="🔍 Fit check of %s running …" % what, foreground=COL["dim"])
        self.log("Fit check: %s" % ", ".join(os.path.basename(f) for f in files))
        threading.Thread(target=self._fit_worker, args=(args,), daemon=True).start()

    def fit_check_assembly(self):
        files = filedialog.askopenfilenames(
            title="Choose ALL parts of the assembly (exported in their assembled positions)",
            initialdir=os.path.dirname(self.model_var.get()) if self.model_var.get() else d4_paths.MODELS,
            filetypes=[("3D models", "*.stl *.3mf *.obj"), ("All files", "*.*")])
        if files:
            self.fit_check([os.path.normpath(f) for f in files])

    def _fit_worker(self, args):
        try:
            code, sout, serr = run_tool("fit_check.py", args, timeout=900)
        except Exception as e:                      # noqa: BLE001 - report anything to the user
            code, sout, serr = 1, "", str(e)
        self.events.put(("fit_done", code, sout or "", serr or ""))

    def on_fit_done(self, code, sout, serr):
        lines = sout.splitlines()
        result = next((ln for ln in lines if ln.startswith("RESULT:")), None)
        if result is None:
            result = "RESULT: FAIL - fit check could not run: " + (serr.strip().splitlines() or ["?"])[-1][:200]
        report = next((ln[len("REPORT: "):].strip() for ln in lines if ln.startswith("REPORT: ")), None)
        verdict = result.split()[1]
        issues = [ln.split(" ", 2)[2] for ln in lines
                  if ln.startswith(("CHECK WARN", "CHECK FAIL", "PAIR WARN", "PAIR FAIL"))]
        text = "%s Fit check: %s" % ({"OK": "✅", "WARN": "⚠"}.get(verdict, "❌"), result[len("RESULT: "):])
        if issues:
            text += "\n" + "\n".join("• " + i for i in issues[:6])
        if report:
            text += "\n3-D report opened in your browser."
        self.gen_status.configure(text=text, foreground={"OK": COL["ok"], "WARN": COL["warn"]}.get(verdict, COL["r"]))
        for ln in lines:
            if ln.startswith(("CHECK", "PAIR", "RESULT")):
                self.log(ln, "ok" if " OK " in ln or ln.startswith("RESULT: OK") else
                         ("alarm" if "FAIL" in ln else None))
        if report and os.path.exists(report):
            import webbrowser
            webbrowser.open("file:///" + os.path.abspath(report).replace("\\", "/"))

    def generate(self):
        obj = OBJECTS[self.obj_var.get()]
        name = obj["name"] if obj.get("fixed_name") else \
            "".join(ch for ch in self.gen_name.get().strip().upper() if ch.isalnum() or ch in "_-")[:24]
        if not name:
            messagebox.showerror("File name", "Enter a file name (letters, numbers, _ or -).")
            return
        args = ["--out", OUT]
        if not obj.get("fixed_name"):
            args += ["--name", name]
        if obj.get("model"):
            model = self.model_var.get().strip().strip('"')
            if not os.path.isfile(model):
                messagebox.showerror("3D model", "Choose a 3D model file (STL, 3MF or OBJ) first.")
                return
            if not d4_paths.find_prusaslicer():
                messagebox.showerror("Slicer engine missing",
                                     "The PrusaSlicer engine was not found.\n\nPut the PrusaSlicer folder in "
                                     "an 'engine' folder next to the app, or install PrusaSlicer.")
                return
            args += ["--model", model]
        for flag, (sb, lo, hi) in self.param_widgets.items():
            try:
                v = float(sb.get())
            except ValueError:
                messagebox.showerror("Settings", "'%s' is not a number." % flag)
                return
            v = max(lo, min(hi, v))
            args += ["--" + flag, ("%d" % v) if v == int(v) and flag not in ("z-offset",) else ("%g" % v)]
        args += obj["fixed"]
        if obj["extruder"]:
            args += ["--only", self.ext_var.get()]
        self.gen_btn.state(["disabled"])
        self.gen_to_print.pack_forget()
        self.gen_status.configure(text="Generating %s.x3g …" % name, foreground=COL["dim"])
        threading.Thread(target=self._generate_worker, args=(obj["script"], args, name),
                         daemon=True).start()

    def _generate_worker(self, script, args, name):
        path = os.path.join(OUT, name + ".x3g")
        try:
            code, sout, serr = run_tool(script, args)
            if code != 0 or not os.path.exists(path):
                self.events.put(("gen_done", False, name, ((serr or "") + "\n" + (sout or "")).strip()[-900:]))
                return
            ok, ctext = self._run_checker(path)
            prev = os.path.join(PREV, name + ".png")
            rp.render(path, out=prev)
            st = s3g.x3g_stats(s3g.split_x3g(open(path, "rb").read()))
            short = "Print time ≈ %s + heat-up   ·   filament R %.0f / L %.0f mm   ·   object height %.1f mm" % (
                fmt_min(st["time_s"]), st["fil"][0], st["fil"][1], st["zprint"])
            if not ok:     # on failure show the checker's problem lines
                short += "\n" + "\n".join(ln for ln in ctext.splitlines() if "cmd" in ln or "RESULT" in ln)[:600]
            self.events.put(("gen_done", ok, name, short))
        except Exception as e:                      # noqa: BLE001 - report anything to the user
            self.events.put(("gen_done", False, name, "Error: %s" % e))

    def on_gen_done(self, ok, name, text):
        self.gen_btn.state(["!disabled"])
        path = os.path.join(OUT, name + ".x3g")
        self._gen_name_done = name
        if ok:
            self.gen_status.configure(text="✅ %s.x3g ready - safety check passed.\n%s" % (name, text),
                                      foreground=COL["ok"])
            self.gen_to_print.pack(side="right", padx=(10, 0))
        else:
            self.gen_status.configure(text="❌ %s: problem.\n%s" % (name, text), foreground=COL["r"])
        prev = os.path.join(PREV, name + ".png")
        if os.path.exists(prev):
            self._gen_src = prev
            self._show_image(self.gen_preview, "_gen_src")
        self.log("Generated %s.x3g (%s)" % (name, "check OK" if ok else "CHECK FAILED"), "ok" if ok else "alarm")
        self._check_cache.pop(path, None)
        self.refresh_library(select=path)

    def _goto_print_generated(self):
        self.nb.select(self.tab_print)
        self.refresh_library(select=os.path.join(OUT, self._gen_name_done + ".x3g"))

    # ======================= PRINT TAB =============================================
    def _build_print_tab(self, tab):
        tab.columnconfigure(0, weight=3, uniform="q")
        tab.columnconfigure(1, weight=2, uniform="q")
        tab.rowconfigure(0, weight=1)
        left = tk.Frame(tab, bg=COL["page"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = tk.Frame(tab, bg=COL["page"])
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        lib = self._panel(left, "Print files (output folder)")
        lib.pack(fill="both", expand=True)
        cols = ("time", "fil", "zhome", "check", "date")
        self.tree = ttk.Treeview(lib, columns=cols, show="tree headings", selectmode="browse", height=10)
        self.tree.heading("#0", text="File")
        self.tree.column("#0", width=200)
        for c, t, w in (("time", "Print time", 90), ("fil", "Filament R / L", 120),
                        ("zhome", "Z homing", 90), ("check", "Safety check", 110), ("date", "Modified", 120)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.on_select_file())
        bf = ttk.Frame(lib, style="Panel.TFrame")
        bf.pack(fill="x", pady=(8, 0))
        ttk.Button(bf, text="↻ Refresh", command=self.refresh_library).pack(side="left")
        ttk.Button(bf, text="📁 Open folder", command=lambda: os.startfile(OUT)).pack(side="left", padx=6)
        ttk.Button(bf, text="➕ Add file…", command=self.add_file).pack(side="left")
        ttk.Button(bf, text="🗑 Delete", command=self.delete_file).pack(side="left", padx=6)

        info = self._panel(left, "Selected file")
        info.pack(fill="x", pady=(10, 0))
        self.file_info = ttk.Label(info, text="Select a file", style="Dim.TLabel", justify="left",
                                   wraplength=700, font=("Consolas", 9))
        self.file_info.pack(fill="x")

        prev = self._panel(right, "Preview")
        prev.pack(fill="both", expand=True)
        self.file_preview = tk.Label(prev, bg=COL["canvas"], text="", fg=COL["dim"])
        self.file_preview.pack(fill="both", expand=True)
        self.file_preview.bind("<Configure>", lambda e: self._show_image(self.file_preview, "_file_src"))

        job = self._panel(right, "Print job")
        job.pack(fill="x", pady=(10, 0))
        self.print_btn = GButton(job, "\u25b6  Print selected file", self.start_print, size=12, pady=10)
        self._controls.append(self.print_btn)
        self.print_btn.pack(fill="x")
        row = ttk.Frame(job, style="Panel.TFrame")
        row.pack(fill="x", pady=6)
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)
        self.pause_btn = self._btn(row, "⏸ Pause / Resume", lambda: self.worker.submit("pause"))
        self.pause_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.cancel_btn = self._btn(row, "✖ Cancel print", self.cancel_print)
        self.cancel_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self.job_name = ttk.Label(job, text="No print running", style="Big.TLabel")
        self.job_name.pack(anchor="w")
        self.prog = GBar(job, color=COL["accent"], height=10)
        self.prog.pack(fill="x", pady=(8, 6))
        grid = ttk.Frame(job, style="Panel.TFrame")
        grid.pack(fill="x")
        self.job_vals = {}
        for i, (k, lab) in enumerate((("pct", "Done"), ("elapsed", "Elapsed"), ("left", "Time left"),
                                      ("z", "Height (Z)"), ("fil", "Filament used"), ("noz", "Nozzle"))):
            cell = ttk.Frame(grid, style="Panel.TFrame")
            cell.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 18), pady=4)
            ttk.Label(cell, text=lab, style="Dim.TLabel").pack(anchor="w")
            v = ttk.Label(cell, text="—", font=("Segoe UI", 13, "bold"))
            v.pack(anchor="w")
            self.job_vals[k] = v

    # ---- library -------------------------------------------------------------------
    def _stats(self, path):
        mt = os.path.getmtime(path)
        c = self._stats_cache.get(path)
        if c and c[0] == mt:
            return c[1]
        st = s3g.x3g_stats(s3g.split_x3g(open(path, "rb").read()))
        self._stats_cache[path] = (mt, st)
        return st

    def refresh_library(self, select=None):
        if not hasattr(self, "tree"):
            return
        cur = select or (self.tree.selection()[0] if self.tree.selection() else None)
        self.tree.delete(*self.tree.get_children())
        files = [os.path.join(OUT, f) for f in os.listdir(OUT) if f.lower().endswith(".x3g")
                 and not f.startswith("_")] if os.path.isdir(OUT) else []
        files.sort(key=os.path.getmtime, reverse=True)
        for p in files:
            try:
                st = self._stats(p)
            except Exception:                       # noqa: BLE001 - unreadable file
                self.tree.insert("", "end", iid=p, text=os.path.basename(p),
                                 values=("?", "?", "?", "unreadable", ""))
                continue
            cc = self._check_cache.get(p)
            check = ("✅ OK" if cc[1] else "❌ FAIL") if cc and cc[0] == os.path.getmtime(p) else "…"
            zh = {"slow": "slow ✓", "fast": "FAST ⚠", None: "none"}[st["z_home"]]
            self.tree.insert("", "end", iid=p, text="  " + os.path.basename(p), values=(
                fmt_min(st["time_s"]), "%.0f / %.0f mm" % tuple(st["fil"]), zh, check,
                time.strftime("%d %b %H:%M", time.localtime(os.path.getmtime(p)))))
        if cur and self.tree.exists(cur):
            self.tree.selection_set(cur)
            self.tree.see(cur)

    def _run_checker(self, path):
        code, sout, serr = run_tool("check_x3g.py", [path], timeout=300)

        class _R:
            stdout = sout
        r = _R()
        lines = [ln for ln in r.stdout.splitlines() if not ln.startswith(("commands", "command types"))]
        text = "\n".join(lines[:14])
        ok = "RESULT        : OK" in r.stdout
        self._check_cache[path] = (os.path.getmtime(path), ok, text)
        return ok, text

    def on_select_file(self):
        sel = self.tree.selection()
        if not sel:
            return
        path = sel[0]
        st = self._stats(path)
        self._show_file_info(path, st)
        prev = os.path.join(PREV, os.path.splitext(os.path.basename(path))[0] + ".png")
        stale = not os.path.exists(prev) or os.path.getmtime(prev) < os.path.getmtime(path)
        cc = self._check_cache.get(path)
        need_check = not (cc and cc[0] == os.path.getmtime(path))
        if stale or need_check:
            self.file_preview.configure(image="", text="Rendering preview / checking …")
            threading.Thread(target=self._prepare_file_worker, args=(path, prev, stale, need_check),
                             daemon=True).start()
        else:
            self._file_src = prev
            self._show_image(self.file_preview, "_file_src")

    def _prepare_file_worker(self, path, prev, stale, need_check):
        try:
            if stale:
                rp.render(path, out=prev)
            if need_check:
                self._run_checker(path)
        except Exception as e:                      # noqa: BLE001
            self.events.put(("log", "Preview/check failed for %s: %s" % (os.path.basename(path), e)))
        self.events.put(("file_ready", path, prev))

    def on_file_ready(self, path, prev):
        sel = self.tree.selection()
        if self.tree.exists(path):
            cc = self._check_cache.get(path)
            if cc:
                vals = list(self.tree.item(path, "values"))
                vals[3] = "✅ OK" if cc[1] else "❌ FAIL"
                self.tree.item(path, values=vals)
        if sel and sel[0] == path:
            self._show_file_info(path, self._stats(path))
            if os.path.exists(prev):
                self._file_src = prev
                self._show_image(self.file_preview, "_file_src")

    def _show_file_info(self, path, st):
        cc = self._check_cache.get(path)
        temps = ", ".join("%s %d°C" % ("Right" if t == 0 else "Left", c) for t, c in sorted(st["temps"].items()) if c)
        lines = [
            "%s    %d commands" % (os.path.basename(path), st["n"]),
            "Print time ≈ %s (+ heat-up)    filament R %.0f mm / L %.0f mm    object height %.1f mm" % (
                fmt_min(st["time_s"]), st["fil"][0], st["fil"][1], st["zprint"]),
            "Nozzles: %s    Bed: %s" % (temps or "off", ("%d°C ⚠ bed sensor faulty!" % st["bed"]) if st["bed"] else "not heated"),
            "Z homing: %s" % {"slow": "slow 5 mm/s (safe)", "fast": "FAST - caused cut-outs on this printer ⚠",
                              None: "none (bed height used as is)"}[st["z_home"]],
        ]
        if st["t1_change"]:
            lines.append("⚠ uses firmware T1 tool change - bogus offset on this printer!")
        lines.append("")
        lines.append(cc[2] if cc else "Safety check: running …")
        self.file_info.configure(text="\n".join(lines))

    def add_file(self):
        p = filedialog.askopenfilename(filetypes=[("x3g print files", "*.x3g")])
        if p:
            import shutil
            dst = os.path.join(OUT, os.path.basename(p))
            if os.path.abspath(p) != os.path.abspath(dst):
                shutil.copy(p, dst)
            self.refresh_library(select=dst)

    def delete_file(self):
        sel = self.tree.selection()
        if not sel:
            return
        p = sel[0]
        if messagebox.askyesno("Delete", "Delete %s ?" % os.path.basename(p)):
            for f in (p, os.path.splitext(p)[0] + ".gcode",
                      os.path.join(PREV, os.path.splitext(os.path.basename(p))[0] + ".png")):
                try:
                    os.remove(f)
                except OSError:
                    pass
            self.refresh_library()

    # ---- printing ------------------------------------------------------------------
    def start_print(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Print", "Select a file in the list first.")
            return
        path = sel[0]
        if not self.connected:
            messagebox.showerror("Print", "Printer is not connected.")
            return
        st = self._stats(path)
        cc = self._check_cache.get(path)
        if not (cc and cc[0] == os.path.getmtime(path)):
            self.config(cursor="watch")
            self.update()
            self._run_checker(path)
            self.config(cursor="")
            cc = self._check_cache.get(path)
        if not cc[1]:
            messagebox.showerror("Safety check failed", "This file failed the safety check and will not "
                                 "be printed:\n\n" + cc[2])
            return
        if st["bed"] and not self.bed_ok.get():
            messagebox.showerror("Bed heating blocked", "This file heats the bed to %d °C, but the bed "
                                 "sensor is faulty. The print would wait forever and overheat the bed.\n\n"
                                 "Use a file with an unheated bed." % st["bed"])
            return
        if st["t1_change"]:
            messagebox.showerror("Unsafe file", "This file uses a firmware T1 tool change. Your printer's "
                                 "stored T1 offset is wrong (~228 mm) - the head would crash.")
            return
        if st["z_home"] == "fast" and not messagebox.askyesno(
                "Fast Z homing", "This file homes Z FAST. On this printer fast Z homing caused board "
                "resets. Print anyway?"):
            return
        if not self._checklist(path, st):
            return
        self.print_stats = st
        self.printing = True
        self.heat_phase = None
        self.job_file = os.path.basename(path)
        self.prog.set(0)
        self.job_name.configure(text="⏳ Homing, then heating - " + self.job_file)
        for v in self.job_vals.values():
            v.configure(text="—")
        self.worker.submit("print", path)
        self.log("Print started: %s" % os.path.basename(path), "ok")

    def _checklist(self, path, st):
        uses = [n for t, n in ((0, "RIGHT"), (1, "LEFT")) if st["fil"][t] > 1]
        items = ["Bed is clean and has blue tape or glue stick (bed is not heated)",
                 "Old prints are removed from the bed"]
        if uses:
            items.append("Filament is loaded in the %s extruder%s" % (" and ".join(uses), "s" if len(uses) > 1 else ""))
        if st["z_home"] is None and st["zmax"] < 60:
            items.append("Bed is LOW (at least 2 cm below the nozzles) - this job does not move the bed")
        items.append("I am at the printer and can press EMERGENCY STOP / power off")
        win = tk.Toplevel(self)
        win.title("Before printing")
        win.configure(bg=COL["panel"])
        win.transient(self)
        win.grab_set()
        tk.Label(win, text="Before printing %s" % os.path.basename(path), bg=COL["panel"], fg=COL["fg"],
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(win, text="Time ≈ %s + heat-up    filament R %.0f / L %.0f mm" % (fmt_min(st["time_s"]), *st["fil"]),
                 bg=COL["panel"], fg=COL["dim"]).pack(anchor="w", padx=16)
        vars_ = []
        res = {"ok": False}
        box = tk.Frame(win, bg=COL["panel"])
        box.pack(fill="x", padx=16, pady=(8, 0))
        bf = tk.Frame(win, bg=COL["panel"])
        bf.pack(fill="x", padx=16, pady=14)

        def ok():
            res["ok"] = True
            win.destroy()
        go = GButton(bf, "\u25b6  Start print", ok)
        go.pack(side="right")
        ttk.Button(bf, text="Cancel", command=win.destroy).pack(side="right", padx=8)

        def upd():
            go.state(["!disabled"] if all(v.get() for v in vars_) else ["disabled"])
        for it in items:
            v = tk.BooleanVar(value=False)
            vars_.append(v)
            ttk.Checkbutton(box, text=it, variable=v, command=upd).pack(anchor="w", pady=3)
        upd()
        win.geometry("+%d+%d" % (self.winfo_rootx() + 200, self.winfo_rooty() + 150))
        self.wait_window(win)
        return res["ok"]

    def cancel_print(self):
        if self.printing and messagebox.askyesno("Cancel print", "Stop the print now? "
                                                 "Motion stops and heaters switch off."):
            self.worker.submit("cancel")

    # ======================= ACTIONS (printer tab) ==================================
    def set_controls(self, on):
        for b in self._controls:
            b.state(["!disabled"] if on else ["disabled"])

    def refresh_ports(self, autoconnect=False):
        ports = s3g.find_ports()
        self._ports = ports
        self.port_box["values"] = [p[1] for p in ports]
        if ports:
            self.port_box.current(0)
            if autoconnect and ports[0][2]:
                self.toggle_connect()
        else:
            self.port_var.set("printer off?")

    def watch_ports(self):
        try:
            if not self.connected and not self.user_disconnected and time.time() > self._connecting_until:
                ports = s3g.find_ports()
                if [p[0] for p in ports] != [p[0] for p in getattr(self, "_ports", [])]:
                    self.refresh_ports()
                printer = next((p for p in ports if p[2]), None)
                if printer:
                    self._connecting_until = time.time() + 8
                    self.log("Printer found on %s - connecting…" % printer[0])
                    self.worker.submit("connect", printer[0])
        finally:
            self.after(3000, self.watch_ports)

    def toggle_connect(self):
        if self.connected:
            self.user_disconnected = True
            self.worker.submit("disconnect")
            return
        self.user_disconnected = False
        idx = self.port_box.current()
        if idx < 0 or not self._ports:
            self.refresh_ports()
            return
        port = self._ports[idx][0]
        self._connecting_until = time.time() + 8
        self.log("Connecting to %s…" % port)
        self.worker.submit("connect", port)

    def estop(self):
        self.worker.emergency_stop()
        self.log("EMERGENCY STOP requested", "alarm")

    def set_heater(self, key, value=None):
        try:
            c = int(float(self.t_entry[key].get())) if value is None else value
        except ValueError:
            return
        if key == "bed":
            if c > 0 and not self.bed_ok.get():
                messagebox.showwarning("Bed heating blocked",
                                       "The bed temperature sensor is faulty.\n"
                                       "Heating the bed with a broken sensor can overheat it.\n"
                                       "Repair the sensor, then tick 'Bed sensor repaired'.")
                return
            self.worker.submit("set_bed", max(0, min(110, c)))
        else:
            self.worker.submit("set_temp", 0 if key == "r" else 1, max(0, min(240, c)))

    def preset(self, c):
        for key in ("r", "l"):
            self.t_entry[key].set(c)
            self.set_heater(key)

    def jog(self, axis, sign):
        self.worker.submit("jog", axis, self.step.get() * sign, 8.0 if axis == 2 else 30.0)

    def extrude(self, tool, sign):
        try:
            mm = float(self.e_amt.get())
        except ValueError:
            return
        cur = self._last_temps.get(("r", "l")[tool])
        if cur is not None and cur < COLD_EXTRUDE_C:
            if not messagebox.askyesno("Nozzle is cold",
                                       "%s nozzle is %d °C (< %d °C).\nPushing filament into a cold nozzle grinds it.\n\n"
                                       "Run the motor for only 2 mm as a motor test?" % (("Right", "Left")[tool], cur, COLD_EXTRUDE_C)):
                return
            mm = 2.0
        self.worker.submit("extrude", tool, sign * mm)

    def filament(self, tool, action):
        try:
            temp = max(170, min(240, int(float(self.fil_temp.get()))))
        except ValueError:
            return
        side = ("RIGHT", "LEFT")[tool]
        if action == "load":
            text = ("LOAD filament - %s extruder\n\n1. Nozzle heats to %d °C.\n2. The extruder turns slowly "
                    "for about 40 s.\n3. Push the filament (cut straight) into the top of the extruder until "
                    "the gears grab it.\n4. When plastic comes out, press '■ Stop filament'.\n\nStart?" % (side, temp))
        else:
            text = ("UNLOAD filament - %s extruder\n\n1. Nozzle heats to %d °C.\n2. Pushes 8 mm, then pulls "
                    "back 100 mm.\n3. When the motor stops, pull the filament out.\n\nStart?" % (side, temp))
        if messagebox.askokcancel(action.capitalize() + " filament", text):
            self.worker.submit(action, tool, temp, self.keep_hot.get())

    def home_z(self):
        if messagebox.askokcancel("Home Z", "The bed moves UP until it presses the Z switch.\n"
                                  "Be ready to press EMERGENCY STOP (Esc)."):
            self.worker.submit("home_z")

    def home_all(self):
        if messagebox.askokcancel("Home all", "Head goes to back-right, then the bed moves UP to the Z switch.\n"
                                  "Be ready to press EMERGENCY STOP (Esc)."):
            self.worker.submit("home_all")

    def motor_test(self):
        if messagebox.askokcancel("Motor test", "Moves X ±20 mm, Y ±20 mm, bed ±10 mm, then each extruder ±2 mm.\n"
                                  "Heaters are switched off. Keep hands clear."):
            self.worker.submit("motor_test")

    # ======================= EVENTS ================================================
    def pump(self):
        try:
            while True:
                ev = self.events.get_nowait()
                getattr(self, "on_" + ev[0])(*ev[1:])
        except queue.Empty:
            pass
        self.after(100, self.pump)

    def on_log(self, msg):
        self.log(msg, "alarm" if msg.startswith(("ERROR", "WARNING")) else None)

    def on_alarm(self, msg):
        self.log(msg, "alarm")
        messagebox.showerror("Printer alarm", msg)

    def on_connected(self, port, fw):
        self.connected = True
        self.conn_btn.configure(text="Disconnect")
        self.conn_lbl.configure(text="● Connected  %s  (%s)" % (port, fw), fg=COL["ok"])
        self.set_controls(True)
        self.log("Connected to %s, firmware %s" % (port, fw), "ok")

    def on_disconnected(self, reason):
        was = self.connected
        self.connected = False
        self.conn_btn.configure(text="Connect")
        self.conn_lbl.configure(text="● Disconnected", fg=COL["r"] if was else COL["dim"])
        self.board_lbl.configure(text="")
        self.set_controls(False)
        self.log(reason, "alarm" if was else None)

    def on_progress(self, i, n, elapsed):
        st = self.print_stats
        frac = i / max(1, n)
        left = None
        if st and st["cum"] and st["time_s"] > 0:
            done_t = st["cum"][min(i, len(st["cum"])) - 1] if i else 0.0
            frac = done_t / st["time_s"]
            left = st["time_s"] - done_t
        self.prog.set(frac)
        self.job_vals["pct"].configure(text="%d %%" % (100 * frac))
        self.job_vals["elapsed"].configure(text=fmt_min(elapsed))
        self.job_vals["left"].configure(text=fmt_min(left) if left is not None else "—")

    def on_phase(self, kind, tool):
        """Worker tells us the printer is waiting for heat (kind 'heat') or printing again."""
        if kind == "heat":
            self.heat_phase = tool
            self._show_heat()
            self.log("Heating the %s nozzle - printing starts when it is hot"
                     % ("right" if tool == 0 else "left"))
        else:
            if self.heat_phase is not None:
                self.log("Nozzle hot - printing", "ok")
            self.heat_phase = None
            self.job_name.configure(text="▶ Printing - " + getattr(self, "job_file", ""))

    def _show_heat(self):
        tool = getattr(self, "heat_phase", None)
        if tool is None or not self.printing:
            return
        key = "r" if tool == 0 else "l"
        t = getattr(self, "_last_temps", {}) or {}
        cur, tgt = t.get(key), t.get(key + "_t")
        side = "right" if tool == 0 else "left"
        temp = " %s° → %s°" % (cur, tgt) if cur is not None and tgt else ""
        self.job_name.configure(text="🔥 Heating %s nozzle%s - print starts when hot" % (side, temp))

    def on_print_done(self, ok, msg):
        self.printing = False
        self.heat_phase = None
        self.job_name.configure(text=("✅ " if ok else "⚠ ") + msg)
        if ok:
            self.prog.set(1.0, color=COL["ok"])
            self.job_vals["pct"].configure(text="100 %")
            self.job_vals["left"].configure(text="0:00")
        self.log(msg, "ok" if ok else "alarm")
        if not ok:
            messagebox.showwarning("Print stopped", msg)

    def on_status(self, s):
        t = s["t"]
        self._last_temps = t
        for key in ("r", "l", "bed"):
            v, tg = t.get(key), t.get(key + "_t")
            self.t_lbl[key].configure(text="%s°" % (v if v is not None else "---"))
            if tg:
                state = "→ %d°" % tg if v is not None and v < tg - 3 else "✓ %d°" % tg
            else:
                state = "off"
            self.t_tgt[key].configure(text=state, foreground=COL["warn"] if tg else COL["dim"])
            self.t_bar[key].set(max(0, v or 0), max(tg or 0, 250 if key != "bed" else 110))
        now = time.time()
        self.hist.append((now, t.get("r"), t.get("l"), t.get("bed"), t.get("r_t"), t.get("l_t"), t.get("bed_t")))
        while self.hist and now - self.hist[0][0] > CHART_SPAN_S:
            self.hist.popleft()
        self.draw_chart()
        es = s["es"]
        for bit in self.sw:
            self._sw_text(bit, bool(es >> bit & 1))
        if self.es_last is not None and es != self.es_last:
            self.es_changes.append(now)
        self.es_last = es
        while self.es_changes and now - self.es_changes[0] > 10:
            self.es_changes.popleft()
        self.sw_warn.configure(text="⚠ switch signal changing a lot - loose wire?" if len(self.es_changes) > 6 else "")
        p = s["pos"]
        self._last_pos = p
        self.pos_lbl.configure(text="X %.2f   Y %.2f   Z %.2f\nRight ext %.1f   Left ext %.1f  (mm)" % tuple(p))
        self.homed_lbl.configure(text="Homed" if s["homed"] else "Not homed - positions relative to power-on",
                                 foreground=COL["ok"] if s["homed"] else COL["dim"])
        st = s["board"]
        flags = [n for b, n in s3g.BOARD_FLAGS if st and st & b]
        self.board_lbl.configure(text="Board: " + (", ".join(flags) if flags else "idle"),
                                 fg=COL["warn"] if any(f in flags for f in ("HEAT_SHUTDOWN", "POWER_ERROR")) else COL["dim"])
        self.status_temps.configure(text="R %s°C   L %s°C   bed %s°C   Z %.2f" % (
            t.get("r"), t.get("l"), t.get("bed"), p[2]))
        if self.printing:
            self._show_heat()
            self.job_vals["z"].configure(text="%.2f mm" % p[2])
            self.job_vals["fil"].configure(text="R %.0f / L %.0f mm" % (max(0, p[3]), max(0, p[4])))
            self.job_vals["noz"].configure(text="R %s° / L %s°" % (t.get("r"), t.get("l")))

    # ======================= MISC ==================================================
    def _show_image(self, label, attr):
        src = getattr(self, attr, None)
        if not src or not os.path.exists(src):
            return
        w, h = max(50, label.winfo_width() - 8), max(50, label.winfo_height() - 8)
        try:
            img = Image.open(src)
            img.thumbnail((w, h), Image.LANCZOS)
            tkimg = ImageTk.PhotoImage(img)
        except Exception:                           # noqa: BLE001
            return
        label.configure(image=tkimg, text="")
        label._img = tkimg                          # keep a reference

    def draw_chart(self):
        c = self.chart
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return
        ml, mr, mt, mb = 38, 8, 8, 20
        tmax = 250
        now = time.time()
        X = lambda t: ml + (w - ml - mr) * (1 - (now - t) / CHART_SPAN_S)
        Y = lambda v: mt + (h - mt - mb) * (1 - v / tmax)
        for v in range(0, tmax + 1, 50):
            c.create_line(ml, Y(v), w - mr, Y(v), fill=COL["grid"])
            c.create_text(ml - 6, Y(v), text=str(v), fill=COL["dim"], anchor="e", font=("Segoe UI", 8))
        for m in range(0, 6):
            c.create_text(X(now - m * 60), h - 6, text="-%dm" % m if m else "now", fill=COL["dim"],
                          anchor="e" if m == 0 else "center", font=("Segoe UI", 8))
        for idx, key in ((1, "r"), (2, "l"), (3, "bed")):
            tg = [(X(r[0]), Y(r[idx + 3])) for r in self.hist if r[idx + 3]]
            if len(tg) > 1:
                c.create_line(*sum(tg, ()), fill=COL[key], dash=(3, 3))
            pts = [(X(r[0]), Y(max(0, min(tmax, r[idx])))) for r in self.hist if r[idx] is not None]
            if len(pts) > 1:
                c.create_line(*sum(pts, ()), fill=COL[key], width=2)

    def log(self, msg, tag=None):
        line = time.strftime("%H:%M:%S  ") + msg + "\n"
        self.logbox.configure(state="normal")
        if tag:
            self.logbox.insert("end", line, tag)
        else:
            self.logbox.insert("end", line)
        self.logbox.see("end")
        self.logbox.configure(state="disabled")
        self.status_lbl.configure(text=msg[:140], fg=COL["r"] if tag == "alarm" else COL["dim"])
        try:
            with open(LOGFILE, "a", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d ") + line)
        except OSError:
            pass

    def change_theme(self):
        choice = self.theme_var.get()
        if choice == THEME_CHOICE:
            return
        if self.printing:
            messagebox.showinfo("Theme", "Change the theme after the print has finished.")
            self.theme_var.set(THEME_CHOICE)
            return
        save_settings(theme=choice)
        self.save_ui()                                  # keep everything across the restart
        self.log("Theme set to %s - restarting the window" % choice)
        # restart this program; the printer itself is not touched (heaters/motion unchanged)
        cmd = [sys.executable] if d4_paths.FROZEN else [sys.executable, os.path.abspath(__file__)]
        subprocess.Popen(cmd, cwd=d4_paths.EXE_DIR if d4_paths.FROZEN else TOOLS)
        self.worker.quit.set()
        self.destroy()

    def on_close(self):
        if self.printing and not messagebox.askyesno(
                "Print running", "A USB print is running. Closing stops sending and the print will stall.\n"
                "Stop the print and close?"):
            return
        if self.printing:
            self.worker.emergency_stop()
            time.sleep(0.5)
        self.save_ui()
        self.worker.quit.set()
        self.destroy()


def selftest():
    """Duplicator4Studio.exe --selftest : check the bundled tools work, write selftest.txt."""
    import tempfile
    lines = ["Duplicator 4 Studio self-test  (frozen=%s)" % d4_paths.FROZEN,
             "data folder : %s" % d4_paths.DATA,
             "slicer      : %s" % d4_paths.find_prusaslicer()]
    ok_all = True
    with tempfile.TemporaryDirectory() as tmp:
        tests = [("make_left_demo.py", ["--out", tmp], "DEMO_LEFT"),
                 ("make_vase.py", ["--out", tmp, "--name", "ST_VASE", "--height", "6"], "ST_VASE")]
        model = os.path.join(d4_paths.DATA, "models", "test_nut.stl")
        if os.path.exists(model) and d4_paths.find_prusaslicer():
            tests.append(("slice_model.py", ["--out", tmp, "--name", "ST_NUT", "--model", model], "ST_NUT"))
        for script, args, name in tests:
            code, sout, serr = run_tool(script, args)
            x3g = os.path.join(tmp, name + ".x3g")
            ccode, cout, _ = run_tool("check_x3g.py", [x3g]) if os.path.exists(x3g) else (1, "", "")
            ok = code == 0 and "RESULT        : OK" in cout
            ok_all &= ok
            lines.append("%-18s %s  %s" % (script, "PASS" if ok else "FAIL",
                                           (serr.strip() or sout.strip().splitlines()[-1:] or [""])[-1][:120]
                                           if not ok else ""))
        # fit check (needs the bundled 3-D libraries + viewer)
        if os.path.exists(model):
            rep = os.path.join(tmp, "fit.html")
            code, sout, serr = run_tool("fit_check.py", [model, "--no-open", "--out", rep])
            ok = "RESULT:" in sout and os.path.exists(rep) and os.path.getsize(rep) > 100000
            ok_all &= ok
            lines.append("%-18s %s  %s" % ("fit_check.py", "PASS" if ok else "FAIL",
                                           "" if ok else (serr.strip() or sout.strip())[-160:]))
    lines.append("OVERALL: %s" % ("PASS" if ok_all else "FAIL"))
    with open(os.path.join(d4_paths.OUT, "selftest.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return 0 if ok_all else 1


def _crash_log(text):
    try:
        with open(os.path.join(d4_paths.OUT, "crash_log.txt"), "a", encoding="utf-8") as fh:
            fh.write(time.strftime("\n==== %Y-%m-%d %H:%M:%S ====\n") + text)
    except OSError:
        pass


def _report_tk_error(self, exc, val, tb):
    """Errors inside button handlers / timers: log them and keep the app running."""
    import traceback
    text = "".join(traceback.format_exception(exc, val, tb))
    _crash_log(text)
    try:
        self.log("ERROR: %s: %s  (details in output\\crash_log.txt)" % (exc.__name__, val), "alarm")
    except Exception:                               # noqa: BLE001
        pass


App.report_callback_exception = _report_tk_error


if __name__ == "__main__":
    if sys.stderr is None:                          # windowed .exe has no console
        sys.stderr = open(os.path.join(d4_paths.OUT, "stderr_log.txt"), "a", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    try:
        App().mainloop()
    except Exception:                               # noqa: BLE001 - startup failure
        import traceback
        tb = traceback.format_exc()
        _crash_log(tb)
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("Duplicator 4 Studio", "The app could not start:\n\n%s\n\nDetails: "
                                 "output\\crash_log.txt" % tb.strip().splitlines()[-1])
        except Exception:                           # noqa: BLE001
            pass
        sys.exit(1)
