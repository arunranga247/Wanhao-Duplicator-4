"""
Finish a print that was stopped part-way, ON TOP OF the part still stuck on the bed.

    python tools/resume_print.py --gcode output/MAP_BOX_COVER.gcode --from-z 1.9 [--name ...]

--from-z is the slicer's layer height (the ";Z:" value) to continue from: the first layer that
was NOT printed. Pick the layer above the last COMPLETE one - re-printing a half-finished layer
would drive the nozzle into the plastic that is already there.

The new file homes X/Y first (nozzle parks off the bed corner, away from the part), homes Z,
heats, primes in front of the part, LIFTS above the part before any sideways move, then prints
only the layers from --from-z up. Same bed position as the original (same G-code), so the new
layers land exactly on the old ones.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import os
import sys
import tempfile

import d4_paths
from gcode2x3g import ConvertError, convert


def resume_lines(lines, from_z):
    """Header (units / modes) + safe lift + every layer from the one at from_z. Relative E only."""
    if not any(ln.startswith("M83") for ln in lines[:40]):
        raise ConvertError("only relative-extrusion G-code (M83, PrusaSlicer default here) can be resumed")
    first = next(i for i, ln in enumerate(lines) if ln.startswith(";LAYER_CHANGE"))
    tag = ";Z:%g" % from_z
    cut = next((i - 1 for i, ln in enumerate(lines) if ln.strip() == tag and lines[i - 1].startswith(";LAYER_CHANGE")),
               None)
    if cut is None:
        raise ConvertError("no layer at Z %g in this G-code" % from_z)
    lift = "G1 Z%.2f F600 ; resume: lift clear of the part BEFORE any sideways move" % (from_z + 1.0)
    return lines[:first] + [lift] + lines[cut:], sum(1 for ln in lines[cut:] if ln.startswith(";LAYER_CHANGE"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gcode", required=True, help="the G-code the stopped print was made from")
    ap.add_argument("--from-z", type=float, required=True, help="slicer ;Z: value of the first layer to print")
    ap.add_argument("--name", default=None)
    ap.add_argument("--out", default=d4_paths.OUT)
    ap.add_argument("--only", choices=("left", "right"), default="left")
    ap.add_argument("--temp", type=int, default=220)
    ap.add_argument("--bed", type=int, default=60)
    ap.add_argument("--z-offset", type=float, default=-0.05, help="must match the original print")
    a = ap.parse_args()
    src = os.path.abspath(a.gcode)
    lines = open(src, encoding="utf-8", errors="replace").read().splitlines()
    try:
        body, n_layers = resume_lines(lines, a.from_z)
    except (ConvertError, StopIteration) as e:
        sys.exit("Cannot resume: %s" % e)
    name = (a.name or os.path.splitext(os.path.basename(src))[0] + "_RESUME").upper()[:24]
    out_x3g = os.path.join(a.out, name + ".x3g")
    with tempfile.TemporaryDirectory() as tmp:
        g = os.path.join(tmp, name + ".gcode")
        open(g, "w", encoding="utf-8").write("\n".join(body) + "\n")
        try:
            res = convert(g, out_x3g, name=name, tool=0 if a.only == "right" else 1, z_offset=a.z_offset,
                          log=lambda m: None, first_temp=a.temp, temp2=a.temp, bed=a.bed)
        except ConvertError as e:
            sys.exit("Conversion refused: %s" % e)
        open(os.path.join(a.out, name + ".gcode"), "w", encoding="utf-8").write("\n".join(body) + "\n")
    print("wrote %s: %d layers from Z %g (printed at %.2f) up to %.1f mm, nozzle %d C, bed %d C, est. %.0f min"
          % (out_x3g, n_layers, a.from_z, a.from_z + a.z_offset, res["zmax"], a.temp, a.bed, res["time_s"] / 60))


if __name__ == "__main__":
    main()
