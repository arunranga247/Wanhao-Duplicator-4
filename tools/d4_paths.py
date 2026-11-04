"""
Where Duplicator 4 Studio keeps its files, and how it runs its helper tools.
Works both from source (python tools/d4_gui.py) and as a single .exe (PyInstaller).

From source : data lives in the project folder (output/, tools/d4_settings.json, engine/)
As .exe     : data lives in  Documents\\Duplicator4Studio\\  (output, settings, log)
              PrusaSlicer is looked up next to the .exe, in that data folder, in the
              project folder the .exe was built from, and in Program Files.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import contextlib
import io
import os
import runpy
import subprocess
import sys
import threading

FROZEN = getattr(sys, "frozen", False)
BUNDLE = getattr(sys, "_MEIPASS", None)
TOOLS = os.path.join(BUNDLE, "tools") if FROZEN else os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# absolute project path recorded when the .exe was built (see build_exe.py)
BUILT_FROM = os.environ.get("D4_PROJECT") or (
    open(os.path.join(BUNDLE, "built_from.txt"), encoding="utf-8").read().strip()
    if FROZEN and os.path.exists(os.path.join(BUNDLE, "built_from.txt")) else PROJECT)

if FROZEN:
    EXE_DIR = os.path.dirname(sys.executable)
    # share files/settings with the source version when the project folder is still there
    if os.path.isdir(os.path.join(BUILT_FROM, "tools")) and os.access(BUILT_FROM, os.W_OK):
        DATA = BUILT_FROM
    else:
        DATA = os.path.join(os.path.expanduser("~"), "Documents", "Duplicator4Studio")
else:
    DATA = PROJECT
    EXE_DIR = PROJECT
OUT = os.path.join(DATA, "output")
PREV = os.path.join(OUT, ".previews")
LOGFILE = os.path.join(OUT, "session_log.txt")
SETTINGS = (os.path.join(DATA, "tools", "d4_settings.json")
            if os.path.isdir(os.path.join(DATA, "tools")) else os.path.join(DATA, "d4_settings.json"))
MODELS = os.path.join(DATA, "models")
for _d in (OUT, PREV, MODELS):
    os.makedirs(_d, exist_ok=True)

PROFILE_CANDIDATES = [os.path.join(BUNDLE, "engine", "duplicator4_pla.ini")] if FROZEN else []
PROFILE_CANDIDATES += [os.path.join(PROJECT, "engine", "duplicator4_pla.ini"),
                       os.path.join(BUILT_FROM, "engine", "duplicator4_pla.ini")]


def profile_path():
    for p in PROFILE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Duplicator 4 slicer profile (duplicator4_pla.ini) not found")


def find_prusaslicer(extra=None):
    """Return the path of prusa-slicer-console.exe, or None."""
    cands = []
    if extra:
        cands.append(extra)
    if os.environ.get("D4_PRUSASLICER"):
        cands.append(os.environ["D4_PRUSASLICER"])
    for root in (EXE_DIR, DATA, PROJECT, BUILT_FROM):
        eng = os.path.join(root, "engine")
        if os.path.isdir(eng):
            for d in sorted(os.listdir(eng), reverse=True):
                cands.append(os.path.join(eng, d, "prusa-slicer-console.exe"))
    for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"),
               os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        cands.append(os.path.join(pf, "Prusa3D", "PrusaSlicer", "prusa-slicer-console.exe"))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


# ---- run a helper script (make_vase.py, slice_model.py, check_x3g.py ...) -------------
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PY = sys.executable
if not FROZEN and PY.lower().endswith("pythonw.exe") and os.path.exists(PY[:-len("pythonw.exe")] + "python.exe"):
    PY = PY[:-len("pythonw.exe")] + "python.exe"
_run_lock = threading.Lock()


def run_tool(script, args, timeout=900):
    """Run tools/<script> with args. Returns (returncode, stdout, stderr).
    From source: separate python process. Inside the .exe: same process (runpy)."""
    path = os.path.join(TOOLS, script)
    if not FROZEN:
        r = subprocess.run([PY, path] + list(args), cwd=TOOLS, capture_output=True, text=True,
                           timeout=timeout, creationflags=NOWIN)
        return r.returncode, r.stdout, r.stderr
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with _run_lock:
        old_argv, old_path = sys.argv, list(sys.path)
        sys.argv = [path] + list(args)
        if TOOLS not in sys.path:
            sys.path.insert(0, TOOLS)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                runpy.run_path(path, run_name="__main__")
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            if not isinstance(e.code, int) and e.code:
                err.write(str(e.code))
        except Exception as e:                      # noqa: BLE001 - report to the GUI
            code = 1
            err.write("%s: %s" % (type(e).__name__, e))
        finally:
            sys.argv, sys.path[:] = old_argv, old_path
    return code, out.getvalue(), err.getvalue()
