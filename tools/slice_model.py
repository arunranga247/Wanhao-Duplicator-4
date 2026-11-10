"""
Slice ANY 3D model (STL / 3MF / OBJ) for the Wanhao Duplicator 4.

    python tools/slice_model.py --model part.stl --name PART --out output/ [options]

1. PrusaSlicer engine slices the model with the Duplicator 4 PLA profile
   (engine/duplicator4_pla.ini) + the options below
2. gcode2x3g converts it with this printer's fixes (extruder direction, software nozzle
   offset, slow Z homing, unheated bed, prime line)
3. prints a short summary; the GUI then runs the safety checker and the preview
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import os
import subprocess
import sys
import tempfile

import d4_paths
from gcode2x3g import ConvertError, convert

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--name", default=None)
ap.add_argument("--out", default=d4_paths.OUT)
ap.add_argument("--only", choices=("left", "right"), default="left", help="extruder")
ap.add_argument("--layer-height", type=float, default=0.2)
ap.add_argument("--infill", type=float, default=20)
ap.add_argument("--walls", type=int, default=3)
ap.add_argument("--supports", type=float, default=0, help="0 = off, 1 = automatic")
ap.add_argument("--brim", type=float, default=5)
ap.add_argument("--scale", type=float, default=100, help="percent")
ap.add_argument("--temp", type=int, default=210)
ap.add_argument("--first-temp", type=int, default=220)
ap.add_argument("--z-offset", type=float, default=-0.05)
ap.add_argument("--color-z", type=float, default=0.0,
                help="two colours: layers above this height (mm) use the OTHER extruder (0 = off)")
ap.add_argument("--fast", type=int, default=0,
                help="1 = faster speeds for simple parts (boxes, brackets), melt rate capped at 8 mm3/s")
ap.add_argument("--prusaslicer", default=None)
a = ap.parse_args()

model = os.path.abspath(a.model)
if not os.path.isfile(model):
    sys.exit("model file not found: %s" % model)
if os.path.splitext(model)[1].lower() not in (".stl", ".3mf", ".obj", ".amf"):
    sys.exit("unsupported file type - use STL, 3MF, OBJ or AMF")
engine = d4_paths.find_prusaslicer(a.prusaslicer)
if not engine:
    sys.exit("PrusaSlicer engine not found. Put PrusaSlicer in an 'engine' folder next to the app "
             "or install PrusaSlicer.")
name = (a.name or os.path.splitext(os.path.basename(model))[0]).upper()
name = "".join(ch for ch in name if ch.isalnum() or ch in "_-")[:24] or "MODEL"
os.makedirs(a.out, exist_ok=True)
out_x3g = os.path.join(a.out, name + ".x3g")

with tempfile.TemporaryDirectory() as tmp:
    gcode = os.path.join(tmp, name + ".gcode")
    cmd = [engine, "--export-gcode", "--load", d4_paths.profile_path(),
           "--layer-height", "%g" % a.layer_height,
           "--fill-density", "%g%%" % a.infill,
           "--perimeters", "%d" % a.walls,
           "--brim-width", "%g" % a.brim,
           "--temperature", "%d" % a.temp,
           "--first-layer-temperature", "%d" % a.first_temp,
           "--scale", "%g%%" % a.scale,
           "--center", "112.5,72.5",
           "--output", gcode]
    if a.supports >= 0.5:
        cmd += ["--support-material", "--support-material-auto"]
    if a.fast:
        # ~35-45 % quicker; the volumetric cap keeps the hot end from running out of melt
        cmd += ["--perimeter-speed", "45", "--external-perimeter-speed", "32", "--infill-speed", "60",
                "--solid-infill-speed", "45", "--top-solid-infill-speed", "28", "--gap-fill-speed", "30",
                "--small-perimeter-speed", "20", "--bridge-speed", "30", "--max-volumetric-speed", "8"]
    cmd.append(model)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not os.path.exists(gcode):
        msg = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip() and "=>" not in ln]
        sys.exit("PrusaSlicer could not slice the model:\n" + "\n".join(msg[-8:]))
    try:
        res = convert(gcode, out_x3g, name=name, tool=0 if a.only == "right" else 1,
                      z_offset=a.z_offset, log=lambda m: print(m),
                      color_z=a.color_z if a.color_z > 0 else None, temp2=a.temp,
                      first_temp=a.first_temp)
    except ConvertError as e:
        sys.exit("Conversion refused: %s" % e)
    # keep a copy of the G-code next to the x3g (handy for checking in a G-code viewer)
    with open(gcode, "rb") as src, open(os.path.join(a.out, name + ".gcode"), "wb") as dst:
        dst.write(src.read())

x0, y0, x1, y1 = res["bbox"]
print("wrote %s" % out_x3g)
print("  %d layers, %.1f mm tall, footprint %.0f x %.0f mm, %s extruder, %d C"
      % (res["layers"], res["zmax"], x1 - x0, y1 - y0, a.only, res["temp"]))
if res.get("two_colour"):
    other = "left" if a.only == "right" else "right"
    fr, fl = res["filament_by_tool"]
    print("  two colours: %s extruder up to Z %.2f mm, then %s extruder  (filament R %.0f / L %.0f mm)"
          % (a.only, a.color_z, other, fr, fl))
print("  filament %.0f mm (~%.1f g PLA), est. %.0f min after heat-up"
      % (res["filament"], res["filament"] * 2.405 * 1.24 / 1000, res["time_s"] / 60))
