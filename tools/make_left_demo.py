"""
DEMO_LEFT: left-extruder demo that is safe with the current printer faults.

  * heats ONLY the left nozzle (right stays off, bed off)
  * homes X/Y only - the bed (Z) never moves, so the Z-homing fault is avoided
  * never sends a firmware tool change (stored T1 offset is bogus) - the 33 mm
    nozzle spacing is handled in software
  * purges 15 mm, then draws a small square spiral in the air while extruding,
    so you can see the left extruder feed plastic. The strand falls onto the bed.

Make sure the bed is at least ~2 cm below the nozzles before running.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import os
import struct

from make_dual_sample import FIL_AREA, SPM, Printer, bead_area

ap = argparse.ArgumentParser()
ap.add_argument("--temp", type=int, default=210)
ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output"))
args = ap.parse_args()

p = Printer()
p._cmd(struct.pack("<BI", 153, 0) + b"DEMO_LEFT\0")
p.percent(0)
p._cmd(struct.pack("<BB", 134, 0), "T0 ; firmware stays on tool 0")
p.set_bed(0)
p.set_temp(0, 0)                      # right nozzle OFF
p.set_temp(1, args.temp)              # left nozzle ON
p.home_xy_only(z_ref=50.0)            # bed never moves; it is LOW (~50 mm below nozzle)
p.change_tool(1, shift=False)         # software: LEFT nozzle becomes the reference (no shift at X end)
p.move(0.0, -30.0, f=60.0)            # left nozzle to front-centre (head goes to X+33)
p.wait_tool(1)                        # printer waits until the left nozzle is hot
p.percent(20)

p.comment("purge 15 mm straight down")
p.move(de=15.0, f=2.0)
p.retract(1.0)
p.percent(40)

p.comment("square spiral in the air while extruding (thick strand)")
k = bead_area(0.5, 0.3) / FIL_AREA * 1.2         # ~0.05 mm filament per mm of path
p.unretract()
cx, cy, r = 0.0, -30.0, 3.0
x, y = cx, cy
for i in range(5):
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        nx, ny = cx + dx * r if dx else x, cy + dy * r if dy else y
        p.move(nx, ny, de=abs(nx - x + ny - y) * k, f=8.0)
        x, y = nx, ny
    r += 1.5
p.retract(2.0)
p.percent(90)

p.comment("end: left heater off, head home")
p.set_temp(1, 0)
p.change_tool(0)
us_xy = round(1e6 / (2500 / 60 * SPM["x"]))
p._cmd(struct.pack("<BBIH", 132, 0x03, us_xy, 20), "G162 X Y F2500")
p._cmd(struct.pack("<BB", 137, 0x1F), "M18 ; motors off")
p.percent(100)
p._cmd(struct.pack("<BB", 154, 0), "M137 ; build end")
struct.pack_into("<I", p.x3g, 1, p.ncmd)

out = os.path.join(args.out, "DEMO_LEFT.x3g")
open(out, "wb").write(p.x3g)
open(os.path.splitext(out)[0] + ".gcode", "w").write("\n".join(p.g) + "\n")
print("wrote %s: %d commands, left filament %.0f mm, ~%.1f min after heat-up"
      % (os.path.normpath(out), p.ncmd, p.e[1], p.time_s / 60))
