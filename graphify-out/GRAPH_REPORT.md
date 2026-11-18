# Graph Report - WAHNO_DUPLICATOR_4  (2026-11-18)

## Corpus Check
- 60 files · ~117,414 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 12 file(s) not represented in the graph (top: (none) 6, .ini 2, .stl 2)

## Summary
- 2811 nodes · 5476 edges · 168 communities (61 shown, 107 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 455 edges (avg confidence: 0.85)
- Token cost: 370,334 input · 0 output

## Community Hubs (Navigation)
- three.js library
- Fit check: fit_checkpy
- three.js library 2
- Worker tests
- three.js library 3
- three.js library 4
- three.js orbit controls: constructor
- three.js library 5
- README app docs: Duplicator 4 Studio app
- three.js library 6
- three.js library 7
- three.js library 8
- Qt window: MainWindow
- three.js library 9
- Qt window: d4_qtpy
- Old Tk window v1: App
- S3G printer link
- three.js library 10
- Qt window: GLViewer
- three.js library 11
- three.js library 12
- three.js library 13
- Dual sample maker: make_dual_samplepy
- Old Tk window: App
- three.js library 14
- G-code porting: argparse
- Old Tk window: d4_guipy
- Window tests: test_d4_qtpy
- three.js library 15
- three.js library 16
- Qt window: ModelArea
- three.js library 17
- Preview renderer: struct
- X3G streaming: os
- Qt window: label
- three.js library 18
- Dual sample maker: Printer
- Old Tk window: build_print_tab
- Window tests: sent
- three.js library 19
- three.js library 20
- Qt window: start_print
- three.js library 21
- three.js library 22
- Window tests: Prepare
- Qt window: log
- three.js library 23
- three.js library 24
- three.js library 25
- three.js library 26
- three.js library 27
- three.js library 28
- three.js library 29
- three.js library 30
- Old Tk window v1: Worker
- three.js library 31
- three.js library 32
- three.js library 33
- three.js library 34
- three.js library 35
- Prepare Dark: Prepare Tab 3step workfl
- three.js library 36
- three.js library 37
- three.js library 38
- Qt window: refresh_library
- Old Tk window: apply_theme
- Old Tk window: panel
- Window tests: status
- three.js library 39
- three.js library 40
- three.js library 41
- Safety rules core: d4_corepy
- Safety rules core: Texts
- three.js library 42
- Prepare: Prepare Tab choose objec
- Core tests: bed_heat_decision
- X3G streaming: Link
- Core tests
- three.js library 43
- three.js library 44
- Printer: Printer Tab Printer  Pre
- Old Tk window: log
- three.js library 45
- three.js library 46
- three.js library 47
- Paths: Prepare Tab choose objec
- Old Tk window: GButton
- three.js library 48
- three.js library 49
- three.js library 51
- three.js library 52
- three.js library 54
- Core tests: generate_args
- three.js library 55
- three.js library 56
- three.js library 57
- three.js library 58
- three.js library 59
- Qt window: Dot
- Safety rules core: set_heater
- three.js library 60
- three.js library 61
- Print: Print tab screenshot Dup
- Window tests: Ports
- Window tests: Heaters
- three.js library 63
- three.js library 64
- three.js library 65
- Old Tk window: ScrollFrame
- three.js library 66
- three.js library 67
- three.js library 68
- three.js library 69
- Core tests: parse_fit_result
- Window tests: FakePrinter
- three.js library 70
- three.js library 71
- three.js library 72
- three.js library 73
- three.js library 74
- Core tests: test_d4_corepy
- Core tests: progress
- Window tests: Toolpath
- three.js library 75
- three.js library 76
- three.js library 77
- X3G streaming: BedGuard
- Window tests: Layout
- three.js library 79
- three.js library 80
- three.js library 82
- three.js library 83
- three.js library 84
- three.js library 85
- three.js library 86
- Help: Infill  Help Dialog Scre
- Fit report page: render rAFcoalesced
- three.js library 88
- three.js library 89
- three.js library 90
- three.js library 91
- Requirements: numpy126
- Requirements: pillow100
- three.js library 92
- three.js library 93
- three.js library 94
- three.js library 95
- three.js library 96
- three.js library 97
- three.js library 98
- three.js library 99
- three.js library 100
- Requirements: svttk commented out old 
- Third Party Notices: Python 314 PSF License
- Third Party Notices: Trademark  nonaffiliatio

## God Nodes (most connected - your core abstractions)
1. `Lt` - 135 edges
2. `MainWindow` - 103 edges
3. `App` - 93 edges
4. `vt` - 90 edges
5. `tn` - 65 edges
6. `St` - 60 edges
7. `Ce` - 59 edges
8. `sn` - 53 edges
9. `se` - 49 edges
10. `App` - 39 edges

## Surprising Connections (you probably didn't know these)
- `Overhang face detection (normal.z < -0.707, above 0.3 mm)` --semantically_similar_to--> `Safety checker (check_x3g)`  [INFERRED] [semantically similar]
  tools/fit_view_template.html → README.md
- `No-WebGL fallback message (checks still complete)` --semantically_similar_to--> `3D model viewer (OpenGL with CPU fallback)`  [INFERRED] [semantically similar]
  tools/fit_view_template.html → README.md
- `Printer bed plate + 25 mm grid` --conceptually_related_to--> `Wanhao Duplicator 4 printer`  [INFERRED]
  tools/fit_view_template.html → README.md
- `Fit Check HTML report template` --implements--> `Fit check / assembly check`  [INFERRED]
  tools/fit_view_template.html → README.md
- `three.js r128 + OrbitControls (MIT)` --conceptually_related_to--> `Fit Check HTML report template`  [INFERRED]
  THIRD_PARTY_NOTICES.md → tools/fit_view_template.html

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Printer-specific fault workarounds** — readme_bed_heating_limit, readme_slow_z_homing, readme_t1_offset_workaround, readme_extruder_direction_constant, readme_extruder_speed_limit, readme_first_layer_priming, readme_no_cooling_fan_slowdown [EXTRACTED 1.00]
- **Model to print flow** — readme_prusaslicer_engine, readme_gcode2x3g_converter, readme_safety_checker, readme_usb_printing [EXTRACTED 1.00]
- **Fit-check viewer display controls** — tools_fit_view_template_applysection, tools_fit_view_template_applyghost, tools_fit_view_template_applyexplode, tools_fit_view_template_applyvisible, tools_fit_view_template_themecolors, tools_fit_view_template_setview [EXTRACTED 1.00]
- **Prepare workflow: choose object, set parameters, generate X3G, preview paths** — docs_images_paths_twisted_flower_vase, docs_images_paths_parametric_settings_panel, docs_images_paths_x3g_generation, docs_images_paths_print_paths_preview, docs_images_paths_safety_check [EXTRACTED 1.00]
- **Model to X3G preparation flow** — docs_images_prepare_test_nut_stl, docs_images_prepare_slice_settings_panel, docs_images_prepare_3d_model_preview, docs_images_prepare_x3g_output [INFERRED 0.85]
- **Prepare workflow: choose object, set settings, generate x3g** — docs_images_prepare_dark_choose_object, docs_images_prepare_dark_slice_settings, docs_images_prepare_dark_generate_x3g, docs_images_prepare_dark_3d_preview [EXTRACTED 1.00]
- **Select file, check safety, preview, then print** — docs_images_print_print_files_table, docs_images_print_x3g_safety_check, docs_images_print_toolpath_preview, docs_images_print_print_job_panel [INFERRED 0.85]
- **Printer tab manual-control dashboard panels** — docs_images_printer_temperatures_panel, docs_images_printer_limit_switches_panel, docs_images_printer_extruders_panel, docs_images_printer_move_panel, docs_images_printer_temperature_history_chart, docs_images_printer_log_panel [EXTRACTED 1.00]

## Communities (168 total, 107 thin omitted)

### Community 0 - "three.js library"
Cohesion: 0.03
Nodes (35): as(), bind(), br(), copy(), Eo, er(), es(), getValue() (+27 more)

### Community 1 - "Fit check: fit_checkpy"
Cohesion: 0.06
Nodes (28): analyze(), b64(), face_geometry(), load_3mf(), emit(), mat(), load_any(), load_obj() (+20 more)

### Community 2 - "three.js library 2"
Cohesion: 0.05
Nodes (5): jt(), Jt, Mh, Pt, Dt()

### Community 3 - "Worker tests"
Cohesion: 0.07
Nodes (7): bed_override(), Worker, BedTimer, FakeLink, Override, Streaming, TimerLink

### Community 6 - "three.js orbit controls: constructor"
Cohesion: 0.09
Nodes (39): MapControls, OrbitControls, dollyIn(), dollyOut(), getZoomScale(), handleKeyDown(), handleMouseDownDolly(), handleMouseDownPan() (+31 more)

### Community 7 - "three.js library 5"
Cohesion: 0.07
Nodes (38): bi(), bs, Ei(), fi(), gi(), mi(), f(), h() (+30 more)

### Community 8 - "README app docs: Duplicator 4 Studio app"
Cohesion: 0.05
Nodes (38): 3D model viewer (OpenGL with CPU fallback), Single-file exe build (build_exe.py), duplicator4_pla.ini PLA slicing profile, Duplicator 4 Studio (app), Emergency stop (Esc), Fit check / assembly check, gcode2x3g converter with printer fixes, GPL-3.0 licence (+30 more)

### Community 11 - "three.js library 8"
Cohesion: 0.07
Nodes (7): ds(), F(), G(), k(), V(), z(), xc

### Community 12 - "Qt window: MainWindow"
Cohesion: 0.11
Nodes (3): filament_temp(), parse_number(), MainWindow

### Community 13 - "three.js library 9"
Cohesion: 0.08
Nodes (17): Ao, bo, ci, clone(), Co, Da, Ga, gn() (+9 more)

### Community 14 - "Qt window: d4_qtpy"
Cohesion: 0.07
Nodes (16): apply_app_theme(), _caption(), _crash_log(), _draw_help(), help_picture(), main(), hook(), make_app() (+8 more)

### Community 16 - "S3G printer link"
Cohesion: 0.09
Nodes (4): crc8(), Link, NoResponse, PrinterGone

### Community 17 - "three.js library 10"
Cohesion: 0.07
Nodes (3): Ce, sh, ts()

### Community 18 - "Qt window: GLViewer"
Cohesion: 0.08
Nodes (3): GLViewer, SoftViewer, ViewMixin

### Community 19 - "three.js library 11"
Cohesion: 0.07
Nodes (6): ai, Jl, kl, Ql, vl(), Yl

### Community 22 - "Dual sample maker: make_dual_samplepy"
Cohesion: 0.11
Nodes (12): bead_area(), prime_line(), square_layer(), travel_to(), hexagon_loop(), ring_prism(), write_stl(), extrude_path() (+4 more)

### Community 24 - "three.js library 14"
Cohesion: 0.10
Nodes (5): en, Si(), Ti(), updateMatrixWorld(), wh()

### Community 25 - "G-code porting: argparse"
Cohesion: 0.14
Nodes (9): ConvertError, parse(), scan(), body_lines(), extents(), main(), port(), main() (+1 more)

### Community 26 - "Old Tk window: d4_guipy"
Cohesion: 0.10
Nodes (5): _crash_log(), _report_tk_error(), selftest(), find_prusaslicer(), run_tool()

### Community 27 - "Window tests: test_d4_qtpy"
Cohesion: 0.10
Nodes (8): Base, Closing, HelpSigns, Layout2, Licence, Persistence, tearDownModule(), Theme

### Community 28 - "three.js library 15"
Cohesion: 0.08
Nodes (15): bindSkeletons(), ei, ii, mc(), i(), parse(), parseAnimations(), parseImages() (+7 more)

### Community 32 - "Preview renderer: struct"
Cohesion: 0.10
Nodes (5): log(), main(), decode(), font(), split_x3g()

### Community 33 - "X3G streaming: os"
Cohesion: 0.18
Nodes (13): log(), main(), run(), wait_idle(), Cancelled, live_bed(), live_nozzle(), live_pause() (+5 more)

### Community 34 - "Qt window: label"
Cohesion: 0.16
Nodes (6): button(), card(), label(), B(), NoWheelCombo, NoWheelSpin

### Community 35 - "three.js library 18"
Cohesion: 0.10
Nodes (3): $e(), Ke(), tn

### Community 36 - "Dual sample maker: Printer"
Cohesion: 0.21
Nodes (3): convert(), build(), Printer

### Community 37 - "Old Tk window: build_print_tab"
Cohesion: 0.12
Nodes (4): fmt_min(), GBar, render(), x3g_stats()

### Community 38 - "Window tests: sent"
Cohesion: 0.13
Nodes (3): Emergency, Motion, Printing

### Community 39 - "three.js library 19"
Cohesion: 0.16
Nodes (21): ao(), co(), eo(), go, ho(), io(), ja(), ka() (+13 more)

### Community 44 - "Window tests: Prepare"
Cohesion: 0.17
Nodes (3): Prepare, TwoParts, wait_for()

### Community 47 - "three.js library 24"
Cohesion: 0.10
Nodes (6): hl, ol, setTexturePath(), uc, ul, o()

### Community 49 - "three.js library 26"
Cohesion: 0.14
Nodes (16): _allocateTargets(), _applyPMREM(), _blur(), _cleanup(), fromCubemap(), fromEquirectangular(), fromScene(), _fromTexture() (+8 more)

### Community 55 - "three.js library 31"
Cohesion: 0.12
Nodes (8): Et, Jn, ni, pi(), ti, Tt(), Xn(), yi()

### Community 56 - "three.js library 32"
Cohesion: 0.12
Nodes (4): Aa, bt, li(), Ra

### Community 57 - "three.js library 33"
Cohesion: 0.12
Nodes (8): Ah, ca, fa, fh, hh, uh(), xa, ya

### Community 58 - "three.js library 34"
Cohesion: 0.16
Nodes (7): cl, i(), load(), c(), oc, parseGeometries(), vc

### Community 60 - "Prepare Dark: Prepare Tab 3step workfl"
Cohesion: 0.15
Nodes (16): Prepare Tab Screenshot (Dark Theme), 3D Model Preview Viewer, Assembly Button (two-part prints), Choose an Object (STL / 3MF / OBJ), Colour Z Setting (two-colour switch height), Port / Connection Bar (COM30, Sailfish 7.7), Dark Theme, Duplicator 4 Studio App Window (+8 more)

### Community 61 - "three.js library 36"
Cohesion: 0.12
Nodes (5): _a, Do, Fo, No, zo

### Community 62 - "three.js library 37"
Cohesion: 0.17
Nodes (3): qn, p(), $s

### Community 64 - "Qt window: refresh_library"
Cohesion: 0.18
Nodes (3): file_info_lines(), fmt_min(), app_icon()

### Community 65 - "Old Tk window: apply_theme"
Cohesion: 0.16
Nodes (3): load_settings(), save_settings(), windows_uses_light_theme()

### Community 68 - "Window tests: status"
Cohesion: 0.17
Nodes (3): Extruder, PrinterEvents, status()

### Community 71 - "three.js library 41"
Cohesion: 0.12
Nodes (5): $l, parseObject(), tc, Ts, Vs

### Community 72 - "Safety rules core: d4_corepy"
Cohesion: 0.20
Nodes (6): check_summary(), load_settings(), resolve_theme(), save_settings(), windows_uses_light_theme(), Settings

### Community 73 - "Safety rules core: Texts"
Cohesion: 0.14
Nodes (6): board_text(), is_reserved_name(), name_from_model(), safe_name(), temp_state(), Texts

### Community 74 - "three.js library 42"
Cohesion: 0.17
Nodes (3): ia, parseSkeletons(), ta

### Community 75 - "Prepare: Prepare Tab choose objec"
Cohesion: 0.18
Nodes (13): 3D Model Preview Viewer (drag/zoom, fits-the-bed check), Assembly Button, Duplicator 4 Studio App, Emergency Stop Button (Esc), Fit Check Button, Prepare Tab (choose object, settings, generate), Duplicator 4 Studio Prepare Tab Screenshot, Sailfish Firmware 7.7 (+5 more)

### Community 76 - "Core tests: bed_heat_decision"
Cohesion: 0.22
Nodes (3): bed_heat_decision(), print_gate(), Bed

### Community 79 - "three.js library 43"
Cohesion: 0.21
Nodes (13): compileCubemapShader(), compileEquirectangularShader(), _compileMaterial(), constructor(), d(), u(), $h(), Io (+5 more)

### Community 81 - "Printer: Printer Tab Printer  Pre"
Cohesion: 0.19
Nodes (12): Duplicator 4 Studio Printer Tab Screenshot, Serial Port Connection Bar (COM port, Sailfish 7.7 firmware), Emergency Stop Button (Esc), Extruders / Filament Panel (Retract, Extrude, Load, Unload), Limit Switches and Position Panel, Log Panel, Move / Jog Panel (Head XY, Bed Z, Home, Motor test), Printer Tab (Printer / Prepare / Print tabs) (+4 more)

### Community 83 - "three.js library 45"
Cohesion: 0.15
Nodes (3): Al, el, Tl()

### Community 86 - "Paths: Prepare Tab choose objec"
Cohesion: 0.23
Nodes (10): Brim Rings (bed adhesion), Duplicator 4 Studio (desktop app), Parametric Settings Panel (height, radius, twist, lobes, nozzle/1st layer temp, brim rings, squish), Prepare Tab (choose object, settings, generate), Duplicator 4 Studio Prepare Tab - Print Paths Preview Screenshot, Print Estimate (time, filament per extruder, object height), Print Paths 3D Preview with Layer Slider, Serial Connection (COM30, Sailfish 7.7 firmware) (+2 more)

### Community 89 - "three.js library 49"
Cohesion: 0.20
Nodes (8): cs, v(), S(), y(), g(), us(), b(), M()

### Community 97 - "three.js library 56"
Cohesion: 0.22
Nodes (4): r(), t(), l(), o()

### Community 102 - "Safety rules core: set_heater"
Cohesion: 0.20
Nodes (3): extrude_decision(), nozzle_value(), Nozzle

### Community 105 - "Print: Print tab screenshot Dup"
Cohesion: 0.33
Nodes (7): Print tab screenshot (Duplicator 4 Studio), Emergency Stop button (Esc), Print files table (output folder: print time, filament R/L, Z homing, safety check), Print job panel (Print / Pause-Resume / Cancel, progress stats), Serial connection to Sailfish 7.7 firmware (COM port), Status bar with live temps (R, L, bed, Z) and theme selector, Toolpath preview panel (top view bed + 3D view)

### Community 110 - "three.js library 64"
Cohesion: 0.36
Nodes (7): s(), C(), G(), H(), O(), U(), z()

### Community 113 - "three.js library 66"
Cohesion: 0.25
Nodes (4): Ba, Ko, Na, _o

### Community 120 - "three.js library 71"
Cohesion: 0.33
Nodes (3): dt(), Qe(), ut()

### Community 128 - "three.js library 76"
Cohesion: 0.33
Nodes (3): fo(), mo(), po

### Community 134 - "three.js library 80"
Cohesion: 0.67
Nodes (4): $c(), intersectObject(), intersectObjects(), Kc()

## Knowledge Gaps
- **34 isolated node(s):** `MakerBot Replicator 1 Dual clones`, `Emergency stop (Esc)`, `3D print-path preview with layer slider`, `--selftest installation check`, `3D model slicing settings (layer, infill, walls, supports, squish, colour Z)` (+29 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 929 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **107 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `St` connect `three.js library 6` to `three.js library`, `three.js library 5`, `three.js library 20`, `three.js library 8`, `three.js library 63`, `three.js library 65`, `three.js library 11`, `three.js library 30`, `three.js library 49`, `three.js library 50`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **What connects `MakerBot Replicator 1 Dual clones`, `Emergency stop (Esc)`, `3D print-path preview with layer slider` to the rest of the system?**
  _34 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `three.js library` be split into smaller, more focused modules?**
  _Cohesion score 0.027715355805243445 - nodes in this community are weakly interconnected._
- **Why does `MainWindow` connect `Qt window: MainWindow` to `Qt window: refresh_library`, `Qt window: label`, `Worker tests`, `Safety rules core: set_heater`, `Qt window: start_print`, `Qt window: log`, `Qt window: d4_qtpy`, `Old Tk window: d4_guipy`, `Window tests: test_d4_qtpy`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Should `Fit check: fit_checkpy` be split into smaller, more focused modules?**
  _Cohesion score 0.0647307924984876 - nodes in this community are weakly interconnected._
- **Why does `App` connect `Old Tk window: App` to `Old Tk window: apply_theme`, `Old Tk window: panel`, `Old Tk window: model_sharp`, `Worker tests`, `Old Tk window: build_print_tab`, `Old Tk window: ScrollFrame`, `Old Tk window: log`, `Old Tk window: GButton`, `Old Tk window: d4_guipy`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Should `three.js library 2` be split into smaller, more focused modules?**
  _Cohesion score 0.05263157894736842 - nodes in this community are weakly interconnected._