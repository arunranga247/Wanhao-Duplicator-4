<div align="center">

# 🖨️ Duplicator 4 Studio: Wanhao Duplicator 4 Software

**Wanhao Duplicator 4 software for Windows: a Duplicator 4 slicer, printer control and USB printing in one modern app.**

Open any 3D model (STL, 3MF, OBJ), slice it with the PrusaSlicer engine and print it over USB as
**Sailfish x3g**, with every quirk of this dual-extruder printer handled automatically.
Built and tested on the **Wanhao Duplicator 4**. The **Duplicator 4S** and other
**MakerBot Replicator 1 Dual** clones use the same Sailfish x3g system.

![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![Printer](https://img.shields.io/badge/Printer-Wanhao%20Duplicator%204-34A853)
![Firmware](https://img.shields.io/badge/Firmware-Sailfish%207.7-FBBC04)
![Slicer](https://img.shields.io/badge/Slicer-PrusaSlicer%202.9.6-EA4335)
![Version](https://img.shields.io/badge/version-1.0.0-1A73E8)

**[⬇ Download the latest release](https://github.com/arunranga247/Wanhao-Duplicator-4/releases/latest)**

<img src="docs/images/prepare.png" alt="Wanhao Duplicator 4 software - Duplicator 4 slicer with a sliced 3D model" width="900">

</div>

---

## Contents

- [Features](#-features)
- [Screenshots](#-screenshots)
- [How it works](#-how-it-works)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Your first print](#-your-first-print)
- [User guide](#-user-guide)
- [Printer-specific engineering](#-printer-specific-engineering)
- [Safety](#-safety)
- [Project structure](#-project-structure)
- [Building the executable](#-building-the-executable)
- [Command-line tools](#-command-line-tools)
- [Troubleshooting](#-troubleshooting)
- [Roadmap](#-roadmap)
- [Support me](#-support-me)
- [About](#-about)

---

## ✨ Features

| Feature | What it does |
|---|---|
| 📦 **Print any 3D model** | STL, 3MF, OBJ and AMF are sliced by the PrusaSlicer engine with a tuned Duplicator 4 PLA profile: walls, solid top and bottom, infill, brim and optional supports |
| 🧩 **Built-in demo prints** | Twisted flower vase (spiral "vase mode"), square blocks, two-colour R+L cubes, left-extruder air demo |
| 👁️ **Toolpath preview** | Top view of the whole bed plus a 3D view, colour-coded per extruder |
| ✅ **Safety check on every file** | Bed limits, nozzle height, extruder speed, heated-bed and tool-change rules, checked before anything is printed |
| 🖨️ **Live printer control** | Temperatures with history chart, limit switches, move and home pad, filament load/unload, motor test |
| 📡 **USB printing** | Progress, time left, current height, filament used and nozzle temperatures, with pause and cancel |
| ⛔ **Emergency stop** | One click (or **Esc**) stops all motion and switches every heater off |
| 🎨 **Modern interface** | Windows 11 style, Google Material colours, light or dark theme, resizable with automatic scrolling |
| 💾 **Remembers your settings** | Tab, temperatures, per-object settings, window size and last file |
| 📦 **Single .exe** | Double-click to run; a built-in self-test confirms the installation |

---

## 📸 Screenshots

| Printer | Prepare | Print |
|---|---|---|
| <img src="docs/images/printer.png" alt="Printer tab" width="300"> | <img src="docs/images/prepare.png" alt="Prepare tab" width="300"> | <img src="docs/images/print.png" alt="Print tab" width="300"> |
| Temperatures, limit switches, move pad, extruders | Choose a model or demo, set it up, slice and preview | File library, checklist, live print progress |

---

## 🔄 How it works

```mermaid
flowchart LR
    A["3D model<br/>STL · 3MF · OBJ"] --> B["PrusaSlicer engine<br/>+ Duplicator 4 profile"]
    B -->|G-code| C["gcode2x3g<br/>printer-specific fixes"]
    C -->|.x3g| D["Safety checker"]
    D --> E["Preview"]
    D --> F["USB print<br/>Sailfish 7.7"]
```

1. **Slice:** PrusaSlicer turns the model into layers and toolpaths (walls, infill, supports, brim, speeds, cooling).
2. **Convert:** `gcode2x3g` writes the printer's binary **x3g** format and adds this printer's fixes (see [Printer-specific engineering](#-printer-specific-engineering)).
3. **Check:** every move is verified against the bed limits and the printer's rules. Unsafe files cannot be printed.
4. **Print:** the file is streamed over USB with live progress and an emergency stop.

---

## 📋 Requirements

| Item | Requirement |
|---|---|
| Printer | Wanhao Duplicator 4 (Replicator 1 Dual class), Sailfish 7.x firmware, USB connection |
| Computer | Windows 10 or 11 |
| Material | PLA, 1.75 mm |
| To run the .exe | Nothing else, apart from the PrusaSlicer engine in `engine/` |
| To run from source or build the .exe | Python 3.12+ and the packages in [`requirements.txt`](requirements.txt) |

---

## 🚀 Installation

### 1. Get the project

**Easiest:** download **Duplicator4Studio-v1.0.0-windows.zip** from the
[latest release](https://github.com/arunranga247/Wanhao-Duplicator-4/releases/latest) and extract it.
It contains the app, the profile, test models and an `engine` folder ready for PrusaSlicer.

**Or** clone the source:

```powershell
git clone https://github.com/arunranga247/Wanhao-Duplicator-4.git
cd Wanhao-Duplicator-4
```

### 2. Add the slicing engine

PrusaSlicer is third-party and too large for GitHub, so download it once:

1. Download **`PrusaSlicer-2.9.6.zip`** (Windows portable) from the
   [PrusaSlicer 2.9.6 release](https://github.com/prusa3d/PrusaSlicer/releases/tag/version_2.9.6).
2. Optional, but recommended: check the download is genuine:
   ```powershell
   (Get-FileHash .\PrusaSlicer-2.9.6.zip -Algorithm SHA256).Hash
   # 5AAF22E42F95ACCECFA122D23A835911F289ECC2FF606DB3E83D637DDCC0A209
   ```
3. Extract it so this file exists: `engine\PrusaSlicer-2.9.6\prusa-slicer-console.exe`

> The app also finds PrusaSlicer in an `engine` folder next to the .exe, or in a normal installation
> under `C:\Program Files\Prusa3D\PrusaSlicer\`.

### 3. Python packages (only to run from source or build the .exe)

```powershell
python -m pip install --user -r requirements.txt
```

### 4. Connect the printer

Windows installs the USB driver automatically. The printer appears in Device Manager as
**USB Serial Device (COMxx)**, hardware ID `USB\VID_23C1&PID_D314`.

### 5. Verify

```powershell
.\Duplicator4Studio.exe --selftest
```

The result is written to `output\selftest.txt` in the app's data folder. The last line must be
**OVERALL: PASS**.

| You run | Data folder (print files, settings, logs) |
|---|---|
| The release download (.exe) | `Documents\Duplicator4Studio\` |
| A clone of this repository | The repository folder itself |

### Start the app

| Way | How to start it |
|---|---|
| Executable | Double-click **`Duplicator4Studio.exe`** (or a desktop shortcut to it) |
| From source | `D4_Control.bat` or `pythonw tools\d4_gui.py` |

> The first time you start a new .exe, Windows may show *"Windows protected your PC"* because the
> file is not code-signed. Click **More info → Run anyway**.

---

## 🎯 Your first print

1. Prepare the bed: clean it, then apply **blue painter's tape or glue stick** (the bed is not heated, see [below](#-printer-specific-engineering)).
2. Load PLA into the left extruder: **Printer → ⬇ Load** (Left).
3. **Prepare → 📦 Your 3D model → 📂 Browse…** → `models\test_nut.stl` → **⚙ Generate**.
4. **📂 Open in Print tab → ▶ Print selected file** → tick the checklist.
5. Watch the first layer. The print takes about 14 minutes plus heat-up.

---

## 📖 User guide

### Printer tab
- **Temperatures:** Set/Off per heater, the *PLA: both 210 °C* preset and *All heaters off*. Bars fill toward the target, and a 5-minute chart is shown below.
- **Limit switches:** X / Y / Z badges with **● PRESSED** / **○ open**, plus the current position.
- **Move:** arrows move the head (◄ ► ▲ ▼), **⌂ Home XY** is in the centre, the **Bed (Z)** column moves the bed (▲ Up = toward the nozzles), and the step is 0.1 / 1 / 10 / 50 mm.
- **Extruders:** Retract, Extrude, ⬇ Load and ⬆ Unload per extruder; **■ Stop filament** stops a load or unload.

### Prepare tab: 3D model settings

| Setting | Meaning | Default |
|---|---|---|
| Layer (mm) | 0.1 fine · 0.2 normal · 0.3 draft | 0.2 |
| Infill (%) | inside fill density | 20 |
| Walls | number of outlines | 3 |
| Supports 0/1 | automatic supports under overhangs | 0 |
| Brim (mm) | first-layer rim for grip | 5 |
| Scale (%) | resize the model | 100 |
| Nozzle °C / 1st layer °C | PLA temperatures | 210 / 220 |
| Squish (mm) | first layer closer (negative) or further (positive) | −0.05 |
| Extruder | Left or Right | Left |

### Print tab
The file library shows each file's print time, filament, Z-homing type and safety status. **▶ Print selected
file** opens a checklist, then shows live progress. Keep the app open and the PC awake while printing.

> **Tip:** press **Ctrl + Shift + A** for *About*. Settings are stored in `tools\d4_settings.json`;
> delete that file to reset them.

---

## 🔧 Printer-specific engineering

This Duplicator 4 was analysed over USB. Its faults and firmware quirks are handled in software:

| Finding | Solution in Duplicator 4 Studio |
|---|---|
| Heated-bed thermistor faulty (reads 0–12 °C at room temperature) | The bed is never heated; such files are blocked; a brim plus slow, hot first layer for adhesion |
| Fast Z homing caused controller resets | Slow Z homing (5 mm/s, 40 s limit) with heaters off; heat-up only after homing succeeds |
| Stored T1 (left nozzle) offset is wrong (~228 mm) | The firmware is never switched to T1; the 33 mm nozzle spacing is applied in software |
| Extruder direction inverted (negative steps feed filament) | One global direction constant used by every tool |
| No part-cooling fan | The slicer slows down small layers so they can cool |
| Very short slicer moves could over-speed the extruder | Extruder speed limited to 25 mm/s on every move |
| Empty nozzle for the first seconds of a print | 5 s settle, retract recovery, purge blob and double prime line |

---

## 🔒 Safety

- **⛔ Emergency stop** (button or **Esc**): halts motion, clears the printer's buffer and switches all heaters off.
- **Heater watchdog:** switches all heaters off if a sensor reads implausibly low or a heater does not warm up within 90 s.
- **Bed heating blocked** until *Bed sensor repaired* is ticked. This switch resets at every start, on purpose.
- **Safety checker:** files that leave the bed, dig into it, over-speed an axis, heat the bed or use the faulty T1 offset are refused.
- **Pre-print checklist** before every job.
- **Crash log:** unexpected errors are written to `output\crash_log.txt` and shown on screen.

---

## 📁 Project structure

```
Wanhao-Duplicator-4/
├─ Duplicator4Studio.exe      the app (single file)
├─ D4_Control.bat             start from source
├─ requirements.txt
├─ engine/
│  ├─ duplicator4_pla.ini     Duplicator 4 PLA slicing profile
│  └─ PrusaSlicer-2.9.6/      slicing engine (download, not in git)
├─ models/                    test models (test_nut.stl, test_step_tower.stl)
├─ output/                    print files (.x3g / .gcode), logs, previews
├─ docs/images/               screenshots
└─ tools/
   ├─ d4_gui.py               application window and tabs
   ├─ d4_worker.py            USB connection thread
   ├─ d4_paths.py             folders, engine lookup, tool runner
   ├─ s3g_link.py             s3g/x3g protocol and printer constants
   ├─ slice_model.py          3D model → PrusaSlicer → x3g
   ├─ gcode2x3g.py            G-code → x3g with printer fixes
   ├─ make_dual_sample.py     x3g writer, squares and R+L cubes
   ├─ make_vase.py            twisted flower vase
   ├─ make_left_demo.py       left-extruder air demo
   ├─ check_x3g.py            safety checker
   ├─ render_preview.py       toolpath previews
   ├─ stream_x3g.py           command-line USB printing
   ├─ check_nozzle.py         heater and extruder test
   ├─ make_test_stl.py        test model generator
   └─ build_exe.py            builds Duplicator4Studio.exe
```

---

## 🔨 Building the executable

```powershell
python tools\build_exe.py          # writes Duplicator4Studio.exe (about 20 MB)
.\Duplicator4Studio.exe --selftest # must end with OVERALL: PASS
```

The build packs the app, all tools, the theme and the Duplicator 4 profile into one file, and sets the
Windows file properties (product, version, copyright). The PrusaSlicer engine stays in `engine/`.

---

## 💻 Command-line tools

```powershell
cd tools
python slice_model.py --model ..\models\test_nut.stl --name NUT --only left
python check_x3g.py ..\output\NUT.x3g
python render_preview.py ..\output\NUT.x3g
python stream_x3g.py ..\output\NUT.x3g --port COM30     # close the app first
python check_nozzle.py --tool right
python make_vase.py --height 35 --twist 120 --lobes 8
```

---

## 🩺 Troubleshooting

| Problem | Solution |
|---|---|
| App shows **Disconnected** | Check power and USB. The app reconnects by itself every 3 s; check Device Manager for *USB Serial Device*. |
| *PrusaSlicer engine not found* | Extract PrusaSlicer into `engine\` ([Installation step 2](#2-add-the-slicing-engine)) |
| *Objects are outside of the print volume* | The model is larger than 225 × 145 × 140 mm. Reduce **Scale (%)**. |
| First layer does not stick | Clean the bed, use tape or glue, level the bed, set **Squish** to −0.10 and use a larger **Brim** |
| Nozzle scrapes, or little plastic comes out | Set **Squish** to 0 or +0.05 and level the bed |
| No plastic at all | Load the filament (⬇ Load) and check the extruder lever is closed |
| Printer disconnects during homing | Check the bed cables and the Z switch for pinched or loose wires |
| Window blank or app will not start | See `output\crash_log.txt`, then restart the app |

---

## 🧭 Roadmap

- [ ] Assisted bed-levelling wizard (four corners plus centre)
- [ ] Re-enable bed heating after the thermistor is replaced
- [ ] Two-colour printing from multi-part 3MF models
- [ ] Print from SD card (send x3g to the printer's card over USB)

---

## 💖 Support me

If Duplicator 4 Studio brought your printer back to life or saved you time, here is how you can help:

<p>
<a href="https://github.com/arunranga247/Wanhao-Duplicator-4"><img src="https://img.shields.io/github/stars/arunranga247/Wanhao-Duplicator-4?style=social" alt="GitHub stars"></a>
<a href="https://github.com/arunranga247"><img src="https://img.shields.io/github/followers/arunranga247?style=social" alt="Follow arunranga247"></a>
</p>

| Way to help | How |
|---|---|
| ⭐ **Star the repository** | Click **Star** at the top of the [repository page](https://github.com/arunranga247/Wanhao-Duplicator-4). It helps other Duplicator 4 owners find the project. |
| 🐛 **Report a bug or suggest an idea** | Open an [issue](https://github.com/arunranga247/Wanhao-Duplicator-4/issues/new) with your printer, firmware version and what happened |
| 🔧 **Contribute** | Fork the repository, make your improvement and open a pull request |
| 📢 **Share it** | Tell other Wanhao Duplicator 4 and MakerBot Replicator owners about it, in forums, groups and makerspaces |
| 🖨️ **Show your prints** | Post a photo of something you printed with Duplicator 4 Studio in an issue or discussion |

Every star, report and share keeps this project growing. **Thank you!**

---

## 👤 About

<table>
<tr>
<td width="120" align="center">
<img src="https://github.com/arunranga247.png" width="96" alt="ARUN"><br>
</td>
<td>

**Duplicator 4 Studio** was designed and developed by **ARUN**.

It brings a reliable, modern workflow to the Wanhao Duplicator 4, from 3D model to finished part, by
combining a proven slicing engine with software written specifically for this printer and its hardware.

- GitHub: [arunranga247](https://github.com/arunranga247)
- Repository: [Wanhao-Duplicator-4](https://github.com/arunranga247/Wanhao-Duplicator-4)

</td>
</tr>
</table>

### Acknowledgements

Duplicator 4 Studio uses these open-source projects:

- [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer): slicing engine (AGPL-3.0), used as a separate program
- [Sun Valley ttk theme](https://github.com/rdbende/Sun-Valley-ttk-theme): Windows 11 style widgets
- [pySerial](https://github.com/pyserial/pyserial): USB serial communication
- [Pillow](https://github.com/python-pillow/Pillow): images and previews
- [PyInstaller](https://github.com/pyinstaller/pyinstaller): single-file executable

### Copyright

Copyright © 2026 **ARUN**. All rights reserved.
Third-party components remain under their own licences.

<div align="center">
<sub>Made for the Wanhao Duplicator 4 · Sailfish firmware · Windows</sub>
</div>
