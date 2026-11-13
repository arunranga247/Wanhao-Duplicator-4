"""
Tests for the Qt window: every control, safety rule, printer event and dialog, with a FAKE printer
(nothing is sent to the real one), temporary output / settings folders, and no screen needed.

    python -m unittest tools/tests/test_d4_qt.py -v
"""

__author__ = "ARUN"

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import d4_paths                                  # noqa: E402

TMP = tempfile.mkdtemp(prefix="d4qt_test_")
REAL_SETTINGS = d4_paths.SETTINGS
d4_paths.SETTINGS = os.path.join(TMP, "settings.json")          # never touch the real settings
import d4_core as core                           # noqa: E402
import d4_qt                                     # noqa: E402
from PySide6.QtCore import QPoint, QPointF, Qt   # noqa: E402
from PySide6.QtGui import QPalette, QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest                 # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea, QWidget   # noqa: E402

OUT_T, PREV_T = os.path.join(TMP, "output"), os.path.join(TMP, "preview")
os.makedirs(OUT_T)
os.makedirs(PREV_T)
d4_qt.OUT, d4_qt.PREV = OUT_T, PREV_T                           # generated files go to the temp folder
SAMPLE = os.path.join(d4_paths.OUT, "SMALL_FISH.x3g")
d4_qt.LOGFILE = os.path.join(TMP, "session_log.txt")              # never write into the real logs
d4_paths.OUT = OUT_T                                              # (crash_log.txt lives in d4_paths.OUT)
MODEL = os.path.join(d4_paths.DATA, "models", "test_nut.stl")


class FakePrinter:
    """Stands in for the worker thread: records what the window asks the printer to do."""

    def __init__(self):
        self.events, self.quit, self.sent = None, threading.Event(), []

    def is_alive(self):
        return True

    def submit(self, *a):
        self.sent.append(a)

    def emergency_stop(self):
        self.sent.append(("estop",))

    def join(self, *_):
        pass


def wait_for(cond, timeout=60.0):
    app = QApplication.instance()
    t0 = time.time()
    while time.time() - t0 < timeout:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def status(r=25, l=25, bed=24, r_t=0, l_t=0, bed_t=0, es=0, homed=False, board=0, pos=(1, 2, 3, 4, 5)):
    return {"t": {"r": r, "l": l, "bed": bed, "r_t": r_t, "l_t": l_t, "bed_t": bed_t},
            "pos": list(pos), "es": es, "board": board, "homed": homed}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = d4_qt.make_app(["test"])
        cls.w = cls.new_window()

    @classmethod
    def new_window(cls):
        w = d4_qt.MainWindow(worker=FakePrinter())
        w.answers = {"ask": True, "ask_ok": True, "checklist": True}
        w.shown = []
        w.info = lambda t, m: w.shown.append(("info", t, m))
        w.warn = lambda t, m: w.shown.append(("warn", t, m))
        w.error = lambda t, m: w.shown.append(("error", t, m))
        w.ask = lambda t, m: (w.shown.append(("ask", t, m)), w.answers["ask"])[1]
        w.ask_ok = lambda t, m: (w.shown.append(("ask_ok", t, m)), w.answers["ask_ok"])[1]
        w.checklist = lambda p, st: (w.shown.append(("checklist", p)), w.answers["checklist"])[1]
        w.opened = []
        w.open_url = lambda p: w.opened.append(p)
        w.resize(1366, 740)
        w.show()
        cls.app.processEvents()
        return w

    def setUp(self):
        w = self.w
        w.worker.sent.clear()
        w.shown.clear()
        w.answers.update(ask=True, ask_ok=True, checklist=True)
        w.on_connected("COM30", "Sailfish 7.7")
        w.on_status(status())
        w.bed_ok.setChecked(True)
        w.printing = False
        w.worker.sent.clear()

    def sent(self):
        return self.w.worker.sent

    def titles(self, kind):
        return [t for k, t, *_ in self.w.shown if k == kind]


# ---------------------------------------------------------------------------------------------
class Heaters(Base):
    def test_nozzle_set_and_off(self):
        self.w.t_entry["r"].setValue(215)
        self.w.set_heater("r")
        self.w.set_heater("l", 0)
        self.assertEqual(self.sent(), [("set_temp", 0, 215), ("set_temp", 1, 0)])

    def test_nozzle_box_limit(self):
        self.w.t_entry["l"].setValue(999)
        self.assertEqual(self.w.t_entry["l"].value(), core.NOZZLE_MAX_C)

    def test_bed_ok(self):
        self.w.t_entry["bed"].setValue(60)
        self.w.set_heater("bed")
        self.assertEqual(self.sent(), [("set_bed", 60)])

    def test_bed_box_cannot_exceed_limit(self):
        self.w.t_entry["bed"].setValue(110)
        self.assertEqual(self.w.t_entry["bed"].value(), core.BED_MAX_C)

    def test_bed_broken_sensor_refused(self):
        self.w.on_status(status(bed=4))
        self.w.t_entry["bed"].setValue(60)
        self.w.set_heater("bed")
        self.assertEqual(self.sent(), [])
        self.assertIn("Bed heating blocked", self.titles("warn"))

    def test_bed_switch_off_refused(self):
        self.w.bed_ok.setChecked(False)
        self.w.t_entry["bed"].setValue(60)
        self.w.set_heater("bed")
        self.assertEqual(self.sent(), [])

    def test_bed_off_always_allowed(self):
        self.w.on_status(status(bed=3))
        self.w.bed_ok.setChecked(False)
        self.w.set_heater("bed", 0)
        self.assertEqual(self.sent(), [("set_bed", 0)])

    def test_preset_and_all_off(self):
        self.w.preset(210)
        self.assertEqual(self.sent(), [("set_temp", 0, 210), ("set_temp", 1, 210)])

    def test_wheel_does_not_change_unfocused_box(self):
        sp = self.w.t_entry["r"]
        sp.setValue(200)
        self.w.setFocus()
        ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(sp, ev)
        self.assertEqual(sp.value(), 200)


class Motion(Base):
    def test_jog_steps_and_speeds(self):
        for b in self.w.step_group.buttons():
            if b.property("mm") == 1.0:
                b.setChecked(True)
        self.w.jog(0, -1)
        self.w.jog(2, +1)
        self.assertEqual(self.sent(), [("jog", 0, -1.0, 30.0), ("jog", 2, 1.0, 8.0)])

    def test_homing_needs_confirmation(self):
        self.w.answers["ask_ok"] = False
        self.w.home_z()
        self.w.home_all()
        self.w.motor_test()
        self.assertEqual(self.sent(), [])
        self.w.answers["ask_ok"] = True
        self.w.home_z()
        self.w.home_all()
        self.w.motor_test()
        self.assertEqual(self.sent(), [("home_z",), ("home_all",), ("motor_test",)])

    def test_buttons_follow_connection(self):
        self.assertTrue(all(b.isEnabled() for b in self.w._controls))
        self.w.on_disconnected("cable unplugged")
        self.assertFalse(any(b.isEnabled() for b in self.w._controls))
        self.assertEqual(self.w.conn_lbl.property("tone"), "bad")
        self.assertEqual(self.w.conn_btn.text(), "Connect")


class Ports(Base):
    def setUp(self):
        super().setUp()
        self.real = d4_qt.s3g.find_ports

    def tearDown(self):
        d4_qt.s3g.find_ports = self.real

    def test_connected_port_is_shown(self):
        d4_qt.s3g.find_ports = lambda: []                     # the list was empty when the window opened
        self.w.on_disconnected("x")
        self.assertEqual(self.w.port_box.currentText(), self.w.NO_PORT_TEXT)
        self.w.on_connected("COM30", "Sailfish 7.7")         # link came back by itself
        self.assertTrue(self.w.port_box.currentText().startswith("COM30"))
        self.assertNotIn("printer off", self.w.port_box.currentText())

    def test_picks_the_used_port_among_several(self):
        d4_qt.s3g.find_ports = lambda: [("COM3", "COM3  USB serial", False), ("COM30", "COM30  (Duplicator / MakerBot)", True)]
        self.w.on_connected("COM30", "Sailfish 7.7")
        self.assertTrue(self.w.port_box.currentText().startswith("COM30"))
        self.assertEqual(self.w.port_box.count(), 2)

    def test_no_printer_message(self):
        d4_qt.s3g.find_ports = lambda: []
        self.w.on_disconnected("unplugged")
        self.assertIn("switch it on", self.w.port_box.currentText())
        self.assertEqual(self.w.port_box.property("tone"), "dim")


class Extruder(Base):
    def test_hot_extrude(self):
        self.w.on_status(status(r=210))
        self.w.e_amt.setValue(15)
        self.w.extrude(0, +1)
        self.w.extrude(0, -1)
        self.assertEqual(self.sent(), [("extrude", 0, 15.0), ("extrude", 0, -15.0)])

    def test_cold_extrude_asks_and_limits(self):
        self.w.on_status(status(l=30))
        self.w.answers["ask"] = False
        self.w.extrude(1, +1)
        self.assertEqual(self.sent(), [])
        self.w.answers["ask"] = True
        self.w.extrude(1, +1)
        self.assertEqual(self.sent(), [("extrude", 1, 2.0)])

    def test_load_unload(self):
        self.w.fil_temp.setValue(205)
        self.w.keep_hot.setChecked(True)
        self.w.filament(1, "load")
        self.w.keep_hot.setChecked(False)
        self.w.filament(0, "unload")
        self.assertEqual(self.sent(), [("load", 1, 205, True), ("unload", 0, 205, False)])
        self.w.answers["ask_ok"] = False
        self.w.filament(0, "load")
        self.assertEqual(len(self.sent()), 2)


class Emergency(Base):
    def test_button(self):
        self.w.estop_btn.click()
        self.assertIn(("estop",), self.sent())

    def test_escape_key(self):
        self.w.activateWindow()
        QTest.keyClick(self.w.tabs, Qt.Key.Key_Escape)
        self.assertIn(("estop",), self.sent())

    def test_works_when_disconnected(self):
        self.w.on_disconnected("x")
        self.w.estop_btn.click()
        self.assertIn(("estop",), self.sent())


class PrinterEvents(Base):
    def test_status_updates(self):
        w = self.w
        w.on_status(status(r=150, r_t=210, l=208, l_t=210, bed=24, es=0b10010, homed=True, board=0x40))
        self.assertEqual(w.t_lbl["r"].text(), "150°")
        self.assertEqual(w.t_tgt["r"].text(), "→ 210°")
        self.assertEqual(w.t_tgt["l"].text(), "✓ 210°")
        self.assertEqual(w.t_tgt["r"].property("tone"), "warn")
        self.assertEqual(w.t_tgt["bed"].text(), "off")
        self.assertEqual(w.sw[1][1].property("on"), "true")
        self.assertEqual(w.sw[3][1].property("on"), "false")
        self.assertEqual(w.sw[4][1].property("on"), "true")
        self.assertIn("HEAT_SHUTDOWN", w.board_lbl.text())
        self.assertEqual(w.board_lbl.property("tone"), "warn")
        self.assertEqual(w.homed_lbl.text(), "Homed")
        self.assertIn("X 1.00", w.pos_lbl.text())
        self.assertGreater(len(w.hist), 0)

    def test_none_readings(self):
        self.w.on_status(status(r=None, l=None, bed=None))
        self.assertEqual(self.w.t_lbl["r"].text(), "---°")

    def test_flutter_warning(self):
        for i in range(core.SWITCH_FLUTTER_N + 2):
            self.w.on_status(status(es=(i % 2) << 1))
        self.assertIn("loose wire", self.w.sw_warn.text())

    def test_alarm_pops_up(self):
        self.w.on_alarm("HEATERS SWITCHED OFF: test")
        self.assertIn("Printer alarm", self.titles("error"))

    def test_log_is_plain_text(self):
        self.w.log("<b>not bold</b>  two  spaces & more", "alarm")
        self.assertIn("<b>not bold</b>  two  spaces & more", self.w.logbox.toPlainText())

    def test_bad_event_does_not_stop_pump(self):
        self.w.events.put(("no_such_event", 1))
        self.w.events.put(("log", "after the bad one"))
        self.w.pump()
        self.assertIn("after the bad one", self.w.logbox.toPlainText())

    def test_print_progress_phases_done(self):
        w = self.w
        w.printing, w.job_file = True, "X.x3g"
        w.print_stats = {"cum": [10.0, 20.0, 30.0, 40.0], "time_s": 40.0}
        w.on_phase("heat", "bed")
        self.assertIn("Heating bed", w.job_name.text())
        w.on_phase("print", None)
        self.assertIn("Printing", w.job_name.text())
        w.on_progress(2, 4, 75)
        self.assertEqual(w.job_vals["pct"].text(), "50 %")
        self.assertEqual(w.job_vals["left"].text(), "0:20")
        self.assertEqual(w.prog.value(), 500)
        w.on_status(status(pos=(0, 0, 4.2, 0, 123)))
        self.assertEqual(w.job_vals["z"].text(), "4.20 mm")
        w.on_print_done(True, "Print finished")
        self.assertFalse(w.printing)
        self.assertEqual(w.prog.property("done"), "true")
        w.printing = True
        w.on_print_done(False, "USB link lost")
        self.assertIn("Print stopped", self.titles("warn"))


@unittest.skipUnless(os.path.exists(SAMPLE), "needs output/SMALL_FISH.x3g")
class Printing(Base):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(OUT_T, "T_PRINT.x3g")
        shutil.copy(SAMPLE, self.path)
        self.w.refresh_library(select=self.path)
        self.w._check_cache[self.path] = (os.path.getmtime(self.path), True, "RESULT        : OK")
        self.st = dict(self.w._stats(self.path))
        self.w._stats_cache[self.path] = (os.path.getmtime(self.path), self.st)
        self.w.worker.sent.clear()
        self.w.shown.clear()

    def tearDown(self):
        self.w.printing = False

    def test_selected(self):
        self.assertEqual(self.w.selected_path(), self.path)

    def test_happy_path(self):
        self.w.start_print()
        self.assertEqual(self.sent(), [("print", self.path)])
        self.assertTrue(self.w.printing)
        self.assertIn("checklist", [k for k, *_ in self.w.shown])

    def test_checklist_cancel(self):
        self.w.answers["checklist"] = False
        self.w.start_print()
        self.assertEqual(self.sent(), [])

    def test_not_connected(self):
        self.w.on_disconnected("x")
        self.w.start_print()
        self.assertEqual(self.sent(), [])

    def test_failed_check(self):
        self.w._check_cache[self.path] = (os.path.getmtime(self.path), False, "RESULT : FAIL")
        self.w.start_print()
        self.assertEqual(self.sent(), [])
        self.assertIn("Safety check failed", self.titles("error"))

    def test_bed_file_with_broken_sensor(self):
        self.st["bed"] = 60
        self.w.on_status(status(bed=3))
        self.w.start_print()
        self.assertEqual(self.sent(), [])
        self.assertIn("Bed sensor fault", self.titles("error"))

    def test_t1_file(self):
        self.st["t1_change"] = True
        self.w.start_print()
        self.assertEqual(self.sent(), [])

    def test_fast_z_question(self):
        self.st["z_home"] = "fast"
        self.w.answers["ask"] = False
        self.w.start_print()
        self.assertEqual(self.sent(), [])
        self.w.answers["ask"] = True
        self.w.start_print()
        self.assertEqual(self.sent(), [("print", self.path)])

    def test_cancel_print(self):
        self.w.printing = True
        self.w.answers["ask"] = False
        self.w.cancel_print()
        self.assertEqual(self.sent(), [])
        self.w.answers["ask"] = True
        self.w.cancel_print()
        self.assertEqual(self.sent(), [("cancel",)])

    def test_select_shows_info_and_preview(self):
        self.w._check_cache.pop(self.path)
        self.w.tree.clearSelection()
        self.w.refresh_library(select=self.path)
        self.w.on_select_file()
        self.assertTrue(wait_for(lambda: self.path in self.w._check_cache, 120))
        self.assertTrue(wait_for(lambda: self.w.file_preview.src is not None, 60))
        self.assertIn("T_PRINT.x3g", self.w.file_info.toPlainText())
        self.assertIn(self.w._item_of(self.path).text(4), ("✅ OK", "❌ FAIL"))

    def test_delete(self):
        self.w.answers["ask"] = False
        self.w.delete_file()
        self.assertTrue(os.path.exists(self.path))
        self.w.answers["ask"] = True
        self.w.delete_file()
        self.assertFalse(os.path.exists(self.path))
        self.assertIsNone(self.w._item_of(self.path))


class Prepare(Base):
    def choose(self, title):
        self.w.obj_box.setCurrentText(title)
        self.app.processEvents()

    def test_every_object_builds_its_settings(self):
        for title, obj in core.OBJECTS.items():
            self.choose(title)
            self.assertEqual(set(self.w.param_widgets), {p[0] for p in obj["params"]}, title)
            self.assertEqual(self.w.model_edit is not None, bool(obj.get("model")), title)
            visible = [c for c in self.w.param_host.findChildren(QWidget) if c.isVisible()]
            self.assertTrue(all(c.parent() is not None for c in visible))
            self.assertEqual(self.w.gen_name.isEnabled(), not obj.get("fixed_name"), title)

    def test_info_button(self):
        for title, obj in core.OBJECTS.items():
            self.choose(title)
            self.assertIn(obj["desc"][:30], self.w.obj_info.toolTip())
            self.w.shown.clear()
            self.w.obj_info.click()
            self.assertEqual(self.w.shown, [("info", title, obj["desc"])])

    def test_one_font_everywhere(self):
        fam = QApplication.instance().font().family()
        self.assertEqual(fam, "Segoe UI")
        for wdg in (self.w.port_box, self.w.t_entry["r"], self.w.obj_box, self.w.gen_name, self.w.theme_box):
            self.assertEqual(wdg.font().family(), fam, type(wdg).__name__)

    def test_old_settings_widgets_are_removed(self):
        self.choose("Square block")
        n1 = len(self.w.param_host.findChildren(QWidget))
        for _ in range(3):
            self.choose("Twisted flower vase")
            self.choose("Square block")
        self.app.processEvents()
        QApplication.sendPostedEvents(None, 0)                 # run the deleteLater()s
        self.assertEqual(len(self.w.param_host.findChildren(QWidget)), n1)

    def test_each_object_remembers_its_values(self):
        self.choose("Twisted flower vase")
        self.w.param_widgets["height"][0].setValue(31)
        self.choose("Square block")
        self.choose("Twisted flower vase")
        self.assertEqual(self.w.param_widgets["height"][0].value(), 31)

    def test_bad_names_refused(self):
        self.choose("Twisted flower vase")
        for name in ("   ", "!!!", "CON"):
            self.w.shown.clear()
            self.w.gen_name.setText(name)
            self.w.generate()
            self.assertEqual([k for k, *_ in self.w.shown], ["error"], name)
            self.assertTrue(self.w.gen_btn.isEnabled())

    def test_model_object_needs_a_file(self):
        self.choose("📦 Your 3D model (STL / 3MF / OBJ)")
        self.w.model_edit.setText(r"C:\no\such\file.stl")
        self.w.generate()
        self.assertIn("3D model", self.titles("error"))
        self.w.fit_check()
        self.assertIn("Fit check", self.titles("info"))

    def test_generate_real_vase(self):
        self.choose("Twisted flower vase")
        self.w.param_widgets["height"][0].setValue(6)
        self.w.gen_name.setText("t vase")
        self.w.generate()
        self.assertFalse(self.w.gen_btn.isEnabled())
        self.assertTrue(wait_for(lambda: self.w.gen_btn.isEnabled(), 180), "generate did not finish")
        path = os.path.join(OUT_T, "TVASE.x3g")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(self.w.gen_status.property("tone"), "ok", self.w.gen_status.text())
        self.assertFalse(self.w.gen_to_print.isHidden())
        self.assertIsNotNone(self.w._item_of(path))
        self.assertIs(self.w.model_area.stack.currentWidget(), self.w.model_area.image)
        self.w._goto_print_generated()
        self.assertIs(self.w.tabs.currentWidget(), self.w.tab_print)
        self.assertEqual(self.w.selected_path(), path)

    @unittest.skipUnless(os.path.exists(MODEL), "needs models/test_nut.stl")
    def test_model_viewer_and_mouse(self):
        self.choose("📦 Your 3D model (STL / 3MF / OBJ)")
        self.w.tabs.setCurrentWidget(self.w.tab_prepare)
        self.w.model_edit.setText(MODEL)
        self.assertTrue(wait_for(lambda: self.w.model_area.showing_model(), 60))
        self.assertIn("fits the bed", self.w.gen_status.text())
        v = self.w.model_area.stack.currentWidget()
        y0 = v.view["yaw"]
        QTest.mousePress(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 100))
        QTest.mouseMove(v, QPoint(160, 120))
        QTest.mouseRelease(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(160, 120))
        self.assertNotEqual(v.view["yaw"], y0)
        ev = QWheelEvent(QPointF(50, 50), QPointF(50, 50), QPoint(0, 0), QPoint(0, 240), Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(v, ev)
        self.assertGreater(v.view["zoom"], 1.0)
        QTest.mouseDClick(v, Qt.MouseButton.LeftButton)
        self.assertEqual(v.view, d4_qt.VIEW0)
        if isinstance(v, d4_qt.SoftViewer):
            self.assertIsNotNone(v.pixmap())

    @unittest.skipUnless(os.path.exists(MODEL), "needs models/test_nut.stl")
    def test_fit_check_real(self):
        self.choose("📦 Your 3D model (STL / 3MF / OBJ)")
        self.w.model_edit.setText(MODEL)
        self.w.fit_check()
        self.assertTrue(wait_for(lambda: "running" not in self.w.gen_status.text(), 300))
        self.assertIn("Fit check:", self.w.gen_status.text())
        self.assertIn(self.w.gen_status.property("tone"), ("ok", "warn", "bad"))
        self.assertEqual(len(self.w.opened), 1)

    def test_broken_model_file(self):
        bad = os.path.join(TMP, "broken.stl")
        with open(bad, "wb") as fh:
            fh.write(b"solid x\nthis is not a mesh\n")
        self.choose("📦 Your 3D model (STL / 3MF / OBJ)")
        self.w.model_edit.setText(bad)
        self.assertTrue(wait_for(lambda: "Can't show" in self.w.model_area.msg.text(), 30))


class HelpSigns(Base):
    def test_every_setting_has_a_question_mark(self):
        from PySide6.QtWidgets import QToolButton
        for title, obj in core.OBJECTS.items():
            self.w.obj_box.setCurrentText(title)
            self.app.processEvents()
            flags = {b.property("flag") for b in self.w.param_host.findChildren(QToolButton) if b.objectName() == "help"}
            want = {p[0] for p in obj["params"]} | ({"_model"} if obj.get("model") else set()) \
                | ({"_extruder"} if obj["extruder"] else set())
            self.assertEqual(flags, want, title)

    def test_click_shows_explanation_with_picture(self):
        from PySide6.QtWidgets import QToolButton
        self.w.obj_box.setCurrentText("📦 Your 3D model (STL / 3MF / OBJ)")
        self.app.processEvents()
        b = next(b for b in self.w.param_host.findChildren(QToolButton) if b.property("flag") == "infill")
        self.assertIn("hollow", b.toolTip())
        self.w.shown.clear()
        b.click()
        kind, title, text = self.w.shown[0]
        self.assertEqual((kind, title), ("info", "Infill (%)"))
        self.assertIn("<img", text)
        self.assertTrue(os.path.exists(d4_qt.help_picture("infill")))

    def test_every_help_text_exists(self):
        for obj in core.OBJECTS.values():
            for p in obj["params"]:
                self.assertTrue(core.PARAM_HELP.get(p[0]), p[0])


@unittest.skipUnless(os.path.exists(SAMPLE), "needs output/SMALL_FISH.x3g")
class PrintPaths(Base):
    def test_toolpath_layers(self):
        tp = d4_qt.Toolpath(SAMPLE)
        self.assertGreater(len(tp.layers), 5)
        self.assertTrue(all(b > a for a, b in zip(tp.layers, tp.layers[1:])))     # layers go up
        self.assertTrue(all(b >= a for a, b in zip(tp.counts, tp.counts[1:])))
        self.assertEqual(int(tp.counts[-1]), len(tp.data))
        self.assertEqual(tp.data.shape[1], 9)
        self.assertIn("layers", tp.info)

    def test_empty_file_is_refused(self):
        p = os.path.join(TMP, "empty.x3g")
        open(p, "wb").close()
        with self.assertRaises(Exception):
            d4_qt.Toolpath(p)

    def test_preview_views_without_gpu(self):
        area = self.w.model_area                         # no OpenGL in this test: picture instead
        pic = os.path.join(PREV_T, "pic.png")
        from PIL import Image
        Image.new("RGB", (40, 30), "white").save(pic)
        area.set_result(d4_qt.Toolpath(SAMPLE), pic, keep_model=False)
        self.assertEqual(area.current, "picture")
        self.assertFalse(area.bar.isVisibleTo(self.w))           # only one view: no buttons
        import model_preview
        area.scene = model_preview.Scene(MODEL) if os.path.exists(MODEL) else None
        if area.scene is not None:
            area.show_view("picture")
            self.assertTrue(area.btns["model"].isVisibleTo(area) or not area.isVisible())
            area.show_view("model")
            self.assertEqual(area.current, "model")


class Licence(Base):
    def test_about_states_licence(self):
        self.w.show_about()
        kind, title, text = self.w.shown[-1]
        self.assertIn("GNU General Public License v3.0", text)
        self.assertIn("WITHOUT ANY WARRANTY", text)
        self.assertIn("Not affiliated with Wanhao", text)

    def test_licence_files_exist(self):
        root = d4_qt.MainWindow.licence_folder()
        with open(os.path.join(root, "LICENSE"), encoding="utf-8") as fh:
            self.assertIn("GNU GENERAL PUBLIC LICENSE", fh.read(300))
        for n in ("THIRD_PARTY_NOTICES.md", "LGPL-3.0.txt", "Python-LICENSE.txt", "manifold3d-LICENSE.txt",
                  "Pillow-LICENSE.txt", "pyserial-LICENSE.txt", "three.js-LICENSE.txt", os.path.join("numpy", "LICENSE.txt")):
            p = os.path.join(root, n) if n.endswith(".md") else os.path.join(root, "licenses", n)
            self.assertTrue(os.path.getsize(p) > 200, n)


class Theme(Base):
    def test_live_switch_both_ways(self):
        w = self.w
        for choice, theme in (("Dark", "dark"), ("Light", "light"), ("Dark", "dark")):
            w.apply_theme(choice)
            self.app.processEvents()
            self.assertEqual(d4_qt.THEME, theme)
            page = w.centralWidget().palette().color(QPalette.ColorRole.Window).name()
            self.assertEqual(page, core.PALETTES[theme]["page"])
            self.assertIn(core.PALETTES[theme]["card"] if "card" in core.PALETTES[theme] else
                          core.PALETTES[theme]["bg"], QApplication.instance().styleSheet())
            self.assertEqual(w.theme_box.currentText(), choice)
            self.assertEqual(core.load_settings().get("theme"), choice)
            self.assertTrue(w.isVisible())                     # same window - nothing restarted
        w.apply_theme("Light")

    def test_combo_box_switches(self):
        self.w.theme_box.setCurrentText("Dark")
        self.assertEqual(d4_qt.THEME, "dark")
        self.w.theme_box.setCurrentText("Light")
        self.assertEqual(d4_qt.THEME, "light")

    def test_unknown_choice_ignored(self):
        self.w.apply_theme("Purple")
        self.assertEqual(d4_qt.THEME, "light")


class Layout(Base):
    def visible_inside_window(self, widget):
        tl = widget.mapTo(self.w, QPoint(0, 0))
        return tl.x() >= 0 and tl.y() >= 0 and tl.x() + widget.width() <= self.w.width() \
            and tl.y() + widget.height() <= self.w.height()

    def test_screen_sizes(self):
        for size in ((1366, 740), (1280, 700), (1920, 1040)):
            self.w.resize(*size)
            for i in range(3):
                self.w.tabs.setCurrentIndex(i)
                wait_for(lambda: False, 0.15)
                tab = self.w.tabs.currentWidget()
                if isinstance(tab, QScrollArea):
                    self.assertFalse(tab.horizontalScrollBar().isVisible(),
                                     "tab %d needs sideways scrolling at %s" % (i, size))
            self.w.tabs.setCurrentWidget(self.w.tab_prepare)
            wait_for(lambda: False, 0.15)
            self.assertTrue(self.visible_inside_window(self.w.gen_btn), "Generate hidden at %s" % (size,))
            self.w.tabs.setCurrentWidget(self.w.tab_print)
            wait_for(lambda: False, 0.15)
            self.assertTrue(self.visible_inside_window(self.w.print_btn), "Print button hidden at %s" % (size,))
        self.w.resize(1366, 740)

    def test_no_button_cut_off_sideways(self):
        self.w.resize(1366, 740)
        for i in range(3):
            self.w.tabs.setCurrentIndex(i)
            wait_for(lambda: False, 0.15)
            for b in self.w.tabs.currentWidget().findChildren(QPushButton):
                if b.isVisible():
                    x = b.mapTo(self.w, QPoint(0, 0)).x()
                    self.assertLessEqual(x + b.width(), self.w.width(), b.text())


class Persistence(Base):
    def test_save_and_restore(self):
        w = self.w
        w.t_entry["r"].setValue(222)
        w.e_amt.setValue(37)
        w.keep_hot.setChecked(True)
        w.tabs.setCurrentIndex(2)
        w.obj_box.setCurrentText("Square block")
        w.save_ui()
        w2 = self.new_window()
        try:
            self.assertEqual(w2.t_entry["r"].value(), 222)
            self.assertEqual(w2.e_amt.value(), 37)
            self.assertTrue(w2.keep_hot.isChecked())
            self.assertEqual(w2.tabs.currentIndex(), 2)
            self.assertEqual(w2.obj_box.currentText(), "Square block")
        finally:
            for t in w2.timers:
                t.stop()
            w2.hide()
            w2.deleteLater()

    def test_corrupt_settings_still_start(self):
        with open(d4_paths.SETTINGS, "w") as fh:
            fh.write("{garbage")
        w2 = self.new_window()
        self.assertTrue(w2.isVisible())
        for t in w2.timers:
            t.stop()
        w2.hide()
        w2.deleteLater()


class Closing(Base):
    def test_close_while_printing(self):
        w = self.w
        w.printing = True
        w.answers["ask"] = False
        w.close()
        self.assertTrue(w.isVisible(), "closed although the user said no")
        w.answers["ask"] = True
        w.close()
        self.assertIn(("estop",), self.sent())
        self.assertTrue(w.worker.quit.is_set())
        w.printing = False
        w.worker.quit.clear()
        w.show()
        for t in w.timers:
            t.start()


def tearDownModule():
    d4_paths.SETTINGS = REAL_SETTINGS
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
