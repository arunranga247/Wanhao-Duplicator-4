"""
Stream an .x3g file to a Sailfish / MakerBot printer over USB (direct print).

Usage:  python tools/stream_x3g.py output/RL_TEST.x3g --port COM30

Emergency stop: create a file named STOP next to this script
(tools/STOP) - the streamer sends ABORT (stops motion, heaters off).
Cancelling the print on the printer LCD also ends the stream.
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

OK, BUSY, CRC, CANCEL = 0x81, 0x82, 0x83, 0x89


class Cancelled(Exception):
    """The print was cancelled on the printer's LCD."""


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
        out = []
        for t, q in ((0, 2), (1, 2), (0, 30)):
            r = self.send(bytes([10, t, q]))
            if r and r[0] == CANCEL:
                raise Cancelled()
            out.append(struct.unpack("<h", r[1:3])[0] if r and r[0] == OK and len(r) >= 3 else None)
        return out

    def abort(self):
        self.send(bytes([7]))

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
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)
    link = Link(a.port)
    v = link.send(bytes([0, 0x28, 0]))
    log("connected, firmware %d, %d commands to send" % (struct.unpack("<H", v[1:3])[0], len(cmds)))
    r = link.send(bytes([11]))                      # is finished?
    if r[0] == OK and r[1] == 0:
        log("printer is busy (already building?) - aborting stream, nothing sent")
        return 2

    i, last_log, t_start = 0, 0, time.time()
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
                t0, t1, bed = link.temps()
                fa, fb = link.fed()
                log("sent %d/%d (%d%%)  R %s C  L %s C  bed %s C  | fed R %s mm  L %s mm | Z %.2f  switches %s"
                    % (i, len(cmds), 100 * i // len(cmds), t0, t1, bed, _mm(fa), _mm(fb), link.z, link.sw))
                last_log = time.time()
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
            t0, t1, bed = link.temps()
            fa, fb = link.fed()
            log("finishing...  R %s C  L %s C  bed %s C  | fed R %s mm  L %s mm | Z %.2f  switches %s"
                % (t0, t1, bed, _mm(fa), _mm(fb), link.z, link.sw))
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
