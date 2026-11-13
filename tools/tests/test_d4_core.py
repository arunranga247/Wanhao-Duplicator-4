"""
Tests for the safety rules and helpers in d4_core (no printer, no window needed).

    python -m unittest discover -s tools/tests -v
"""

__author__ = "ARUN"

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import d4_core as c          # noqa: E402
import d4_paths              # noqa: E402

ST = {"bed": 0, "t1_change": False, "z_home": "slow", "fil": [0.0, 500.0], "zmax": 30.0, "zprint": 10.0,
      "time_s": 600.0, "cum": [60.0 * k for k in range(1, 11)], "temps": {1: 210}, "n": 10}


def st(**kw):
    d = dict(ST)
    d.update(kw)
    return d


class Bed(unittest.TestCase):
    def test_off_always_allowed(self):
        self.assertEqual(c.bed_heat_decision(0, False, 3)[:2], (True, 0))
        self.assertEqual(c.bed_heat_decision("-5", True, None)[:2], (True, 0))

    def test_switch_off_blocks(self):
        ok, v, title, _ = c.bed_heat_decision(60, False, 24)
        self.assertFalse(ok)
        self.assertIn("blocked", title)

    def test_broken_sensor_blocks(self):              # the real fault: 1-17 °C at room temperature
        for reading in (1, 5, 14.9):
            self.assertFalse(c.bed_heat_decision(60, True, reading)[0], reading)

    def test_plausible_sensor_allows(self):
        self.assertEqual(c.bed_heat_decision(60, True, 15)[:2], (True, 60))
        self.assertEqual(c.bed_heat_decision(60, True, 25)[:2], (True, 60))

    def test_unknown_reading_allows(self):            # not connected yet: the worker ignores it anyway
        self.assertEqual(c.bed_heat_decision(60, True, None)[:2], (True, 60))

    def test_capped_at_max(self):
        ok, v, title, msg = c.bed_heat_decision(110, True, 25)
        self.assertEqual((ok, v), (True, c.BED_MAX_C))
        self.assertIn("70", msg)
        self.assertEqual(c.bed_heat_decision(70, True, 25)[:2], (True, 70))

    def test_text_input(self):
        self.assertEqual(c.bed_heat_decision("60", True, 25)[:2], (True, 60))
        self.assertEqual(c.bed_heat_decision("59,6", True, 25)[:2], (True, 60))
        self.assertFalse(c.bed_heat_decision("abc", True, 25)[0])
        self.assertFalse(c.bed_heat_decision("", True, 25)[0])
        self.assertFalse(c.bed_heat_decision("nan", True, 25)[0])


class Nozzle(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(c.nozzle_value("215"), 215)
        self.assertEqual(c.nozzle_value(999), 240)
        self.assertEqual(c.nozzle_value(-10), 0)
        self.assertIsNone(c.nozzle_value("x"))
        self.assertIsNone(c.nozzle_value("inf"))

    def test_filament_temp_range(self):
        self.assertEqual(c.filament_temp(100), 170)
        self.assertEqual(c.filament_temp(300), 240)
        self.assertEqual(c.filament_temp("205"), 205)
        self.assertIsNone(c.filament_temp(""))

    def test_cold_extrude(self):
        self.assertEqual(c.extrude_decision(210, 10.0), (10.0, None))
        self.assertEqual(c.extrude_decision(170, 10.0), (10.0, None))          # exactly the limit is OK
        mm, q = c.extrude_decision(169, 10.0)
        self.assertEqual(mm, 2.0)
        self.assertIn("cold", q)
        self.assertEqual(c.extrude_decision(None, 5.0), (5.0, None))


class PrintGate(unittest.TestCase):
    def kinds(self, **kw):
        args = dict(st=st(), check_ok=True, check_text="", connected=True, bed_allowed=True, bed_now=24)
        args.update(kw)
        return [k for k, _, _ in c.print_gate(**args)]

    def test_clean_file_goes(self):
        self.assertEqual(self.kinds(), [])

    def test_not_connected(self):
        self.assertEqual(self.kinds(connected=False), ["block"])

    def test_failed_check(self):
        self.assertEqual(self.kinds(check_ok=False), ["block"])

    def test_bed_file_switch_off(self):
        self.assertEqual(self.kinds(st=st(bed=60), bed_allowed=False), ["block"])

    def test_bed_file_broken_sensor(self):            # new: was not checked before printing
        self.assertEqual(self.kinds(st=st(bed=60), bed_now=4), ["block"])

    def test_bed_file_ok(self):
        self.assertEqual(self.kinds(st=st(bed=60)), [])

    def test_bed_file_too_hot(self):
        self.assertEqual(self.kinds(st=st(bed=90)), ["block"])

    def test_no_bed_ignores_sensor(self):
        self.assertEqual(self.kinds(st=st(bed=0), bed_now=2, bed_allowed=False), [])

    def test_t1_change(self):
        self.assertEqual(self.kinds(st=st(t1_change=True)), ["block"])

    def test_fast_z_asks(self):
        self.assertEqual(self.kinds(st=st(z_home="fast")), ["confirm"])

    def test_several_problems(self):
        self.assertEqual(sorted(self.kinds(st=st(t1_change=True, z_home="fast"))), ["block", "confirm"])


class Checklist(unittest.TestCase):
    def test_items(self):
        items = c.checklist_items(st(bed=60, fil=[300.0, 400.0]))
        self.assertTrue(any("60 °C" in i for i in items))
        self.assertTrue(any("RIGHT and LEFT extruders" in i for i in items))
        self.assertIn("EMERGENCY STOP", items[-1])

    def test_low_bed_warning(self):
        self.assertTrue(any("Bed is LOW" in i for i in c.checklist_items(st(z_home=None, zmax=20))))
        self.assertFalse(any("Bed is LOW" in i for i in c.checklist_items(st(z_home="slow"))))


class Progress(unittest.TestCase):
    def test_time_based(self):
        frac, left = c.progress(st(), 5, 10)
        self.assertAlmostEqual(frac, 0.5)
        self.assertAlmostEqual(left, 300.0)

    def test_start_and_end(self):
        self.assertEqual(c.progress(st(), 0, 10), (0.0, 600.0))
        self.assertEqual(c.progress(st(), 10, 10), (1.0, 0.0))
        self.assertEqual(c.progress(st(), 50, 10)[0], 1.0)             # never above 100 %

    def test_without_table(self):
        self.assertEqual(c.progress(None, 3, 12), (0.25, None))
        self.assertEqual(c.progress(st(cum=[]), 0, 0), (0.0, None))


class Texts(unittest.TestCase):
    def test_temp_state(self):
        self.assertEqual(c.temp_state(25, 0), ("off", False))
        self.assertEqual(c.temp_state(100, 210), ("→ 210°", True))
        self.assertEqual(c.temp_state(208, 210), ("✓ 210°", True))
        self.assertEqual(c.temp_state(None, 210), ("✓ 210°", True))

    def test_fmt_min(self):
        self.assertEqual(c.fmt_min(0), "0:00")
        self.assertEqual(c.fmt_min(65), "1:05")
        self.assertEqual(c.fmt_min(3600), "1h 00m")
        self.assertEqual(c.fmt_min(-5), "0:00")

    def test_safe_name(self):
        self.assertEqual(c.safe_name(" my part v2! "), "MYPARTV2")
        self.assertEqual(c.safe_name("a" * 40), "A" * 24)
        self.assertEqual(c.safe_name("Ünïcode_ok-1"), "NCODE_OK-1")
        self.assertEqual(c.safe_name("!!!", "MODEL"), "MODEL")
        self.assertEqual(c.name_from_model(r"C:\x\c3 case lid.stl"), "C3CASELID")

    def test_reserved(self):
        self.assertTrue(c.is_reserved_name("COM1"))
        self.assertTrue(c.is_reserved_name("nul"))
        self.assertFalse(c.is_reserved_name("COM1_CASE"))

    def test_board_text(self):
        from s3g_link import BOARD_FLAGS
        self.assertEqual(c.board_text(0, BOARD_FLAGS), ("Board: idle", False))
        self.assertEqual(c.board_text(0x40, BOARD_FLAGS), ("Board: HEAT_SHUTDOWN", True))

    def test_file_info(self):
        lines = c.file_info_lines("X.x3g", st(bed=60, t1_change=True), "RESULT        : OK")
        self.assertIn("Bed: 60°C", lines[2])
        self.assertTrue(any("T1" in ln for ln in lines))


class FitResult(unittest.TestCase):
    def test_ok(self):
        r = c.parse_fit_result("CHECK OK Fits\nRESULT: OK - all good\nREPORT: C:\\r.html", "")
        self.assertEqual(r["verdict"], "OK")
        self.assertEqual(r["report"], "C:\\r.html")
        self.assertEqual(r["lines"][-1], ("RESULT: OK - all good", "ok"))

    def test_warn_lists_issues(self):
        r = c.parse_fit_result("CHECK WARN Thin walls: 3 spots\nRESULT: WARN - 1 thing", "")
        self.assertEqual(r["verdict"], "WARN")
        self.assertIn("Thin walls", r["text"])

    def test_crash(self):
        r = c.parse_fit_result("", "Traceback...\nValueError: bad mesh")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("bad mesh", r["text"])

    def test_empty(self):
        self.assertEqual(c.parse_fit_result(None, None)["verdict"], "FAIL")


class Generate(unittest.TestCase):
    VASE = c.OBJECTS["Twisted flower vase"]
    MODEL = c.OBJECTS["📦 Your 3D model (STL / 3MF / OBJ)"]

    def test_defaults(self):
        args, name, et, em = c.generate_args(self.VASE, {}, "left", "my vase", "", "OUT", True)
        self.assertEqual(name, "MYVASE")
        self.assertEqual(args[:4], ["--out", "OUT", "--name", "MYVASE"])
        self.assertIn("--height", args)
        self.assertEqual(args[args.index("--z-offset") + 1], "-0.08")

    def test_clamped(self):
        args, *_ = c.generate_args(self.VASE, {"height": "999", "temp": "100"}, "left", "V", "", "O", True)
        self.assertEqual(args[args.index("--height") + 1], "60")
        self.assertEqual(args[args.index("--temp") + 1], "180")

    def test_bad_number(self):
        self.assertEqual(c.generate_args(self.VASE, {"height": "abc"}, "left", "V", "", "O", True)[2], "Settings")

    def test_empty_name(self):
        self.assertEqual(c.generate_args(self.VASE, {}, "left", "  ", "", "O", True)[2], "File name")

    def test_model_needs_file_and_slicer(self):
        self.assertEqual(c.generate_args(self.MODEL, {}, "left", "M", "nope.stl", "O", True)[2], "3D model")
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as fh:
            path = fh.name
        try:
            self.assertEqual(c.generate_args(self.MODEL, {}, "left", "M", path, "O", False)[2], "Slicer engine missing")
            args, *_ = c.generate_args(self.MODEL, {}, "right", "M", '"%s"' % path, "O", True)
            self.assertEqual(args[args.index("--model") + 1], path)
            self.assertEqual(args[-2:], ["--only", "right"])
        finally:
            os.remove(path)

    def test_fixed_name_object(self):
        demo = c.OBJECTS["Air demo (left, bed not used)"]
        args, name, *_ = c.generate_args(demo, {}, "left", "ignored", "", "O", True)
        self.assertEqual(name, "DEMO_LEFT")
        self.assertNotIn("--name", args)

    def test_every_object_builds(self):
        for title, obj in c.OBJECTS.items():
            if obj.get("model"):
                continue
            args, name, et, em = c.generate_args(obj, {}, "left", "TEST", "", "O", True)
            self.assertIsNone(et, title)


class Settings(unittest.TestCase):
    def test_roundtrip_and_atomic(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(d4_paths, "SETTINGS", os.path.join(d, "s.json")):
                self.assertEqual(c.load_settings(), {})
                c.save_settings(theme="Dark")
                c.save_settings(ui={"tab": "print"})
                self.assertEqual(c.load_settings(), {"theme": "Dark", "ui": {"tab": "print"}})
                self.assertFalse(os.path.exists(os.path.join(d, "s.json.tmp")))

    def test_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            for junk in ("{not json", "[1, 2]", ""):
                with open(p, "w") as fh:
                    fh.write(junk)
                with mock.patch.object(d4_paths, "SETTINGS", p):
                    self.assertEqual(c.load_settings(), {}, junk)

    def test_resolve_theme(self):
        self.assertEqual(c.resolve_theme("Light"), "light")
        self.assertEqual(c.resolve_theme("Dark"), "dark")
        with mock.patch.object(c, "windows_uses_light_theme", return_value=True):
            self.assertEqual(c.resolve_theme("System"), "light")
        with mock.patch.object(c, "windows_uses_light_theme", return_value=False):
            self.assertEqual(c.resolve_theme("System"), "dark")
            self.assertEqual(c.resolve_theme("garbage"), "dark")


if __name__ == "__main__":
    unittest.main()
