"""
G-code (PrusaSlicer, reprap flavour, relative E) -> x3g for the Wanhao Duplicator 4.

Uses the same proven x3g writer (make_dual_sample.Printer) as the demo prints, so every
quirk of this printer is handled the same way:
  * extruder direction (EXTRUDE_SIGN), relative A/B moves
  * NO firmware tool change (bogus T1 offset) - nozzle spacing done in software
  * slow Z homing (5 mm/s, 40 s limit) with heaters OFF, heat only after homing works
  * bed heated only when asked (bed=, max 70 C): bed first, then the nozzle; bed commands in the
    G-code itself are ignored
  * prime line at the front, layer progress (M73-style) for the printer LCD

Coordinates: PrusaSlicer bed is 0..225 x 0..145 (origin front-left); the printer's
coordinates are centred (x - 112.5, y - 72.5).

    python tools/gcode2x3g.py model.gcode --out model.x3g [--tool left|right] [--z-offset -0.05]
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import math
import os
import re
import struct

from make_dual_sample import SPM, Printer, prime_line

BED_W, BED_D = 225.0, 145.0
BED_MAX_C = 70                                   # PLA never needs more; above that it softens
TILT_MAX = 0.5                                   # mm per 100 mm: more than this = level the bed
CX, CY = BED_W / 2, BED_D / 2
MAX_XY_F, MAX_Z_F, MAX_E_F = 100.0, 10.0, 25.0       # mm/s limits for this machine
LEFT_DX = 33.0                                        # left nozzle sits 33 mm left of the head
HEAD_X_MAX = 152.0                                    # X end of the rail (home)

_WORD = re.compile(r"([A-Z])([-+]?\d*\.?\d+)")


class ConvertError(Exception):
    pass


def parse(line):
    code = line.split(";", 1)[0].strip()
    if not code:
        return None, {}
    parts = code.split(None, 1)
    cmd = parts[0].upper()
    words = {k: float(v) for k, v in _WORD.findall(parts[1].upper())} if len(parts) > 1 else {}
    return cmd, words


def scan(lines):
    """First pass: object bounding box (bed coords), layer count, temperatures."""
    x0 = y0 = 1e9
    x1 = y1 = -1e9
    zmax, layers, temps, bed = 0.0, 0, [], 0
    x = y = z = 0.0
    for ln in lines:
        if ln.startswith(";LAYER_CHANGE"):
            layers += 1
        cmd, w = parse(ln)
        if cmd in ("G0", "G1"):
            x, y, z = w.get("X", x), w.get("Y", y), w.get("Z", z)
            if w.get("E", 0) > 0 and ("X" in w or "Y" in w):
                x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
                zmax = max(zmax, z)
        elif cmd in ("G2", "G3"):
            raise ConvertError("arc moves (G2/G3) are not supported - disable arc fitting")
        elif cmd in ("M104", "M109") and "S" in w:
            temps.append(w["S"])
        elif cmd in ("M140", "M190") and w.get("S", 0) > 0:
            bed = max(bed, w["S"])
    return {"bbox": (x0, y0, x1, y1), "zmax": zmax, "layers": layers, "temps": temps, "bed": bed}


STANDBY_C = 170          # second nozzle waits warm (PLA barely oozes) until its colour starts
SWAP_LIFT_MM = 2.0       # lift before the extruder swap
SWAP_PURGE_MM = 6.0      # purge of the new nozzle (in the air, in front of the part)


def convert(gcode_path, out_path, name=None, tool=1, z_offset=0.0, prime=True, log=print,
            color_z=None, tool2=None, temp2=None, first_temp=None, bed=0, tilt_x=0.0, tools=None):
    """color_z: print every layer ABOVE this height (mm) with tool2 (the other extruder).
    One colour change per print -> clean two-colour parts on a dual-nozzle machine.
    tools: two parts in two colours (G-code from a 2-extruder slice with T0 / T1 changes):
    (nozzle for T0, nozzle for T1), e.g. (1, 0) = part 1 left, part 2 right. Both nozzles are hot
    for the whole print; every T change is a software nozzle shift (never the bogus firmware T1).
    bed: heated-bed temperature (0 = off). Only the converter sets it - bed commands inside the
    G-code are ignored - and it is capped at BED_MAX_C.
    tilt_x: bed tilt compensation, mm per 100 mm toward the RIGHT. + lifts the nozzle on the right
    (right side squashed / paper tight), - lowers it (right side gap too big). Centre unchanged."""
    if abs(tilt_x) > TILT_MAX:
        raise ConvertError("tilt %.2f mm/100 mm refused - more than %.1f: level the bed with the knobs first"
                           % (tilt_x, TILT_MAX))
    lines = open(gcode_path, encoding="utf-8", errors="replace").read().splitlines()
    info = scan(lines)
    bed = int(bed or 0)
    if not 0 <= bed <= BED_MAX_C:
        raise ConvertError("bed temperature %d C refused - 0 (off) to %d C for PLA" % (bed, BED_MAX_C))
    if info["bed"] > 0 and not bed:
        raise ConvertError("G-code heats the bed to %d C - choose the bed temperature in this app "
                           "(bed option) and set it 0 in the slicer." % info["bed"])
    if not info["temps"] and not first_temp:
        raise ConvertError("no nozzle temperature found in the G-code")
    x0, y0, x1, y1 = info["bbox"]
    if x0 > x1:
        raise ConvertError("no printing moves found in the G-code")
    if x0 < -0.5 or y0 < -0.5 or x1 > BED_W + 0.5 or y1 > BED_D + 0.5:
        raise ConvertError("model does not fit on the bed (%.0f..%.0f x %.0f..%.0f mm, bed 225 x 145)"
                           % (x0, x1, y0, y1))
    if tool == 0 and x1 - CX > HEAD_X_MAX:
        raise ConvertError("right nozzle cannot reach X %.0f" % x1)
    # PrusaSlicer writes no start temperature (empty start G-code), so the first M104 in the file
    # is the LATER-layer temperature - use the first-layer temperature the user asked for
    first_temp = int(first_temp or info["temps"][0])
    name = (name or os.path.splitext(os.path.basename(out_path))[0])[:20]

    p = Printer()
    p.tilt_x = tilt_x / 100.0
    p._cmd(struct.pack("<BI", 153, 0) + name.encode("ascii", "replace") + b"\0")
    p.percent(0)
    p.set_bed(0)
    p._cmd(struct.pack("<BB", 134, 0), "T0 ; firmware stays on tool 0 (bogus T1 offset)")
    p.set_temp(0, 0)
    p.set_temp(1, 0)                                  # heaters OFF until homing worked
    p.change_tool(0)
    p.home(z_fast=5.0, z_timeout=40)                  # slow Z homing - proven safe
    p.move(z=5.0, f=5.0)
    two_parts = tools is not None
    if two_parts:
        if color_z:
            raise ConvertError("two parts and a colour height cannot be combined")
        tmap = {0: tools[0], 1: tools[1]}
        first_t = next((int(ln.strip()[1]) for ln in lines if ln.strip() in ("T0", "T1")), 0)
        tool = tmap[first_t]                           # the nozzle that prints first
        tool2 = tmap[1 - first_t]
        temp2 = int(temp2 or first_temp)
    two_colour = bool(color_z) and color_z > 0
    if two_colour:
        tool2 = (1 - tool) if tool2 is None else tool2
        temp2 = int(temp2 or first_temp)
        if color_z >= info["zmax"]:
            raise ConvertError("colour change at Z %.2f mm is above the top of the model (%.2f mm)"
                               % (color_z, info["zmax"]))
    if bed:
        p.set_bed(bed)                                 # bed first (slow); nozzle heats after it,
        p.wait_bed()                                   # so the nozzle does not ooze while waiting
    p.set_temp(tool, first_temp)
    if two_colour:
        p.set_temp(tool2, STANDBY_C)                   # second colour waits warm, not hot
    if two_parts:
        p.set_temp(tool2, first_temp)                  # both parts grow together: both nozzles hot
    p.wait_tool(tool)
    if two_colour or two_parts:
        p.wait_tool(tool2)                             # standby nozzle warm too: nothing heats mid-print
    p.change_tool(tool, shift=False)                 # head at the X end: next move goes direct

    # prime line in front of the object (skipped if the object reaches the front edge)
    py = min(-66.0, (y0 - CY) - 6.0)
    if prime and py >= -70.0:
        if tool == 1:
            px0, px1 = -60.0, -15.0
        else:
            px0, px1 = 15.0, 60.0
        p.move(px0, py, f=80.0)
        prime_line(p, px0, px1, py, 0.3 + z_offset, 80.0)
        p.move(z=p.pos[2] + 0.6, f=10.0)
    else:
        p.move((x0 + x1) / 2 - CX, (y0 + y1) / 2 - CY, f=80.0)

    # ---- stream the sliced moves --------------------------------------------------
    absolute = True
    rel_e = True
    f = 30.0
    last_e = 0.0
    x, y, z = p.pos[0] + CX, p.pos[1] + CY, None
    layer = 0
    warned = set()
    active = tool
    swapped = False
    swaps = 0
    purge_y = min(-62.0, (y0 - CY) - 10.0)
    for ln in lines:
        if ln.startswith(";LAYER_CHANGE"):
            layer += 1
            if info["layers"]:
                p.percent(min(99, round(100 * layer / info["layers"])))
            continue
        if two_colour and not swapped and ln.startswith(";Z:"):
            if float(ln[3:]) > color_z + 1e-6:
                # ---- colour change: first extruder done, second extruder takes over ----
                p.comment("colour change at Z %.2f: tool %d -> tool %d" % (color_z, active, tool2))
                p.move(de=-2.0, f=25.0)                       # retract the first colour
                p.move(z=p.pos[2] + SWAP_LIFT_MM, f=10.0)     # lift clear of the part
                p.set_temp(tool2, temp2)
                p.wait_tool(tool2)
                p.set_temp(active, 0)                         # first colour is finished
                p.change_tool(tool2)                          # head shifts by the nozzle spacing
                active = tool2
                px = -45.0 if tool2 == 1 else 45.0            # in front of the part, own spot
                p.move(px, purge_y, f=60.0)
                p._cmd(struct.pack("<BI", 133, 3000), "G4 P3000 ; settle the new nozzle")
                p.move(de=SWAP_PURGE_MM, f=2.0)               # purge (falls on the bed)
                p.move(px + (12.0 if px < 0 else -12.0), purge_y, f=80.0)   # wipe: snap the strand
                swapped = True
                x, y = p.pos[0] + CX, p.pos[1] + CY
            continue
        cmd, w = parse(ln)
        if cmd is None:
            continue
        if two_parts and cmd in ("T0", "T1"):
            # ---- part change: the other nozzle prints the other part (and purges on the tower) ----
            new = tmap[int(cmd[1])]
            if new != active:
                p.comment("nozzle change: tool %d -> tool %d" % (active, new))
                p.change_tool(new)                    # head shifts so the new nozzle is where the old one was
                active = new
                swaps += 1
            continue
        if cmd in ("G0", "G1"):
            if "F" in w:
                f = w["F"] / 60.0
            if not any(k in w for k in "XYZE"):
                continue
            nx, ny, nz = w.get("X"), w.get("Y"), w.get("Z")
            px, py_, pz = x, y, z
            if not absolute:
                nx = None if nx is None else x + nx
                ny = None if ny is None else y + ny
                nz = None if nz is None else (z or 0) + nz
            if nx is not None:
                x = nx
            if ny is not None:
                y = ny
            if nz is not None:
                z = nz
            if "E" in w:
                de = w["E"] if rel_e else w["E"] - last_e
                last_e = w["E"] if not rel_e else last_e
            else:
                de = 0.0
            xy_move = nx is not None or ny is not None
            if xy_move:
                speed = min(f, MAX_XY_F)
            elif nz is not None:
                speed = min(f, MAX_Z_F)
            else:
                speed = min(f, MAX_E_F)
            if de and (xy_move or nz is not None):
                # never spin the extruder faster than MAX_E_F (e.g. wipe/retract while moving)
                dist = math.sqrt((x - px) ** 2 + (y - py_) ** 2 + ((z or 0) - (pz or 0)) ** 2)
                if dist > 0:
                    speed = min(speed, dist * MAX_E_F / abs(de))
            p.move(x - CX if nx is not None else None, y - CY if ny is not None else None,
                   z + z_offset if nz is not None else None, de=de, f=max(speed, 1.0))
        elif cmd == "G90":
            absolute = True
        elif cmd == "G91":
            absolute = False
        elif cmd == "M82":
            rel_e = False
        elif cmd == "M83":
            rel_e = True
        elif cmd == "G92":
            if "E" in w:
                last_e = w["E"]
        elif cmd in ("M104", "M109"):
            if "S" in w:
                which = tmap.get(int(w["T"]), active) if two_parts and "T" in w else active
                p.set_temp(which, int(w["S"]))
                if cmd == "M109":
                    p.wait_tool(which)
        elif cmd == "G4":
            ms = int(w.get("P", 0) + w.get("S", 0) * 1000)
            if ms > 0:
                p._cmd(struct.pack("<BI", 133, ms), "G4 P%d" % ms)
        elif cmd in ("M140", "M190"):
            pass                                          # bed stays off (checked above)
        elif cmd in ("G21", "M106", "M107", "M84", "M73", "M117", "M107", "M204", "M201",
                     "M203", "M205", "M220", "M221", "M900", "M486", "T0", "T1", "G28"):
            pass                                          # not needed / handled by our start code
        else:
            if cmd not in warned:
                warned.add(cmd)
                log("note: ignored G-code command %s" % cmd)

    # ---- finish ---------------------------------------------------------------------
    p.comment("end")
    p.move(de=-2.0, f=25.0)
    p.set_temp(0, 0)
    p.set_temp(1, 0)
    p.set_bed(0)
    p.move(z=min(140.0, p.pos[2] + 40.0), f=10.0)        # bed down, away from the part
    p.change_tool(0)
    us_xy = round(1e6 / (2500 / 60 * SPM["x"]))
    p._cmd(struct.pack("<BBIH", 132, 0x03, us_xy, 60), "G162 X Y F2500")
    p._cmd(struct.pack("<BB", 137, 0x1F), "M18 ; motors off")
    p.percent(100)
    p._cmd(struct.pack("<BB", 154, 0), "M137 ; build end")
    struct.pack_into("<I", p.x3g, 1, p.ncmd)
    with open(out_path, "wb") as fh:
        fh.write(p.x3g)
    return {"layers": info["layers"], "zmax": info["zmax"], "commands": p.ncmd,
            "filament": p.e[tool] + (p.e[tool2] if (two_colour or two_parts) else 0.0),
            "filament_by_tool": tuple(p.e), "time_s": p.time_s, "temp": first_temp,
            "two_colour": two_colour, "swapped": swapped, "two_parts": two_parts, "swaps": swaps,
            "bbox": (x0 - CX, y0 - CY, x1 - CX, y1 - CY)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("gcode")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tool", choices=("left", "right"), default="left")
    ap.add_argument("--z-offset", type=float, default=0.0)
    ap.add_argument("--no-prime", action="store_true")
    ap.add_argument("--color-z", type=float, default=0.0,
                    help="layers above this height (mm) print with the OTHER extruder (0 = off)")
    ap.add_argument("--temp2", type=int, default=None, help="temperature of the second extruder")
    a = ap.parse_args()
    r = convert(a.gcode, a.out, tool=0 if a.tool == "right" else 1, z_offset=a.z_offset,
                prime=not a.no_prime, color_z=a.color_z or None, temp2=a.temp2)
    print("wrote %s: %d layers, %.1f mm tall, %d commands, %.0f mm filament, ~%.0f min"
          % (a.out, r["layers"], r["zmax"], r["commands"], r["filament"], r["time_s"] / 60))
