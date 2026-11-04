"""
Wanhao Duplicator 4 - USB control panel (Sailfish / s3g).

    python tools/d4_gui.py        (or double-click D4_Control.bat)

Features: live temperatures + chart, limit-switch indicators, jog / home,
heater control with a safety watchdog, extruder test, USB printing of .x3g
files, and an EMERGENCY STOP (also: Esc key).
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import collections
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import s3g_link as s3g

POLL_IDLE_S = 0.5
POLL_PRINT_S = 1.0
CHART_SPAN_S = 300
COLD_EXTRUDE_C = 170

# Heater watchdog: a heater with a target must rise this much within this time
WD_RISE_C, WD_WINDOW_S = 8, 90


# =============================================================================
# Worker thread: the only code that touches the serial port
# =============================================================================
class Worker(threading.Thread):
    def __init__(self, events):
        super().__init__(daemon=True)
        self.events = events
        self.jobs = queue.Queue()
        self.estop = threading.Event()
        self.quit = threading.Event()
        self.link = None
        self.port = None
        self.auto_reconnect = True
        self.print_job = None          # dict(cmds, i, name, t0)
        self.wd = {}                   # heater -> (t_start, temp_start)
        self.homed = False
        self._last_poll = 0.0

    # ---- public (called from GUI thread) ---------------------------------
    def submit(self, name, *args):
        self.jobs.put((name, args))

    def emergency_stop(self):
        self.estop.set()

    # ---- helpers -----------------------------------------------------------
    def post(self, *ev):
        self.events.put(ev)

    def log(self, msg):
        self.post("log", msg)

    def _abort_check(self):
        return self.estop.is_set()

    def _drop_link(self, reason):
        if self.link:
            self.link.close()
        self.link = None
        if self.print_job:
            self.post("print_done", False, "USB link lost during print (printer reset or power loss)")
            self.print_job = None
        self.wd.clear()
        self.post("disconnected", reason)

    # ---- main loop ---------------------------------------------------------
    def run(self):
        while not self.quit.is_set():
            try:
                if self.estop.is_set():
                    self._do_estop()
                try:
                    name, args = self.jobs.get(timeout=0.02)
                    self._run_job(name, args)
                except queue.Empty:
                    pass
                if self.link is None:
                    self._maybe_reconnect()
                    continue
                if self.print_job:
                    self._stream_step()
                interval = POLL_PRINT_S if self.print_job else POLL_IDLE_S
                if time.time() - self._last_poll > interval:
                    self._poll()
            except s3g.PrinterGone as e:
                self._drop_link("printer disconnected: %s" % e)
            except s3g.NoResponse as e:
                self.log("WARNING: %s" % e)
            except Exception as e:                     # keep the worker alive
                self.log("ERROR: %s" % e)
        if self.link:
            self.link.close()

    def _maybe_reconnect(self):
        if not (self.auto_reconnect and self.port):
            time.sleep(0.1)
            return
        if not hasattr(self, "_next_try") or time.time() > self._next_try:
            self._next_try = time.time() + 3
            if any(p[0] == self.port for p in s3g.find_ports()):
                self._connect(self.port, quiet=True)

    def _connect(self, port, quiet=False):
        if self.link:
            self.link.close()
            self.link = None
        self.port = port
        try:
            link = s3g.Link(port)
            ver = link.version()
            var = link.variant()
        except (s3g.PrinterGone, s3g.NoResponse) as e:
            if not quiet:
                self.post("disconnected", "cannot connect to %s: %s" % (port, e))
            return
        self.link = link
        self.homed = False
        self.post("connected", port, "%s %d.%d" % (var, ver // 100, ver % 100))

    def _run_job(self, name, args):
        if name == "connect":
            self.auto_reconnect = True
            self._connect(args[0])
            return
        if name == "disconnect":
            self.auto_reconnect = False
            if self.link:
                self.link.close()
            self.link = None
            self.post("disconnected", "disconnected by user")
            return
        if self.link is None:
            self.log("Not connected - '%s' ignored" % name)
            return
        L, kw = self.link, {"abort_check": self._abort_check}
        if name == "set_temp":
            tool, c = args
            L.set_temp(tool, c, **kw)
            self._wd_arm(("r", "l")[tool], c)
            self.log("%s extruder target -> %d C" % (("Right", "Left")[tool], c))
        elif name == "set_bed":
            L.set_bed(args[0], **kw)
            self._wd_arm("bed", args[0])
            self.log("Bed target -> %d C" % args[0])
        elif name == "heaters_off":
            L.heaters_off()
            self.wd.clear()
            self.log("All heaters OFF")
        elif name == "jog":
            axis, mm, speed = args
            L.jog(axis, mm, speed, **kw)
        elif name == "extrude":
            tool, mm = args
            # Stay on tool 0: this printer's stored T1 offset is bogus (~228 mm), so a
            # firmware tool change would throw the head sideways. Drive the A/B axis directly.
            L.change_tool(0, **kw)
            L.jog(3 + tool, mm, 4.0, **kw)
            self.log("%s extruder %+.1f mm" % (("Right", "Left")[tool], mm))
        elif name in ("load", "unload"):
            tool, temp, keep_hot = args
            side = ("Right", "Left")[tool]
            L.change_tool(0, **kw)                       # never switch to T1 (bad offset)
            L.set_temp(tool, temp, **kw)
            self._wd_arm(("r", "l")[tool], temp)
            L.wait_tool(tool, **kw)
            if name == "load":
                L.jog(3 + tool, +100.0, 2.5, **kw)        # ~40 s slow feed
                self.log("%s LOAD: heating to %d C, then feeding 100 mm slowly. "
                         "Push filament in; press 'Stop filament' when plastic flows." % (side, temp))
            else:
                L.jog(3 + tool, +8.0, 2.0, **kw)          # soften / purge the tip
                L.jog(3 + tool, -100.0, 8.0, **kw)        # pull filament back out
                self.log("%s UNLOAD: heating to %d C, purge 8 mm, then retract 100 mm. "
                         "Pull the filament out when the motor stops." % (side, temp))
            if not keep_hot:
                L.set_temp(tool, 0, **kw)
                self.log("%s nozzle will switch off when the filament move ends" % side)
        elif name == "stop_motion":
            t = L.temps()
            L.abort()                                    # stop motion + clear queue
            for tool, key in ((0, "r_t"), (1, "l_t")):   # keep nozzle temps as they were
                L.set_temp(tool, t.get(key) or 0)
            L.set_bed(0)
            self.log("Filament move stopped (nozzle temperatures kept)")
        elif name == "home_xy":
            L.home_xy(**kw)
            self.log("Homing X/Y (head to back-right, 20 s limit)")
        elif name == "home_z":
            L.home_z(**kw)
            self.log("Homing Z (bed up to Z switch, 20 s limit)")
        elif name == "home_all":
            L.home_xy(**kw)
            L.home_z(**kw)
            self.log("Homing X/Y then Z")
        elif name == "motors_off":
            L.motors_off(**kw)
            self.log("Motors released")
        elif name == "motor_test":
            self._motor_test()
        elif name == "print":
            path = args[0]
            cmds = s3g.split_x3g(open(path, "rb").read())
            if not L.is_finished():
                self.log("Printer is busy - finish or stop the current job first")
                return
            self.print_job = {"cmds": cmds, "i": 0, "name": os.path.basename(path), "t0": time.time()}
            self.log("USB print started: %s (%d commands)" % (os.path.basename(path), len(cmds)))
        elif name == "pause":
            L.pause_toggle()
            self.log("Pause / resume toggled")
        elif name == "cancel":
            self._do_estop(reason="Print cancelled")

    def _motor_test(self):
        L, kw = self.link, {"abort_check": self._abort_check}
        self.log("Motor test: X, Y, Z (bed), right & left extruder - watch the printer")
        for t in (0, 1):
            L.set_temp(t, 0, **kw)
        for axis, d, f in ((0, -20, 25), (0, 20, 25), (1, -20, 25), (1, 20, 25),
                           (2, -10, 8), (2, 10, 8)):
            L.jog(axis, d, f, **kw)
        L.change_tool(0, **kw)                           # never switch to T1 (bad offset)
        for tool in (0, 1):
            L.jog(3 + tool, -2, 4, **kw)
            L.jog(3 + tool, 2, 4, **kw)

    def _do_estop(self, reason="EMERGENCY STOP"):
        self.estop.clear()
        if self.link is None:
            self.post("alarm", "%s pressed but printer is not connected" % reason)
            return
        try:
            self.link.abort()
            self.link.heaters_off()
            self.homed = False
        finally:
            if self.print_job:
                self.post("print_done", False, reason)
                self.print_job = None
            self.wd.clear()
        self.log("%s: motion halted, buffer cleared, heaters off" % reason)

    # ---- printing ----------------------------------------------------------
    def _stream_step(self):
        job = self.print_job
        t_end = time.time() + 0.15
        while job["i"] < len(job["cmds"]) and time.time() < t_end:
            r = self.link.send(job["cmds"][job["i"]])
            if r[0] == s3g.OK:
                job["i"] += 1
            elif r[0] == s3g.BUSY:
                time.sleep(0.03)
                break
            elif r[0] == s3g.CANCELLED:
                self.post("print_done", False, "Print cancelled on the printer LCD")
                self.print_job = None
                return
            else:
                self._do_estop("Printer error: %s" % s3g.RESPONSES.get(r[0], hex(r[0])))
                return
        self.post("progress", job["i"], len(job["cmds"]), time.time() - job["t0"])
        if job["i"] >= len(job["cmds"]):
            if self.link.is_finished():
                self.post("print_done", True, "Print finished: %s in %.1f min"
                          % (job["name"], (time.time() - job["t0"]) / 60))
                self.print_job = None

    # ---- status + heater watchdog -------------------------------------------
    def _wd_arm(self, key, target):
        if target > 0:
            self.wd[key] = None        # armed; start sample taken on next poll
        else:
            self.wd.pop(key, None)

    def _watchdog(self, t):
        now = time.time()
        for key, name in (("r", "Right extruder"), ("l", "Left extruder"), ("bed", "Bed")):
            cur, tgt = t.get(key), t.get(key + "_t")
            if not tgt:
                self.wd.pop(key, None)
                continue
            if cur is None:
                continue
            if cur < 5:
                self._heater_fault("%s sensor reads %d C while heating - sensor fault" % (name, cur))
                return
            if key not in self.wd:            # heating started outside this app (LCD)
                self.wd[key] = None
            if self.wd[key] is None:
                self.wd[key] = (now, cur)
                continue
            t0, c0 = self.wd[key]
            if cur >= tgt - 5:                 # reached target: re-arm window
                self.wd[key] = (now, cur)
            elif now - t0 > WD_WINDOW_S:
                if cur - c0 < WD_RISE_C:
                    self._heater_fault("%s rose only %d C in %d s (target %d C) - heater or sensor fault"
                                       % (name, cur - c0, WD_WINDOW_S, tgt))
                    return
                self.wd[key] = (now, cur)

    def _heater_fault(self, msg):
        self.link.heaters_off()
        self.wd.clear()
        if time.time() - getattr(self, "_last_alarm", 0) > 15:   # no pop-up spam
            self._last_alarm = time.time()
            self.post("alarm", "HEATERS SWITCHED OFF: " + msg)
        else:
            self.log("HEATERS SWITCHED OFF again: " + msg)

    def _poll(self):
        self._last_poll = time.time()
        L = self.link
        t = L.temps()
        pos, es, steps = L.position()
        st = L.board_status()
        self._watchdog(t)
        if tuple(steps[:3]) == s3g.HOME_STEPS[:3]:
            self.homed = True                  # home offsets recalled after a full home
        self.post("status", {"t": t, "pos": pos, "es": es, "board": st, "homed": self.homed})


# =============================================================================
# GUI
# =============================================================================
COL = {"bg": "#1e2228", "panel": "#272c34", "fg": "#e6e6e6", "dim": "#8a93a0",
       "r": "#ff6b6b", "l": "#4dabf7", "bed": "#ffd43b", "ok": "#51cf66",
       "off": "#495057", "warn": "#ff922b", "grid": "#343a44"}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Duplicator 4 Control")
        self.configure(bg=COL["bg"])
        self.minsize(980, 600)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        self.events = queue.Queue()
        self.worker = Worker(self.events)
        self.worker.start()
        self.hist = collections.deque()
        self.es_last, self.es_changes = None, collections.deque()
        self.connected = False
        self.printing = False
        self._style()
        self._build()
        self.bind("<Escape>", lambda e: self.estop())
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.user_disconnected = False
        self._connecting_until = 0.0
        self.refresh_ports(autoconnect=True)
        self.after(100, self.pump)
        self.after(3000, self.watch_ports)

    def watch_ports(self):
        """While disconnected, look for the printer every 3 s and connect when it appears."""
        try:
            if not self.connected and not self.user_disconnected and time.time() > self._connecting_until:
                ports = s3g.find_ports()
                if [p[0] for p in ports] != [p[0] for p in getattr(self, "_ports", [])]:
                    self.refresh_ports()
                printer = next((p for p in ports if p[2]), None)
                if printer:
                    self._connecting_until = time.time() + 8      # give the connect time to finish
                    self.log("Printer found on %s - connecting…" % printer[0])
                    self.worker.submit("connect", printer[0])
        finally:
            self.after(3000, self.watch_ports)

    # ---- styling -------------------------------------------------------------
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=COL["panel"], foreground=COL["fg"], fieldbackground="#323842",
                    bordercolor=COL["grid"], font=("Segoe UI", 10))
        s.configure("TFrame", background=COL["bg"])
        s.configure("Panel.TFrame", background=COL["panel"])
        s.configure("TLabelframe", background=COL["panel"], bordercolor=COL["grid"])
        s.configure("TLabelframe.Label", background=COL["panel"], foreground=COL["dim"],
                    font=("Segoe UI", 10, "bold"))
        s.configure("TLabel", background=COL["panel"])
        s.configure("Dim.TLabel", foreground=COL["dim"])
        s.configure("Big.TLabel", font=("Segoe UI", 16, "bold"))
        s.configure("TButton", background="#3a414c", padding=(8, 4))
        s.map("TButton", background=[("active", "#4a5260"), ("disabled", "#2c3139")],
              foreground=[("disabled", "#666")])
        s.map("TCombobox", fieldbackground=[("readonly", "#323842")],
              foreground=[("readonly", COL["fg"])], selectbackground=[("readonly", "#323842")],
              selectforeground=[("readonly", COL["fg"])])
        s.configure("TCheckbutton", background=COL["panel"])
        s.configure("TRadiobutton", background=COL["panel"])
        s.configure("Horizontal.TProgressbar", background=COL["ok"], troughcolor="#323842")

    def _panel(self, parent, title):
        f = ttk.LabelFrame(parent, text=" %s " % title, padding=8)
        return f

    # ---- layout ----------------------------------------------------------------
    def _build(self):
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="Port", background=COL["bg"]).pack(side="left")
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(top, textvariable=self.port_var, width=34, state="readonly")
        self.port_box.pack(side="left", padx=6)
        ttk.Button(top, text="↻", width=3, command=self.refresh_ports).pack(side="left")
        self.conn_btn = ttk.Button(top, text="Connect", command=self.toggle_connect)
        self.conn_btn.pack(side="left", padx=6)
        self.conn_lbl = tk.Label(top, text="● Disconnected", bg=COL["bg"], fg=COL["dim"],
                                 font=("Segoe UI", 11, "bold"))
        self.conn_lbl.pack(side="left", padx=10)
        self.board_lbl = tk.Label(top, text="", bg=COL["bg"], fg=COL["dim"])
        self.board_lbl.pack(side="left")
        tk.Button(top, text="⛔  EMERGENCY STOP  (Esc)", command=self.estop, bg="#e03131",
                  fg="white", activebackground="#ff4d4d", font=("Segoe UI", 12, "bold"),
                  relief="flat", padx=16, pady=6).pack(side="right")

        body = ttk.Frame(self, padding=(10, 0, 10, 10))
        body.pack(fill="both", expand=True)
        for c in range(3):
            body.columnconfigure(c, weight=1, uniform="col")
        body.rowconfigure(0, weight=1)
        left, mid, right = (ttk.Frame(body) for _ in range(3))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        mid.grid(row=0, column=1, sticky="nsew", padx=6)
        right.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        self._build_temps(left)
        self._build_switches(mid)
        self._build_jog(mid)
        self._build_print(right)
        self._build_log(right)
        self.set_controls(False)

    def _build_temps(self, parent):
        f = self._panel(parent, "Temperatures")
        f.pack(fill="x")
        self.t_lbl, self.t_tgt, self.t_entry = {}, {}, {}
        rows = (("r", "Right (T0)", 210), ("l", "Left (T1)", 210), ("bed", "Bed", 0))
        for i, (key, name, default) in enumerate(rows):
            tk.Label(f, text="■", fg=COL[key], bg=COL["panel"]).grid(row=i, column=0, sticky="w")
            ttk.Label(f, text=name).grid(row=i, column=1, sticky="w")
            self.t_lbl[key] = ttk.Label(f, text="--- °C", style="Big.TLabel", width=6, anchor="e")
            self.t_lbl[key].grid(row=i, column=2, padx=4)
            self.t_tgt[key] = ttk.Label(f, text="→ off", style="Dim.TLabel", width=9)
            self.t_tgt[key].grid(row=i, column=3)
            e = ttk.Spinbox(f, from_=0, to=(240 if key != "bed" else 110), width=4, increment=5)
            e.set(default)
            e.grid(row=i, column=4, padx=2)
            self.t_entry[key] = e
            ttk.Button(f, text="Set", width=3, command=lambda k=key: self.set_heater(k)).grid(row=i, column=5, padx=2)
            ttk.Button(f, text="Off", width=3, command=lambda k=key: self.set_heater(k, 0)).grid(row=i, column=6)
        self.bed_ok = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Bed sensor repaired (allow bed heating)", variable=self.bed_ok).grid(
            row=3, column=1, columnspan=6, sticky="w", pady=(6, 0))
        bb = ttk.Frame(f, style="Panel.TFrame")
        bb.grid(row=4, column=1, columnspan=6, sticky="w", pady=(6, 0))
        ttk.Button(bb, text="PLA: both 210 °C", command=lambda: self.preset(210)).pack(side="left")
        ttk.Button(bb, text="All heaters OFF", command=lambda: self.worker.submit("heaters_off")).pack(side="left", padx=6)

        c = self._panel(parent, "Temperature history (5 min)")
        c.pack(fill="both", expand=True, pady=(10, 0))
        self.chart = tk.Canvas(c, bg="#20242b", highlightthickness=0, height=160)
        self.chart.pack(fill="both", expand=True)
        self.chart.bind("<Configure>", lambda e: self.draw_chart())

    def _build_switches(self, parent):
        f = self._panel(parent, "Limit switches  &  position")
        f.pack(fill="x")
        self.sw = {}
        for i, (bit, name, where) in enumerate(((1, "X", "right end"), (3, "Y", "back"), (4, "Z", "bed top"))):
            cv = tk.Canvas(f, width=20, height=20, bg=COL["panel"], highlightthickness=0)
            cv.grid(row=i, column=0, padx=(0, 6), pady=1)
            dot = cv.create_oval(2, 2, 18, 18, fill=COL["off"], outline="")
            lbl = ttk.Label(f, text="", style="Dim.TLabel")
            lbl.grid(row=i, column=1, sticky="w")
            self.sw[bit] = (cv, dot, lbl, name, where)
            self._sw_text(bit, False)
        self.sw_warn = ttk.Label(f, text="", foreground=COL["warn"])
        self.sw_warn.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.pos_lbl = ttk.Label(f, text="X ---  Y ---  Z ---", font=("Consolas", 10))
        self.pos_lbl.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.homed_lbl = ttk.Label(f, text="Not homed", style="Dim.TLabel")
        self.homed_lbl.grid(row=5, column=0, columnspan=2, sticky="w")

    def _sw_text(self, bit, on):
        cv, dot, lbl, name, where = self.sw[bit]
        cv.itemconfigure(dot, fill=COL["ok"] if on else COL["off"])
        lbl.configure(text="%s switch (%s):  %s" % (name, where, "PRESSED" if on else "open"),
                      foreground=COL["ok"] if on else COL["dim"])

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
        g.pack(fill="x", pady=6)
        for c in range(4):
            g.columnconfigure(c, weight=1, uniform="jog")
        B = lambda text, cmd, r, c: self._btn(g, text, cmd).grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
        B("Y+ back", lambda: self.jog(1, +1), 0, 1)
        B("X− left", lambda: self.jog(0, -1), 1, 0)
        B("X+ right", lambda: self.jog(0, +1), 1, 2)
        B("Y− front", lambda: self.jog(1, -1), 2, 1)
        B("Bed ▲ UP", lambda: self.jog(2, -1), 0, 3)
        B("Bed ▼ DOWN", lambda: self.jog(2, +1), 2, 3)

        h = ttk.Frame(f, style="Panel.TFrame")
        h.pack(fill="x", pady=(2, 0))
        for c in range(4):
            h.columnconfigure(c, weight=1, uniform="home")
        self._btn(h, "Home X/Y", lambda: self.worker.submit("home_xy")).grid(row=0, column=0, sticky="ew", padx=2)
        self._btn(h, "Home Z", self.home_z).grid(row=0, column=1, sticky="ew", padx=2)
        self._btn(h, "Home all", self.home_all).grid(row=0, column=2, sticky="ew", padx=2)
        self._btn(h, "Motors off", lambda: self.worker.submit("motors_off")).grid(row=0, column=3, sticky="ew", padx=2)

        e = ttk.LabelFrame(f, text=" Extruders / filament ", padding=6)
        e.pack(fill="x", pady=(10, 0))
        for c in range(1, 5):
            e.columnconfigure(c, weight=1, uniform="ext")
        ttk.Label(e, text="Move mm").grid(row=0, column=0, sticky="w")
        self.e_amt = ttk.Spinbox(e, from_=1, to=100, width=4, increment=5)
        self.e_amt.set(10)
        self.e_amt.grid(row=0, column=1, sticky="w", padx=2)
        ttk.Label(e, text="Filament °C").grid(row=0, column=2, sticky="e")
        self.fil_temp = ttk.Spinbox(e, from_=170, to=240, width=4, increment=5)
        self.fil_temp.set(210)
        self.fil_temp.grid(row=0, column=3, sticky="w", padx=2)
        for i, (tool, name) in enumerate(((0, "Right"), (1, "Left"))):
            ttk.Label(e, text=name).grid(row=1 + i, column=0, sticky="w", pady=2)
            self._btn(e, "Retract", lambda t=tool: self.extrude(t, -1)).grid(row=1 + i, column=1, padx=2, sticky="ew")
            self._btn(e, "Extrude", lambda t=tool: self.extrude(t, +1)).grid(row=1 + i, column=2, padx=2, sticky="ew")
            self._btn(e, "⬇ Load", lambda t=tool: self.filament(t, "load")).grid(row=1 + i, column=3, padx=2, sticky="ew")
            self._btn(e, "⬆ Unload", lambda t=tool: self.filament(t, "unload")).grid(row=1 + i, column=4, padx=2, sticky="ew")
        self.keep_hot = tk.BooleanVar(value=False)
        ttk.Checkbutton(e, text="Keep nozzle hot afterwards", variable=self.keep_hot).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self._btn(e, "■ Stop filament", lambda: self.worker.submit("stop_motion")).grid(
            row=3, column=3, columnspan=2, sticky="ew", padx=2, pady=(4, 0))
        self._btn(f, "Run motor test (heaters off)", self.motor_test).pack(fill="x", pady=(10, 0))

    def _build_print(self, parent):
        f = self._panel(parent, "USB print (.x3g)")
        f.pack(fill="x")
        self.file_var = tk.StringVar(value=self._default_file())
        ttk.Entry(f, textvariable=self.file_var).pack(fill="x")
        row = ttk.Frame(f, style="Panel.TFrame")
        row.pack(fill="x", pady=6)
        for c in range(2):
            row.columnconfigure(c, weight=1, uniform="pr")
        ttk.Button(row, text="Browse…", command=self.browse).grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        self.print_btn = self._btn(row, "▶ Start print", self.start_print)
        self.print_btn.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        self.pause_btn = self._btn(row, "Pause / Resume", lambda: self.worker.submit("pause"))
        self.pause_btn.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        self.cancel_btn = self._btn(row, "Cancel print", lambda: self.worker.submit("cancel"))
        self.cancel_btn.grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        self.prog = ttk.Progressbar(f, maximum=1000)
        self.prog.pack(fill="x")
        self.prog_lbl = ttk.Label(f, text="Idle", style="Dim.TLabel")
        self.prog_lbl.pack(anchor="w", pady=(4, 0))

    def _build_log(self, parent):
        f = self._panel(parent, "Log")
        f.pack(fill="both", expand=True, pady=(10, 0))
        self.logbox = tk.Text(f, bg="#20242b", fg=COL["fg"], relief="flat", height=10,
                              font=("Consolas", 9), wrap="word", state="disabled")
        self.logbox.pack(fill="both", expand=True)
        self.logbox.tag_configure("alarm", foreground=COL["r"], font=("Consolas", 9, "bold"))
        self.logbox.tag_configure("ok", foreground=COL["ok"])

    def _btn(self, parent, text, cmd):
        b = ttk.Button(parent, text=text, command=cmd)
        self._controls = getattr(self, "_controls", [])
        self._controls.append(b)
        return b

    def _default_file(self):
        p = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output", "RL_TEST.x3g"))
        return p if os.path.exists(p) else ""

    # ---- actions ---------------------------------------------------------------
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
            self.port_var.set("(no ports - is the printer on and plugged in?)")

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
                                       "The bed temperature sensor reads 0-1 °C, which is a fault.\n\n"
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
        d = self.step.get() * sign
        self.worker.submit("jog", axis, d, 8.0 if axis == 2 else 30.0)

    def extrude(self, tool, sign):
        try:
            mm = float(self.e_amt.get())
        except ValueError:
            return
        cur = self._last_temps.get(("r", "l")[tool]) if hasattr(self, "_last_temps") else None
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
            text = ("LOAD filament - %s extruder\n\n"
                    "1. Nozzle heats to %d °C (the printer waits until hot).\n"
                    "2. Then the extruder turns slowly for about 40 s.\n"
                    "3. Push the filament end (cut straight) into the top of the %s extruder\n"
                    "    until the gears grab it.\n"
                    "4. When plastic comes out of the nozzle, press '■ Stop filament'.\n\n"
                    "Start?" % (side, temp, side.lower()))
        else:
            text = ("UNLOAD filament - %s extruder\n\n"
                    "1. Nozzle heats to %d °C (the printer waits until hot).\n"
                    "2. It pushes 8 mm (to soften the tip), then pulls back 100 mm.\n"
                    "3. When the motor stops, pull the filament out by hand.\n\n"
                    "Start?" % (side, temp))
        if messagebox.askokcancel(action.capitalize() + " filament", text):
            self.worker.submit(action, tool, temp, self.keep_hot.get())

    def home_z(self):
        if messagebox.askokcancel("Home Z",
                                  "The bed will move UP until it presses the Z switch.\n\n"
                                  "Last time the printer cut out when the bed reached the top. "
                                  "Check the bed cables are not pinched, and be ready to press "
                                  "EMERGENCY STOP (Esc) or switch the printer off."):
            self.worker.submit("home_z")

    def home_all(self):
        if messagebox.askokcancel("Home all", "Head goes to back-right, then the bed moves UP to the Z switch.\n"
                                  "Be ready to press EMERGENCY STOP (Esc)."):
            self.worker.submit("home_all")

    def motor_test(self):
        if messagebox.askokcancel("Motor test", "Moves X ±20 mm, Y ±20 mm, bed ±10 mm, then each extruder ±2 mm.\n"
                                  "Heaters are switched off. Keep hands clear."):
            self.worker.submit("motor_test")

    def browse(self):
        p = filedialog.askopenfilename(filetypes=[("x3g print files", "*.x3g"), ("All files", "*.*")])
        if p:
            self.file_var.set(p)

    def start_print(self):
        p = self.file_var.get()
        if not os.path.isfile(p):
            messagebox.showerror("No file", "Choose an .x3g file first.")
            return
        if not messagebox.askokcancel("Start USB print",
                                      "Print %s over USB?\n\nKeep this window open and the PC awake "
                                      "until the print finishes." % os.path.basename(p)):
            return
        self.printing = True
        self.prog["value"] = 0
        self.worker.submit("print", p)

    # ---- event pump --------------------------------------------------------------
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
        if was and "user" not in reason:
            self.log("Will reconnect automatically when the printer comes back.")

    def on_progress(self, i, n, elapsed):
        self.prog["value"] = 1000 * i / max(1, n)
        eta = ""
        if i > 50:
            eta = " — ~%d min left (sending)" % max(0, (elapsed / i * (n - i)) / 60)
        self.prog_lbl.configure(text="Sent %d / %d commands (%d%%)%s" % (i, n, 100 * i // max(1, n), eta))

    def on_print_done(self, ok, msg):
        self.printing = False
        self.prog_lbl.configure(text=msg)
        self.log(msg, "ok" if ok else "alarm")
        if not ok:
            messagebox.showwarning("Print stopped", msg)

    def on_status(self, s):
        t = s["t"]
        self._last_temps = t
        for key in ("r", "l", "bed"):
            v, tg = t.get(key), t.get(key + "_t")
            self.t_lbl[key].configure(text="%s °C" % (v if v is not None else "---"))
            self.t_tgt[key].configure(text="→ %d °C" % tg if tg else "→ off")
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
        self.pos_lbl.configure(text="X %.2f   Y %.2f   Z %.2f\nRight ext %.1f   Left ext %.1f  (mm)" % tuple(p))
        self.homed_lbl.configure(text="Homed (position = home offsets)" if s["homed"] else
                                 "Not homed - positions are relative to power-on",
                                 foreground=COL["ok"] if s["homed"] else COL["dim"])
        st = s["board"]
        flags = [n for b, n in s3g.BOARD_FLAGS if st and st & b]
        self.board_lbl.configure(text="Board: " + (", ".join(flags) if flags else "idle"),
                                 fg=COL["warn"] if any(f in flags for f in ("HEAT_SHUTDOWN", "POWER_ERROR")) else COL["dim"])

    # ---- chart -------------------------------------------------------------------
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
            x = X(now - m * 60)
            c.create_text(x, h - 6, text="-%dm" % m if m else "now", fill=COL["dim"],
                          anchor="e" if m == 0 else "center", font=("Segoe UI", 8))
        for idx, key in ((1, "r"), (2, "l"), (3, "bed")):
            tg = [(X(r[0]), Y(r[idx + 3])) for r in self.hist if r[idx + 3]]
            if len(tg) > 1:
                c.create_line(*sum(tg, ()), fill=COL[key], dash=(3, 3))
            pts = [(X(r[0]), Y(max(0, min(tmax, r[idx])))) for r in self.hist if r[idx] is not None]
            if len(pts) > 1:
                c.create_line(*sum(pts, ()), fill=COL[key], width=2)

    # ---- misc --------------------------------------------------------------------
    def log(self, msg, tag=None):
        self.logbox.configure(state="normal")
        line = time.strftime("%H:%M:%S  ") + msg + "\n"
        if tag:
            self.logbox.insert("end", line, tag)
        else:
            self.logbox.insert("end", line)
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def on_close(self):
        if self.printing and not messagebox.askyesno("Print running",
                                                     "A USB print is running. Closing stops sending and the print will stall.\n"
                                                     "Stop the print and close?"):
            return
        if self.printing:
            self.worker.emergency_stop()
            time.sleep(0.5)
        self.worker.quit.set()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
