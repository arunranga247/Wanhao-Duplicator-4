"""
Dual-extruder (R + L) sample print generator for the Wanhao Duplicator 4
(Replicator 1 Dual clone) running Sailfish 7.x.

Prints two small cubes side by side:
  * RIGHT extruder (tool 0, x3g axis A) -> cube at X = +30 mm
  * LEFT  extruder (tool 1, x3g axis B) -> cube at X = -30 mm
Layers alternate between the two tools (one tool change per layer), so both
extruders and the tool-change logic are exercised.

The cubes are 66 mm apart centre-to-centre on purpose: with the 33 mm nozzle
spacing the idle nozzle never passes over the other cube, even if the
firmware tool offsets are a few mm off.

Outputs:
  output/RL_TEST.x3g    -> copy to the printer SD card and print
  output/RL_TEST.gcode  -> human readable / previewable equivalent (M83, T0/T1)

The heated bed is NOT used (bed thermistor currently reads ~0-1 C, which is a
fault). Print PLA on blue painter's tape or glue stick.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import math
import os
import struct

from s3g_link import EXTRUDE_SIGN       # -1 on this printer: negative A/B steps = push filament in

# ---- machine constants (read from this printer's EEPROM, Sailfish 7.7) ----
SPM = {"x": 94.139704, "y": 94.139704, "z": 400.0, "a": 96.275202, "b": 96.275202}
HOME_MM = (14309 / SPM["x"], 7060 / SPM["y"], 0.0)   # EEPROM home offsets
BED_X, BED_Y = 112.0, 72.0                          # +/- usable bed half-sizes
HOME_STEPS = (14309, 7060, 0, 0, 0)

# Nozzle spacing handled in SOFTWARE. This printer's EEPROM tool-1 offset is bogus
# (21464 steps ~ 228 mm), so the files never send a firmware tool change (x3g 134).
# Coordinates are always "nozzle of the active extruder"; the head (= right nozzle)
# is sent to nozzle_x + LEFT_NOZZLE_DX when the LEFT extruder is active.
LEFT_NOZZLE_DX = 33.0
MAX_E_MM_S = 25.0          # extruder speed limit (EEPROM max for A/B is 26.7 mm/s)

FIL_DIA = 1.75
FIL_AREA = math.pi * (FIL_DIA / 2) ** 2


def bead_area(w, h):
    """Cross-section of an extruded bead (rectangle with round sides)."""
    return (w - h) * h + math.pi * (h / 2) ** 2


class Printer:
    def __init__(self, dry=False):
        self.dry = dry                   # dry run: no Z moves, no extrusion
        self.x3g = bytearray()
        self.ncmd = 0
        self.g = []
        self.pos = [0.0, 0.0, 0.0]       # mm, tool coordinates
        self.e = [0.0, 0.0]              # cumulative filament mm (A, B)
        self.tool = 0
        self.retracted = [0.0, 0.0]
        self.time_s = 0.0
        self.last = None                 # last step position sent to the printer (head)

    # ---- low level -------------------------------------------------------
    def _cmd(self, data, gcode=None):
        self.x3g += data
        self.ncmd += 1
        if gcode:
            self.g.append(gcode)

    def comment(self, text):
        self.g.append("; " + text)

    def _steps(self):
        hx = self.pos[0] + (LEFT_NOZZLE_DX if self.tool == 1 else 0.0)   # head position
        return (round(hx * SPM["x"]), round(self.pos[1] * SPM["y"]),
                round(self.pos[2] * SPM["z"]), round(EXTRUDE_SIGN * self.e[0] * SPM["a"]),
                round(EXTRUDE_SIGN * self.e[1] * SPM["b"]))

    def set_position(self, gcode):
        """Tell the printer its current position = our model (x3g 140)."""
        self.last = self._steps()
        self._cmd(struct.pack("<B5i", 140, *self.last), gcode)

    def move(self, x=None, y=None, z=None, de=0.0, f=30.0, gcode=True):
        """Linear move. f in mm/s, de = filament mm for the ACTIVE tool."""
        if self.dry:
            z, de = None, 0.0
        old = self.last
        if x is not None: self.pos[0] = x
        if y is not None: self.pos[1] = y
        if z is not None: self.pos[2] = z
        self.e[self.tool] += de
        new = self._steps()
        d = [n - o for n, o in zip(new, old)]
        longest = max(abs(v) for v in d)
        if longest == 0:
            return
        self.last = new
        spm = (SPM["x"], SPM["y"], SPM["z"])
        dist = math.sqrt(sum((d[i] / spm[i]) ** 2 for i in range(3)))   # real head travel
        e_mm = max(abs(d[3]) / SPM["a"], abs(d[4]) / SPM["b"])         # real extruder travel
        if dist < 1e-6:
            # extruder-only move (or XYZ too small to step): time it by the extruder
            dist = e_mm
            f = min(f, MAX_E_MM_S)
        elif e_mm > 0:
            # never spin an extruder faster than MAX_E_MM_S, however short the XY move is
            f = min(f, dist * MAX_E_MM_S / e_mm)
        t = dist / f
        self.time_s += t
        dda_rate = max(1, round(longest / t))         # steps/s of dominant axis
        # X/Y/Z absolute; extruders A/B RELATIVE (same style as the app's working
        # Load/Extrude and as GPX): send the step delta and set relative bits 3+4.
        payload = (new[0], new[1], new[2], d[3], d[4])
        self._cmd(struct.pack("<B5iIBfH", 155, *payload, dda_rate, 0x18, dist, round(f * 64)))
        if gcode:
            parts = ["G1"]
            if x is not None: parts.append("X%.3f" % x)
            if y is not None: parts.append("Y%.3f" % y)
            if z is not None: parts.append("Z%.3f" % z)
            if de: parts.append("E%.5f" % de)
            parts.append("F%d" % round(f * 60))
            self.g.append(" ".join(parts))

    # ---- high level ------------------------------------------------------
    def set_temp(self, tool, c):
        self._cmd(struct.pack("<BBBBh", 136, tool, 3, 2, c), "M104 S%d T%d" % (c, tool))

    def set_bed(self, c):
        self._cmd(struct.pack("<BBBBh", 136, 0, 31, 2, c), "M140 S%d" % c)

    def wait_tool(self, tool):
        self._cmd(struct.pack("<BBHH", 135, tool, 100, 1200), "M6 T%d ; wait for heat" % tool)

    def change_tool(self, tool, f=60.0, shift=True):
        """Software tool change: no firmware command. With shift=True the head moves by
        the nozzle spacing (at the current height) so the new nozzle sits where the old
        one was. With shift=False the next move() goes straight to the new target -
        use that near the X end (e.g. right after homing) where a shift would overrun."""
        if tool == self.tool:
            return
        self.tool = tool
        self.g.append("; T%d (software nozzle offset, no firmware tool change)" % tool)
        if shift and self.last is not None:
            self.move(f=f)

    def percent(self, p):
        self._cmd(struct.pack("<BBB", 150, p, 0), "M73 P%d" % p)

    def retract(self, mm, f=25.0):
        need = mm - self.retracted[self.tool]
        if need > 0:
            self.move(de=-need, f=f)
            self.retracted[self.tool] = mm

    def unretract(self, f=25.0, extra=0.0):
        r = self.retracted[self.tool]
        if r > 0 or extra > 0:
            self.move(de=r + extra, f=f)
            self.retracted[self.tool] = 0.0

    def home(self, z_fast=1100 / 60, z_timeout=60):
        """XY max, then Z min (bed up to the Z switch). z_fast in mm/s."""
        self.comment("home: XY max, Z min (Replicator 1 sequence), Z at %.1f mm/s" % z_fast)
        us_xy = round(1e6 / (2500 / 60 * SPM["x"]))
        us_z = round(1e6 / (z_fast * SPM["z"]))
        us_z_slow = round(1e6 / (100 / 60 * SPM["z"]))
        self._cmd(struct.pack("<BBIH", 132, 0x03, us_xy, 60), "G162 X Y F2500")
        self._cmd(struct.pack("<BBIH", 131, 0x04, us_z, z_timeout), "G161 Z F%d" % round(z_fast * 60))
        assert self.tool == 0
        self.pos = [0.0, 0.0, -5.0]
        self.e = [0.0, 0.0]
        self.set_position("G92 X0 Y0 Z-5 A0 B0")
        self.move(z=0.0, f=1100 / 60)
        self._cmd(struct.pack("<BBIH", 131, 0x04, us_z_slow, 60), "G161 Z F100")
        self._cmd(struct.pack("<BB", 144, 0x1F), "M132 X Y Z A B ; recall home offsets")
        self.pos = [HOME_MM[0], HOME_MM[1], HOME_MM[2]]
        self.e = [0.0, 0.0]
        self.last = HOME_STEPS

    def home_xy_only(self, z_ref=0.0):
        """Home X/Y, then call the CURRENT bed height z_ref (bed never moves).
        Use z_ref > 0 for jobs that run with the bed lowered (air demos)."""
        assert self.tool == 0
        us_xy = round(1e6 / (2500 / 60 * SPM["x"]))
        self._cmd(struct.pack("<BBIH", 132, 0x03, us_xy, 20), "G162 X Y F2500")
        self.pos = [HOME_MM[0], HOME_MM[1], z_ref]
        self.e = [0.0, 0.0]
        self.set_position("G92 X%.3f Y%.3f Z%g A0 B0 ; Z is NOT homed - bed stays put"
                          % (HOME_MM[0], HOME_MM[1], z_ref))


# ---- toolpath generation --------------------------------------------------
def square_layer(p, cx, cy, size, w, h, z, solid, horizontal, speed_per, speed_inf,
                 travel_f, hop, retract_mm):
    """One layer of a cube: 2 perimeters (inner first) + rectilinear infill."""
    k = bead_area(w, h) / FIL_AREA
    half = size / 2

    def loop(o):
        x0, x1, y0, y1 = cx - half + o, cx + half - o, cy - half + o, cy + half - o
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]

    loops = [loop(w / 2 + w), loop(w / 2)]          # inner, then outer
    start = loops[0][0]
    travel_to(p, start[0], start[1], z, travel_f, hop, retract_mm)
    for li, pts in enumerate(loops):
        if li > 0:
            p.move(pts[0][0], pts[0][1], f=travel_f)  # short hop inside the part
        for (x, y) in pts[1:]:
            px, py = p.pos[0], p.pos[1]
            p.move(x, y, de=math.hypot(x - px, y - py) * k, f=speed_per)

    inset = 2 * w - 0.15 * w
    lo_x, hi_x = cx - half + inset, cx + half - inset
    lo_y, hi_y = cy - half + inset, cy + half - inset
    spacing = w if solid else w / 0.25
    lines = []
    if horizontal:
        y = lo_y + w / 2
        while y <= hi_y - w / 2 + 1e-9:
            lines.append(((lo_x, y), (hi_x, y)))
            y += spacing
    else:
        x = lo_x + w / 2
        while x <= hi_x - w / 2 + 1e-9:
            lines.append(((x, lo_y), (x, hi_y)))
            x += spacing
    for i, (a, b) in enumerate(lines):
        if i % 2:
            a, b = b, a
        px, py = p.pos[0], p.pos[1]
        if i == 0:
            p.move(a[0], a[1], f=travel_f)
        else:                                     # connect along the edge
            p.move(a[0], a[1], de=math.hypot(a[0] - px, a[1] - py) * k, f=speed_inf)
        p.move(b[0], b[1], de=math.hypot(b[0] - a[0], b[1] - a[1]) * k, f=speed_inf)


def travel_to(p, x, y, z, travel_f, hop, retract_mm):
    p.retract(retract_mm)
    p.move(z=max(p.pos[2], z) + hop, f=10.0)
    p.move(x, y, f=travel_f)
    p.move(z=z, f=10.0)
    p.unretract()


PRIME_RECOVER_MM = 2.0     # every print ends with a 2 mm retract -> push it back first
PRIME_BLOB_MM = 5.0        # refills what oozed out while the nozzle was heating


def prime_line(p, x0, x1, y, z, travel_f):
    """Get the plastic flowing BEFORE the part starts (no empty first seconds):
    5 s settle, recover last print's retract, slow purge blob, thick line out,
    thinner line back next to it (also wipes the nozzle)."""
    travel_to(p, x0, y, z, travel_f, 1.0, 0.0)
    p.unretract(extra=0.0)
    p._cmd(struct.pack("<BI", 133, 5000), "G4 P5000 ; let the melt settle after heat-up")
    p.move(de=PRIME_RECOVER_MM, f=2.0)
    p.move(de=PRIME_BLOB_MM, f=2.0)
    k = bead_area(0.8, z) / FIL_AREA * 1.15
    p.move(x1, y, de=abs(x1 - x0) * k, f=12.0)
    y2 = y + 0.9 if y < 0 else y - 0.9            # second line on the side away from the bed edge
    k2 = bead_area(0.5, z) / FIL_AREA
    xb = x0 + (x1 - x0) * 0.3
    p.move(x1, y2, f=12.0)
    p.move(xb, y2, de=abs(x1 - xb) * k2, f=15.0)


def build(args):
    p = Printer(dry=args.dry)
    name = args.name
    first_h, h = 0.30, 0.20
    n_layers = 1 + int(round((args.height - first_h) / h))
    solid_bottom, solid_top = 3, 3
    travel_f, hop = 80.0, 0.6
    retract_mm, tc_retract_mm = 1.0, 2.0
    cubes = {0: (+30.0, 0.0), 1: (-30.0, 0.0)}      # tool -> centre (mm)
    primes = {0: (10.0, 60.0, -60.0), 1: (-60.0, -10.0, -50.0)}  # x0, x1, y
    tools = {"both": (0, 1), "left": (1,), "right": (0,)}[args.only]
    if len(tools) == 1:                              # single extruder: object in the middle
        cubes = {tools[0]: (0.0, 0.0)}

    # bounds sanity check
    for t, (cx, cy) in cubes.items():
        assert abs(cx) + args.size / 2 + 33 < BED_X and abs(cy) + args.size / 2 < BED_Y

    p.g += ["; Wanhao Duplicator 4 - dual extruder R+L sample",
            "; tool 0 = RIGHT extruder (cube X+30), tool 1 = LEFT extruder (cube X-30)",
            "; PLA %d C, bed unheated, %.0fx%.0fx%.1f mm cubes, %d layers"
            % (args.temp, args.size, args.size, args.height, n_layers),
            "M136 ; build start", "M83 ; relative E (preview gcode only)"]
    p._cmd(struct.pack("<BI", 153, 0) + name.encode() + b"\0")  # patched later
    p.percent(0)
    p.set_bed(0)
    # make sure the FIRMWARE is on tool 0 (zero offset) - we never switch it to T1
    p._cmd(struct.pack("<BB", 134, 0), "T0 ; firmware tool 0, kept for the whole job")
    if args.dry:
        # DRY RUN: home X/Y only, bed (Z) never moves, nothing extruded.
        # --hot keeps both nozzles at --temp during the run (heater-under-load test).
        t = args.temp if args.hot else 0
        p.set_temp(0, t)
        p.set_temp(1, t)
        p.change_tool(0)
        p.home_xy_only()
        if args.hot:
            p.wait_tool(0)
            p.wait_tool(1)
    else:
        for t in (0, 1):                          # heaters OFF until homing has worked
            p.set_temp(t, 0 if args.slow_z else (args.temp if t in tools else 0))
        p.change_tool(0)
        if args.slow_z:
            p.home(z_fast=5.0, z_timeout=40)      # bed rises slowly to the Z switch
            p.move(z=5.0, f=5.0)
            for t in tools:                       # homing succeeded -> now heat
                p.set_temp(t, args.temp)
        elif args.manual_z:
            # MANUAL Z: the bed was raised by hand until the nozzle just touches paper.
            # That height becomes Z=0. Z is never homed; the bed only ever moves DOWN.
            p.pos, p.e = [0.0, 0.0, 0.0], [0.0, 0.0]
            p.set_position("G92 X0 Y0 Z0 A0 B0 ; current bed height = Z0 (paper test)")
            p.move(z=5.0, f=5.0)                  # bed 5 mm down before the head moves
            us_xy = round(1e6 / (2500 / 60 * SPM["x"]))
            p._cmd(struct.pack("<BBIH", 132, 0x03, us_xy, 20), "G162 X Y F2500")
            p.pos = [HOME_MM[0], HOME_MM[1], 5.0]
            p.set_position("G92 X%.3f Y%.3f Z5 A0 B0" % (HOME_MM[0], HOME_MM[1]))
        else:
            p.home()
            p.move(z=5.0, f=10.0)                 # drop the bed before moving XY
        for t in tools:
            p.wait_tool(t)
        if tools == (1,):
            p.change_tool(1, shift=False)         # head is at the X end: no shift here...
            x0, x1, py = primes[1]
            p.move(x0, py, f=travel_f)            # ...the first move goes straight to the prime line

    primed = set()
    for li in range(n_layers):
        z = first_h + li * h
        first = li == 0
        w = 0.50 if first else 0.45
        lh = first_h if first else h
        solid = li < solid_bottom or li >= n_layers - solid_top
        horizontal = li % 2 == 0
        sp_per = 15.0 if first else 30.0
        sp_inf = 20.0 if first else 40.0
        p.comment("layer %d  z=%.2f" % (li + 1, z))
        for tool in [t for t in ((0, 1) if li % 2 == 0 else (1, 0)) if t in tools]:
            if tool != p.tool:
                p.retract(tc_retract_mm)
                p.move(z=p.pos[2] + hop, f=10.0)
                p.change_tool(tool)
            if tool not in primed:
                p.comment("prime tool %d" % tool)
                x0, x1, py = primes[tool]
                prime_line(p, x0, x1, py, first_h, travel_f)
                primed.add(tool)
            cx, cy = cubes[tool]
            p.comment("cube tool %d" % tool)
            square_layer(p, cx, cy, args.size, w, lh, z, solid, horizontal,
                         sp_per, sp_inf, travel_f, hop, retract_mm)
        p.percent(min(99, round(100 * (li + 1) / n_layers)))

    p.comment("end")
    p.retract(tc_retract_mm)          # the other extruder was retracted at its last swap
    p.set_temp(0, 0)
    p.set_temp(1, 0)
    p.set_bed(0)
    p.move(z=min(140.0, p.pos[2] + 60.0), f=10.0)   # bed down first, away from the part
    p.change_tool(0)                  # shift head back to right-nozzle coordinates
    us_xy = round(1e6 / (2500 / 60 * SPM["x"]))
    p._cmd(struct.pack("<BBIH", 132, 0x03, us_xy, 60), "G162 X Y F2500")
    p._cmd(struct.pack("<BB", 137, 0x1F), "M18 ; motors off")
    p.percent(100)
    p._cmd(struct.pack("<BB", 154, 0), "M137 ; build end")

    # patch command count into build-start packet
    struct.pack_into("<I", p.x3g, 1, p.ncmd)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, name + ".x3g"), "wb") as fh:
        fh.write(p.x3g)
    with open(os.path.join(args.out, name + ".gcode"), "w") as fh:
        fh.write("\n".join(p.g) + "\n")
    print("layers        : %d" % n_layers)
    print("x3g commands  : %d  (%d bytes)" % (p.ncmd, len(p.x3g)))
    print("filament R/L  : %.0f mm / %.0f mm" % (p.e[0], p.e[1]))
    print("est. print    : %.0f min (+ heat-up)" % (p.time_s / 60))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--temp", type=int, default=210, help="nozzle temp C (PLA ~210)")
    ap.add_argument("--size", type=float, default=20.0, help="cube side mm")
    ap.add_argument("--height", type=float, default=5.0, help="cube height mm")
    ap.add_argument("--name", default="RL_TEST", help="output file name (no extension)")
    ap.add_argument("--dry", action="store_true",
                    help="dry run: no heat, no extrusion, X/Y homing only, bed never moves")
    ap.add_argument("--only", choices=("both", "left", "right"), default="both",
                    help="which extruder(s) print; single extruder puts the object in the middle")
    ap.add_argument("--manual-z", action="store_true",
                    help="no Z homing: current bed height (paper test) = Z0; bed only moves down")
    ap.add_argument("--slow-z", action="store_true",
                    help="home Z slowly (5 mm/s, 40 s limit) with heaters off; heat only after homing")
    ap.add_argument("--hot", action="store_true",
                    help="with --dry: heat both nozzles to --temp and hold during the run")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output"))
    build(ap.parse_args())
