"""
Tests for the printer worker's per-print bed choice (no printer needed).

    python -m unittest tools/tests/test_d4_worker.py -v
"""

__author__ = "ARUN"

import os
import queue
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import s3g_link as s3g                    # noqa: E402
from d4_worker import Worker, bed_override, nozzle_override  # noqa: E402

BED60 = struct.pack("<BBBBh", 136, 0, 31, 2, 60)
BED0 = struct.pack("<BBBBh", 136, 0, 31, 2, 0)
WAIT_BED = struct.pack("<BBHH", 141, 0, 100, 600)
NOZZLE = struct.pack("<BBBBh", 136, 1, 3, 2, 215)
MOVE = bytes([155]) + bytes(31)


class Override(unittest.TestCase):
    def test_as_in_file_changes_nothing(self):
        for c in (BED60, WAIT_BED, NOZZLE, MOVE, BED0):
            self.assertEqual(bed_override(c, None), (c, False))

    def test_bed_value_replaces_target_and_skips_wait(self):
        self.assertEqual(bed_override(BED60, 0), (BED0, False))
        self.assertEqual(bed_override(BED60, 40), (struct.pack("<BBBBh", 136, 0, 31, 2, 40), False))
        self.assertEqual(bed_override(WAIT_BED, 40), (WAIT_BED, True))

    def test_bed_off_at_the_end_is_never_changed(self):
        self.assertEqual(bed_override(BED0, 40), (BED0, False))
        self.assertEqual(bed_override(BED0, 40, started=True), (BED0, False))

    def test_bed_off_at_the_start_gets_the_chosen_bed(self):     # file made with the bed off
        self.assertEqual(bed_override(BED0, 40, started=False),
                         (struct.pack("<BBBBh", 136, 0, 31, 2, 40), False))
        self.assertEqual(bed_override(BED0, 0, started=False), (BED0, False))     # 0 chosen: stays off
        self.assertEqual(bed_override(BED0, None, started=False), (BED0, False))  # as in file

    def test_other_commands_untouched(self):
        for c in (NOZZLE, MOVE):
            self.assertEqual(bed_override(c, 0), (c, False))


class NozzleOverride(unittest.TestCase):
    def test_printing_temps_change_standby_and_off_stay(self):
        hot_r = struct.pack("<BBBBh", 136, 0, 3, 2, 215)
        hot_l = struct.pack("<BBBBh", 136, 1, 3, 2, 210)
        standby = struct.pack("<BBBBh", 136, 1, 3, 2, 150)
        off = struct.pack("<BBBBh", 136, 0, 3, 2, 0)
        self.assertEqual(nozzle_override(hot_r, 225), struct.pack("<BBBBh", 136, 0, 3, 2, 225))
        self.assertEqual(nozzle_override(hot_l, 200), struct.pack("<BBBBh", 136, 1, 3, 2, 200))
        self.assertEqual(nozzle_override(standby, 225), standby)
        self.assertEqual(nozzle_override(off, 225), off)
        self.assertEqual(nozzle_override(hot_r, None), hot_r)               # as in file
        self.assertEqual(nozzle_override(BED60, 225), BED60)                # the bed is not a nozzle


class FakeLink:
    def __init__(self):
        self.sent = []

    def send(self, c):
        self.sent.append(bytes(c))
        return (s3g.OK,)

    def is_finished(self):
        return True


class Streaming(unittest.TestCase):
    def stream(self, bed):
        w = Worker(queue.Queue())
        w.link = FakeLink()
        w.print_job = {"cmds": [BED60, WAIT_BED, NOZZLE, MOVE, MOVE, BED0], "i": 0, "name": "T",
                       "t0": 0.0, "bed": bed}
        for _ in range(20):
            if w.print_job is None:
                break
            w._stream_step()
        return w.link.sent

    def test_file_as_is(self):
        self.assertEqual(self.stream(None), [BED60, WAIT_BED, NOZZLE, MOVE, MOVE, BED0])

    def test_bed_off_print_starts_at_once(self):
        self.assertEqual(self.stream(0), [BED0, NOZZLE, MOVE, MOVE, BED0])

    def test_bed_off_file_heats_when_a_bed_is_chosen(self):    # the bug: "Bed for this print" ignored
        BED42 = struct.pack("<BBBBh", 136, 0, 31, 2, 42)
        w = Worker(queue.Queue())
        w.link = FakeLink()
        w.print_job = {"cmds": [BED0, NOZZLE, MOVE, MOVE, BED0], "i": 0, "name": "T", "t0": 0.0, "bed": 42}
        for _ in range(20):
            if w.print_job is None:
                break
            w._stream_step()
        self.assertEqual(w.link.sent, [BED42, NOZZLE, MOVE, MOVE, BED0])      # heats at start, OFF at end


class TimerLink(FakeLink):
    def __init__(self):
        super().__init__()
        self.bed_target = 0

    def set_bed(self, c, **kw):
        self.sent.append(("bed", int(c)))
        self.bed_target = int(c)

    def heaters_off(self):
        self.sent.append(("all off",))


class BedTimer(unittest.TestCase):
    def setUp(self):
        self.ev = queue.Queue()
        self.w = Worker(self.ev)
        self.w.link = TimerLink()

    def alarms(self):
        out = []
        while not self.ev.empty():
            e = self.ev.get()
            if e[0] == "alarm":
                out.append(e[1])
        return out

    def test_switches_bed_off_when_time_is_up(self):
        self.w._run_job("bed_timer", (3,))
        t = {"bed": 1, "bed_t": 60}
        self.w._bed_timer(t)                                  # starts counting
        self.assertIsNotNone(self.w.bed_off_at)
        self.w._bed_timer(t)                                  # not yet
        self.assertNotIn(("bed", 0), self.w.link.sent)
        self.w.bed_off_at -= 3 * 60 + 1                       # 3 min later
        self.w._bed_timer(t)
        self.assertIn(("bed", 0), self.w.link.sent)
        self.assertTrue(any("Bed timer" in a for a in self.alarms()))

    def test_print_stays_bed_off_after_timer(self):
        self.w._run_job("bed_timer", (2,))
        self.w.print_job = {"cmds": [], "i": 0, "name": "T", "t0": 0.0, "bed": 60}
        self.w._bed_timer({"bed": 1, "bed_t": 60})
        self.w.bed_off_at = 0.0
        self.w._bed_timer({"bed": 1, "bed_t": 60})
        self.assertEqual(self.w.print_job["bed"], 0)

    def test_watchdog_leaves_bad_bed_to_the_timer(self):
        t = {"r": 25, "r_t": 0, "l": 25, "l_t": 0, "bed": 1, "bed_t": 60}
        self.w._watchdog(t)                                   # no timer: bad sensor -> all heaters off
        self.assertIn(("all off",), self.w.link.sent)
        self.w.link.sent.clear()
        self.w._last_alarm = 0
        self.w._run_job("bed_timer", (3,))
        self.w._watchdog(t)                                   # timer on: heating continues
        self.assertNotIn(("all off",), self.w.link.sent)

    def test_timer_off_does_nothing(self):
        self.w._bed_timer({"bed": 1, "bed_t": 60})
        self.assertIsNone(self.w.bed_off_at)
        self.assertEqual(self.w.link.sent, [])


if __name__ == "__main__":
    unittest.main()
