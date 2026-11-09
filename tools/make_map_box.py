"""
Map-display enclosure for an ESP32 DOIT DevKit V1 (30-pin) + 1.44" SPI TFT 128x128 V1.1
(ST7735, 8 pins: VCC GND CS RESET A0 SDA SCK LED). Vehicle mount: flat back for 3M VHB
tape + two side tabs that take an M3 screw OR a zip tie.

WEATHER-SEALED version:
  * clear 2 mm acrylic window (34 x 34 mm) held in a rim inside the cover, sealed with silicone;
    the display presses against it from behind
  * tongue-and-groove joint between cover and tray (silicone bead or 1 mm rubber cord)
  * no USB hole: power comes in on 2 wires (5 V -> VIN, GND) through a small sealed hole on the
    BOTTOM side (cable hangs down = water drips off), with a zip-tie anchor inside
  * code upload: open the cover, or use WiFi (OTA) updates

    python tools/make_map_box.py
        -> models/map_box_base.stl     tray: ESP32 cradle, seal groove, cable entry, tabs
        -> models/map_box_cover.stl    front cover: window + acrylic rim, display clips
        -> models/map_box_plate.stl    both parts laid out for ONE print (cover face-down)
        -> models/map_box_render.png

Every size is a named number below - measure your boards and adjust if needed.

Inside (front to back):  cover + window | display (glass, PCB, pins pointing back) |
ESP32 lying flat, chip side to the front | jumper-wire space + power wires | back.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import math
import os

import numpy as np
from manifold3d import CrossSection, JoinType, Manifold

from make_test_stl import write_stl

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")

# ---- parts (mm) ---------------------------------------------------------------------------
ESP_L, ESP_W, ESP_PCB = 51.5, 28.3, 1.6      # DOIT DevKit V1 30-pin board
ESP_PARTS = 3.4                              # tallest part on the chip side (WROOM module shield)
USB_OVER, USB_W, USB_H = 1.0, 8.0, 3.0       # micro-USB: sticks out past the board end, size
ESP_WIRE_DROP = 2.5                          # BOTH headers REMOVED: wires soldered to the pads stick
                                             # out this far below a board (insulation + bend)
WIRE_SPACE = 3.5                             # room under the ESP32 (wires + 1 mm)
DSP_GAP = 1.0                                # WROOM chip top -> display back (nothing else hangs there now)
                                             # (with headers kept: WIRE_SPACE 9.3 / jumper plugs 19, DSP_GAP 1.5)
DSP_W, DSP_L, DSP_PCB, DSP_GLASS = 30.0, 44.0, 1.6, 2.6       # robu.in 1.44" module: PCB 44 x 30 mm
AA_W, AA_L, AA_DY = 26.2, 27.2, 2.5          # visible screen + its offset away from the pin edge
PANE_W, PANE_H, PANE_T = 34.0, 34.0, 2.0     # clear acrylic window (cut to this size)
CABLE_D = 4.5                                # power cable / 2-wire entry hole
FIT = 0.3                                    # clearance around boards
LIP = 0.8                                    # display clip lip: hooks LIP - FIT = 0.5 mm over the PCB

# ---- box -------------------------------------------------------------------------------------
WALL, FLOOR, COVER, R_OUT = 3.0, 2.0, 2.0, 3.5   # 3 mm walls carry the seal groove
IX = ESP_L + USB_OVER + 1.5                  # cavity length: board + USB + stop lip
IY = DSP_L + 2 * FIT + 2 * 1.6                # cavity height: display + clearance + its snap fingers
OX, OY = IX + 2 * WALL, IY + 2 * WALL
ESP_X0, ESP_Y0 = 1.5, 7.6                    # board corner in cavity coords (USB end at +x)
ESP_X1 = ESP_X0 + ESP_L
ESP_YC = ESP_Y0 + ESP_W / 2
DSP_X0, DSP_Y0 = (IX - DSP_W) / 2, (IY - DSP_L) / 2           # pins along the bottom edge
Z_ESP_BOT = FLOOR + WIRE_SPACE
Z_ESP_TOP = Z_ESP_BOT + ESP_PCB
Z_DSP_BACK = Z_ESP_TOP + ESP_PARTS + DSP_GAP
Z_TOP = Z_DSP_BACK + DSP_PCB + DSP_GLASS + PANE_T + 0.1      # tray rim = cover inner face
GROOVE = (0.9, 2.1, 1.6)                     # seal groove in the wall top: from/to inset, depth
TONGUE = (1.1, 1.9, 1.3)                     # matching tongue on the cover
WIN_X, WIN_Y = DSP_X0 + DSP_W / 2, DSP_Y0 + DSP_L / 2 + AA_DY      # window centre (cavity)
BOSS_R, BOSS_IN, PILOT = 3.4, 3.4, 2.6       # corner screw bosses (M3 self-tapping, 10 mm)
TAB_L, TAB_W, TAB_T = 9.0, 16.0, 2.6         # mounting tabs
SEG = 48


def cx(x):
    return WALL + x


def cy(y):
    return WALL + y


def box(x0, y0, z0, x1, y1, z1):
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def rrect(x0, y0, w, h, r):
    r = min(r, w / 2 - 0.01, h / 2 - 0.01)
    cs = CrossSection.square([w - 2 * r, h - 2 * r]).translate([x0 + r, y0 + r])
    return cs.offset(r, JoinType.Round, 2.0, SEG)


def prism(cs, z0, z1):
    return cs.extrude(z1 - z0).translate([0, 0, z0])


def cyl(x, y, z0, z1, r, r2=None):
    return Manifold.cylinder(z1 - z0, r, r if r2 is None else r2, SEG).translate([x, y, z0])


def boss_xy():
    return [(cx(BOSS_IN), cy(BOSS_IN)), (cx(IX - BOSS_IN), cy(BOSS_IN)),
            (cx(BOSS_IN), cy(IY - BOSS_IN)), (cx(IX - BOSS_IN), cy(IY - BOSS_IN))]


# ---- tray (back) -------------------------------------------------------------------------
def base():
    shell = prism(rrect(0, 0, OX, OY, R_OUT), 0, Z_TOP)
    shell -= prism(rrect(WALL, WALL, IX, IY, 1.0), FLOOR, Z_TOP + 1)
    for x, y in boss_xy():                                     # screw bosses (merge with walls)
        shell += cyl(x, y, FLOOR - 0.01, Z_TOP, BOSS_R)
    # ESP32 cradle: one block under each board end (no pins there), side lips, end stop
    for xa, xb in ((ESP_X0 - 0.01, ESP_X0 + 4.4), (ESP_X1 - 4.4, ESP_X1)):
        shell += box(cx(xa), cy(ESP_Y0 + 1.0), FLOOR - 0.01, cx(xb), cy(ESP_Y0 + ESP_W - 1.0), Z_ESP_BOT)
        for ya, yb in ((ESP_Y0 - FIT - 1.2, ESP_Y0 - FIT), (ESP_Y0 + ESP_W + FIT, ESP_Y0 + ESP_W + FIT + 1.2)):
            shell += box(cx(xa), cy(ya), FLOOR - 0.01, cx(xb), cy(yb), Z_ESP_BOT + 1.5)
        shell += box(cx(xa), cy(ESP_Y0 - FIT), FLOOR - 0.01, cx(xb), cy(ESP_Y0 + 1.01), Z_ESP_BOT)
        shell += box(cx(xa), cy(ESP_Y0 + ESP_W - 1.01), FLOOR - 0.01, cx(xb), cy(ESP_Y0 + ESP_W + FIT), Z_ESP_BOT)
    shell += box(cx(-0.01), cy(ESP_Y0 - FIT), FLOOR - 0.01, cx(ESP_X0 - FIT), cy(ESP_Y0 + ESP_W + FIT),
                 Z_ESP_BOT + 2.5)                              # end stop (USB plug pushes this way)
    # mounting tabs: flat with the back, slot fits an M3 screw or a 5 mm zip tie
    for sgn in (-1, 1):
        x_root = 0 if sgn < 0 else OX
        tx0 = -TAB_L if sgn < 0 else OX - R_OUT          # tab overlaps the wall by R_OUT
        tab = rrect(tx0, (OY - TAB_W) / 2, TAB_L + R_OUT, TAB_W, 3.0)
        shell += prism(tab, 0, TAB_T)
        sx = x_root + sgn * (TAB_L * 0.55)
        shell -= prism(rrect(sx - 1.7, OY / 2 - 3.0, 3.4, 6.0, 1.7), -1, TAB_T + 1)
    # pilot holes for the cover screws (blind: water in a screw hole cannot reach the inside)
    for x, y in boss_xy():
        shell -= cyl(x, y, Z_TOP - 11, Z_TOP + 1, PILOT / 2)
    # seal groove all round the wall top (silicone bead or 1 mm rubber cord)
    g0, g1, gd = GROOVE
    shell -= prism(rrect(g0, g0, OX - 2 * g0, OY - 2 * g0, R_OUT - g0), Z_TOP - gd, Z_TOP + 1) \
        - prism(rrect(g1, g1, OX - 2 * g1, OY - 2 * g1, R_OUT - g1), Z_TOP - gd - 1, Z_TOP + 2)
    # power entry on the BOTTOM side (-y) below the ESP32's USB end: a short spout
    # around a 4.5 mm hole - fill with silicone after the wires are in
    ex, ez = cx(ESP_X1 - 9.0), FLOOR + 6.0
    shell += _y_tube(ex, ez, -4.0, WALL, 4.5)
    shell += box(ex - 4.5, -4.0, 0, ex + 4.5, 0.5, ez)              # foot: prints without support
    shell -= _y_tube(ex, ez, -5.0, WALL + 1, CABLE_D / 2)
    # zip-tie anchor inside, right behind the entry (strain relief for the wires)
    ax0, ay0 = ex - 5.5, cy(2.2)                       # between display pins and corner boss
    shell += box(ax0, ay0, FLOOR - 0.01, ax0 + 7.5, ay0 + 3.6, FLOOR + 4.0)
    shell -= box(ax0 - 1, ay0 + 0.8, FLOOR + 0.8, ax0 + 8.5, ay0 + 2.8, FLOOR + 2.4)
    return shell


def _y_tube(x, z, y0, y1, r):
    """Cylinder along +y (axis at x, z) from y0 to y1."""
    return Manifold.cylinder(y1 - y0, r, r, SEG).rotate([-90, 0, 0]).translate([x, y0, z])


# ---- front cover ---------------------------------------------------------------------------
def cover():
    z0, z1 = Z_TOP, Z_TOP + COVER
    c = prism(rrect(0, 0, OX, OY, R_OUT), z0, z1)
    # screen window: AA + 0.9 mm margin, 45 deg bevel toward the front
    wx, wy = cx(WIN_X), cy(WIN_Y)
    ww, wh, ch = AA_W + 1.8, AA_L + 1.8, 1.0
    inner = rrect(wx - ww / 2, wy - wh / 2, ww, wh, 0.8)
    outer = rrect(wx - ww / 2 - ch, wy - wh / 2 - ch, ww + 2 * ch, wh + 2 * ch, 0.8 + ch)
    c -= prism(inner, z0 - 1, z1 + 1)
    c -= _bevel(inner, outer, z1 - ch, z1 + 0.02)
    # countersunk M3 screw holes
    for x, y in boss_xy():
        c -= cyl(x, y, z0 - 1, z1 + 1, 1.7)
        c -= cyl(x, y, z1 - 1.6, z1 + 0.01, 1.7, 3.3)
    # sealing tongue: drops into the groove on the tray walls (silicone / rubber cord in there)
    t0, t1, th = TONGUE
    c += prism(rrect(t0, t0, OX - 2 * t0, OY - 2 * t0, R_OUT - t0), z0 - th, z0 + 0.01) \
        - prism(rrect(t1, t1, OX - 2 * t1, OY - 2 * t1, R_OUT - t1), z0 - th - 1, z0 + 1)
    # acrylic window rim: the 34 x 34 x 2 mm pane sits here, sealed with clear silicone
    px0, px1 = wx - PANE_W / 2 - FIT, wx + PANE_W / 2 + FIT
    py0, py1 = wy - PANE_H / 2 - FIT, wy + PANE_H / 2 + FIT
    pane_out = rrect(px0 - 1.2, py0 - 1.2, px1 - px0 + 2.4, py1 - py0 + 2.4, 1.5)
    pane_in = rrect(px0, py0, px1 - px0, py1 - py0, 0.5)
    c += prism(pane_out, z0 - PANE_T + 0.2, z0 + 0.01) - prism(pane_in, z0 - PANE_T - 1, z0 + 1)
    # display: held by corner stops + 4 snap fingers on the SHORT ends (the pane fills the
    # space beside its long edges); the display glass presses on the pane
    dx0, dx1 = cx(DSP_X0 - FIT), cx(DSP_X0 + DSP_W + FIT)
    dy0, dy1 = cy(DSP_Y0 - FIT), cy(DSP_Y0 + DSP_L + FIT)
    zb = Z_DSP_BACK + DSP_PCB * 0.5                   # stops reach halfway down the PCB edge
    for ya, yb in ((dy0 - 1.2, dy0 + 2.0), (dy1 - 1.5, dy1 + 1.2)):           # corner stops (x)
        for xa, xb in ((dx0 - 1.2, dx0), (dx1, dx1 + 1.2)):
            c += box(xa, ya, zb, xb, yb, z0 + 0.01)
    zl = Z_DSP_BACK - 1.0                             # finger tip: ~1 mm thick lip hooks behind the PCB
    for ya, yb, lip in ((dy0 - 1.0, dy0, (dy0, dy0 + LIP)), (dy1, dy1 + 1.0, (dy1 - LIP, dy1))):
        for xa in (dx0 + 0.6, dx1 - 0.6 - 3.6):       # near the corners: clear of pins / ribbon
            c += box(xa, ya, zl, xa + 3.6, yb, z0 + 0.01)
            c += box(xa, lip[0], zl, xa + 3.6, lip[1], Z_DSP_BACK - 0.05)
    # hold-down posts for the ESP32 (beside the chip at the far end, on the USB shell)
    for py in (ESP_Y0 + 2.65, ESP_Y0 + ESP_W - 2.65):
        c += cyl(cx(ESP_X0 + 2.2), cy(py), Z_ESP_TOP + 0.3, z0 + 0.01, 1.5)
    c += cyl(cx(ESP_X1 - 2.0), cy(ESP_YC), Z_ESP_TOP + USB_H + 0.3, z0 + 0.01, 1.8)
    return c


def _bevel(inner, outer, za, zb):
    """Frustum between two outlines (window bevel), as the hull of two thin slabs."""
    return Manifold.batch_hull([prism(inner, za, za + 0.01), prism(outer, zb - 0.01, zb)])


# ---- output ----------------------------------------------------------------------------------
def tris_of(m):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    t = np.asarray(mesh.tri_verts)
    return [tuple(tuple(float(c) for c in v[i]) for i in tri) for tri in t]


COL_ESP, COL_CHIP, COL_PLUG = (40, 52, 78), (190, 193, 200), (28, 28, 32)
COL_DSP, COL_GLASS, COL_PANE = (196, 48, 44), (20, 22, 30), (120, 200, 235)


def mock_boards():
    """Stand-in ESP32 + display (only for the picture), as (Manifold, colour) pairs."""
    m = []
    ex0, ex1, ey0, ey1 = cx(ESP_X0), cx(ESP_X1), cy(ESP_Y0), cy(ESP_Y0 + ESP_W)
    m.append((box(ex0, ey0, Z_ESP_BOT, ex1, ey1, Z_ESP_TOP), COL_ESP))
    m.append((box(ex0, cy(ESP_YC - 9), Z_ESP_TOP, ex0 + 25.5, cy(ESP_YC + 9), Z_ESP_TOP + ESP_PARTS), COL_CHIP))
    m.append((box(ex1 - 5, cy(ESP_YC - 3.8), Z_ESP_TOP, ex1 + USB_OVER, cy(ESP_YC + 3.8), Z_ESP_TOP + USB_H),
              COL_CHIP))
    pc = (ex0 + ex1) / 2
    for py in (ESP_Y0 + 1.45, ESP_Y0 + ESP_W - 1.45):           # header rows + jumper plugs below
        m.append((box(pc - 19.1, cy(py) - 1.25, Z_ESP_BOT - ESP_WIRE_DROP, pc + 19.1, cy(py) + 1.25, Z_ESP_BOT),
                  COL_PLUG))
    dx0, dy0 = cx(DSP_X0), cy(DSP_Y0)
    m.append((box(dx0, dy0, Z_DSP_BACK, dx0 + DSP_W, dy0 + DSP_L, Z_DSP_BACK + DSP_PCB), COL_DSP))
    gy = dy0 + DSP_L / 2 + AA_DY
    m.append((box(dx0 + 0.6, gy - AA_L / 2 - 2.5, Z_DSP_BACK + DSP_PCB, dx0 + DSP_W - 0.6, gy + AA_L / 2 + 3.5,
                  Z_DSP_BACK + DSP_PCB + DSP_GLASS), COL_GLASS))
    hx = dx0 + DSP_W / 2
    m.append((box(hx - 10.2, dy0 + 1.3, Z_DSP_BACK - ESP_WIRE_DROP, hx + 10.2, dy0 + 3.8, Z_DSP_BACK), COL_PLUG))
    wx, wy = cx(WIN_X), cy(WIN_Y)
    m.append((box(wx - PANE_W / 2, wy - PANE_H / 2, Z_TOP - PANE_T, wx + PANE_W / 2, wy + PANE_H / 2,
                  Z_TOP - 0.05), COL_PANE))
    return m


def render(parts, path):
    from PIL import Image, ImageDraw, ImageFont
    from make_warden_bust import _render_view
    b, c = parts
    plastic = (92, 97, 110)

    def coloured(pairs, shift):
        out = []
        for m, col in pairs:
            out += [t + (col,) for t in tris_of(m.translate(shift))]
        return out

    def shift_of(m):
        lo, hi = np.array(m.bounding_box()[:3]), np.array(m.bounding_box()[3:])
        mid = (lo + hi) / 2
        return [-mid[0], -mid[1], -lo[2]], (hi[2] - lo[2]) / 2

    s, za = shift_of(b + c)
    assembled = coloured([(b, plastic), (c, plastic)], s)
    # cross-section through the middle of the ESP32, seen from the cut side
    cut = cy(ESP_YC)
    sec = [(m.trim_by_plane([0, -1, 0], -cut), col) for m, col in [(b, plastic), (c, plastic)] + mock_boards()]
    section = coloured([p for p in sec if not p[0].is_empty()], s)
    cf = c.rotate([180, 0, 0])
    s2, zc = shift_of(cf)
    cov = coloured([(cf, plastic)], s2)
    kw = dict(smooth_cos=0.95)
    panels = [("Assembled - cable entry at the bottom", _render_view(assembled, 600, 560, 7.0, za, -1, yaw_deg=30, pitch_deg=22, **kw)),
              ("Cut-away: how the boards sit", _render_view(section, 600, 560, 8.0, za, -1, yaw_deg=180 - 18,
                                                             pitch_deg=12, **kw)),
              ("Cover inside - display pocket", _render_view(cov, 600, 560, 7.0, zc, -1, yaw_deg=180 - 20,
                                                              pitch_deg=55, **kw))]
    out = Image.new("RGB", (1840, 660), (214, 217, 223))
    d = ImageDraw.Draw(out)
    try:
        f = ImageFont.truetype("segoeuib.ttf", 24)
        fs = ImageFont.truetype("segoeui.ttf", 18)
    except OSError:
        f = fs = ImageFont.load_default()
    for i, (title, im) in enumerate(panels):
        out.paste(im, (i * 615, 55))
        d.text((i * 615 + 18, 14), title, fill=(40, 44, 52), font=f)
    x = 560
    for label, col in (("acrylic window", COL_PANE), ("display PCB", COL_DSP), ("screen glass", COL_GLASS),
                       ("ESP32 board", COL_ESP),
                       ("WROOM chip / USB", COL_CHIP), ("pins / wire joints", COL_PLUG)):
        d.rectangle((x, 624, x + 18, 642), fill=col)
        d.text((x + 24, 620), label, fill=(40, 44, 52), font=fs)
        x += 24 + d.textlength(label, font=fs) + 22
    out.save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    b, c = base(), cover()
    for name, m in (("base", b), ("cover", c)):
        assert m.status().name == "NoError", m.status()
    write_stl(os.path.join(OUT, "map_box_base.stl"), tris_of(b))
    # cover printed face-down: flip it so the window face sits on the bed
    cf = c.rotate([180, 0, 0])
    lo = cf.bounding_box()
    cf = cf.translate([-lo[0], -lo[1], -lo[2]])
    write_stl(os.path.join(OUT, "map_box_cover.stl"), tris_of(cf))
    blo = b.bounding_box()
    plate = b.translate([-blo[0], -blo[1], -blo[2]]) + cf.translate([blo[3] - blo[0] + 8, 0, 0])
    write_stl(os.path.join(OUT, "map_box_plate.stl"), tris_of(plate))
    render((b, c), os.path.join(OUT, "map_box_render.png"))
    ob = (b + c).bounding_box()
    print("box: %.1f x %.1f x %.1f mm (with tabs %.1f wide)" % (OX, OY, Z_TOP + COVER, ob[3] - ob[0]))
    print("cavity %.1f x %.1f, ESP32 sits %.1f mm above the floor (header removed), "
          "window: %.0f x %.0f x %.0f mm acrylic" % (IX, IY, WIRE_SPACE, PANE_W, PANE_H, PANE_T))
    print("wrote models/map_box_base.stl, map_box_cover.stl, map_box_plate.stl, map_box_render.png")


if __name__ == "__main__":
    main()
