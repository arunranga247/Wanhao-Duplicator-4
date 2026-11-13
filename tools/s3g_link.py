"""
s3g / x3g protocol link for MakerBot-type printers running Sailfish
(Wanhao Duplicator 4 / Replicator 1 Dual).

Only the host thread that owns a Link may call it (pyserial is not thread-safe).
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import struct
import time

import serial
from serial.tools import list_ports

VID_MAKERBOT = 0x23C1

# Steps per mm read from this printer's EEPROM (Sailfish 7.7)
SPM = (94.139704, 94.139704, 400.0, 96.275202, 96.275202)   # X Y Z A B
HOME_STEPS = (14309, 7060, 0, 0, 0)                          # EEPROM home offsets

# Extruder direction on this printer: NEGATIVE A/B steps push filament INTO the nozzle.
# Verified 2026-11-04: a +10 mm move on B (left) pulled the filament UP and out.
# Everything that builds extruder moves multiplies filament mm by this sign.
EXTRUDE_SIGN = -1

OK, BUSY, CANCELLED = 0x81, 0x82, 0x89
RESPONSES = {
    0x80: "generic error", 0x81: "ok", 0x82: "buffer full", 0x83: "CRC mismatch",
    0x84: "query too big", 0x85: "command not supported", 0x87: "downstream timeout",
    0x88: "tool lock timeout", 0x89: "build cancelled", 0x8A: "printer is building",
    0x8B: "printer overheated", 0x8C: "packet timeout",
}
ENDSTOP_NAMES = ("Xmin", "Xmax", "Ymin", "Ymax", "Zmin", "Zmax")
BOARD_FLAGS = ((0x01, "PREHEAT"), (0x02, "MANUAL"), (0x04, "ONBOARD_SCRIPT"),
               (0x08, "ONBOARD_PROCESS"), (0x10, "WAIT_FOR_BUTTON"),
               (0x20, "CANCELLING"), (0x40, "HEAT_SHUTDOWN"), (0x80, "POWER_ERROR"))

# x3g payload lengths (bytes after the command byte) for fixed-size commands
_FIXED = {131: 7, 132: 7, 133: 4, 134: 1, 135: 5, 137: 1, 140: 20, 141: 5,
          144: 1, 150: 2, 154: 1, 155: 31}


class PrinterGone(Exception):
    """USB link lost (printer reset, powered off, or cable unplugged)."""


class NoResponse(Exception):
    """Printer did not answer a packet after several retries."""


def crc8(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc >> 1) ^ 0x8C) if crc & 1 else (crc >> 1)
    return crc


def find_ports():
    """Return [(device, label, is_printer)], printers first."""
    out = []
    for p in list_ports.comports():
        is_bot = p.vid == VID_MAKERBOT
        label = "%s  %s" % (p.device, "(Duplicator / MakerBot)" if is_bot else (p.description or ""))
        out.append((p.device, label, is_bot))
    out.sort(key=lambda t: not t[2])
    return out


def split_x3g(data):
    """Split an .x3g byte stream into individual command payloads."""
    cmds, i = [], 0
    while i < len(data):
        c = data[i]
        if c == 136:
            ln = 4 + data[i + 3]
        elif c == 153:
            ln = data.index(0, i + 5) + 1 - i
        elif c in _FIXED:
            ln = 1 + _FIXED[c]
        else:
            raise ValueError("unknown x3g command %d at byte %d" % (c, i))
        cmds.append(bytes(data[i:i + ln]))
        i += ln
    return cmds


class Link:
    def __init__(self, port, baud=115200, settle_s=2.0):
        try:
            self.sp = serial.Serial(port, baud, timeout=0.3, write_timeout=1.0)
        except serial.SerialException as e:
            raise PrinterGone(str(e))
        time.sleep(settle_s)
        self.sp.reset_input_buffer()
        self.port = port

    def close(self):
        try:
            self.sp.close()
        except Exception:
            pass

    # ---- packet layer ----------------------------------------------------
    def send(self, payload, tries=8):
        payload = bytes(payload)
        pkt = bytes([0xD5, len(payload)]) + payload + bytes([crc8(payload)])
        try:
            for _ in range(tries):
                self.sp.reset_input_buffer()
                self.sp.write(pkt)
                r = self._read()
                if r is None or r[0] in (0x83, 0x8C):      # lost/corrupt -> resend
                    continue
                return r
        except (serial.SerialException, OSError) as e:
            raise PrinterGone(str(e))
        raise NoResponse("no response to command %d" % payload[0])

    def _read(self):
        t0 = time.time()
        while time.time() - t0 < 0.8:
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

    def send_buffered(self, payload, abort_check=None, timeout_s=15.0):
        """Send a buffered (motion/heater) command, waiting while the printer buffer is full."""
        t0 = time.time()
        while True:
            if abort_check and abort_check():
                return None
            r = self.send(payload)
            if r[0] != BUSY:
                if r[0] != OK:
                    raise RuntimeError("printer refused command %d: %s"
                                       % (payload[0], RESPONSES.get(r[0], hex(r[0]))))
                return r
            if time.time() - t0 > timeout_s:
                raise RuntimeError("printer buffer stayed full for %.0f s" % timeout_s)
            time.sleep(0.05)

    # ---- queries -----------------------------------------------------------
    def version(self):
        r = self.send(bytes([0, 0x28, 0]))
        return struct.unpack("<H", r[1:3])[0]

    def variant(self):
        r = self.send(bytes([27, 0x28, 0]))
        if r[0] == OK and len(r) >= 6:
            return {0x01: "MakerBot", 0x80: "Sailfish"}.get(r[5], "0x%02X" % r[5])
        return "unknown"

    def _tool_query16(self, tool, q):
        r = self.send(bytes([10, tool, q]))
        return struct.unpack("<h", r[1:3])[0] if r[0] == OK else None

    def temps(self):
        return {
            "r": self._tool_query16(0, 2), "r_t": self._tool_query16(0, 32),
            "l": self._tool_query16(1, 2), "l_t": self._tool_query16(1, 32),
            "bed": self._tool_query16(0, 30), "bed_t": self._tool_query16(0, 33),
        }

    def position(self):
        """Return (position_mm[5], endstop_bits)."""
        r = self.send(bytes([21]))
        steps = struct.unpack("<5i", r[1:21])
        mm = [steps[i] / SPM[i] * (EXTRUDE_SIGN if i >= 3 else 1) for i in range(5)]   # A/B: + = fed in
        return mm, struct.unpack("<H", r[21:23])[0], steps

    def board_status(self):
        r = self.send(bytes([23]))
        return r[1] if r[0] == OK else None

    def build_state(self):
        """s3g 24: 0 none, 1 running, 2 finished, 3 PAUSED, 4 cancelled, 5 sleeping (None = no reply)."""
        r = self.send(bytes([24]))
        return r[1] if r[0] == OK and len(r) >= 2 else None

    def is_finished(self):
        r = self.send(bytes([11]))
        return r[0] == OK and r[1] == 1

    # ---- actions (buffered on the printer) --------------------------------
    def set_temp(self, tool, c, **kw):
        self.send_buffered(struct.pack("<BBBBh", 136, tool, 3, 2, int(c)), **kw)

    def set_bed(self, c, **kw):
        self.send_buffered(struct.pack("<BBBBh", 136, 0, 31, 2, int(c)), **kw)

    def wait_tool(self, tool, timeout_s=600, **kw):
        """Queue 'wait until nozzle reaches its target' (printer holds later commands)."""
        self.send_buffered(struct.pack("<BBHH", 135, tool, 100, timeout_s), **kw)

    def heaters_off(self):
        for t in (0, 1):
            self.set_temp(t, 0)
        self.set_bed(0)

    def home_xy(self, timeout_s=20, **kw):
        us = round(1e6 / (2500 / 60 * SPM[0]))
        self.send_buffered(struct.pack("<BBIH", 132, 0x03, us, timeout_s), **kw)

    def home_z(self, timeout_s=20, **kw):
        """Replicator 1 Z sequence: fast to Z-min (bed up), back off 5 mm, slow re-home, recall offsets."""
        us_fast = round(1e6 / (1100 / 60 * SPM[2]))
        us_slow = round(1e6 / (100 / 60 * SPM[2]))
        self.send_buffered(struct.pack("<BBIH", 131, 0x04, us_fast, timeout_s), **kw)
        self.jog(2, +5.0, 1100 / 60, **kw)
        self.send_buffered(struct.pack("<BBIH", 131, 0x04, us_slow, 10), **kw)
        self.send_buffered(struct.pack("<BB", 144, 0x1F), **kw)

    def jog(self, axis, mm, speed_mm_s, **kw):
        """Relative move of one axis (0..4 = X Y Z A B). For A/B, +mm = push filament in."""
        d = [0] * 5
        d[axis] = round(mm * SPM[axis] * (EXTRUDE_SIGN if axis >= 3 else 1))
        if d[axis] == 0:
            return
        t = abs(mm) / speed_mm_s
        rate = max(1, round(abs(d[axis]) / t))
        self.send_buffered(struct.pack("<B5iIBfH", 155, *d, rate, 0x1F, abs(mm),
                                       round(speed_mm_s * 64)), **kw)

    def change_tool(self, tool, **kw):
        self.send_buffered(struct.pack("<BB", 134, tool), **kw)

    def motors_off(self, **kw):
        self.send_buffered(struct.pack("<BB", 137, 0x1F), **kw)

    def pause_toggle(self):
        return self.send(bytes([8]))

    def abort(self):
        """Emergency stop: halt motion and clear the printer's command buffer."""
        return self.send(bytes([7]))


def x3g_stats(cmds):
    """Quick facts about a split .x3g job (for the GUI file library / ETA).

    Returns dict: time_s (motion time), cum (motion seconds up to each command),
    fil (mm pushed by right/left extruder), zmax, z_home (None/'slow'/'fast'),
    temps {tool: max C}, bed (max bed C), t1_change (firmware T1 used)."""
    t, cum = 0.0, []
    fil = [0.0, 0.0]
    pos = [0, 0, 0, 0, 0]
    zmax, z_home, temps, bed, t1 = 0.0, None, {}, 0, False
    zprint = 0.0
    for c in cmds:
        k = c[0]
        if k == 155:
            tgt = struct.unpack("<5i", c[1:21])
            rel = c[25]
            dist = struct.unpack("<f", c[26:30])[0]
            f64 = struct.unpack("<H", c[30:32])[0]
            if f64:
                t += dist / (f64 / 64.0)
            new = [pos[i] + tgt[i] if rel >> i & 1 else tgt[i] for i in range(5)]
            pushing = False
            for e in (3, 4):
                d = (new[e] - pos[e]) * EXTRUDE_SIGN / SPM[e]
                if d > 0:
                    fil[e - 3] += d
                    pushing = True
            zmax = max(zmax, new[2] / SPM[2])
            if pushing and (new[0] != pos[0] or new[1] != pos[1]):
                zprint = max(zprint, new[2] / SPM[2])     # height of the printed object
            pos = new
        elif k == 140:
            pos = list(struct.unpack("<5i", c[1:21]))
        elif k == 144:
            pos = [HOME_STEPS[i] if c[1] >> i & 1 else pos[i] for i in range(5)]
        elif k == 131 and c[1] & 0x04:
            us = struct.unpack("<I", c[2:6])[0]
            speed = 1e6 / us / SPM[2]
            if speed > 6:
                z_home = "fast"
            elif z_home is None:
                z_home = "slow"
        elif k == 136 and c[2] == 3:
            temps[c[1]] = max(temps.get(c[1], 0), struct.unpack("<h", c[4:6])[0])
        elif k == 136 and c[2] == 31:
            bed = max(bed, struct.unpack("<h", c[4:6])[0])
        elif k == 134 and c[1] != 0:
            t1 = True
        cum.append(t)
    return {"time_s": t, "cum": cum, "fil": fil, "zmax": zmax, "zprint": zprint, "z_home": z_home,
            "temps": temps, "bed": bed, "t1_change": t1, "n": len(cmds)}
