"""
Port a G-code sliced for ANOTHER printer (Cura / PrusaSlicer for an Ender 3 etc.) to the
Duplicator 4, when you only have the G-code and not the 3-D model.

    python tools/port_gcode.py --gcode downloaded.gcode --name PART [--only left|right]
                               [--temp 220 --first-temp 225 --max-retract 1.5 --z-offset -0.05]

What it fixes:
  * drops the other printer's start / end code (G28 + purge lines that run off this bed,
    "present the print" moves) - the Duplicator 4's own safe start + prime line is used instead
  * replaces the other printer's bed heating with this printer's own (--bed, 60 C for PLA)
  * re-centres the parts on this 225 x 145 mm bed
  * shortens long Bowden retractions (e.g. 6.5 mm) to a direct-drive friendly length
  * sets this printer's temperatures (first layer + rest)
Then converts with gcode2x3g (speed limits, extruder direction, software nozzle offset).
Toolpaths stay exactly as the original slicer made them (0.4 mm nozzle, 1.75 mm filament).
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import os
import re
import sys
import tempfile

import d4_paths
from gcode2x3g import ConvertError, convert

BED_CX, BED_CY = 112.5, 72.5          # bed centre in slicer coordinates (see slice_model --center)
NUM = r"(-?\d+(?:\.\d*)?|-?\.\d+)"


def body_lines(lines):
    """Lines of the print itself: from the first layer to the last layer's end."""
    start = next((i for i, ln in enumerate(lines) if ln.startswith((";LAYER:0", ";LAYER_CHANGE"))), None)
    if start is None:
        raise ConvertError("no layer markers found (;LAYER:0 / ;LAYER_CHANGE) - is this a sliced G-code?")
    # Cura: the print ends at the LAST ";TIME_ELAPSED" (its end code - "present print" moves that
    # leave this bed - follows). Other slicers: the line where their end code starts.
    elapsed = [i for i, ln in enumerate(lines) if ln.startswith(";TIME_ELAPSED") and i > start]
    if elapsed:
        return lines[start:max(elapsed) + 1]
    ends = [i for i, ln in enumerate(lines) if i > start and ln.lstrip(";").strip().lower().startswith(
        ("end gcode", "end_gcode", "end of gcode", "filament end gcode", "end g-code"))]
    return lines[start:min(ends)] if ends else lines[start:]


def extents(body):
    xs, ys = [], []
    e_last = 0.0
    absolute_e = True
    for ln in body:
        s = ln.split(";")[0].strip()
        if s.startswith("M83"):
            absolute_e = False
        elif s.startswith("M82"):
            absolute_e = True
        if not s.startswith("G1 "):
            continue
        e = re.search(r"\bE" + NUM, s)
        if not e:
            continue
        ev = float(e.group(1))
        extruding = (ev > 0) if not absolute_e else (ev > e_last)
        if absolute_e:
            e_last = max(e_last, ev)
        if extruding:
            x, y = re.search(r"\bX" + NUM, s), re.search(r"\bY" + NUM, s)
            if x:
                xs.append(float(x.group(1)))
            if y:
                ys.append(float(y.group(1)))
    if not xs or not ys:
        raise ConvertError("no printing moves found")
    return min(xs), max(xs), min(ys), max(ys)


def port(src, temp, max_retract, speed=1.0, first_speed=None, flow=1.0):
    """speed: factor on printing feed rates (other printers often print faster than this one can
    melt plastic); first_speed: mm/s cap on the first layer; flow: extrusion multiplier."""
    lines = open(src, encoding="utf-8", errors="replace").read().splitlines()
    body = body_lines(lines)
    x0, x1, y0, y1 = extents(body)
    dx, dy = BED_CX - (x0 + x1) / 2, BED_CY - (y0 + y1) / 2
    out = ["G90", "M82", "G92 E0"]
    absolute_e, e_hi, e_last = True, 0.0, 0.0
    n_ret = 0
    first_layer = True

    def set_e(line, value):
        return re.sub(r"\bE" + NUM, "E%.5f" % (value * flow), line)

    def feed(m):
        f = float(m.group(1)) * speed
        if first_layer and first_speed:
            f = min(f, first_speed * 60)
        return "F%.0f" % f

    for ln in body:
        s = ln.split(";")[0].strip()
        if ln.startswith(";LAYER:"):
            out.append(";LAYER_CHANGE")
            if ln.strip() == ";LAYER:1":
                out.append("M104 S%d" % temp)                   # rest of the print
                first_layer = False
            out.append(ln)
            continue
        if not s:
            out.append(ln)
            continue
        cmd = s.split()[0]
        if cmd in ("M104", "M109", "M140", "M190", "G28", "G29", "M84", "M18"):
            continue                                            # temperatures / homing are ours
        if cmd == "M83":
            absolute_e = False
        elif cmd == "M82":
            absolute_e = True
        elif cmd == "G92":
            e = re.search(r"\bE" + NUM, s)
            if e:
                e_hi = e_last = float(e.group(1))
                s = set_e(s, e_hi)
        elif cmd in ("G0", "G1"):
            def shift(m, axis, d):
                return "%s%.3f" % (axis, float(m.group(1)) + d)
            s = re.sub(r"\bX" + NUM, lambda m: shift(m, "X", dx), s)
            s = re.sub(r"\bY" + NUM, lambda m: shift(m, "Y", dy), s)
            if cmd == "G1":                                     # printing moves: slower
                s = re.sub(r"\bF" + NUM, feed, s)
            e = re.search(r"\bE" + NUM, s)
            only_e = e and not re.search(r"\b[XYZ]" + NUM, s)
            if e:
                ev = float(e.group(1))
                if absolute_e:
                    if only_e and ev < e_hi - 1e-6:             # retraction: shorten it
                        r = e_hi - ev
                        if r > max_retract:
                            ev = e_hi - max_retract
                            n_ret += 1
                    e_hi = max(e_hi, ev)
                    e_last = ev
                    s = set_e(s, ev)
                elif only_e and ev < -max_retract:              # relative E retraction
                    s = set_e(s, -max_retract)
                    n_ret += 1
                elif only_e and ev > max_retract and out and "E-" in out[-1]:
                    s = set_e(s, max_retract)
                else:
                    s = set_e(s, ev)
        out.append(s)
    return out, (x1 - x0, y1 - y0), (dx, dy), n_ret


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gcode", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--out", default=d4_paths.OUT)
    ap.add_argument("--only", choices=("left", "right"), default="left")
    ap.add_argument("--temp", type=int, default=220)
    ap.add_argument("--first-temp", type=int, default=225)
    ap.add_argument("--max-retract", type=float, default=1.5)
    ap.add_argument("--z-offset", type=float, default=-0.05)
    ap.add_argument("--speed", type=float, default=0.6, help="factor on printing speeds (0.6 = 60 %%)")
    ap.add_argument("--first-speed", type=float, default=15.0, help="first layer speed cap, mm/s")
    ap.add_argument("--flow", type=float, default=1.05, help="extrusion multiplier")
    ap.add_argument("--bed", type=int, default=60, help="heated bed C (PLA 60, 0 = off, max 70)")
    a = ap.parse_args()
    src = os.path.abspath(a.gcode)
    name = (a.name or os.path.splitext(os.path.basename(src))[0]).upper()
    name = "".join(ch for ch in name if ch.isalnum() or ch in "_-")[:24] or "PORTED"
    try:
        lines, size, shift, n_ret = port(src, a.temp, a.max_retract, a.speed, a.first_speed, a.flow)
    except ConvertError as e:
        sys.exit("Cannot port this G-code: %s" % e)
    os.makedirs(a.out, exist_ok=True)
    out_x3g = os.path.join(a.out, name + ".x3g")
    with tempfile.TemporaryDirectory() as tmp:
        g = os.path.join(tmp, name + ".gcode")
        with open(g, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        try:
            res = convert(g, out_x3g, name=name, tool=0 if a.only == "right" else 1, z_offset=a.z_offset,
                          log=lambda m: print(m), first_temp=a.first_temp, bed=a.bed)
        except ConvertError as e:
            sys.exit("Conversion refused: %s" % e)
        with open(g, "rb") as fh, open(os.path.join(a.out, name + ".gcode"), "wb") as dst:
            dst.write(fh.read())
    print("ported %s -> %s" % (os.path.basename(src), out_x3g))
    print("  parts %.0f x %.0f mm, moved %+.1f / %+.1f mm to the bed centre, %d long retractions shortened to %.1f mm"
          % (size[0], size[1], shift[0], shift[1], n_ret, a.max_retract))
    print("  %d layers, %.1f mm tall, %s extruder, %d C first layer then %d C, bed %s"
          % (res["layers"], res["zmax"], a.only, a.first_temp, a.temp, "%d C" % a.bed if a.bed else "off"))
    print("  speed %d %% of the original (first layer max %g mm/s), flow %d %%, first layer squish %+.2f mm"
          % (a.speed * 100, a.first_speed, a.flow * 100, a.z_offset))
    print("  filament %.0f mm (~%.1f g PLA), est. %.0f min after heat-up"
          % (res["filament"], res["filament"] * 2.405 * 1.24 / 1000, res["time_s"] / 60))


if __name__ == "__main__":
    main()
