"""
Printer worker thread for the Duplicator 4 control software.

The ONLY code that touches the serial port. The GUI talks to it through
Worker.submit(job, *args) and receives events (tuples) on a queue:
  ("log", msg) ("alarm", msg) ("connected", port, fw) ("disconnected", reason)
  ("status", dict) ("progress", sent, total, elapsed_s) ("print_done", ok, msg)
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import os
import queue
import threading
import time

import s3g_link as s3g

POLL_IDLE_S = 0.5
POLL_PRINT_S = 1.0

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
        if job.get("heat_wait") is not None:
            # the printer is executing a "wait for heat": send nothing more until it is hot,
            # so progress / time left only start counting when printing really starts
            if time.time() - job.get("heat_check", 0) < 0.5:
                return
            job["heat_check"] = time.time()
            if not self.link.is_finished():
                self.post("progress", job["i"], len(job["cmds"]), time.time() - job["t0"])
                return
            job["heat_wait"] = None
            self.post("phase", "print", None)
        t_end = time.time() + 0.15
        while job["i"] < len(job["cmds"]) and time.time() < t_end:
            c = job["cmds"][job["i"]]
            r = self.link.send(c)
            if r[0] == s3g.OK:
                job["i"] += 1
                if c[0] == 135:                       # wait-for-heat command now queued
                    job["heat_wait"] = c[1]
                    self.post("phase", "heat", c[1])
                    break
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
