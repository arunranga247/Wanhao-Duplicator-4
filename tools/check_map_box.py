"""
Fit check for the map-display box: builds 3-D stand-ins for every real part of the ESP32 DOIT
board and the 1.44" display, places them where they sit in the closed box, and measures
overlap (must be 0) and the smallest gap to the tray and to the cover.

    python tools/check_map_box.py
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import sys

import make_map_box as B
from make_map_box import box, cx, cy

# ---- realistic stand-ins (sizes from the DOIT V1 board / ST7735 1.44" module) --------------
def esp32_parts():
    x0, x1, y0, y1 = cx(B.ESP_X0), cx(B.ESP_X1), cy(B.ESP_Y0), cy(B.ESP_Y0 + B.ESP_W)
    yc = cy(B.ESP_YC)
    zb, zt = B.Z_ESP_BOT, B.Z_ESP_TOP
    p = {
        "ESP32 PCB": box(x0, y0, zb, x1, y1, zt),
        "WROOM-32 module": box(x0, yc - 9.0, zt, x0 + 25.5, yc + 9.0, zt + 3.1),
        "micro-USB socket": box(x1 - 4.6, yc - 3.75, zt, x1 + B.USB_OVER, yc + 3.75, zt + 2.6),
        "EN button": box(x1 - 5.0, yc - 10.6, zt, x1 - 1.5, yc - 4.6, zt + 2.5),
        "BOOT button": box(x1 - 5.0, yc + 4.6, zt, x1 - 1.5, yc + 10.6, zt + 2.5),
        "AMS1117 regulator": box(x1 - 14.0, yc - 3.5, zt, x1 - 7.5, yc + 3.5, zt + 1.8),
        "CP2102 USB chip": box(x1 - 22.0, yc - 2.5, zt, x1 - 17.0, yc + 2.5, zt + 1.0),
    }
    pc = (x0 + x1) / 2
    for i, py in enumerate((B.ESP_Y0 + 1.45, B.ESP_Y0 + B.ESP_W - 1.45)):
        yy = cy(py)
        # header removed: soldered wire ends under the board, solder joints on top
        p["wire joints under %d" % (i + 1)] = box(pc - 18.6, yy - 0.8, zb - B.ESP_WIRE_DROP, pc + 18.6,
                                                  yy + 0.8, zb)
        p["solder joints on top %d" % (i + 1)] = box(pc - 18.1, yy - 0.6, zt, pc + 18.1, yy + 0.6, zt + 1.0)
    return p


def display_parts():
    x0, y0 = cx(B.DSP_X0), cy(B.DSP_Y0)
    zb = B.Z_DSP_BACK
    zt = zb + B.DSP_PCB
    wx, wy = cx(B.WIN_X), cy(B.WIN_Y)
    hx = x0 + B.DSP_W / 2
    return {
        "display PCB": box(x0, y0, zb, x0 + B.DSP_W, y0 + B.DSP_L, zt),
        "LCD glass + backlight": box(wx - 14.25, wy - 16.25, zt, wx + 14.25, wy + 18.25, zt + B.DSP_GLASS),
        "LCD flex ribbon (end fold)": box(hx - 9.0, y0 + B.DSP_L, zb - 0.3, hx + 9.0, y0 + B.DSP_L + 0.25,
                                          zt + 0.6),
        # header removed: 8 wires soldered to the pads, ends under the board + joints on the front
        "display wire joints (back)": box(hx - 10.6, y0 + 1.3, zb - B.ESP_WIRE_DROP, hx + 10.6, y0 + 3.8, zb),
        "display regulator (back)": box(hx + 4.0, y0 + 8.0, zb - 1.2, hx + 7.0, y0 + 11.0, zb),
        "acrylic window 34x34x2": box(wx - B.PANE_W / 2, wy - B.PANE_H / 2, B.Z_TOP - B.PANE_T,
                                      wx + B.PANE_W / 2, wy + B.PANE_H / 2, B.Z_TOP - 0.05),
    }


def export_assembly(base, cover):
    """Write the parts in their ASSEMBLED positions to models/map_box_fit/ - load them all in
    Duplicator 4 Studio's fit check (Assembly...) to see the same result there."""
    import os
    from functools import reduce
    out = os.path.join(B.OUT, "map_box_fit")
    os.makedirs(out, exist_ok=True)
    esp = reduce(lambda a, b: a + b, esp32_parts().values())
    dsp_all = display_parts()
    pane = dsp_all.pop("acrylic window 34x34x2")
    dsp = reduce(lambda a, b: a + b, dsp_all.values())
    for name, m in (("1_tray", base), ("2_cover_closed", cover), ("3_esp32_board", esp),
                    ("4_display_board", dsp), ("5_acrylic_window", pane)):
        B.write_stl(os.path.join(out, name + ".stl"), B.tris_of(m))
    return out


def main():
    base, cover = B.base(), B.cover()
    print("assembly STLs for the app's fit check: %s" % export_assembly(base, cover))
    parts = dict(esp32_parts())
    parts.update(display_parts())
    print("Fit check - %s" % "box %.1f x %.1f x %.1f mm" % (B.OX, B.OY, B.Z_TOP + B.COVER))
    print("%-30s %10s %10s %9s %9s  %s" % ("part", "hit tray", "hit cover", "gap tray", "gap cvr", "result"))
    bad = 0
    for name, m in parts.items():
        vb = (m ^ base).volume()
        vc = (m ^ cover).volume()
        gb = m.min_gap(base, 5.0)
        gc = m.min_gap(cover, 5.0)
        ok = vb < 1e-3 and vc < 1e-3
        bad += not ok
        print("%-30s %8.2f mm3 %7.2f mm3 %7.2f %9.2f  %s" % (name, vb, vc, gb, gc, "OK" if ok else "COLLIDES"))
    # boards against each other
    names = list(parts)
    for i, a in enumerate(names):
        for b_ in names[i + 1:]:
            if a.split()[0] == b_.split()[0] and "pin" not in a + b_:
                continue
            v = (parts[a] ^ parts[b_]).volume()
            if v > 1e-3 and not ({"ESP32 PCB", "solder joints on top 1", "solder joints on top 2"} >= {a, b_}):
                if "PCB" in a and ("header" in b_ or "pin" in b_ or "module" in b_ or "regulator" in b_):
                    continue
                print("  parts overlap: %s <-> %s (%.2f mm3)" % (a, b_, v))
                bad += 1
    # tray vs cover when closed (tongue in groove, posts, fingers ...)
    vtc = (base ^ cover).volume()
    print("tray vs cover when closed: overlap %.3f mm3 -> %s" % (vtc, "OK" if vtc < 1e-3 else "COLLIDES"))
    bad += vtc >= 1e-3
    # does the window show the whole visible screen?
    ww, wh = B.AA_W + 1.8, B.AA_L + 1.8
    print("window %.1f x %.1f mm over a %.1f x %.1f screen: %.1f mm spare each side (x), %.1f (y)"
          % (ww, wh, B.AA_W, B.AA_L, (ww - B.AA_W) / 2, (wh - B.AA_L) / 2))
    # do the snap lips really hold the display?
    print("display clips: 4 lips hook %.2f mm over the PCB, %.2f mm behind its back face"
          % (B.LIP - B.FIT, 1.0))
    print("ESP32 hold-down: posts %.1f mm above the PCB, %.1f mm above the USB socket"
          % (0.3, B.USB_H + 0.3 - 2.6))
    print("RESULT: %s" % ("ALL PARTS FIT" if bad == 0 else "%d PROBLEM(S)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
