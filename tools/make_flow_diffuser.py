"""
Universal aquarium flow diffuser - fits ANY filter outlet pipe from 12 to 22 mm.

    python tools/make_flow_diffuser.py
        -> models/flow_diffuser.stl, models/flow_diffuser_render.png

* stepped bore (22, 21, 20 ... 12 mm, 3 mm per step): push it on, it stops at your size
* 4 slots make the sleeve a collet: a zip tie around it squeezes it onto the pipe
* water leaves through 24 side holes + 3 tip holes (more total area than a 12 mm pipe),
  so the strong jet becomes a soft spray without choking the pump
Print standing, open end down, no supports. PETG is best for water; PLA works too.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import math
import os

from manifold3d import Manifold

from make_map_box import tris_of
from make_test_stl import write_stl

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")
SEG = 64
STEPS = list(range(22, 11, -1))          # pipe sizes, mm (outer diameter of the filter outlet)
STEP_H = 3.0
CLEAR = 0.3                              # printed holes come out a little small
STEEP = 1.25                             # chamfers + roof at ~51 deg: clearly printable, no supports
WALL = 2.0
SLEEVE_R = (STEPS[0] + CLEAR) / 2 + WALL
CH_R = (STEPS[-1] + CLEAR) / 2           # chamber bore = smallest step
CH_H = 13.0


def cyl(z0, z1, r, r2=None):
    return Manifold.cylinder(z1 - z0, r, r if r2 is None else r2, SEG).translate([0, 0, z0])


FAN_W, FAN_T, FAN_L, FAN_WALL = 44.0, 6.5, 38.0, 1.6   # fan slot (exit) and its spreading duct
VANES = (-11.0, 0.0, 11.0)                              # guide vanes across the slot


def sleeve(step_h=STEP_H):
    """Universal stepped sleeve (12-22 mm pipes) with collet slots, open at z = 0."""
    z_steps = step_h * len(STEPS)
    body = cyl(0, z_steps, SLEEVE_R)
    for k, d in enumerate(STEPS):
        r = (d + CLEAR) / 2
        r_next = (STEPS[k + 1] + CLEAR) / 2 if k + 1 < len(STEPS) else r
        z0 = k * step_h - (1 if k == 0 else 0.01)
        zt = (k + 1) * step_h - (r - r_next) * STEEP
        body -= cyl(z0, zt + 0.01, r)
        if r_next < r:
            body -= cyl(zt, (k + 1) * step_h + 0.01, r, r_next)
    for a in (0, 90, 180, 270):
        slot = Manifold.cube([SLEEVE_R + 2, 1.3, z_steps - 3]).translate([0, -0.65, -1])
        body -= slot.rotate([0, 0, a + 45])
    return body, z_steps


def _slab(w, t, z, h=0.01):
    return Manifold.cube([w, t, h]).translate([-w / 2, -t / 2, z])


def fan_nozzle():
    """Sleeve + a duct that spreads the jet into a wide flat sheet ONE way, ~2.2x the pipe area
    at the exit, so the water leaves at less than half the speed."""
    body, z0 = sleeve()
    z1 = z0 + FAN_L
    outer = Manifold.batch_hull([cyl(z0 - 0.01, z0, SLEEVE_R),
                                 _slab(FAN_W + 2 * FAN_WALL, FAN_T + 2 * FAN_WALL, z1 - 0.01)])
    duct = Manifold.batch_hull([cyl(z0 - 0.02, z0 - 0.01, CH_R),
                                _slab(FAN_W, FAN_T, z1 - 0.01), _slab(FAN_W, FAN_T, z1 + 1.0)])
    body += outer
    body -= duct
    body -= cyl(z0 - 1.0, z0 + 0.01, CH_R)                              # throat joins the sleeve
    # guide vanes keep the sheet even across the full width
    zv = z0 + FAN_L * 0.38
    for x in VANES:
        vane = Manifold.cube([1.0, FAN_T + 4, z1 - zv]).translate([x - 0.5, -(FAN_T + 4) / 2, zv])
        body += vane ^ duct
    return body


# ---- calm box: impingement roof + perforated settling wall + one slow slotted exit ---------
CB_W, CB_D, CB_H, CB_WALL = 46.0, 26.0, 34.0, 2.0       # chamber inside (x, y, height), wall
CB_DY = 5.0                                             # box centre sits 5 mm toward the exit side
SLOT_W, SLOT_PITCH, SLOT_N = 2.4, 4.0, 10               # exit slots in the front wall (+y)
BAF_Y, BAF_T, BAF_HOLE, BAF_PITCH = 7.0, 1.6, 3.2, 5.0  # settling wall with holes


def _rect(w, d, cy_, z, h=0.01):
    return Manifold.cube([w, d, h]).translate([-w / 2, cy_ - d / 2, z])


def calm_box():
    """Physics: the 12 mm jet (~2.2 m/s at 880 L/h) shoots up into a closed chamber and hits the
    roof (its energy turns into swirl), passes a perforated settling wall that evens the flow out,
    and leaves through 10 tall slots on ONE side with ~6x the pipe area -> ~0.25-0.34 m/s."""
    body, z0 = sleeve()
    W, D = CB_W + 2 * CB_WALL, CB_D + 2 * CB_WALL
    ri = max(CB_W / 2 - CH_R, CB_D / 2 + CB_DY - CH_R)
    reach = math.hypot(W / 2, D / 2 + CB_DY) - SLEEVE_R      # outer funnel corners
    zb = z0 + max(ri * 1.1, reach * 1.15)                  # funnel under 45 deg inside AND outside
    zt = zb + CB_H
    rise = CB_D / 2 * STEEP                                # hip roof, ~51 deg inside
    # outside: funnel + box + roof
    body += Manifold.batch_hull([cyl(z0 - 0.01, z0, SLEEVE_R), _rect(W, D, CB_DY, zb)])
    body += _rect(W, D, CB_DY, zb, zt - zb)
    body += Manifold.batch_hull([_rect(W, D, CB_DY, zt - 0.01), _rect(CB_W - CB_D + 4, 4, CB_DY, zt + rise + 1.6)])
    # inside: funnel + chamber + roof cavity
    cavity = Manifold.batch_hull([cyl(z0 - 0.02, z0 - 0.01, CH_R), _rect(CB_W, CB_D, CB_DY, zb)])
    cavity += _rect(CB_W, CB_D, CB_DY, zb - 0.01, zt - zb + 0.02)
    cavity += Manifold.batch_hull([_rect(CB_W, CB_D, CB_DY, zt - 0.01), _rect(CB_W - CB_D, 0.4, CB_DY, zt + rise)])
    body -= cavity
    body -= cyl(z0 - 1.0, z0 + 0.01, CH_R)
    # settling wall: a perforated plate between the jet column and the exit
    plate = Manifold.cube([CB_W + 2, BAF_T, zt + rise - z0]).translate([-(CB_W + 2) / 2, BAF_Y - BAF_T / 2, z0])
    plate = plate ^ cavity
    nx = int(CB_W // BAF_PITCH) - 1
    for i in range(nx):
        x = (i - (nx - 1) / 2) * BAF_PITCH
        z = zb - 6.0
        while z < zt + rise * 0.6:
            hole = Manifold.cylinder(BAF_T + 2, BAF_HOLE / 2, BAF_HOLE / 2, 16).rotate([-90, 0, 0])
            plate -= hole.translate([x, BAF_Y - BAF_T / 2 - 1, z])
            z += BAF_PITCH
    body += plate
    # exit: 10 tall slots in the front wall only (+y)
    y_front = CB_DY + CB_D / 2
    for i in range(SLOT_N):
        x = (i - (SLOT_N - 1) / 2) * SLOT_PITCH
        body -= Manifold.cube([SLOT_W, CB_WALL + 2, CB_H - 4]).translate([x - SLOT_W / 2, y_front - 1, zb + 2])
    return body


# ---- sponge cage: the gentlest outlet - water leaves through a disc of filter foam -----------
SP_R, SP_H, SP_WALL = 20.5, 18.0, 1.6      # basket inside radius / height (sponge disc 42 x 19 mm)
SP_SLOT_W, SP_SLOTS = 5.2, 6               # wide slots in the FRONT half only (fast to print)


def sponge_cage():
    """Physics: foam has thousands of tiny pores - the jet's energy is used up pushing through
    them and the water seeps out over the whole foam surface (~1,900 mm2 open) at ~0.1 m/s.
    Short (60 mm) so it prints in under an hour."""
    body, z0 = sleeve(step_h=1.6)
    ro = SP_R + SP_WALL
    zb = z0 + (ro - SLEEVE_R) * 1.1                      # ~42 deg shoulder up to the basket
    zt = zb + SP_H
    body += cyl(z0 - 0.01, zb, SLEEVE_R, ro)            # solid shoulder = basket floor
    body += cyl(zb, zt, ro) - cyl(zb + 0.01, zt + 1, SP_R)
    body -= cyl(z0 - 1.0, zb + 0.5, CH_R)                # water enters the foam through the floor (cut LAST)
    # slots in the front half (+y): water goes forward and up, not backwards
    for i in range(SP_SLOTS):
        a = math.radians(15 + i * (150 / (SP_SLOTS - 1)))
        slot = Manifold.cube([SP_WALL + 2, SP_SLOT_W, SP_H - 4.5]).translate([SP_R - 1, -SP_SLOT_W / 2, zb + 2])
        body -= slot.rotate([0, 0, math.degrees(a)])
    # 4 lips at the rim keep the foam in (45 deg underside = no support needed)
    for k in range(4):
        lip = Manifold.batch_hull([
            Manifold.cube([0.01, 6, 0.01]).translate([SP_R + 0.5, -3, zt - 3.6]),
            Manifold.cube([3.0, 6, 0.01]).translate([SP_R - 2.5, -3, zt - 0.01])])
        body += lip.rotate([0, 0, 45 + k * 90])
    return body


def radial_hole(z, ang_deg, r, length):
    h = Manifold.cylinder(length, r, r, 20).rotate([0, 90, 0])        # along +x from the axis
    return h.rotate([0, 0, ang_deg]).translate([0, 0, z])


def diffuser():
    z_steps = STEP_H * len(STEPS)
    zc = z_steps + 4
    head_r = CH_R + 2.2
    body = cyl(0, z_steps, SLEEVE_R)
    body += cyl(z_steps, zc, SLEEVE_R, head_r)                              # taper to the head
    body += cyl(zc, zc + CH_H, head_r)
    body += cyl(zc + CH_H, zc + CH_H + (head_r - 0.6) * STEEP, head_r, 0.6)   # pointed roof (~51 deg)
    # stepped bore: each step ends in a 45 deg chamfer (no flat ledges = no overhangs)
    for k, d in enumerate(STEPS):
        r = (d + CLEAR) / 2
        r_next = (STEPS[k + 1] + CLEAR) / 2 if k + 1 < len(STEPS) else r
        z0 = k * STEP_H - (1 if k == 0 else 0.01)
        zt = (k + 1) * STEP_H - (r - r_next) * STEEP
        body -= cyl(z0, zt + 0.01, r)
        if r_next < r:
            body -= cyl(zt, (k + 1) * STEP_H + 0.01, r, r_next)
    body -= cyl(z_steps - 0.01, zc + CH_H + 0.01, CH_R)                      # spray chamber
    body -= cyl(zc + CH_H, zc + CH_H + (CH_R - 0.6) * STEEP, CH_R, 0.6)       # with a pointed roof
    # collet slots (a zip tie squeezes the sleeve onto the pipe)
    for a in (0, 90, 180, 270):
        slot = Manifold.cube([SLEEVE_R + 2, 1.3, z_steps - 3]).translate([0, -0.65, -1])
        body -= slot.rotate([0, 0, a + 45])
    # spray holes: 3 rings of 8 + 3 at the tip
    for i, z in enumerate((zc + 3.0, zc + 6.5, zc + 10.0)):
        for k in range(8):
            body -= radial_hole(z, k * 45 + (22.5 if i % 2 else 0), 1.3, CH_R + 4)
    for k in range(3):                                                       # 3 holes in the roof
        a = math.radians(k * 120)
        body -= cyl(zc + CH_H, zc + CH_H + (head_r + 1) * STEEP, 1.0).translate([3.0 * math.cos(a), 3.0 * math.sin(a), 0])
    return body


def render(m, path, title="Flow diffuser", sc=9.0, side_cut=False):
    from PIL import Image, ImageDraw, ImageFont
    from make_warden_bust import _render_view
    col = (40, 110, 160)
    lo = m.bounding_box()
    zc = (lo[5] - lo[2]) / 2
    full = [t + (col,) for t in tris_of(m)]
    kw = dict(smooth_cos=0.9)
    if side_cut:      # cut along the flow: jet -> roof -> settling wall -> exit slots
        cut = [t + (col,) for t in tris_of(m.trim_by_plane([-1, 0, 0], 0.0))]
        cut_view = _render_view(cut, 560, 620, sc, zc, -1, yaw_deg=-90, pitch_deg=8, **kw)
        cut_title = "Cut along the flow (exit on the right)"
    else:
        cut = [t + (col,) for t in tris_of(m.trim_by_plane([0, -1, 0], 0.0))]
        cut_view = _render_view(cut, 560, 620, sc, zc, -1, yaw_deg=180, pitch_deg=8, **kw)
        cut_title = "Cut open: steps 22 -> 12 mm, duct"
    panels = [(title, _render_view(full, 560, 620, sc, zc, -1, yaw_deg=180 - 35, pitch_deg=18, **kw)),
              (cut_title, cut_view)]
    out = Image.new("RGB", (1140, 680), (214, 217, 223))
    d = ImageDraw.Draw(out)
    try:
        f = ImageFont.truetype("segoeuib.ttf", 24)
    except OSError:
        f = ImageFont.load_default()
    for i, (title, im) in enumerate(panels):
        out.paste(im, (i * 575, 55))
        d.text((i * 575 + 18, 14), title, fill=(40, 44, 52), font=f)
    out.save(path)


def main():
    import sys
    style = sys.argv[sys.argv.index("--style") + 1] if "--style" in sys.argv else "sponge"
    if style == "sponge":
        m = sponge_cage()
        assert m.status().name == "NoError", m.status()
        write_stl(os.path.join(OUT, "flow_sponge_cage.stl"), tris_of(m))
        render(m, os.path.join(OUT, "flow_sponge_cage_render.png"), "Sponge cage - gentlest outlet", 8.0,
               side_cut=True)
        bb = m.bounding_box()
        q = 880 / 3600 / 1000
        a_pipe = math.pi * CH_R ** 2 * 1e-6
        a_side = SP_SLOTS * SP_SLOT_W * (SP_H - 4.5)
        a_top = math.pi * SP_R ** 2 - 4 * 6 * 2.5
        a_out = (a_side + a_top) * 1e-6
        print("sponge cage: %.1f x %.1f x %.1f mm, fits pipes %d-%d mm, sponge disc %.0f x %.0f mm" % (
            bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], STEPS[-1], STEPS[0], 2 * SP_R + 1, SP_H + 1))
        print("at 880 L/h: jet %.2f m/s -> out of the foam %.2f m/s (%.0fx slower), open area %.0f mm2"
              % (q / a_pipe, q / a_out, a_out / a_pipe, a_out * 1e6))
        print("wrote models/flow_sponge_cage.stl, models/flow_sponge_cage_render.png")
        return
    if style == "calm":
        m = calm_box()
        assert m.status().name == "NoError", m.status()
        write_stl(os.path.join(OUT, "flow_calm_box.stl"), tris_of(m))
        render(m, os.path.join(OUT, "flow_calm_box_render.png"), "Calm box - slow, one side only", 6.0, side_cut=True)
        bb = m.bounding_box()
        q = 880 / 3600 / 1000                                   # m3/s at the pump's maximum
        a_pipe = math.pi * CH_R ** 2 * 1e-6
        a_out = SLOT_N * SLOT_W * (CB_H - 4) * 1e-6
        v_in, v_out = q / a_pipe, q / a_out
        print("calm box: %.1f x %.1f x %.1f mm, fits pipes %d-%d mm" % (
            bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], STEPS[-1], STEPS[0]))
        print("at 880 L/h: jet %.2f m/s -> exit %.2f m/s (%.1fx slower), push %.2f N -> %.2f N"
              % (v_in, v_out, v_in / v_out, 1000 * q * v_in, 1000 * q * v_out))
        print("wrote models/flow_calm_box.stl, models/flow_calm_box_render.png")
        return
    if style == "fan":
        m = fan_nozzle()
        assert m.status().name == "NoError", m.status()
        write_stl(os.path.join(OUT, "flow_fan_nozzle.stl"), tris_of(m))
        render(m, os.path.join(OUT, "flow_fan_nozzle_render.png"), "Fan nozzle - one wide, gentle sheet", 7.5)
        bb = m.bounding_box()
        exit_a = FAN_W * FAN_T - len(VANES) * FAN_T
        pipe_a = math.pi * CH_R ** 2
        print("fan nozzle: %.1f x %.1f x %.1f mm, fits pipes %d-%d mm" % (
            bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], STEPS[-1], STEPS[0]))
        print("exit %.0f mm2 = %.1f x the %.0f mm2 throat -> water leaves at %.0f %% of the pipe speed"
              % (exit_a, exit_a / pipe_a, pipe_a, 100 * pipe_a / exit_a))
        print("wrote models/flow_fan_nozzle.stl, models/flow_fan_nozzle_render.png")
        return
    m = diffuser()
    assert m.status().name == "NoError", m.status()
    write_stl(os.path.join(OUT, "flow_diffuser.stl"), tris_of(m))
    render(m, os.path.join(OUT, "flow_diffuser_render.png"))
    bb = m.bounding_box()
    holes = 24 * math.pi * 1.3 ** 2 + 3 * math.pi * 1.0 ** 2
    print("diffuser: %.1f mm wide x %.1f mm tall, fits pipes %d-%d mm" % (bb[3] - bb[0], bb[5] - bb[2],
                                                                          STEPS[-1], STEPS[0]))
    print("spray holes %.0f mm2 vs %.0f mm2 for a %d mm pipe" % (holes, math.pi * (CH_R ** 2), STEPS[-1]))
    print("wrote models/flow_diffuser.stl, models/flow_diffuser_render.png")


if __name__ == "__main__":
    main()
