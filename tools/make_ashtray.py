"""
Ashtray with a METAL ember cup - printed plastic never touches a lit cigarette.

    python tools/make_ashtray.py  ->  models/ashtray.stl, models/ashtray_render.png

* centre pocket holds a standard aluminium tea-light cup (39 mm x 16 mm): stub out in the metal
* the dish slopes 25 deg toward the cup, so ash slides into the metal, not onto the plastic
* push-out hole under the cup: press from below to lift the cup out for emptying / swapping
* no plastic cigarette rests (a resting cigarette burns down toward its rest)
* fluted outside for grip; wide flat base so it does not tip
Print upright, no supports.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import math
import os

from manifold3d import CrossSection, Manifold

from make_map_box import tris_of
from make_test_stl import write_stl

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")
SEG = 96
CUP_D, CUP_H, CUP_FIT = 39.0, 16.0, 0.8        # tea-light cup + clearance on the diameter
R_BASE, R_TOP, H = 39.0, 41.0, 27.0             # outside: base radius, rim radius, height
RIM_W, DISH_DEG = 5.0, 25.0                     # flat rim width, dish slope
FLOOR = 2.4                                     # plastic under the cup
PUSH_D = 14.0                                   # push-out hole


def body():
    rp = (CUP_D + CUP_FIT) / 2                                   # pocket radius
    r_dish0 = R_TOP - RIM_W                                       # dish starts inside the rim
    z_dish1 = H - (r_dish0 - rp) * math.tan(math.radians(DISH_DEG))
    z_pocket = z_dish1 - CUP_H - 0.5                             # cup rim sits 0.5 mm below the dish
    assert z_pocket >= FLOOR, "not enough height for the cup"
    # half profile (r, z), counter-clockwise, revolved around the axis
    prof = [(PUSH_D / 2, 0.0), (R_BASE - 1.0, 0.0), (R_BASE, 1.0), (R_TOP, H - 1.0), (R_TOP - 1.0, H),
            (r_dish0, H), (rp, z_dish1), (rp, z_pocket), (PUSH_D / 2, z_pocket)]
    m = Manifold.revolve(CrossSection([prof]), SEG)
    # flutes around the outside (grip + looks), stopping short of base and rim
    n = 28
    for k in range(n):
        a = 2 * math.pi * k / n
        fl = Manifold.cylinder(H - 6.0, 1.6, 1.6, 24).translate([0, 0, 3.0])
        rr = (R_BASE + R_TOP) / 2 + 0.9
        m -= fl.translate([rr * math.cos(a), rr * math.sin(a), 0])
    return m, z_pocket, z_dish1


def render(m, path):
    from PIL import Image, ImageDraw, ImageFont
    from make_warden_bust import _render_view
    col, metal = (52, 58, 70), (200, 202, 208)
    _, zp, _ = body()
    cup = (Manifold.cylinder(CUP_H, CUP_D / 2, CUP_D / 2, SEG)
           - Manifold.cylinder(CUP_H, CUP_D / 2 - 0.4, CUP_D / 2 - 0.4, SEG).translate([0, 0, 0.3])).translate([0, 0, zp])
    zc = H / 2
    full = [t + (col,) for t in tris_of(m)] + [t + (metal,) for t in tris_of(cup)]
    cut = [t + (col,) for t in tris_of(m.trim_by_plane([0, -1, 0], 0))] + \
          [t + (metal,) for t in tris_of(cup.trim_by_plane([0, -1, 0], 0))]
    kw = dict(smooth_cos=0.92)
    panels = [("Ashtray with metal cup", _render_view(full, 600, 480, 6.2, zc, -1, yaw_deg=180 - 30, pitch_deg=35, **kw)),
              ("Cut open: dish slopes into the cup", _render_view(cut, 600, 480, 6.2, zc, -1, yaw_deg=180,
                                                                   pitch_deg=12, **kw))]
    out = Image.new("RGB", (1220, 540), (214, 217, 223))
    d = ImageDraw.Draw(out)
    try:
        f = ImageFont.truetype("segoeuib.ttf", 24)
    except OSError:
        f = ImageFont.load_default()
    for i, (title, im) in enumerate(panels):
        out.paste(im, (i * 615, 55))
        d.text((i * 615 + 18, 14), title, fill=(40, 44, 52), font=f)
    out.save(path)


def main():
    m, zp, zd = body()
    assert m.status().name == "NoError", m.status()
    write_stl(os.path.join(OUT, "ashtray.stl"), tris_of(m))
    render(m, os.path.join(OUT, "ashtray_render.png"))
    bb = m.bounding_box()
    print("ashtray: %.0f mm across x %.0f mm tall; cup pocket %.1f mm, cup rim %.1f mm below the dish edge"
          % (bb[3] - bb[0], bb[5] - bb[2], CUP_D + CUP_FIT, zd - (zp + CUP_H)))
    print("wrote models/ashtray.stl, models/ashtray_render.png")


if __name__ == "__main__":
    main()
