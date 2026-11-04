"""Independent decoder / sanity checker for x3g files (Replicator 1 Dual / Duplicator 4)."""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import struct
import sys

from s3g_link import EXTRUDE_SIGN   # -1: negative A/B steps push filament in

SPM = (94.139704, 94.139704, 400.0, 96.275202, 96.275202)
MAX_MM_S = (150.0, 150.0, 19.0, 100.0, 100.0)   # conservative per-axis limits
LEFT_NOZZLE_DX = 33.0                           # left nozzle sits 33 mm left of the head (right nozzle)
FIXED = {131: 7, 132: 7, 133: 4, 134: 1, 135: 5, 137: 1, 140: 20, 141: 5,
         144: 1, 150: 2, 154: 1, 155: 31}


def main(path):
    data = open(path, "rb").read()
    i, n = 0, 0
    pos = None
    tool = 0
    temps = {}
    errors = []
    bounds = {0: [1e9, -1e9, 1e9, -1e9], 1: [1e9, -1e9, 1e9, -1e9]}
    zmin_extrude = 1e9
    zmax = -1e9
    counts = {}
    homed = xyhomed = zhomed = zmoved = False
    fil = [0.0, 0.0]
    while i < len(data):
        c = data[i]
        i += 1
        n += 1
        counts[c] = counts.get(c, 0) + 1
        if c == 136:
            t, act, ln = data[i], data[i + 1], data[i + 2]
            payload = data[i + 3:i + 3 + ln]
            i += 3 + ln
            if act in (3, 31):
                v = struct.unpack("<h", payload)[0]
                temps[("bed" if act == 31 else "T%d" % t)] = v
                if act == 3 and v > 240: errors.append("nozzle temp %d too high" % v)
                if act == 31 and v != 0: errors.append("bed heater turned ON (%d)" % v)
            continue
        if c == 153:
            j = data.index(0, i + 4)
            print("build start: '%s' (%d cmds declared)"
                  % (data[i + 4:j].decode(), struct.unpack_from("<I", data, i)[0]))
            i = j + 1
            continue
        if c not in FIXED:
            errors.append("unknown command %d at byte %d" % (c, i - 1))
            break
        body = data[i:i + FIXED[c]]
        i += FIXED[c]
        if c == 134:
            tool = body[0]
            if tool != 0:
                errors.append("cmd %d: firmware tool change to T%d - this printer's stored T1 "
                              "offset is bogus (~228 mm), head would be thrown sideways" % (n, tool))
        elif c == 131 and body[0] & 0x04:
            zhomed = True
        elif c == 132 and body[0] & 0x03 == 0x03:
            xyhomed = True
        elif c == 140:
            pos = list(struct.unpack("<5i", body))
            homed = homed or xyhomed           # position defined after an X/Y home
        elif c == 144:
            pos = [14309 if body[0] & 1 else pos[0], 7060 if body[0] & 2 else pos[1],
                   0 if body[0] & 4 else pos[2], 0, 0] if pos else [14309, 7060, 0, 0, 0]
            homed = True
        elif c == 155:
            tgt = list(struct.unpack("<5i", body[:20]))
            rate, rel, dist, f64 = struct.unpack("<IBfH", body[20:])
            if pos is None:
                errors.append("move before position known")
                break
            tgt = [pos[k] + tgt[k] if rel >> k & 1 else tgt[k] for k in range(5)]   # relative axes
            d = [tgt[k] - pos[k] for k in range(5)]
            sd = [d[0], d[1], d[2], d[3] * EXTRUDE_SIGN, d[4] * EXTRUDE_SIGN]   # + = filament fed in
            longest = max(abs(v) for v in d)
            t = longest / rate
            for k in range(5):
                v = abs(d[k]) / SPM[k] / t
                if v > MAX_MM_S[k] * 1.01:
                    errors.append("cmd %d axis %d speed %.1f mm/s" % (n, k, v))
            mm = [tgt[k] / SPM[k] for k in range(5)]
            ext = (sd[3] > 0 or sd[4] > 0) and (d[0] or d[1])
            if homed:
                if ext:
                    if sd[3] > 0 and sd[4] > 0:
                        errors.append("cmd %d: both extruders push at once" % n)
                    et = 0 if sd[3] > 0 else 1                  # which extruder is printing
                    nx = mm[0] - (LEFT_NOZZLE_DX if et == 1 else 0.0)   # real nozzle X
                    b = bounds[et]
                    b[0] = min(b[0], nx); b[1] = max(b[1], nx)
                    b[2] = min(b[2], mm[1]); b[3] = max(b[3], mm[1])
                    zmin_extrude = min(zmin_extrude, mm[2])
                    if mm[2] < 0.15: errors.append("cmd %d extrudes at Z %.2f - nozzle would dig into the bed" % (n, mm[2]))
                if abs(mm[0]) > 112 + 40 or abs(mm[1]) > 75.1:
                    errors.append("cmd %d out of bed: X%.1f Y%.1f" % (n, mm[0], mm[1]))
                # Z=0 is the nozzle touching the bed (homed, or set by paper test):
                # the bed must never go above it, whether Z was homed or not.
                if mm[2] < 0:
                    errors.append("cmd %d Z below 0 (%.2f) - bed would push into the nozzle" % (n, mm[2]))
                if d[2]:
                    zmoved = True
                zmax = max(zmax, mm[2])
            if sd[3] > 0 or sd[4] > 0:
                fil[0 if sd[3] > 0 else 1] += (sd[3] / SPM[3]) if sd[3] > 0 else (sd[4] / SPM[4])
            pos = tgt
    print("commands      : %d, bytes parsed %d/%d" % (n, i, len(data)))
    print("command types :", dict(sorted(counts.items())))
    for t in (0, 1):
        b = bounds[t]
        if b[0] > b[1]:
            print("%s extruder: no extrusion" % ("RIGHT" if t == 0 else "LEFT "))
            continue
        print("%s extruder nozzle prints in X %.1f..%.1f  Y %.1f..%.1f"
              % ("RIGHT" if t == 0 else "LEFT ", b[0], b[1], b[2], b[3]))
    if zhomed:
        print("Z homing      : yes - lowest extruding Z %.2f mm, highest Z %.1f mm" % (zmin_extrude, zmax))
    elif zmoved:
        print("Z homing      : NO - Z0 = bed height at start (paper test); bed only moves DOWN, max Z %.1f" % zmax)
        if zmin_extrude < 1e8:
            print("                lowest extruding Z %.2f mm" % zmin_extrude)
    else:
        print("Z homing      : NO - bed is never moved")
    print("final temps   :", temps)
    print("filament pushed (incl. re-push after retract): right %.0f mm, left %.0f mm" % tuple(fil))
    print("RESULT        :", "OK" if not errors else "PROBLEMS:\n  " + "\n  ".join(errors[:20]))


if __name__ == "__main__":
    main(sys.argv[1])
