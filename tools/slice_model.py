"""
Slice ANY 3D model (STL / 3MF / OBJ) for the Wanhao Duplicator 4.

    python tools/slice_model.py --model part.stl --name PART --out output/ [options]

1. PrusaSlicer engine slices the model with the Duplicator 4 PLA profile
   (engine/duplicator4_pla.ini) + the options below
2. gcode2x3g converts it with this printer's fixes (extruder direction, software nozzle
   offset, slow Z homing, heated bed 60 C for PLA, prime line)
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
ap.add_argument("--supports", type=float, default=0,
                help="0 = off, 1 = tree supports (standard, best for figures), 2 = straight pillars")
ap.add_argument("--brim", type=float, default=5)
ap.add_argument("--scale", type=float, default=100, help="percent")
ap.add_argument("--temp", type=int, default=210)
ap.add_argument("--first-temp", type=int, default=220)
ap.add_argument("--z-offset", type=float, default=-0.05)
ap.add_argument("--color-z", type=float, default=0.0,
                help="two colours: layers above this height (mm) use the OTHER extruder (0 = off)")
ap.add_argument("--fast", type=int, default=0,
                help="1 = faster speeds for simple parts (boxes, brackets), melt rate capped at 8 mm3/s")
ap.add_argument("--bed", type=int, default=60, help="heated bed C (PLA 60, 0 = off, max 70)")
ap.add_argument("--fine", type=int, default=0,
                help="1 = best finish: 0.12 mm layers, slow outer walls, ironed top surfaces, seam at "
                     "the back (about 1.7x longer)")
ap.add_argument("--tilt-x", type=float, default=0.0,
                help="bed tilt fix, mm per 100 mm to the right (+ = right side too tight, - = gap too big)")
ap.add_argument("--min-layer-time", type=float, default=0,
                help="seconds per layer at least (0 = profile's 15 s); more = small parts cool better")
ap.add_argument("--clean", type=int, default=1,
                help="1 = travel moves stay inside the part (no strings across holes / gaps)")
ap.add_argument("--model2", default=None,
                help="second part, printed by the OTHER extruder in the same job (two colours, e.g. a "
                     "case base in one colour and its lid in another)")
ap.add_argument("--tower", type=int, default=1,
                help="two parts: 1 = purge tower next to the parts keeps the colours clean (0 = off)")
ap.add_argument("--prusaslicer", default=None)
a = ap.parse_args()

model = os.path.abspath(a.model)
if not os.path.isfile(model):
    sys.exit("model file not found: %s" % model)
if os.path.splitext(model)[1].lower() not in (".stl", ".3mf", ".obj", ".amf"):
    sys.exit("unsupported file type - use STL, 3MF, OBJ or AMF")
model2 = os.path.abspath(a.model2) if a.model2 else None
if model2:
    if not os.path.isfile(model2):
        sys.exit("second model file not found: %s" % model2)
    if os.path.splitext(model2)[1].lower() not in (".stl", ".3mf", ".obj"):
        sys.exit("second part: use STL, 3MF or OBJ")
    if a.color_z > 0:
        sys.exit("two parts and 'Colour Z' cannot be combined - choose one")
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
           "--layer-height", "%g" % (0.12 if a.fine else a.layer_height),
           "--fill-density", "%g%%" % a.infill,
           "--perimeters", "%d" % a.walls,
           "--brim-width", "%g" % a.brim,
           "--output", gcode]
    lay = None
    if model2:
        # both parts side by side + purge tower, part 1 = extruder 1, part 2 = extruder 2
        import two_part
        project = os.path.join(tmp, name + "_2parts.3mf")
        try:
            lay = two_part.write_3mf(model, model2, project, scale_pct=a.scale, brim=a.brim)
        except two_part.LayoutError as e:
            sys.exit(str(e))
        cmd += two_part.slicer_options(a.temp, a.first_temp, tower=bool(a.tower))
    else:
        cmd += ["--temperature", "%d" % a.temp, "--first-layer-temperature", "%d" % a.first_temp,
                "--scale", "%g%%" % a.scale, "--center", "112.5,72.5"]
    if a.supports >= 0.5:
        cmd += ["--support-material", "--support-material-auto"]
        if a.supports < 1.5:
            # 1 = tree (organic) supports - the standard: thin branches touch the model only where
            # needed, less plastic, cleaner surfaces, snap off easily
            cmd += ["--support-material-style", "organic"]
        # 2 = classic straight pillars (only for big flat overhangs)
    if a.fast:
        # ~35-45 % quicker; the volumetric cap keeps the hot end from running out of melt
        cmd += ["--perimeter-speed", "45", "--external-perimeter-speed", "32", "--infill-speed", "60",
                "--solid-infill-speed", "45", "--top-solid-infill-speed", "28", "--gap-fill-speed", "30",
                "--small-perimeter-speed", "20", "--bridge-speed", "30", "--max-volumetric-speed", "8"]
    if a.clean:
        cmd += ["--avoid-crossing-perimeters"]
    if a.min_layer_time > 0:
        cmd += ["--slowdown-below-layer-time", "%g" % a.min_layer_time, "--min-print-speed", "5"]
    if a.fine:
        # smooth walls (slow outer line), ironed flat tops, seam hidden at the back
        cmd += ["--external-perimeter-speed", "15", "--perimeter-speed", "25",
                "--top-solid-infill-speed", "15", "--ironing", "--ironing-type", "top",
                "--ironing-flowrate", "15%", "--ironing-speed", "15", "--seam-position", "rear"]
    cmd.append(project if model2 else model)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not os.path.exists(gcode):
        msg = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip() and "=>" not in ln]
        sys.exit("PrusaSlicer could not slice the model:\n" + "\n".join(msg[-8:]))
    try:
        first = 0 if a.only == "right" else 1              # nozzle of part 1 (1 = left)
        res = convert(gcode, out_x3g, name=name, tool=first,
                      z_offset=a.z_offset, log=lambda m: print(m),
                      color_z=a.color_z if a.color_z > 0 else None, temp2=a.temp,
                      first_temp=a.first_temp, bed=a.bed, tilt_x=a.tilt_x,
                      tools=(first, 1 - first) if model2 else None)
    except ConvertError as e:
        sys.exit("Conversion refused: %s" % e)
    # keep a copy of the G-code next to the x3g (handy for checking in a G-code viewer)
    with open(gcode, "rb") as src, open(os.path.join(a.out, name + ".gcode"), "wb") as dst:
        dst.write(src.read())

x0, y0, x1, y1 = res["bbox"]
print("wrote %s" % out_x3g)
print("  %d layers, %.1f mm tall, footprint %.0f x %.0f mm, %s extruder, %d C, bed %s"
      % (res["layers"], res["zmax"], x1 - x0, y1 - y0, a.only, res["temp"],
         "%d C" % a.bed if a.bed else "off"))
if res.get("two_parts"):
    fr, fl = res["filament_by_tool"]
    other = "right" if a.only != "right" else "left"
    print("  two parts: part 1 = %s nozzle, part 2 = %s nozzle, %d nozzle changes%s  (filament R %.0f / L %.0f mm)"
          % (a.only, other, res["swaps"], ", purge tower" if a.tower else "", fr, fl))
if res.get("two_colour"):
    other = "left" if a.only == "right" else "right"
    fr, fl = res["filament_by_tool"]
    print("  two colours: %s extruder up to Z %.2f mm, then %s extruder  (filament R %.0f / L %.0f mm)"
          % (a.only, a.color_z, other, fr, fl))
print("  filament %.0f mm (~%.1f g PLA), est. %.0f min after heat-up"
      % (res["filament"], res["filament"] * 2.405 * 1.24 / 1000, res["time_s"] / 60))
