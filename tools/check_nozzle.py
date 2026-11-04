"""
Check one nozzle of the Duplicator 4: heater + extruder.

    python tools/check_nozzle.py --tool right      (or left)

1. If X/Y are homed, moves the head so that nozzle is over the front-centre of the bed.
2. Heats the nozzle to --temp and logs the rise (heater/thermocouple test).
3. Pushes --mm of filament slowly, logging the extruder counter (motor test).
4. Retracts 1 mm, heater off, head back home.
Never heats the bed, never moves Z, never sends a firmware tool change.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import struct
import time

import s3g_link as s3g

ap = argparse.ArgumentParser()
ap.add_argument("--tool", choices=("right", "left"), default="right")
ap.add_argument("--temp", type=int, default=210)
ap.add_argument("--mm", type=float, default=15.0)
ap.add_argument("--port", default="COM30")
a = ap.parse_args()
tool = 0 if a.tool == "right" else 1
key = "r" if tool == 0 else "l"
NAME = a.tool.upper()


def log(msg):
    print(time.strftime("%H:%M:%S ") + msg, flush=True)


L = s3g.Link(a.port, settle_s=1.5)
pos, es, steps = L.position()
t = L.temps()
log("connected. %s nozzle %s C, head X %.1f Y %.1f, switches %s"
    % (NAME, t[key], pos[0], pos[1], [n for i, n in enumerate(s3g.ENDSTOP_NAMES) if es >> i & 1] or "none"))
L.change_tool(0)                                   # firmware stays on T0 (bogus T1 offset)

homed = abs(pos[0] - 152.0) < 1.0 and abs(pos[1] - 75.0) < 1.0
if homed:
    head_x = 0.0 + (33.0 if tool == 1 else 0.0)   # left nozzle sits 33 mm left of the head
    L.jog(0, head_x - pos[0], 40.0)
    L.jog(1, -30.0 - pos[1], 40.0)
    log("moving head so the %s nozzle is over the front-centre of the bed" % NAME)
else:
    log("X/Y not at home position - head stays where it is")

# ---- 1. heater test ----
L.set_temp(tool, a.temp)
t0 = time.time()
c0 = L.temps()[key]
last = c0
ok_heat = False
while time.time() - t0 < 180:
    time.sleep(3)
    c = L.temps()[key]
    log("heating %s nozzle: %d C (target %d)" % (NAME, c, a.temp))
    if c >= a.temp - 3:
        ok_heat = True
        break
    if time.time() - t0 > 60 and c - c0 < 8:
        break
    last = c
dt = time.time() - t0
if not ok_heat:
    L.set_temp(tool, 0)
    log("HEATER FAIL: %s nozzle only went %d -> %d C in %.0f s. Heater OFF. "
        "Check heater cartridge / thermocouple wiring." % (NAME, c0, c, dt))
    L.close()
    raise SystemExit(2)
log("HEATER OK: %s nozzle %d -> %d C in %.0f s" % (NAME, c0, c, dt))

# ---- 2. extruder test ----
_, _, st0 = L.position()
L.jog(3 + tool, a.mm, 2.0)                         # +mm = push filament in (sign handled in s3g_link)
log("pushing %.0f mm of filament through the %s nozzle (%.0f s) - WATCH THE NOZZLE" % (a.mm, NAME, a.mm / 2))
t1 = time.time()
while time.time() - t1 < a.mm / 2 + 4:
    time.sleep(2)
    p, _, st = L.position()
    log("  %s extruder fed %.1f mm   nozzle %d C" % (NAME, p[3 + tool] - (st0[3 + tool] / s3g.SPM[3 + tool] * s3g.EXTRUDE_SIGN), L.temps()[key]))
p, _, st = L.position()
fed = (st[3 + tool] - st0[3 + tool]) / s3g.SPM[3 + tool] * s3g.EXTRUDE_SIGN
log("EXTRUDER: motor fed %.1f of %.0f mm" % (fed, a.mm))

# ---- 3. finish ----
L.jog(3 + tool, -1.0, 10.0)                        # small retract
L.set_temp(tool, 0)
L.home_xy()
L.motors_off()
log("done: %s heater OFF, head going home" % NAME)
L.close()
