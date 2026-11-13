"""
Stream an .x3g file to a Sailfish / MakerBot printer over USB (direct print).

Usage:  python tools/stream_x3g.py output/RL_TEST.x3g --port COM30

Emergency stop: create a file named STOP next to this script
(tools/STOP) - the streamer sends ABORT (stops motion, heaters off).
Cancelling the print on the printer LCD also ends the stream.

Live bed temperature: write a number into a file named BED next to this script
(tools/BED, e.g. "55") - the streamer sets the bed to it during the print (0..70 C) and
deletes the file. The bed watchdog keeps checking against the new target.

Pause / resume: create tools/PAUSE (or pause on the LCD) and tools/RESUME. While the printer is
paused the bed "not heating" check waits (the firmware may switch heaters off during a pause);
after a resume the bed gets 5 minutes to reheat. Open sensor / over-temperature / jumping
readings are checked all the time.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import os
import struct
import sys
import time

import serial

FIXED = {131: 7, 132: 7, 133: 4, 134: 1, 135: 5, 137: 1, 140: 20, 141: 5,
         144: 1, 150: 2, 154: 1, 155: 31}
STOP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "STOP")
BED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BED")
NOZZLE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NOZZLE")
NOZZLE_MIN_C, NOZZLE_MAX_C = 180, 240
PAUSE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PAUSE")
RESUME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "RESUME")
PAUSED_STATES = (3, 5)                          # paused / sleeping (LCD pause, or ours)
BED_MAX_C = 70

OK, BUSY, CRC, CANCEL = 0x81, 0x82, 0x83, 0x89


class Cancelled(Exception):
    """The print was cancelled on the printer's LCD."""


class BedGuard:
    """Heated-bed watchdog (the bed sensor on this printer has had loose-wire faults).
    check() returns a reason to ABORT, or None."""
    JUMP, OVER, MAX_C, STALL_S = 8, 12, 80, 120

    def __init__(self):
        self.prev, self.hist = None, []

    def check(self, bed, target, stall=True):
        """stall=False: skip the 'not heating' test (paused / reheating after a resume)."""
        now = time.time()
        if bed is None or not target:
            self.prev, self.hist = None, []
            return None
        reason = None
        if bed < 5:
            reason = "bed reads %d C - sensor wire open?" % bed
        elif bed > min(self.MAX_C, target + self.OVER):
            reason = "bed %d C is far above its target %d C" % (bed, target)
        elif self.prev is not None and abs(bed - self.prev) > self.JUMP:
            reason = "bed reading jumped %d -> %d C - loose sensor wire?" % (self.prev, bed)
        else:
            self.hist.append((now, bed))
            self.hist = [h for h in self.hist if now - h[0] <= self.STALL_S + 10]
            old = [v for t, v in self.hist if t <= now - self.STALL_S]
            if stall and bed < target - 5 and old and bed - old[-1] < 1:
                reason = "bed stuck at %d C for %d s while heating to %d C" % (bed, self.STALL_S, target)
        self.prev = bed
        return reason


def live_bed(link):
    """Apply a bed temperature written into tools/BED (then delete the file)."""
    if not os.path.exists(BED_FILE):
        return
    try:
        with open(BED_FILE, encoding="utf-8") as fh:
            txt = fh.read().strip()
        os.remove(BED_FILE)
        c = int(float(txt))
    except (OSError, ValueError):
        log("BED file ignored (write just a number, e.g. 55)")
        return
    if not 0 <= c <= BED_MAX_C:
        log("BED %s C refused - allowed 0..%d C" % (txt, BED_MAX_C))
        return
    for _ in range(50):                             # the printer queue may be full for a moment
        r = link.send(struct.pack("<BBBBh", 136, 0, 31, 2, c))
        if r[0] == OK:
            log("live bed change -> target %d C (runs after the moves already queued)" % c)
            return
        if r[0] == CANCEL:
            raise Cancelled()
        time.sleep(0.1)
    log("BED change not accepted by the printer - try again")


REHEAT_GRACE_S = 300                            # after a resume: no "stuck" alarm while it reheats


def watch(link, guard, bed, bed_t, ps):
    """Live controls + bed watchdog, pause-aware. Returns a reason to ABORT, or None.
    While the printer is paused (LCD or PAUSE file) its firmware may switch heaters off, so the
    'bed not heating' check waits; after a resume it gives the bed time to reheat. The hard
    limits (open sensor, over-temperature, jumping reading) are always checked."""
    st = link.build_state()
    live_pause(link, st)
    live_bed(link)
    live_nozzle(link)
    if st in PAUSED_STATES:
        if not ps.get("paused"):
            log("printer PAUSED - bed 'not heating' check on hold until it resumes")
            ps["paused"] = True
        guard.prev, guard.hist = None, []
        return guard.check(bed, bed_t, stall=False)
    if ps.get("paused"):
        log("printer RESUMED - bed check restarts, %d s allowed to reheat" % REHEAT_GRACE_S)
        ps["paused"], ps["resumed"] = False, time.time()
        guard.prev, guard.hist = None, []
    return guard.check(bed, bed_t, stall=time.time() - ps.get("resumed", 0) > REHEAT_GRACE_S)


def live_nozzle(link):
    """Apply a nozzle temperature written into tools/NOZZLE ("215", or "right 215") - default left."""
    if not os.path.exists(NOZZLE_FILE):
        return
    try:
        with open(NOZZLE_FILE, encoding="utf-8") as fh:
            words = fh.read().strip().lower().split()
        os.remove(NOZZLE_FILE)
        tool = 0 if words and words[0] == "right" else 1
        c = int(float(words[-1]))
    except (OSError, ValueError, IndexError):
        log("NOZZLE file ignored (write a number, e.g. 215, or 'right 215')")
        return
    if not NOZZLE_MIN_C <= c <= NOZZLE_MAX_C:
        log("NOZZLE %d C refused - allowed %d..%d C while printing" % (c, NOZZLE_MIN_C, NOZZLE_MAX_C))
        return
    for _ in range(50):
        r = link.send(struct.pack("<BBBBh", 136, tool, 3, 2, c))
        if r[0] == OK:
            log("live nozzle change -> %s nozzle %d C (runs after the moves already queued)"
                % ("right" if tool == 0 else "left", c))
            return
        if r[0] == CANCEL:
            raise Cancelled()
        time.sleep(0.1)
    log("NOZZLE change not accepted by the printer - try again")


def live_pause(link, state):
    """tools/PAUSE pauses a running build, tools/RESUME continues a paused one (files deleted)."""
    for f, want, verb in ((PAUSE_FILE, 1, "PAUSE"), (RESUME_FILE, 3, "RESUME")):
        if os.path.exists(f):
            os.remove(f)
            if state == want:
                link.send(bytes([8]))                   # s3g pause/unpause toggle
                log("%s sent to the printer" % verb)
            else:
                log("%s ignored - printer state is %s" % (verb, state))


def crc8(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc >> 1) ^ 0x8C) if crc & 1 else (crc >> 1)
    return crc


def split_commands(data):
    cmds, i = [], 0
    while i < len(data):
        c = data[i]
        if c == 136:
            ln = 4 + data[i + 3]
        elif c == 153:
            ln = data.index(0, i + 5) + 1 - i
        elif c in FIXED:
            ln = 1 + FIXED[c]
        else:
            raise ValueError("unknown command %d at byte %d" % (c, i))
        cmds.append(bytes(data[i:i + ln]))
        i += ln
    return cmds


def log(msg):
    print(time.strftime("%H:%M:%S ") + msg, flush=True)


class Link:
    def __init__(self, port, baud=115200):
        self.sp = serial.Serial(port, baud, timeout=0.5)
        self.z, self.sw = 0.0, "?"                  # last good position reading
        time.sleep(3)
        self.sp.reset_input_buffer()

    def send(self, payload, tries=20):
        pkt = bytes([0xD5, len(payload)]) + payload + bytes([crc8(payload)])
        for _ in range(tries):
            self.sp.write(pkt)
            r = self._read()
            if r is None or r[0] == CRC or r[0] == 0x8C:   # lost / corrupted -> resend
                continue
            return r
        raise IOError("printer not responding")

    def _read(self):
        t0 = time.time()
        while time.time() - t0 < 1.0:
            b = self.sp.read(1)
            if b == b"\xD5":
                n = self.sp.read(1)
                if not n:
                    return None
                body = self.sp.read(n[0] + 1)
                if len(body) == n[0] + 1 and crc8(body[:-1]) == body[-1]:
                    return body[:-1]
                return None
        return None

    def temps(self):
        """Right nozzle, left nozzle, bed, bed target (C; None = no good reading)."""
        out = []
        for t, q in ((0, 2), (1, 2), (0, 30), (0, 33)):
            r = self.send(bytes([10, t, q]))
            if r and r[0] == CANCEL:
                raise Cancelled()
            out.append(struct.unpack("<h", r[1:3])[0] if r and r[0] == OK and len(r) >= 3 else None)
        return out

    def abort(self):
        self.send(bytes([7]))

    def build_state(self):
        """Printer build state (s3g 24): 1 running, 2 finished, 3 PAUSED, 4 cancelled, 5 sleeping;
        None = no good reply."""
        r = self.send(bytes([24]))
        if r and r[0] == CANCEL:
            raise Cancelled()
        return r[1] if r and r[0] == OK and len(r) >= 2 else None

    def heaters_off(self):
        """Both nozzles and the bed to 0 C (sent after an abort, so they run at once)."""
        for pkt in (struct.pack("<BBBBh", 136, 0, 3, 2, 0), struct.pack("<BBBBh", 136, 1, 3, 2, 0),
                    struct.pack("<BBBBh", 136, 0, 31, 2, 0)):
            try:
                self.send(pkt)
            except Exception:                       # noqa: BLE001 - best effort
                pass

    def fed(self):
        """Filament fed by right/left extruder since last position reset (mm, + = in)."""
        r = self.send(bytes([21]))
        if r and r[0] == CANCEL:
            raise Cancelled()
        if not r or r[0] != OK or len(r) < 23:
            return None, None                       # garbled / short reply: skip this reading
        p = struct.unpack("<5i", r[1:21])
        self.z = p[2] / 400.0
        e = struct.unpack("<H", r[21:23])[0]
        self.sw = ",".join(n for i, n in enumerate(("Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax"))
                           if e >> i & 1) or "none"
        return -p[3] / 96.275202, -p[4] / 96.275202     # EXTRUDE_SIGN = -1 on this printer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--port", default="COM30")
    a = ap.parse_args()

    cmds = split_commands(open(a.file, "rb").read())
    for f in (STOP_FILE, BED_FILE, NOZZLE_FILE, PAUSE_FILE, RESUME_FILE):   # leftovers from an earlier print
        if os.path.exists(f):
            os.remove(f)
    link = Link(a.port)
    v = link.send(bytes([0, 0x28, 0]))
    log("connected, firmware %d, %d commands to send" % (struct.unpack("<H", v[1:3])[0], len(cmds)))
    r = link.send(bytes([11]))                      # is finished?
    if r[0] == OK and r[1] == 0:
        log("printer is busy (already building?) - aborting stream, nothing sent")
        return 2

    i, last_log, t_start = 0, 0, time.time()
    guard = BedGuard()
    ps = {}                                         # pause state for watch()
    try:
        while i < len(cmds):
            if os.path.exists(STOP_FILE):
                log("STOP file found -> ABORT")
                link.abort()
                link.heaters_off()
                return 1
            r = link.send(cmds[i])
            if r[0] == OK:
                i += 1
            elif r[0] == BUSY:                      # printer buffer full -> wait
                time.sleep(0.05)
            elif r[0] == CANCEL:
                raise Cancelled()
            else:
                log("printer error 0x%02X on command %d -> ABORT" % (r[0], i))
                link.abort()
                link.heaters_off()
                return 1
            if time.time() - last_log > 3:
                t0, t1, bed, bed_t = link.temps()
                fa, fb = link.fed()
                log("sent %d/%d (%d%%)  R %s C  L %s C  bed %s/%s C  | fed R %s mm  L %s mm | Z %.2f  switches %s"
                    % (i, len(cmds), 100 * i // len(cmds), t0, t1, bed, bed_t, _mm(fa), _mm(fb), link.z, link.sw))
                last_log = time.time()
                why = watch(link, guard, bed, bed_t, ps)
                if why:
                    log("BED FAULT: %s -> ABORT, heaters off" % why)
                    link.abort()
                    link.heaters_off()
                    return 1
        log("all commands sent, waiting for printer to finish")
        while True:
            if os.path.exists(STOP_FILE):
                log("STOP file found -> ABORT")
                link.abort()
                link.heaters_off()
                return 1
            r = link.send(bytes([11]))
            if r[0] == OK and r[1] == 1:
                break
            t0, t1, bed, bed_t = link.temps()
            fa, fb = link.fed()
            log("finishing...  R %s C  L %s C  bed %s/%s C  | fed R %s mm  L %s mm | Z %.2f  switches %s"
                % (t0, t1, bed, bed_t, _mm(fa), _mm(fb), link.z, link.sw))
            why = watch(link, guard, bed, bed_t, ps)
            if why:
                log("BED FAULT: %s -> ABORT, heaters off" % why)
                link.abort()
                link.heaters_off()
                return 1
            time.sleep(2)
        log("PRINT COMPLETE in %.1f min" % ((time.time() - t_start) / 60))
        return 0
    except Cancelled:
        log("print cancelled on the printer -> heaters off")
        link.heaters_off()
        return 1
    except KeyboardInterrupt:
        log("interrupted -> ABORT")
        link.abort()
        link.heaters_off()
        return 1
    except Exception as e:                          # noqa: BLE001 - never leave the printer hot
        log("streamer error (%s: %s) -> ABORT, heaters off" % (type(e).__name__, e))
        try:
            link.abort()
        finally:
            link.heaters_off()
        return 1



def _mm(v):
    return "%.1f" % v if v is not None else "?"


if __name__ == "__main__":
    sys.exit(main())
