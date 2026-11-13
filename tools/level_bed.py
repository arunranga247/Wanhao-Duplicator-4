"""
Guided bed levelling (paper test) for the Duplicator 4 over USB.

    python tools/level_bed.py [--port COM30]

Homes (slow Z), then parks the LEFT nozzle at Z 0 over 5 points: 4 corners of the print area
and the centre. At each point slide a sheet of paper under the nozzle and turn the bed knob
nearest to it until the paper drags lightly.

Control files next to this script:
    tools/LEVEL_NEXT   -> go to the next point (round and round)
    tools/LEVEL_DONE   -> lift the nozzle 20 mm, end
    tools/STOP         -> emergency stop
No heaters are switched on.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import os
import sys
import time

from make_dual_sample import Printer
from stream_x3g import BUSY, CANCEL, OK, STOP_FILE, Link, split_commands

HERE = os.path.dirname(os.path.abspath(__file__))
NEXT_FILE, DONE_FILE = os.path.join(HERE, "LEVEL_NEXT"), os.path.join(HERE, "LEVEL_DONE")
POINTS = [("front-left", -55, -45), ("front-right", 55, -45), ("back-right", 55, 45),
          ("back-left", -55, 45), ("centre", 0, 0)]        # left-nozzle coordinates, bed centre = 0,0
LIFT = 3.0


def log(m):
    print(time.strftime("%H:%M:%S ") + m, flush=True)


def run(link, p, start):
    """Send p's commands from index `start`; return the new end index."""
    cmds = split_commands(bytes(p.x3g))
    i = start
    while i < len(cmds):
        if os.path.exists(STOP_FILE):
            raise KeyboardInterrupt
        r = link.send(cmds[i])
        if r[0] == OK:
            i += 1
        elif r[0] == BUSY:
            time.sleep(0.05)
        elif r[0] == CANCEL:
            raise KeyboardInterrupt
        else:
            raise IOError("printer error 0x%02X" % r[0])
    return i


def wait_idle(link):
    while True:
        r = link.send(bytes([11]))
        if r[0] == OK and r[1] == 1:
            return
        if os.path.exists(STOP_FILE):
            raise KeyboardInterrupt
        time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM30")
    a = ap.parse_args()
    for f in (NEXT_FILE, DONE_FILE, STOP_FILE):
        if os.path.exists(f):
            os.remove(f)
    link = Link(a.port)
    if not (lambda r: r[0] == OK and r[1] == 1)(link.send(bytes([11]))):
        log("printer is busy - nothing sent")
        return 2
    p = Printer()
    p.set_temp(0, 0)
    p.set_temp(1, 0)
    p.home(z_fast=5.0, z_timeout=40)
    p.move(z=LIFT, f=5.0)
    p.change_tool(1, shift=False)                       # left nozzle = the one that prints
    sent = 0
    k = 0
    try:
        log("homing (slow Z, ~40 s) ...")
        while True:
            name, x, y = POINTS[k % len(POINTS)]
            p.move(z=LIFT, f=5.0)
            p.move(x, y, f=60.0)
            p.move(z=0.0, f=3.0)
            sent = run(link, p, sent)
            wait_idle(link)
            log("POINT %d/%d %s: nozzle at Z 0 - paper test now (round %d)"
                % (k % len(POINTS) + 1, len(POINTS), name, k // len(POINTS) + 1))
            while not (os.path.exists(NEXT_FILE) or os.path.exists(DONE_FILE)):
                if os.path.exists(STOP_FILE):
                    raise KeyboardInterrupt
                time.sleep(0.3)
            if os.path.exists(DONE_FILE):
                os.remove(DONE_FILE)
                break
            os.remove(NEXT_FILE)
            k += 1
        p.move(z=20.0, f=5.0)
        sent = run(link, p, sent)
        wait_idle(link)
        log("LEVELLING DONE - nozzle lifted 20 mm")
        return 0
    except KeyboardInterrupt:
        log("STOP -> ABORT")
        link.abort()
        link.heaters_off()
        return 1
    except Exception as e:                              # noqa: BLE001
        log("error (%s: %s) -> ABORT" % (type(e).__name__, e))
        link.abort()
        link.heaters_off()
        return 1


if __name__ == "__main__":
    sys.exit(main())
