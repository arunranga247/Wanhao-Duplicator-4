# Duplicator 4 Studio

Printer software for the **Wanhao Duplicator 4** (dual extruder, Sailfish 7.7 firmware, USB).
It slices any 3D model, makes demo prints, controls the printer and prints over USB, with all the
fixes this particular printer needs built in.

| Tab | What it does |
|---|---|
| 🖨 **Printer** | Live temperatures and chart, limit switches, move and home, extruders, filament load/unload, motor test |
| 🧩 **Prepare** | Turn a 3D model (STL/3MF/OBJ) into a print file, or make a built-in demo (twisted vase, square, two-colour cubes, air demo) |
| 📂 **Print** | File library with preview, print time, filament and safety check; pre-print checklist; live progress |

---

## 1. Quick start (already set up)

1. Switch the printer on and connect the USB cable.
2. Double-click **Duplicator 4 Studio** on the desktop (or `Duplicator4Studio.exe` in this folder).
   The app finds the printer by itself (COM port with USB ID `23C1`).
3. **Prepare** → **📦 Your 3D model** → **📂 Browse…** → choose settings → **⚙ Generate**.
4. **📂 Open in Print tab** → **▶ Print selected file** → tick the checklist → the print starts.

Good first test: `models\test_nut.stl` (20 mm hex nut, about 14 min).

---

## 2. Setup on a new PC

### 2.0 Get the project

```powershell
git clone https://github.com/M2C-ARUN/Wanhao-Duplicator-4.git
cd Wanhao-Duplicator-4
```

The PrusaSlicer engine is not stored in the repository (it is third-party and too large for GitHub);
download it as described in 2.2.

### 2.1 Python and packages (only needed to run from source or build the .exe)

- Windows 10/11, **Python 3.12 or newer** (developed with 3.14.6) from python.org.
  Tick *"Add python.exe to PATH"* during installation.
- In a terminal, inside this folder:

```powershell
python -m pip install --user -r requirements.txt
```

### 2.2 Slicing engine (PrusaSlicer)

The app uses the free, open-source **PrusaSlicer** engine to slice 3D models. It is **not** inside the
.exe (it is about 100 MB) and must be in the `engine` folder.

1. Download **PrusaSlicer 2.9.6** for Windows (the portable `.zip`) from
   <https://github.com/prusa3d/PrusaSlicer/releases/tag/version_2.9.6> → `PrusaSlicer-2.9.6.zip`
2. Optional, but recommended: check the download is genuine:

   ```powershell
   (Get-FileHash .\PrusaSlicer-2.9.6.zip -Algorithm SHA256).Hash
   # must be 5AAF22E42F95ACCECFA122D23A835911F289ECC2FF606DB3E83D637DDCC0A209
   ```

3. Extract it so this file exists:
   `engine\PrusaSlicer-2.9.6\prusa-slicer-console.exe`

The app also finds PrusaSlicer in an `engine` folder next to the .exe, or in a normal installation in
`C:\Program Files\Prusa3D\PrusaSlicer\`. You never need to open PrusaSlicer yourself.
The Duplicator 4 settings it uses are in `engine\duplicator4_pla.ini`.

### 2.3 Printer USB driver

Windows 10/11 installs the driver automatically. The printer appears as
**"USB Serial Device (COMxx)"** with hardware ID `USB\VID_23C1&PID_D314`.
Check this in Device Manager → *Ports (COM & LPT)* if the app shows **Disconnected**.

### 2.4 Check that everything works

```powershell
.\Duplicator4Studio.exe --selftest
type output\selftest.txt          # last line must be: OVERALL: PASS
```

From source: `python tools\d4_gui.py --selftest`.

---

## 3. Running

| How | Command |
|---|---|
| The .exe (normal use) | `Duplicator4Studio.exe` or the desktop shortcut |
| From source | `D4_Control.bat` or `pythonw tools\d4_gui.py` |
| Build the .exe again (after changing code) | `python tools\build_exe.py` → writes `Duplicator4Studio.exe` |

The .exe and the source version share the same files and settings when the project folder exists.
On another PC (no project folder) the .exe uses `Documents\Duplicator4Studio\`.

To make a desktop shortcut: right-click `Duplicator4Studio.exe` → *Send to* → *Desktop (create shortcut)*.

The first time you start a new .exe, Windows may show *"Windows protected your PC"* (the .exe is not
code-signed). Click **More info → Run anyway**.

---

## 4. Using the app

### Printer tab
- **Temperatures:** Set/Off per heater, "PLA: both 210 °C", "All heaters off". The bars fill up toward the target.
- **Limit switches:** green **● PRESSED** / grey **○ open** for X (right end), Y (back), Z (bed top).
- **Move:** the arrows move the head (◄ ► ▲ ▼); **⌂ Home XY** sits in the middle; the **Bed (Z)** column moves the bed (▲ Up = toward the nozzles).
- **Extruders:** Retract / Extrude / ⬇ Load / ⬆ Unload per extruder; **■ Stop filament** stops a load or unload.
- **⛔ EMERGENCY STOP** (or **Esc**) stops all motion and switches every heater off.

### Prepare tab: settings for your own 3D models

| Setting | Meaning | Typical |
|---|---|---|
| Layer (mm) | 0.1 fine · 0.2 normal · 0.3 draft | 0.2 |
| Infill (%) | inside fill | 15–25 |
| Walls | number of outlines | 3 |
| Supports 0/1 | 1 = automatic supports under overhangs | 0 |
| Brim (mm) | extra rim on the first layer for grip | 5 |
| Scale (%) | resize the model | 100 |
| Nozzle °C / 1st layer °C | PLA temperatures | 210 / 220 |
| Squish (mm) | first layer closer (negative) or further (positive) | −0.05 |
| Extruder | Left or Right | Left |

Models that are too big, or would need a heated bed, are refused with a clear message.

### Print tab
Select a file → **▶ Print selected file** → tick the checklist (clean bed with tape or glue, old prints
removed, filament loaded, you are at the printer). The live view shows the % done, time left, height,
filament used and temperatures. **Keep the app open and the PC awake until the print finishes.**

The app remembers its settings (tab, temperatures, object settings, window size) in
`tools\d4_settings.json`. Delete that file to go back to the defaults.

---

## 5. ⚠ Important facts about this printer

These were found by testing on this printer, and the software handles all of them automatically.

| Fact | What the software does |
|---|---|
| **Bed temperature sensor is faulty** (reads 0–12 °C at room temperature) | The bed is **never heated**. Files that heat the bed are blocked. Print PLA on **blue painter's tape or glue stick**. Do not print SD-card or LCD files that heat the bed: they wait forever and overheat it. |
| Fast Z homing made the board **reset** | Z is homed **slowly (5 mm/s)** with the heaters off; the nozzle heats only after homing has worked |
| Stored left-nozzle (T1) offset is wrong (~228 mm) | The printer is **never** switched to tool 1; the 33 mm nozzle spacing is handled in software |
| Extruder motors run "backwards" (negative steps push filament in) | Handled in every file and button |
| No part-cooling fan | The slicer slows down small layers so they can cool |
| Limit switches had loose plugs | Reseated; the app warns if a switch signal starts flickering |

If the **bed sensor** is repaired (100 kΩ thermistor), tick **"Bed sensor repaired"** in the Printer tab
to allow bed heating. It is switched off again every time the app starts, on purpose.

---

## 6. Folder layout

```
WAHNO_DUPLICATOR_4/
├─ Duplicator4Studio.exe     the app (single file, about 20 MB)
├─ D4_Control.bat            start from source
├─ requirements.txt          Python packages
├─ engine/
│  ├─ PrusaSlicer-2.9.6/     slicing engine (download, see 2.2)
│  └─ duplicator4_pla.ini    Duplicator 4 PLA profile
├─ models/                   3D models (test_nut.stl, test_step_tower.stl)
├─ output/                   print files (.x3g), previews, session_log.txt, crash_log.txt
└─ tools/                    source code
   ├─ d4_gui.py              the app (window, tabs)
   ├─ d4_worker.py           printer connection thread (USB)
   ├─ d4_paths.py            folders, engine lookup, running helper tools
   ├─ s3g_link.py            s3g/x3g protocol, printer constants
   ├─ slice_model.py         3D model → PrusaSlicer → x3g
   ├─ gcode2x3g.py           G-code → x3g with this printer's fixes
   ├─ make_dual_sample.py    x3g writer (+ R/L cubes, squares)
   ├─ make_vase.py           twisted flower vase
   ├─ make_left_demo.py      left-extruder air demo
   ├─ check_x3g.py           safety checker (run on every file)
   ├─ render_preview.py      preview images
   ├─ stream_x3g.py          print over USB from the command line
   ├─ check_nozzle.py        heater + extruder test for one nozzle
   ├─ make_test_stl.py       creates the test models
   └─ build_exe.py           builds Duplicator4Studio.exe
```

`engine\download\` only holds the downloaded zip and can be deleted after extracting.

---

## 7. Command-line tools (optional)

```powershell
cd tools
python slice_model.py --model ..\models\test_nut.stl --name NUT --only left --layer-height 0.2
python check_x3g.py ..\output\NUT.x3g                 # safety check
python render_preview.py ..\output\NUT.x3g            # preview image
python stream_x3g.py ..\output\NUT.x3g --port COM30   # print over USB (app must be closed)
python check_nozzle.py --tool right                   # heater + extruder test
```

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| App shows **Disconnected** | Printer on? USB plugged in? Check Device Manager for "USB Serial Device (COMxx)". The app reconnects by itself every 3 s. |
| "PrusaSlicer engine not found" | Extract PrusaSlicer into `engine\` (section 2.2) |
| "All objects are outside of the print volume" | The model is bigger than 225 × 145 × 140 mm. Lower **Scale (%)**. |
| First layer does not stick | Clean the bed, use tape or glue stick, level the bed (paper test), set **Squish** to −0.10, and use a bigger **Brim** |
| First layer scrapes, or little plastic comes out | Nozzle too close: set **Squish** to 0 or +0.05 |
| No plastic comes out | Load the filament (⬇ Load, push it in while the gear turns) and check the extruder lever is closed |
| Printer disconnects during homing | Check the cables under the bed and the Z switch for pinched or loose wires |
| Window blank / app won't start | Look in `output\crash_log.txt`; restart the app |
| Window too big or too small | Drag the edges; the app scrolls when the window is small. Delete `tools\d4_settings.json` to reset. |
