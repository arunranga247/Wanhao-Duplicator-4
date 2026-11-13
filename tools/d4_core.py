"""
Duplicator 4 Studio - everything the windows share that is NOT drawing: the object list, saved
settings, themes, and every safety decision as a small plain function (so each rule can be
tested on its own, and the Qt window and the old Tk window follow exactly the same rules).
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import json
import os
import re

import d4_paths

# ---- limits ----------------------------------------------------------------------------------
CHART_SPAN_S = 300              # temperature chart: last 5 minutes
COLD_EXTRUDE_C = 170            # below this, pushing filament grinds it
NOZZLE_MAX_C = 240
FILAMENT_MIN_C, FILAMENT_MAX_C = 170, 240
BED_MAX_C = 70                  # PLA never needs more; matches gcode2x3g / stream_x3g limits
BED_MIN_PLAUSIBLE_C = 15        # a bed reading below room temperature = broken sensor wire
SWITCH_FLUTTER_N, SWITCH_FLUTTER_S = 6, 10      # >6 limit-switch changes in 10 s = loose wire?

# Google Material colours (light = Google Workspace, dark = Google dark theme tints)
PALETTES = {
    "light": {"page": "#f1f3f4", "border": "#dadce0", "bg": "#ffffff", "panel": "#ffffff", "fg": "#202124",
              "dim": "#5f6368", "r": "#ea4335", "l": "#1a73e8", "bed": "#f9ab00", "ok": "#34a853",
              "off": "#dadce0", "warn": "#e37400", "grid": "#e8eaed", "accent": "#1a73e8",
              "accent2": "#1765cc", "on_accent": "#ffffff", "tonal": "#e8f0fe", "tonal_fg": "#1967d2",
              "danger": "#d93025", "danger2": "#b3261e", "field": "#f1f3f4", "btn": "#ffffff",
              "btn_active": "#f1f3f4", "btn_dis": "#f1f3f4", "dis_fg": "#9aa0a6",
              "canvas": "#ffffff", "trough": "#e8eaed", "status": "#ffffff"},
    "dark": {"page": "#202124", "border": "#3c4043", "bg": "#2d2e31", "panel": "#2d2e31", "fg": "#e8eaed",
             "dim": "#9aa0a6", "r": "#f28b82", "l": "#8ab4f8", "bed": "#fdd663", "ok": "#81c995",
             "off": "#5f6368", "warn": "#fcad70", "grid": "#3c4043", "accent": "#8ab4f8",
             "accent2": "#aecbfa", "on_accent": "#202124", "tonal": "#394457", "tonal_fg": "#d2e3fc",
             "danger": "#d93025", "danger2": "#b3261e", "field": "#303134", "btn": "#303134",
             "btn_active": "#3c4043", "btn_dis": "#2a2b2e", "dis_fg": "#5f6368",
             "canvas": "#2d2e31", "trough": "#3c4043", "status": "#2d2e31"},
}
THEME_CHOICES = ("System", "Light", "Dark")


# ---- settings (one JSON file next to the app) -------------------------------------------------
def load_settings():
    try:
        with open(d4_paths.SETTINGS, encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**kw):
    """Merge kw into the settings file. Written to a temp file first, then swapped in, so a
    crash or power cut while saving can never leave a half-written (unreadable) file."""
    s = load_settings()
    s.update(kw)
    tmp = d4_paths.SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=2)
    os.replace(tmp, d4_paths.SETTINGS)


def windows_uses_light_theme():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 1
    except (OSError, ImportError):
        return False


def resolve_theme(choice):
    """'System' / 'Light' / 'Dark' -> 'light' or 'dark'."""
    if choice == "Light":
        return "light"
    if choice == "Dark":
        return "dark"
    return "light" if windows_uses_light_theme() else "dark"


# ---- small helpers ----------------------------------------------------------------------------
def fmt_min(s):
    s = max(0, int(s))
    return "%d:%02d" % (s // 60, s % 60) if s < 3600 else "%dh %02dm" % (s // 3600, s % 3600 // 60)


def safe_name(text, fallback=""):
    """Print-file name from what the user typed: letters, digits, _ and - only, max 24."""
    n = "".join(ch for ch in (text or "").strip().upper() if ch.isalnum() and ch.isascii() or ch in "_-")[:24]
    return n or fallback


def name_from_model(path):
    return safe_name(os.path.splitext(os.path.basename(path))[0], "MODEL")


def parse_number(text):
    """User-typed number -> float, or None (accepts a comma as decimal point)."""
    try:
        v = float(str(text).strip().replace(",", "."))
    except ValueError:
        return None
    return v if v == v and abs(v) != float("inf") else None


# ---- objects the Prepare tab can make ---------------------------------------------
# param: (cli flag, label, default, min, max, step)
OBJECTS = {
    "📦 Your 3D model (STL / 3MF / OBJ)": {
        "script": "slice_model.py", "name": "MODEL", "extruder": True, "model": True, "fixed": [],
        "desc": "Any 3D design (Paint 3D, Tinkercad, Thingiverse …) sliced by the PrusaSlicer "
                "engine with the Duplicator 4 profile. Layer 0.1 fine · 0.2 normal · 0.3 draft. "
                "Squish: negative = first layer closer to the bed. Colour Z: above this height "
                "the OTHER extruder prints (two colours, 0 = off). Fast 1: ~40 % quicker for "
                "simple parts like boxes and brackets (keep 0 for detailed figures). "
                "🔍 Fit check: will it print well (3-D report). 🧩 Assembly: do several parts "
                "(e.g. a box + the boards inside) collide?",
        "params": [("layer-height", "Layer (mm)", 0.2, 0.1, 0.3, 0.05),
                   ("infill", "Infill (%)", 20, 0, 100, 5),
                   ("walls", "Walls", 3, 1, 6, 1),
                   ("supports", "Supports 0/1/2", 0, 0, 2, 1),
                   ("brim", "Brim (mm)", 5, 0, 15, 1),
                   ("scale", "Scale (%)", 100, 10, 500, 5),
                   ("temp", "Nozzle °C", 210, 180, 240, 5),
                   ("first-temp", "1st layer °C", 220, 180, 240, 5),
                   ("z-offset", "Squish (mm)", -0.05, -0.3, 0.3, 0.02),
                   ("color-z", "Colour Z (mm)", 0, 0, 140, 0.1),
                   ("fast", "Fast 0/1", 0, 0, 1, 1)]},
    "Twisted flower vase": {
        "script": "make_vase.py", "name": "TWIST_VASE", "extruder": False, "fixed": [],
        "desc": "6-lobed vase that twists and bulges. Brim + solid spiral base, then one "
                "continuous spiral wall. Left extruder. Looks great, ~15-20 min.",
        "params": [("height", "Height (mm)", 25, 5, 60, 1), ("radius", "Radius (mm)", 14, 6, 30, 1),
                   ("twist", "Twist (°)", 60, 0, 360, 10), ("lobes", "Lobes", 6, 3, 12, 1),
                   ("temp", "Nozzle °C", 210, 180, 240, 5),
                   ("first-temp", "1st layer °C", 220, 180, 240, 5),
                   ("brim", "Brim rings", 6, 0, 15, 1),
                   ("z-offset", "Squish (mm)", -0.08, -0.3, 0.3, 0.02)]},
    "Square block": {
        "script": "make_dual_sample.py", "name": "SQUARE", "extruder": True, "fixed": ["--slow-z"],
        "desc": "Solid square block in the middle of the bed, one extruder. Quick test print.",
        "params": [("size", "Size (mm)", 15, 5, 40, 1), ("height", "Height (mm)", 2, 0.5, 20, 0.5),
                   ("temp", "Nozzle temp (C)", 210, 180, 240, 5)]},
    "Two-colour cubes (R + L)": {
        "script": "make_dual_sample.py", "name": "RL_CUBES", "extruder": False,
        "fixed": ["--slow-z", "--only", "both"],
        "desc": "One cube per extruder, layers alternate R/L. Needs filament in BOTH extruders.",
        "params": [("size", "Cube size (mm)", 10, 5, 25, 1), ("height", "Height (mm)", 2, 0.5, 20, 0.5),
                   ("temp", "Nozzle temp (C)", 210, 180, 240, 5)]},
    "Air demo (left, bed not used)": {
        "script": "make_left_demo.py", "name": "DEMO_LEFT", "extruder": False, "fixed": [],
        "fixed_name": True,
        "desc": "Left nozzle heats and draws a spiral in the air. Bed never moves. "
                "Good quick check that the left extruder feeds.",
        "params": [("temp", "Nozzle temp (C)", 210, 180, 240, 5)]},
}


# ---- plain-language help for every setting (the small "?" next to each setting) ------------------
PARAM_HELP = {
    "layer-height": "Thickness of each printed layer. Thinner layers give a smoother surface and finer "
                    "detail but take longer.\n0.1 = fine  ·  0.2 = normal  ·  0.3 = draft (fast).",
    "infill": "How full the inside of the part is.\n0 % = hollow (only the walls)  ·  20 % = normal  ·  "
              "100 % = solid.\nMore infill = stronger, heavier and slower.",
    "walls": "How many outlines go round every layer. More walls = stronger sides that do not leak.\n"
             "2 - 3 is normal.",
    "supports": "Removable supports under parts that hang in the air (overhangs steeper than 45°).\n"
                "0 = no supports  ·  1 = tree supports (standard): thin branches that touch the model only "
                "where needed - less plastic, cleaner surface, snap off easily  ·  2 = straight pillars, only "
                "for big flat overhangs.",
    "brim": "A thin flat ring printed round the part on the first layer so the corners do not lift. "
            "Peel it off after printing.\n0 = no brim.",
    "scale": "Size of the model.\n100 % = as designed  ·  50 % = half size  ·  200 % = double size.",
    "temp": "Nozzle temperature while printing. PLA: 200 - 215 °C.\nHotter flows better but can leave "
            "thin strings.",
    "first-temp": "Nozzle temperature for the FIRST layer only. A few degrees hotter helps it stick to "
                  "the bed.",
    "z-offset": "'Squish' - how close the first layer is to the bed.\nFirst layer looks like loose "
                "strings -> make it more negative (closer).\nNozzle scrapes / layer looks see-through -> "
                "less negative.",
    "color-z": "Two colours: above this height the OTHER extruder prints.\n0 = one colour only.",
    "fast": "1 = about 40 % quicker, for simple parts such as boxes and brackets.\nKeep 0 for detailed "
            "figures.",
    "height": "How tall the object is.",
    "radius": "How wide the object is, measured from the centre to the side.",
    "twist": "How far the vase turns from the bottom to the top (360° = one full turn).",
    "lobes": "How many petals go round the vase.",
    "size": "Length of each side of the block / cube.",
    "_extruder": "Which nozzle prints: Left or Right. Load filament in that nozzle first.\n"
                 "Both = two parts in two colours in ONE print, e.g. a case base in one colour and its "
                 "lid in another: part 1 on the left nozzle, part 2 on the right nozzle, side by side "
                 "with a small purge tower that keeps the colours clean.",
    "_model2": "Part 2 of a two-colour print (for example the lid). It is printed by the RIGHT nozzle, "
               "next to part 1. Load the second colour in the right nozzle.",
    "_model": "The 3D design file to print: STL, 3MF or OBJ (from Tinkercad, Thingiverse, Paint 3D ...).",
}


# ---- safety decisions (pure functions: easy to test, same in every window) ---------------------
def bed_heat_decision(target, allowed, bed_now):
    """May the bed be set to `target` °C?  -> (ok, value, title, message).
    Blocked when bed heating is switched off, or the bed sensor reads below room temperature
    (broken wire: the controller would think the bed is cold and heat without limit)."""
    t = parse_number(target)
    if t is None:
        return False, 0, "Bed", "'%s' is not a number." % target
    t = int(round(t))
    if t <= 0:
        return True, 0, "", ""
    if not allowed:
        return False, 0, "Bed heating blocked", (
            "Bed heating is switched off ('Allow bed heating').\n"
            "Heating the bed with a faulty sensor can overheat it.")
    if bed_now is not None and bed_now < BED_MIN_PLAUSIBLE_C:
        return False, 0, "Bed heating blocked", (
            "The bed sensor reads %s °C - below room temperature.\n"
            "The sensor wire is probably broken, so the bed could overheat.\n"
            "Repair the wire and run the supervised bed test first." % bed_now)
    if t > BED_MAX_C:
        return True, BED_MAX_C, "Bed limited", "Bed set to the %d °C maximum (asked %d °C)." % (BED_MAX_C, t)
    return True, t, "", ""


def nozzle_value(target):
    """Nozzle target from text -> int clamped to 0..240, or None if not a number."""
    t = parse_number(target)
    return None if t is None else max(0, min(NOZZLE_MAX_C, int(round(t))))


def filament_temp(text):
    t = parse_number(text)
    return None if t is None else max(FILAMENT_MIN_C, min(FILAMENT_MAX_C, int(round(t))))


def extrude_decision(nozzle_now, mm):
    """-> (mm, question). question is None when it is fine; otherwise the nozzle is cold and the
    user must agree to a 2 mm motor test instead (cold filament grinds in the gears)."""
    if nozzle_now is not None and nozzle_now < COLD_EXTRUDE_C:
        return 2.0, ("The nozzle is %d °C (< %d °C).\nPushing filament into a cold nozzle grinds it.\n\n"
                     "Run the motor for only 2 mm as a motor test?" % (nozzle_now, COLD_EXTRUDE_C))
    return mm, None


def print_gate(st, check_ok, check_text, connected, bed_allowed, bed_now):
    """Can this file be printed?  -> list of (kind, title, message), kind 'block' or 'confirm'.
    Empty list = go ahead. Any 'block' = never print; 'confirm' = ask the user."""
    if not connected:
        return [("block", "Print", "The printer is not connected.")]
    if not check_ok:
        return [("block", "Safety check failed",
                 "This file failed the safety check and will not be printed:\n\n" + (check_text or ""))]
    out = []
    if st.get("bed"):
        if not bed_allowed:
            out.append(("block", "Bed heating blocked",
                        "This file heats the bed to %d °C, but 'Allow bed heating' is switched off "
                        "in the Printer tab.\n\nSwitch it on if the bed reads room temperature correctly, "
                        "or use a file made with bed 0." % st["bed"]))
        elif bed_now is not None and bed_now < BED_MIN_PLAUSIBLE_C:
            out.append(("block", "Bed sensor fault",
                        "This file heats the bed to %d °C, but the bed sensor reads %s °C (below room "
                        "temperature) - the wire is probably broken and the bed could overheat.\n\n"
                        "Repair it, or use a file made with bed 0." % (st["bed"], bed_now)))
        elif st["bed"] > BED_MAX_C:
            out.append(("block", "Bed too hot", "This file heats the bed to %d °C (limit %d °C)."
                        % (st["bed"], BED_MAX_C)))
    if st.get("t1_change"):
        out.append(("block", "Unsafe file", "This file uses a firmware T1 tool change. Your printer's "
                    "stored T1 offset is wrong (~228 mm) - the head would crash."))
    if st.get("z_home") == "fast":
        out.append(("confirm", "Fast Z homing", "This file homes Z FAST. On this printer fast Z homing "
                    "caused board resets. Print anyway?"))
    return out


def checklist_items(st):
    uses = [n for t, n in ((0, "RIGHT"), (1, "LEFT")) if st["fil"][t] > 1]
    items = [("Bed is clean and has a thin layer of glue stick (bed heats to %d °C - don't touch it)"
              % st["bed"]) if st["bed"] else "Bed is clean and has blue tape or glue stick (bed is not heated)",
             "Old prints are removed from the bed"]
    if uses:
        items.append("Filament is loaded in the %s extruder%s" % (" and ".join(uses), "s" if len(uses) > 1 else ""))
    if st["z_home"] is None and st["zmax"] < 60:
        items.append("Bed is LOW (at least 2 cm below the nozzles) - this job does not move the bed")
    items.append("I am at the printer and can press EMERGENCY STOP / power off")
    return items


def progress(st, i, n):
    """-> (fraction 0..1, seconds left or None). Uses the motion-time table when there is one,
    so the bar follows real time, not the command count."""
    frac, left = i / max(1, n), None
    if st and st.get("cum") and st.get("time_s", 0) > 0:
        done_t = st["cum"][min(i, len(st["cum"])) - 1] if i else 0.0
        frac, left = done_t / st["time_s"], max(0.0, st["time_s"] - done_t)
    return max(0.0, min(1.0, frac)), left


def temp_state(cur, tgt):
    """Text under a heater name -> (text, heating)."""
    if not tgt:
        return "off", False
    return ("→ %d°" % tgt if cur is not None and cur < tgt - 3 else "✓ %d°" % tgt), True


def board_text(status_bits, flags_table):
    flags = [n for b, n in flags_table if status_bits and status_bits & b]
    return "Board: " + (", ".join(flags) if flags else "idle"), any(f in flags for f in ("HEAT_SHUTDOWN", "POWER_ERROR"))


def parse_fit_result(sout, serr):
    """fit_check.py output -> dict(verdict, text, report, lines[(line, tag)])."""
    lines = (sout or "").splitlines()
    result = next((ln for ln in lines if ln.startswith("RESULT:")), None)
    if result is None:
        result = "RESULT: FAIL - fit check could not run: " + ((serr or "").strip().splitlines() or ["?"])[-1][:200]
    report = next((ln[len("REPORT: "):].strip() for ln in lines if ln.startswith("REPORT: ")), None)
    verdict = (result.split() + ["", "FAIL"])[1]
    issues = [ln.split(" ", 2)[2] for ln in lines
              if ln.startswith(("CHECK WARN", "CHECK FAIL", "PAIR WARN", "PAIR FAIL")) and len(ln.split(" ", 2)) > 2]
    text = "%s Fit check: %s" % ({"OK": "✅", "WARN": "⚠"}.get(verdict, "❌"), result[len("RESULT: "):])
    if issues:
        text += "\n" + "\n".join("• " + i for i in issues[:6])
    if report:
        text += "\n3-D report opened in your browser."
    tagged = [(ln, "ok" if " OK " in ln or ln.startswith("RESULT: OK") else ("alarm" if "FAIL" in ln else None))
              for ln in lines if ln.startswith(("CHECK", "PAIR", "RESULT"))]
    return {"verdict": verdict, "text": text, "report": report, "lines": tagged}


def generate_args(obj, values, extruder, name_text, model, out_dir, slicer_found, model2=None):
    """Command-line arguments for an object's generator script.
    values: flag -> text typed by the user. extruder: "left", "right" or "both" (two parts, two
    colours: model = part 1 on the left nozzle, model2 = part 2 on the right nozzle).
    -> (args, name, error_title, error_message)."""
    name = obj["name"] if obj.get("fixed_name") else safe_name(name_text)
    if not name:
        return None, None, "File name", "Enter a file name (letters, numbers, _ or -)."
    args = ["--out", out_dir]
    if not obj.get("fixed_name"):
        args += ["--name", name]
    if obj.get("model"):
        m = (model or "").strip().strip('"')
        if not os.path.isfile(m):
            return None, None, "3D model", "Choose a 3D model file (STL, 3MF or OBJ) first."
        if not slicer_found:
            return None, None, "Slicer engine missing", (
                "The PrusaSlicer engine was not found.\n\nPut the PrusaSlicer folder in an 'engine' "
                "folder next to the app, or install PrusaSlicer.")
        args += ["--model", m]
        if extruder == "both":
            m2 = (model2 or "").strip().strip('"')
            if not os.path.isfile(m2):
                return None, None, "Part 2", ("Choose the file of part 2 (printed by the RIGHT nozzle), "
                                              "for example the lid of a case.")
            if os.path.normcase(os.path.abspath(m2)) == os.path.normcase(os.path.abspath(m)):
                return None, None, "Part 2", "Part 1 and part 2 are the same file - choose two different parts."
            cz = parse_number(values.get("color-z", 0))
            if cz:
                return None, None, "Colour Z", ("Two parts already gives two colours. Set 'Colour Z' to 0 "
                                                "for a two-part print.")
            args += ["--model2", m2]
    for flag, label, default, lo, hi, step in obj["params"]:
        v = parse_number(values.get(flag, default))
        if v is None:
            return None, None, "Settings", "'%s' is not a number." % label
        v = max(lo, min(hi, v))
        args += ["--" + flag, ("%d" % v) if v == int(v) and flag != "z-offset" else ("%g" % v)]
    args += obj["fixed"]
    if obj["extruder"]:
        args += ["--only", extruder if extruder in ("left", "right") else "left"]
    return args, name, None, None


def file_info_lines(path, st, check_text):
    temps = ", ".join("%s %d°C" % ("Right" if t == 0 else "Left", c) for t, c in sorted(st["temps"].items()) if c)
    lines = [
        "%s    %d commands" % (os.path.basename(path), st["n"]),
        "Print time ≈ %s (+ heat-up)    filament R %.0f mm / L %.0f mm    object height %.1f mm" % (
            fmt_min(st["time_s"]), st["fil"][0], st["fil"][1], st["zprint"]),
        "Nozzles: %s    Bed: %s" % (temps or "off", ("%d°C" % st["bed"]) if st["bed"] else "not heated"),
        "Z homing: %s" % {"slow": "slow 5 mm/s (safe)", "fast": "FAST - caused cut-outs on this printer ⚠",
                          None: "none (bed height used as is)"}[st["z_home"]],
    ]
    if st["t1_change"]:
        lines.append("⚠ uses firmware T1 tool change - bogus offset on this printer!")
    lines += ["", check_text or "Safety check: running …"]
    return lines


def check_summary(stdout):
    """check_x3g.py output -> (ok, short text)."""
    lines = [ln for ln in (stdout or "").splitlines() if not ln.startswith(("commands", "command types"))]
    return "RESULT        : OK" in (stdout or ""), "\n".join(lines[:14])


_WIN_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM\d|LPT\d)$", re.I)


def is_reserved_name(name):
    """Windows cannot create files called CON, NUL, COM1 ..."""
    return bool(_WIN_RESERVED.match(name or ""))
