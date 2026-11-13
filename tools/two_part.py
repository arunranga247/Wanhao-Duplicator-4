"""
Two parts, two colours, one print: lays two models out side by side on the Duplicator 4 bed with a
purge tower next to them, and writes a PrusaSlicer project (.3mf) in which part 1 belongs to
extruder 1 and part 2 to extruder 2.

    from two_part import layout, write_3mf
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import zipfile

import numpy as np

from fit_check import load_any

BED_W, BED_D = 225.0, 145.0
EDGE = 5.0                      # keep this far from the bed edges
TOWER_W, TOWER_D = 15.0, 18.0   # purge tower footprint reserved on the bed (it is usually smaller)


class LayoutError(Exception):
    pass


def load_part(path, scale_pct=100.0):
    """Mesh of one part, scaled, standing on the bed with its min corner at the origin."""
    V, T = load_any(path)
    if len(T) == 0:
        raise LayoutError("%s has no triangles" % path)
    V = V * (scale_pct / 100.0)
    V = V - V.min(axis=0)
    return V, T


def layout(sizes, brim=5.0):
    """Where to put two parts (+ the purge tower) on the bed.

    sizes: [(width, depth), (width, depth)] in mm.  -> dict(parts=[(x, y), (x, y)], tower=(x, y),
    rows=1|2). Positions are the parts' min corners in bed coordinates (0..225 x 0..145).
    Side by side if it fits, otherwise part 2 behind part 1. Brims never touch each other."""
    gap = 2 * max(0.0, brim) + 4.0
    (w1, d1), (w2, d2) = sizes
    cx, cy = BED_W / 2, BED_D / 2
    # 1) side by side:  [part 1] gap [part 2] gap [tower]
    total = w1 + gap + w2 + gap + TOWER_W
    if total <= BED_W - 2 * EDGE and max(d1, d2, TOWER_D) <= BED_D - 2 * EDGE:
        x = cx - total / 2
        parts = [(x, cy - d1 / 2), (x + w1 + gap, cy - d2 / 2)]
        tower = (x + w1 + gap + w2 + gap, cy - TOWER_D / 2)
        return {"parts": parts, "tower": tower, "rows": 1, "gap": gap}
    # 2) one behind the other, tower on the right
    width = max(w1, w2) + gap + TOWER_W
    depth = d1 + gap + d2
    if width <= BED_W - 2 * EDGE and depth <= BED_D - 2 * EDGE:
        x = cx - width / 2
        y = cy - depth / 2
        parts = [(x, y), (x, y + d1 + gap)]
        tower = (x + max(w1, w2) + gap, cy - TOWER_D / 2)
        return {"parts": parts, "tower": tower, "rows": 2, "gap": gap}
    raise LayoutError("the two parts are too big to print together (%.0f x %.0f and %.0f x %.0f mm on a "
                      "225 x 145 mm bed) - print them one at a time or lower the Scale" % (w1, d1, w2, d2))


def _mesh_xml(V, T, oid):
    vs = "".join('<vertex x="%.5f" y="%.5f" z="%.5f"/>' % (v[0], v[1], v[2]) for v in V)
    ts = "".join('<triangle v1="%d" v2="%d" v3="%d"/>' % (t[0], t[1], t[2]) for t in T)
    return '<object id="%d" type="model"><mesh><vertices>%s</vertices><triangles>%s</triangles></mesh></object>' \
        % (oid, vs, ts)


def write_3mf(path1, path2, out, scale_pct=100.0, brim=5.0):
    """Write the two-part PrusaSlicer project. -> the layout dict (+ 'sizes')."""
    meshes = [load_part(path1, scale_pct), load_part(path2, scale_pct)]
    sizes = [(float(V[:, 0].max()), float(V[:, 1].max())) for V, T in meshes]
    lay = layout(sizes, brim)
    lay["sizes"] = sizes
    lay["heights"] = [float(V[:, 2].max()) for V, T in meshes]
    objs, items, cfg = [], [], ['<?xml version="1.0" encoding="utf-8"?>\n<config>']
    for i, ((V, T), (ox, oy)) in enumerate(zip(meshes, lay["parts"]), start=1):
        objs.append(_mesh_xml(V, T, i))
        items.append('<item objectid="%d" transform="1 0 0 0 1 0 0 0 1 %.4f %.4f 0" printable="1"/>' % (i, ox, oy))
        cfg.append('<object id="%d" instances_count="1"><metadata type="object" key="name" value="part %d"/>'
                   '<metadata type="object" key="extruder" value="%d"/><volume firstid="0" lastid="%d">'
                   '<metadata type="volume" key="name" value="part %d"/></volume></object>' % (i, i, i, len(T) - 1, i))
    cfg.append("</config>")
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
             'xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">\n'
             '<metadata name="slic3rpe:Version3mf">1</metadata>\n<resources>%s</resources>\n<build>%s</build>\n'
             '</model>' % ("".join(objs), "".join(items)))
    tx, ty = lay["tower"]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.'
                   'openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType='
                   '"application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats'
                   '.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type='
                   '"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/Slic3r_PE_model.config", "\n".join(cfg))
        # PrusaSlicer 2.9 reads the purge-tower position from here (not from the command line)
        z.writestr("Metadata/Prusa_Slicer_wipe_tower_information.xml",
                   '<?xml version="1.0" encoding="utf-8"?>\n<wipe_tower_information bed_idx="0" '
                   'position_x="%.3f" position_y="%.3f" rotation_deg="0"/>\n' % (tx, ty))
    return lay


def slicer_options(temp, first_temp, tower=True):
    """PrusaSlicer command-line options for two extruders (nozzle offset is handled later in
    gcode2x3g, so the slicer sees both nozzles at the same place)."""
    opts = ["--nozzle-diameter", "0.4,0.4", "--filament-diameter", "1.75,1.75",
            "--temperature", "%d,%d" % (temp, temp), "--first-layer-temperature", "%d,%d" % (first_temp, first_temp),
            "--extruder-offset", "0x0,0x0", "--retract-length", "1,1",
            "--retract-length-toolchange", "4,4",              # gentle: this printer's extruders
            "--single-extruder-multi-material-priming=0",       # no prime lines at the bed edge
            "--dont-arrange"]
    if tower:
        opts += ["--wipe-tower", "--wipe-tower-width", "%g" % TOWER_W, "--wiping-volumes-matrix", "0,25,25,0",
                 "--wipe-tower-no-sparse-layers"]
    return opts
