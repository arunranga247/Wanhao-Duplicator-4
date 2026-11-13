"""Render a toolpath preview PNG from an .x3g file (top view of the bed + 3D view).

    python tools/render_preview.py output/RL_MINI.x3g [output/DEMO_AIR.x3g ...]
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import math
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFont

from s3g_link import EXTRUDE_SIGN, HOME_STEPS, SPM, split_x3g

BED = (-112.5, 112.5, -72.5, 72.5)          # X/Y bed limits in mm (225 x 145)
TOOL_COL = {0: (235, 87, 87), 1: (66, 153, 225), 2: (200, 200, 200)}   # 2 = head travel
BG, PANEL, GRID, FG, DIM = (24, 27, 33), (34, 38, 46), (52, 58, 68), (230, 230, 230), (140, 148, 160)


def font(size, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def decode(path):
    """Return (segments, info). segment = (x0,y0,z0,x1,y1,z1,tool,extruding)."""
    cmds = split_x3g(open(path, "rb").read())
    pos, tool, segs = None, 0, []
    last_et = None
    info = {"name": os.path.basename(path), "temps": {}, "zhome": False, "fil": [0.0, 0.0], "n": len(cmds)}
    for c in cmds:
        k = c[0]
        if k == 140:
            pos = list(struct.unpack("<5i", c[1:21]))
        elif k == 144:
            pos = pos or [0] * 5
            for i in range(5):
                if c[1] >> i & 1:
                    pos[i] = HOME_STEPS[i]
        elif k == 131 and c[1] & 0x04:
            us = struct.unpack("<I", c[2:6])[0]
            info["zspeed"] = max(info.get("zspeed", 0), 1e6 / us / SPM[2])   # fastest Z home, mm/s
            info["zhome"] = True
        elif k == 134:
            tool = c[1]
        elif k == 136 and c[2] == 3:
            info["temps"]["T%d" % c[1]] = max(info["temps"].get("T%d" % c[1], 0), struct.unpack("<h", c[4:6])[0])
        elif k == 136 and c[2] == 31:
            info["bed"] = max(info.get("bed", 0), struct.unpack("<h", c[4:6])[0])
        elif k == 155:
            tgt = list(struct.unpack("<5i", c[1:21]))
            rel = c[25]
            if pos is None:
                pos = [0] * 5
            new = [pos[i] + tgt[i] if rel >> i & 1 else tgt[i] for i in range(5)]
            sg = (1, 1, 1, EXTRUDE_SIGN, EXTRUDE_SIGN)                 # A/B: + = fed in
            mm0 = [pos[i] / SPM[i] * sg[i] for i in range(5)]
            mm1 = [new[i] / SPM[i] * sg[i] for i in range(5)]
            de = (mm1[3] - mm0[3]) + (mm1[4] - mm0[4])
            # net filament used = furthest position each extruder reached (ignores retract/unretract)
            info["fil"][0] = max(info["fil"][0], mm1[3])
            info["fil"][1] = max(info["fil"][1], mm1[4])
            if mm1[2] != mm0[2]:
                info["zmoved"] = True
            if (mm0[0], mm0[1], mm0[2]) != (mm1[0], mm1[1], mm1[2]):
                if de > 0:
                    # which extruder pushes decides the colour; the LEFT nozzle sits
                    # 33 mm left of the head (software nozzle offset, no firmware T1)
                    et = 0 if mm1[3] > mm0[3] else 1
                    last_et = et
                    dx = 33.0 if et == 1 else 0.0
                    segs.append((mm0[0] - dx, mm0[1], mm0[2], mm1[0] - dx, mm1[1], mm1[2], et, True))
                else:
                    # travel: draw it where the active nozzle goes, not the head
                    dx = 33.0 if last_et == 1 else 0.0
                    segs.append((mm0[0] - dx, mm0[1], mm0[2], mm1[0] - dx, mm1[1], mm1[2], 2, False))
            pos = new
    return segs, info


def render(path, out=None):
    segs, info = decode(path)
    dry = not any(s[7] for s in segs)
    W, H = 1600, 900
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_title, f_h, f_txt, f_small = font(30, True), font(18, True), font(16), font(13)

    d.text((30, 20), "%s  —  toolpath preview" % info["name"], fill=FG, font=f_title)
    sub = ("DRY RUN: no filament pushed, bed does not move  (white = head path)" if dry else
           "Red = right extruder, blue = left extruder, grey = head travel")
    d.text((30, 62), sub, fill=(255, 196, 0) if dry else DIM, font=f_txt)

    # ---- panel 1: top view of the whole bed ---------------------------------
    px0, py0, pw, ph = 30, 100, 900, 600
    d.rounded_rectangle((px0, py0, px0 + pw, py0 + ph), 10, fill=PANEL)
    d.text((px0 + 16, py0 + 10), "Top view - whole bed (225 x 145 mm)", fill=DIM, font=f_h)
    m = 50
    sx = (pw - 2 * m) / (BED[1] - BED[0])
    sy = (ph - 2 * m - 20) / (BED[3] - BED[2])
    s = min(sx, sy)
    cx, cy = px0 + pw / 2, py0 + 30 + (ph - 30) / 2
    T = lambda x, y: (cx + x * s, cy - y * s)
    bx0, by0 = T(BED[0], BED[3])
    bx1, by1 = T(BED[1], BED[2])
    d.rectangle((bx0, by0, bx1, by1), outline=GRID, width=2, fill=(30, 33, 40))
    for gx in range(-100, 101, 20):
        d.line((T(gx, BED[2]), T(gx, BED[3])), fill=GRID)
    for gy in range(-60, 61, 20):
        d.line((T(BED[0], gy), T(BED[1], gy)), fill=GRID)
    d.line((T(-5, 0), T(5, 0)), fill=DIM, width=1)
    d.line((T(0, -5), T(0, 5)), fill=DIM, width=1)
    d.text((bx0 + 4, by1 + 6), "FRONT", fill=DIM, font=f_small)
    d.text((bx0 + 4, by0 - 20), "BACK", fill=DIM, font=f_small)
    hx, hy = T(min(HOME_STEPS[0] / SPM[0], BED[1]), min(HOME_STEPS[1] / SPM[1], BED[3]))
    d.ellipse((hx - 6, hy - 6, hx + 6, hy + 6), outline=(255, 196, 0), width=2)
    d.text((hx - 70, hy + 8), "home (back-right)", fill=(255, 196, 0), font=f_small)
    for x0, y0, z0, x1, y1, z1, tool, ext in segs:
        if ext:
            continue
        if max(abs(x0), abs(x1)) > 115 or max(abs(y0), abs(y1)) > 76:   # clip home travel
            x0, y0 = max(min(x0, 112), -112), max(min(y0, 72), -72)
            x1, y1 = max(min(x1, 112), -112), max(min(y1, 72), -72)
        d.line((T(x0, y0), T(x1, y1)), fill=TOOL_COL[tool] if dry else (80, 86, 96), width=2 if dry else 1)
    for x0, y0, z0, x1, y1, z1, tool, ext in segs:
        if ext:
            d.line((T(x0, y0), T(x1, y1)), fill=TOOL_COL[tool], width=3)
    # labels for the two objects
    for tool in (0, 1):
        xs = [p for sg in segs if sg[6] == tool and sg[7] for p in (sg[0], sg[3]) if abs(p) < 100]
        ys = [p for sg in segs if sg[6] == tool and sg[7] for p in (sg[1], sg[4]) if abs(p) < 70]
        if xs:
            lx, ly = T(sum(xs) / len(xs), max(ys))
            label = "RIGHT extruder (T0)" if tool == 0 else "LEFT extruder (T1)"
            tw = d.textlength(label, font=f_small)
            d.text((lx - tw / 2, ly - 26), label, fill=TOOL_COL[tool], font=f_small)

    # ---- panel 2: 3D view of the squares -------------------------------------
    qx0, qy0, qw, qh = 950, 100, 620, 600
    d.rounded_rectangle((qx0, qy0, qx0 + qw, qy0 + qh), 10, fill=PANEL)
    d.text((qx0 + 16, qy0 + 10), "3D view", fill=DIM, font=f_h)
    work = [sg for sg in segs if (sg[7] or dry) and abs(sg[0]) < 50 and abs(sg[1]) < 30 and abs(sg[3]) < 50]
    if work:
        ztop = max(max(sg[2], sg[5]) for sg in work) or 1.0
        zx = max(1.0, min(6.0, 12.0 / ztop))      # stretch flat prints, keep tall ones true
        a = math.radians(30)
        P = lambda x, y, z: ((x - y) * math.cos(a), (x + y) * math.sin(a) * 0.9 - z * zx)
        pts = [P(x, y, z) for sg in work for (x, y, z) in ((sg[0], sg[1], sg[2]), (sg[3], sg[4], sg[5]))]
        minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
        miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
        sc = min((qw - 80) / (maxx - minx + 1e-9), (qh - 120) / (maxy - miny + 1e-9))
        ox, oy = qx0 + 40 - minx * sc, qy0 + 70 - miny * sc
        V = lambda x, y, z: (ox + P(x, y, z)[0] * sc, qy0 + qh - 40 - (P(x, y, z)[1] - miny) * sc * -1
                             - (maxy - miny) * sc)
        V = lambda x, y, z: (ox + P(x, y, z)[0] * sc, oy + P(x, y, z)[1] * sc)
        zmax = max(max(sg[2], sg[5]) for sg in work) or 1
        # draw from back to front so near lines overlap far ones
        for x0, y0, z0, x1, y1, z1, tool, ext in sorted(work, key=lambda sg: (sg[2], -(sg[0] + sg[1]))):
            shade = 0.55 + 0.45 * (z1 / zmax if zmax else 1)
            col = tuple(int(c * shade) for c in TOOL_COL[tool])
            d.line((V(x0, y0, z0), V(x1, y1, z1)), fill=col, width=2)

    # ---- footer: stats ---------------------------------------------------------
    fy = 720
    d.rounded_rectangle((30, fy, W - 30, H - 20), 10, fill=PANEL)
    zs = sorted({round(sg[2], 2) for sg in segs if sg[7]})
    ext = [sg for sg in segs if sg[7]]
    # vase mode = most printing moves climb while they extrude (not just many layer heights)
    spiral = bool(ext) and sum(1 for sg in ext if abs(sg[5] - sg[2]) > 1e-4) > 0.5 * len(ext)
    rows = [
        ("Commands", "%d" % info["n"]),
        ("Nozzle temps", ", ".join("%s %d °C" % kv for kv in sorted(info["temps"].items())) or "OFF"),
        ("Bed", "%d °C" % info["bed"] if info.get("bed") else "not heated"),
        ("Z homing", ("YES - slow, %.0f mm/s (safe)" % info["zspeed"] if info.get("zspeed", 99) <= 6 else
                      "YES - FAST %.0f mm/s (cut-out risk)" % info.get("zspeed", 0)) if info["zhome"] else
         ("NO - paper-test height = Z0, bed only moves DOWN" if info.get("zmoved") else "NO - bed never moves")),
        ("Layers", ("spiral / vase mode, %.1f - %.1f mm" % (zs[0], zs[-1]) if spiral else
                    "%d  (%.1f - %.1f mm)" % (len(zs), zs[0], zs[-1])) if zs else "none (dry run)"),
        ("Filament", "right %.0f mm,  left %.0f mm" % tuple(info["fil"])),
    ]
    for i, (k, v) in enumerate(rows):
        x = 50 + (i % 3) * 510
        y = fy + 18 + (i // 3) * 70
        d.text((x, y), k, fill=DIM, font=f_small)
        warn = k == "Z homing" and "FAST" in v
        d.text((x, y + 20), v, fill=(255, 146, 43) if warn else FG, font=f_h)

    out = out or os.path.splitext(path)[0] + "_preview.png"
    img.save(out)
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print("wrote", render(p))
