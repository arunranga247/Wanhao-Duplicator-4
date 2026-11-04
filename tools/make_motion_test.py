"""Heaters-OFF motion test for the Duplicator 4: homes, moves XY/Z, nudges both extruders.
Used to check whether the board resets under motor load alone (power-supply diagnosis)."""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import os
import struct

from make_dual_sample import Printer, SPM

p = Printer()
p._cmd(struct.pack("<BI", 153, 0) + b"MOTION_TEST\0")
p.percent(0)
for t in (0, 1):
    p.set_temp(t, 0)
p.set_bed(0)
p.change_tool(0)
p.home()
p.move(z=10.0, f=10.0)                              # bed well clear of the nozzles
p.percent(20)
for _ in range(3):                                  # rectangle + diagonals around bed centre
    for x, y in ((-50, -40), (50, -40), (50, 40), (-50, 40), (-50, -40), (50, 40), (50, -40), (-50, 40)):
        p.move(x, y, f=80.0)
p.percent(50)
for z in (30.0, 10.0, 30.0, 10.0):                  # Z up/down
    p.move(z=z, f=10.0)
p.percent(70)
for t in (0, 1):                                    # extruder motors: 1 mm back, 1 mm forward
    p.change_tool(t)
    for _ in range(3):
        p.move(de=-1.0, f=10.0)
        p.move(de=+1.0, f=10.0)
p.change_tool(0)
p.percent(90)
p.move(z=40.0, f=10.0)
us_xy = round(1e6 / (2500 / 60 * SPM["x"]))
p._cmd(struct.pack("<BBIH", 132, 0x03, us_xy, 60), "G162 X Y F2500")
p._cmd(struct.pack("<BB", 137, 0x1F), "M18")
p.percent(100)
p._cmd(struct.pack("<BB", 154, 0), "M137")
struct.pack_into("<I", p.x3g, 1, p.ncmd)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output", "MOTION_TEST.x3g")
open(out, "wb").write(p.x3g)
print("wrote %s: %d commands, ~%.1f min of motion" % (os.path.normpath(out), p.ncmd, p.time_s / 60))
