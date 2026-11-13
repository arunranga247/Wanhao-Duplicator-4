"""
Build Duplicator4Studio.exe (single file) with PyInstaller.

    python tools/build_exe.py

Result: <project>/Duplicator4Studio.exe
The PrusaSlicer engine is NOT packed inside the .exe (100+ MB); the .exe finds it in
<project>/engine/ (or an 'engine' folder next to the .exe, or Program Files).
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFont

TOOLS = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.normpath(os.path.join(TOOLS, ".."))
BUILD = os.path.join(PROJECT, "build")
# --dist DIR : write the .exe somewhere else (e.g. while the old .exe is still open and locked)
DIST = os.path.abspath(sys.argv[sys.argv.index("--dist") + 1]) if "--dist" in sys.argv else PROJECT
os.makedirs(BUILD, exist_ok=True)

# ---- icon: Google-blue circle with "D4" -------------------------------------------
ico = os.path.join(BUILD, "d4studio.ico")
big = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(big)
d.ellipse((8, 8, 248, 248), fill=(26, 115, 232, 255))
d.ellipse((20, 168, 236, 236), fill=(52, 168, 83, 255))          # green "bed" band
d.ellipse((8, 8, 248, 248), outline=(255, 255, 255, 255), width=6)
try:
    f = ImageFont.truetype("segoeuib.ttf", 112)
except OSError:
    f = ImageFont.load_default()
tw = d.textlength("D4", font=f)
d.text(((256 - tw) / 2, 36), "D4", fill="white", font=f)
big.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

with open(os.path.join(BUILD, "built_from.txt"), "w", encoding="utf-8") as fh:
    fh.write(PROJECT)

# ---- Windows file properties (right-click .exe -> Properties -> Details) --------------
VERSION = (1, 0, 0, 0)
version_file = os.path.join(BUILD, "version_info.txt")
with open(version_file, "w", encoding="utf-8") as fh:
    fh.write('''VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(v)s, prodvers=%(v)s, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'ARUN'),
      StringStruct('FileDescription', 'Duplicator 4 Studio'),
      StringStruct('FileVersion', '%(s)s'),
      StringStruct('InternalName', 'Duplicator4Studio'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 ARUN - GNU GPL v3.0'),
      StringStruct('OriginalFilename', 'Duplicator4Studio.exe'),
      StringStruct('ProductName', 'Duplicator 4 Studio'),
      StringStruct('ProductVersion', '%(s)s'),
      StringStruct('Comments', 'Developer: ARUN')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
''' % {"v": repr(VERSION), "s": ".".join(str(n) for n in VERSION[:3])})

sep = ";" if os.name == "nt" else ":"
datas = []
for py in glob.glob(os.path.join(TOOLS, "*.py")):
    if "backup" not in os.path.basename(py) and not os.path.basename(py).startswith("d4_gui"):  # old Tk window
        datas += ["--add-data", py + sep + "tools"]
datas += ["--add-data", os.path.join(PROJECT, "engine", "duplicator4_pla.ini") + sep + "engine",
          "--add-data", os.path.join(BUILD, "built_from.txt") + sep + "."]
# fit check: 3-D report template + three.js (MIT, bundled so the report works offline)
datas += ["--add-data", os.path.join(TOOLS, "fit_view_template.html") + sep + "tools"]
# licences: our GPL-3.0 + every third-party licence travel inside the exe (shown via About)
datas += ["--add-data", os.path.join(PROJECT, "LICENSE") + sep + ".",
          "--add-data", os.path.join(PROJECT, "THIRD_PARTY_NOTICES.md") + sep + ".",
          "--add-data", os.path.join(PROJECT, "licenses") + sep + "licenses"]
for f in glob.glob(os.path.join(TOOLS, "vendor", "*")):
    datas += ["--add-data", f + sep + os.path.join("tools", "vendor")]

hidden = ["argparse", "runpy", "contextlib", "tempfile", "json", "math", "struct", "glob",
          "shutil", "winreg", "serial", "serial.tools.list_ports", "PIL.ImageDraw", "PIL.ImageFont",
          # the Qt window (PySide6, LGPL) + its 3D viewer
          "d4_core", "model_preview", "shiboken6", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
          # fit_check.py (runs inside the exe): mesh maths + 3-D booleans
          "numpy", "manifold3d", "base64", "webbrowser", "zipfile", "xml.etree.ElementTree"]
args = ["--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "Duplicator4Studio",
        "--icon", ico,
        "--version-file", version_file,
        "--paths", TOOLS,
        "--distpath", DIST,
        "--workpath", os.path.join(BUILD, "work"),
        "--specpath", BUILD,
        # the Tk window is retired: keep Tcl/Tk out of the exe
        "--exclude-module", "tkinter", "--exclude-module", "_tkinter", "--exclude-module", "sv_ttk"]
for h in hidden:
    args += ["--hidden-import", h]
args += datas + [os.path.join(TOOLS, "d4_qt.py")]

import PyInstaller.__main__  # noqa: E402

print("building ...")
PyInstaller.__main__.run(args)
exe = os.path.join(DIST, "Duplicator4Studio.exe")
print("\nDONE: %s (%.1f MB)" % (exe, os.path.getsize(exe) / 1e6) if os.path.exists(exe) else "BUILD FAILED")
sys.exit(0 if os.path.exists(exe) else 1)
