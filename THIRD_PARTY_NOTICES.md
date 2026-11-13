# Third-party notices

Duplicator 4 Studio is free software by **ARUN**, released under the
**GNU General Public License v3.0** (see [`LICENSE`](LICENSE)).

It uses the open-source components below. Each keeps its own licence; the full texts are in the
[`licenses/`](licenses) folder of this repository, and the same files are packed inside
`Duplicator4Studio.exe`.

## Packed inside Duplicator4Studio.exe

| Component | Version | Licence | Copyright | Source code | Used for |
|---|---|---|---|---|---|
| **Qt for Python (PySide6, Shiboken6)** and the **Qt 6** libraries | 6.12.0 | LGPL-3.0 (used under the LGPL; see below) | The Qt Company Ltd. and other contributors | <https://code.qt.io/> · <https://download.qt.io/official_releases/QtForPython/> | the app window, 3D viewers |
| **Python** | 3.14 | PSF License Agreement | Python Software Foundation | <https://www.python.org/downloads/source/> | runs the app |
| **NumPy** (and the libraries it bundles) | 2.5 | BSD-3-Clause; bundled parts: 0BSD, MIT, Zlib, CC0-1.0, others listed in `licenses/numpy/` | NumPy Developers and others | <https://github.com/numpy/numpy> | 3D model maths, previews, fit check |
| **Manifold** (`manifold3d`) | 3.5 | Apache-2.0 | Manifold authors | <https://github.com/elalish/manifold> | fit check (3D booleans) |
| **Pillow** | 12.3 | MIT-CMU (HPND) | Jeffrey A. Clark and contributors; Secret Labs AB; Fredrik Lundh | <https://github.com/python-pillow/Pillow> | pictures and previews |
| **pySerial** | 3.5 | BSD-3-Clause | Chris Liechti | <https://github.com/pyserial/pyserial> | USB link to the printer |
| **three.js** (+ OrbitControls) | r128 | MIT | three.js authors | <https://github.com/mrdoob/three.js> | 3D fit-check report in the browser |

### Qt / PySide6 and the LGPL-3.0

Qt and Qt for Python are used under the **GNU Lesser General Public License v3.0**
([`licenses/LGPL-3.0.txt`](licenses/LGPL-3.0.txt), which builds on the GPL v3.0 in [`LICENSE`](LICENSE)).
The Qt libraries are unmodified. Because the complete source of Duplicator 4 Studio and the build script
(`tools/build_exe.py`) are public in this repository, you can rebuild the program with your own or a
modified version of Qt / PySide6 at any time.

## Used, but NOT packed inside the program

| Component | Licence | How it is used |
|---|---|---|
| **PrusaSlicer** 2.9.6 | AGPL-3.0 | Slicing engine. Run as a **separate program** that you download yourself from <https://github.com/prusa3d/PrusaSlicer>; it is not part of this repository or of the .exe. |
| **PyInstaller** | GPL-2.0-or-later with the bootloader exception | Builds the .exe. The exception allows programs built with it to use any licence. |

## Names and trademarks

*Wanhao* and *Duplicator* are trademarks of Wanhao; *MakerBot* and *Replicator* are trademarks of
MakerBot Industries; *Sailfish* is the name of the open-source firmware by its authors. These names are
used only to say which printers and firmware this software works with. Duplicator 4 Studio is an
independent project and is **not affiliated with, endorsed by or supported by** any of them.

No code from the Sailfish firmware, GPX, ReplicatorG or MakerBot software is included. The s3g / x3g
communication is an independent implementation written for this project.
