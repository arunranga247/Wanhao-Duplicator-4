"""
Fit check for ANY design - printability on the Duplicator 4, and fit between parts.

    python tools/fit_check.py part.stl                      one design: will it print well?
    python tools/fit_check.py box.stl pcb.stl lid.stl       assembly: do the parts collide?
        options: --supports 0/1  --brim 5  --scale 100  --out report.html  --no-open

One file  -> bed size and height, watertight mesh, separate pieces, overhangs that need
             supports, bed contact (sticking / tipping), walls thinner than 2 nozzle lines,
             tiny pieces.
Two+ files (exported in their ASSEMBLED positions, same origin) -> every pair of parts:
             overlap volume (must be 0) and the smallest gap.
Writes an interactive 3-D report (works offline) and prints a short summary:
    CHECK <OK|WARN|FAIL> <title>: <message>
    RESULT: <OK|WARN|FAIL> ...
    REPORT: <path to html>
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import base64
import json
import os
import struct
import sys
import webbrowser
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

try:
    import d4_paths
    OUT_DIR = d4_paths.OUT
except Exception:                                   # noqa: BLE001 - also usable stand-alone
    OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")

HERE = os.path.dirname(os.path.abspath(__file__))
BED_X, BED_Y, MAX_Z = 225.0, 145.0, 140.0           # Duplicator 4 build volume (mm)
MIN_WALL = 0.8                                      # 2 lines of a 0.4 mm nozzle
OVERHANG_COS = 0.707                                # steeper than 45 deg from vertical
PALETTE = ["#4b5260", "#2f6fdf", "#d9480f", "#2b8a3e", "#ae3ec9", "#e8a317", "#0c8599", "#c92a2a",
           "#5f3dc4", "#868e96"]


# ---- loading ----------------------------------------------------------------------------------
def load_stl(path):
    data = open(path, "rb").read()
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if 84 + 50 * n == len(data):
            rec = np.frombuffer(data[84:84 + 50 * n],
                                dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
            return rec["v"].reshape(-1, 3).astype(np.float64)
    pts = []
    for line in data.decode("utf-8", "replace").splitlines():
        s = line.strip().split()
        if len(s) == 4 and s[0] == "vertex":
            pts.append([float(s[1]), float(s[2]), float(s[3])])
    if not pts:
        raise ValueError("no triangles found")
    return np.array(pts, dtype=np.float64)


def load_obj(path):
    vs, soup = [], []
    for line in open(path, encoding="utf-8", errors="replace"):
        s = line.split()
        if not s:
            continue
        if s[0] == "v":
            vs.append([float(s[1]), float(s[2]), float(s[3])])
        elif s[0] == "f":
            idx = [int(t.split("/")[0]) for t in s[1:]]
            idx = [i - 1 if i > 0 else len(vs) + i for i in idx]
            for k in range(1, len(idx) - 1):                     # fan-triangulate polygons
                soup += [vs[idx[0]], vs[idx[k]], vs[idx[k + 1]]]
    return np.array(soup, dtype=np.float64)


def load_3mf(path):
    z = zipfile.ZipFile(path)
    soup = []
    for name in z.namelist():
        if not name.lower().endswith(".model"):
            continue
        root = ET.fromstring(z.read(name))
        ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
        objs = {}
        for ob in root.iter(ns + "object"):
            mesh = ob.find(ns + "mesh")
            comps = ob.find(ns + "components")
            if mesh is not None:
                v = np.array([[float(e.get("x")), float(e.get("y")), float(e.get("z"))]
                              for e in mesh.find(ns + "vertices")], dtype=np.float64)
                t = np.array([[int(e.get("v1")), int(e.get("v2")), int(e.get("v3"))]
                              for e in mesh.find(ns + "triangles")], dtype=np.int64)
                objs[ob.get("id")] = ("mesh", v, t)
            elif comps is not None:
                objs[ob.get("id")] = ("comp", [(c.get("objectid"), c.get("transform"))
                                               for c in comps.findall(ns + "component")])

        def mat(tr):
            if not tr:
                return np.eye(4)
            a = [float(x) for x in tr.split()]
            m = np.eye(4)
            m[:3, :3] = np.array(a[:9]).reshape(3, 3).T
            m[:3, 3] = a[9:12]
            return m

        def emit(oid, m, depth=0):
            o = objs.get(oid)
            if o is None or depth > 8:
                return
            if o[0] == "mesh":
                v = (np.c_[o[1], np.ones(len(o[1]))] @ m.T)[:, :3]
                soup.append(v[o[2]].reshape(-1, 3))
            else:
                for cid, tr in o[1]:
                    emit(cid, m @ mat(tr), depth + 1)

        build = root.find(ns + "build")
        items = build.findall(ns + "item") if build is not None else []
        for it in items:
            emit(it.get("objectid"), mat(it.get("transform")))
    if not soup:
        raise ValueError("no mesh found in the 3MF file")
    return np.vstack(soup)


def load_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".stl":
        soup = load_stl(path)
    elif ext == ".obj":
        soup = load_obj(path)
    elif ext == ".3mf":
        soup = load_3mf(path)
    else:
        raise ValueError("unsupported file type %s (use STL, 3MF or OBJ)" % ext)
    q = np.round(soup / 1e-4).astype(np.int64)                 # weld duplicate corners
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    V = uniq.astype(np.float64) * 1e-4
    T = inv.reshape(-1, 3)
    T = T[(T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])]    # drop slivers
    return V, T


def to_manifold(V, T):
    """Closed solid from the mesh, with overlapping shells merged into one (so hidden inner
    faces of overlapping pieces don't count as walls or overhangs). None if not watertight."""
    try:
        from manifold3d import Manifold, Mesh, OpType
        m = Manifold(Mesh(vert_properties=V.astype(np.float32), tri_verts=T.astype(np.uint32)))
        if m.status().name != "NoError" or m.is_empty():
            return None
        shells = m.decompose()
        return Manifold.batch_boolean(shells, OpType.Add) if len(shells) > 1 else m
    except Exception:                                          # noqa: BLE001
        return None


def mesh_of(M):
    g = M.to_mesh()
    return np.asarray(g.vert_properties)[:, :3].astype(np.float64), np.asarray(g.tri_verts).astype(np.int64)


# ---- per-part analysis ----------------------------------------------------------------------------
def face_geometry(V, T):
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    cr = np.cross(b - a, c - a)
    area2 = np.linalg.norm(cr, axis=1)
    n = cr / np.maximum(area2, 1e-12)[:, None]
    return a, b, c, n, area2 / 2


SMALL_SPAN = 3.0        # overhang spots no wider than this (holes, slots, short bridges) print fine


def overhang_islands(V, T, idx, area):
    """Group touching overhang faces into spots. Returns (area of spots that need support,
    area of narrow spots - round holes, slots, short bridges - that print fine without)."""
    if len(idx) == 0:
        return 0.0, 0.0
    parent = list(range(len(idx)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner = {}
    for k, f in enumerate(idx):
        for v in T[f]:
            j = owner.setdefault(int(v), k)
            if j != k:
                a, b = find(j), find(k)
                if a != b:
                    parent[a] = b
    groups = {}
    for k in range(len(idx)):
        groups.setdefault(find(k), []).append(idx[k])
    big = small = 0.0
    for faces in groups.values():
        xy = V[T[faces].ravel()][:, :2]
        xy = xy - xy.mean(axis=0)
        # true narrow width, whatever direction the spot runs (diagonal slots and holes too)
        _, vecs = np.linalg.eigh(np.cov(xy.T) + np.eye(2) * 1e-9) if len(xy) > 2 else (None, np.eye(2))
        span = min(np.ptp(xy @ vecs[:, 0]), np.ptp(xy @ vecs[:, 1]))
        if span <= SMALL_SPAN:
            small += float(area[faces].sum())
        else:
            big += float(area[faces].sum())
    return big, small


def analyze(V, T, M, supports, thin_samples=1500):
    a, b, c, n, area = face_geometry(V, T)
    z0 = V[:, 2].min()
    fmin = np.minimum(np.minimum(a[:, 2], b[:, 2]), c[:, 2])
    fmax = np.maximum(np.maximum(a[:, 2], b[:, 2]), c[:, 2])
    over = (n[:, 2] < -OVERHANG_COS) & (fmin > z0 + 0.3)
    contact = (n[:, 2] < -0.985) & (fmax < z0 + 0.05)
    # open / non-manifold edges
    e = np.sort(np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    big_area, small_area = overhang_islands(V, T, np.where(over)[0], area)
    r = {"open_edges": int((cnt == 1).sum()), "nonmanifold_edges": int((cnt > 2).sum()),
         "overhang_area": big_area, "overhang_small": small_area, "contact_area": float(area[contact].sum()),
         "watertight": M is not None, "bodies": [], "thin": [], "volume": None}
    if M is None:
        return r
    r["volume"] = float(M.volume())
    for body in M.decompose():
        bb = body.bounding_box()
        r["bodies"].append({"size": [bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]], "volume": body.volume()})
    # wall thickness: shoot rays inward from a sample of faces
    rng = np.random.default_rng(1)
    big = np.where(area > 0.02)[0]
    if len(big):
        pick = rng.choice(big, size=min(thin_samples, len(big)), replace=False,
                          p=area[big] / area[big].sum())
        cen = (a[pick] + b[pick] + c[pick]) / 3
        for i, p0 in zip(pick, cen):
            o = p0 - n[i] * 0.005
            end = p0 - n[i] * (MIN_WALL + 0.4)
            try:
                hits = M.ray_cast(o.tolist(), end.tolist())
            except Exception:                                  # noqa: BLE001
                break
            if hits:
                d = float(np.linalg.norm(np.array(hits[0].position) - p0))
                # a real wall: the far side faces the other way (not a bevel / countersink edge)
                facing = float(np.dot(np.array(hits[0].normal), n[i]))
                if 0.02 < d < MIN_WALL - 0.03 and facing < -0.85:
                    r["thin"].append([float(x) for x in p0] + [round(d, 2)])
    return r


def part_checks(name, V, r, supports, brim, scale):
    out = []
    size = (V.max(axis=0) - V.min(axis=0)) * scale / 100
    fx, fy = size[0] + 2 * brim, size[1] + 2 * brim
    fits = (fx <= BED_X and fy <= BED_Y) or (fy <= BED_X and fx <= BED_Y)
    out.append(("OK" if fits and size[2] <= MAX_Z else "FAIL", "Fits the printer",
                "%.1f x %.1f x %.1f mm%s (bed 225 x 145, height 140)" % (
                    size[0], size[1], size[2], " + %g mm brim" % brim if brim else "")
                + ("" if fits else " - TOO BIG for the bed") + ("" if size[2] <= MAX_Z else " - TOO TALL")))
    if max(size) < 3:
        out.append(("WARN", "Units", "the model is only %.2f mm - was it saved in cm or inches? "
                    "Use Scale to fix it" % max(size)))
    if r["watertight"]:
        out.append(("OK", "Watertight mesh", "closed solid - the slicer will read it cleanly"))
    else:
        out.append(("WARN", "Watertight mesh", "%d open edges, %d non-manifold edges - the slicer will try to "
                    "repair it; check the preview for missing walls" % (r["open_edges"], r["nonmanifold_edges"])))
    nb = len(r["bodies"])
    if nb > 1:
        out.append(("OK", "Separate pieces", "%d pieces in this file (they print together)" % nb))
    tiny = [bd for bd in r["bodies"] if min(bd["size"]) * scale / 100 < 1.0]
    if tiny:
        out.append(("WARN", "Tiny pieces", "%d piece(s) thinner than 1 mm - may not print or may break off"
                    % len(tiny)))
    oa = r["overhang_area"] * (scale / 100) ** 2
    sa = r.get("overhang_small", 0.0) * (scale / 100) ** 2
    small_note = (" (+ %.0f mm2 in small holes / slots / short bridges - those print fine)" % sa) if sa >= 1 else ""
    if oa < 50:
        out.append(("OK", "Overhangs", "no large overhangs - prints without supports%s" % small_note))
    elif supports:
        out.append(("OK", "Overhangs", "%.0f mm2 steeper than 45 deg - supports are ON%s" % (oa, small_note)))
    else:
        out.append(("WARN", "Overhangs", "%.0f mm2 steeper than 45 deg (red in the 3-D view) - "
                    "set Supports 1 or turn the part%s" % (oa, small_note)))
    ca = r["contact_area"] * (scale / 100) ** 2
    tip = size[2] / max(np.sqrt(max(ca, 1e-6)), 1e-6)
    if ca < 40:
        out.append(("WARN", "Bed contact", "only %.0f mm2 touches the bed - unheated bed: use a brim%s"
                    % (ca, " and expect it may tip over" if tip > 8 else "")))
    elif tip > 10:
        out.append(("WARN", "Bed contact", "%.0f mm2 base for a %.0f mm tall part - may wobble or tip; "
                    "add a brim" % (ca, size[2])))
    else:
        out.append(("OK", "Bed contact", "%.0f mm2 flat on the bed" % ca))
    if r["watertight"]:
        th = r["thin"]
        if th:
            out.append(("WARN", "Thin walls", "%d spot(s) thinner than %.1f mm (thinnest %.2f mm, marked in the "
                        "3-D view) - may print weak or vanish" % (len(th), MIN_WALL, min(t[3] for t in th))))
        else:
            out.append(("OK", "Thin walls", "no wall thinner than %.1f mm (2 nozzle lines)" % MIN_WALL))
    return out


# ---- report -----------------------------------------------------------------------------------
def b64(arr):
    return base64.b64encode(np.ascontiguousarray(arr).tobytes()).decode("ascii")


def write_report(path, title, mode, parts, checks, pairs, verdict, shift):
    tpl = open(os.path.join(HERE, "fit_view_template.html"), encoding="utf-8").read()
    vend = os.path.join(HERE, "vendor")
    three = open(os.path.join(vend, "three.min.js"), encoding="utf-8").read()
    orbit = open(os.path.join(vend, "OrbitControls.js"), encoding="utf-8").read()
    data = {"title": title, "mode": mode, "verdict": verdict, "checks": checks, "pairs": pairs,
            "bed": [BED_X, BED_Y], "parts": []}
    for p in parts:
        V = (p["V"] + shift).astype(np.float32)
        data["parts"].append({"name": p["name"], "color": p["color"], "v": b64(V),
                              "i": b64(p["T"].astype(np.uint32)), "thin": [
                                  [t[0] + shift[0], t[1] + shift[1], t[2] + shift[2], t[3]] for t in p["thin"]]})
    html = (tpl.replace("/*__THREE__*/", three).replace("/*__ORBIT__*/", orbit)
            .replace("__DATA__", json.dumps(data, separators=(",", ":"))))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--supports", type=float, default=0)
    ap.add_argument("--brim", type=float, default=5)
    ap.add_argument("--scale", type=float, default=100)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)

    parts = []
    for i, f in enumerate(a.files):
        f = os.path.abspath(f.strip('"'))
        if not os.path.isfile(f):
            print("CHECK FAIL File: not found: %s" % f)
            print("RESULT: FAIL - file not found")
            return 2
        try:
            V, T = load_any(f)
        except Exception as e:                               # noqa: BLE001
            print("CHECK FAIL File: %s could not be read (%s)" % (os.path.basename(f), e))
            print("RESULT: FAIL - unreadable file")
            return 2
        V = V * a.scale / 100
        M = to_manifold(V, T)
        if M is not None:
            V, T = mesh_of(M)                          # analyse + show the merged solid
        parts.append({"name": os.path.splitext(os.path.basename(f))[0], "file": f, "V": V, "T": T, "M": M,
                      "color": PALETTE[i % len(PALETTE)], "thin": []})

    checks, pairs = [], []
    mode = "single" if len(parts) == 1 else "assembly"
    if mode == "single":
        p = parts[0]
        r = analyze(p["V"], p["T"], p["M"], a.supports)
        p["thin"] = r["thin"][:400]
        for st, t, msg in part_checks(p["name"], p["V"], r, a.supports, a.brim, 100):
            checks.append({"status": st, "title": t, "msg": msg})
        lo, hi = p["V"].min(axis=0), p["V"].max(axis=0)
        shift = np.array([-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]])    # centred on the bed
    else:
        for p in parts:
            size = p["V"].max(axis=0) - p["V"].min(axis=0)
            if p["M"] is None:
                checks.append({"status": "WARN", "title": p["name"],
                               "msg": "mesh is not watertight - overlaps with it cannot be measured exactly"})
            else:
                checks.append({"status": "OK", "title": p["name"],
                               "msg": "%.1f x %.1f x %.1f mm, closed solid" % tuple(size)})
        for i in range(len(parts)):
            for j in range(i + 1, len(parts)):
                A, B = parts[i]["M"], parts[j]["M"]
                if A is None or B is None:
                    pairs.append({"a": parts[i]["name"], "b": parts[j]["name"], "overlap": None, "gap": None,
                                  "status": "WARN"})
                    continue
                ov = max(0.0, (A ^ B).volume())
                gap = A.min_gap(B, 10.0) if ov < 1e-3 else 0.0
                # touching (0 gap, no overlap) = parts resting on each other: fine
                st = "FAIL" if ov >= 1e-3 else ("TOUCH" if gap < 0.005 else ("WARN" if gap < 0.2 else "OK"))
                pairs.append({"a": parts[i]["name"], "b": parts[j]["name"], "overlap": round(ov, 3),
                              "gap": round(gap, 2), "status": st})
        allv = np.vstack([p["V"] for p in parts])
        lo, hi = allv.min(axis=0), allv.max(axis=0)
        shift = -(lo + hi) / 2
        shift[2] = -lo[2]

    statuses = [c["status"] for c in checks] + [("OK" if p["status"] == "TOUCH" else p["status"]) for p in pairs]
    verdict = "FAIL" if "FAIL" in statuses else ("WARN" if "WARN" in statuses else "OK")
    for c in checks:
        print("CHECK %s %s: %s" % (c["status"], c["title"], c["msg"]))
    for p in pairs:
        if p["overlap"] is None:
            print("PAIR WARN %s <-> %s: not measurable (open mesh)" % (p["a"], p["b"]))
        else:
            note = {"FAIL": " - COLLIDE", "TOUCH": " - touching (resting on each other)",
                    "WARN": " - tight (< 0.2 mm): fine for clips / press fits, else add clearance"}.get(p["status"], "")
            print("PAIR %s %s <-> %s: overlap %.3f mm3, gap %.2f mm%s" % (p["status"], p["a"], p["b"],
                                                                          p["overlap"], p["gap"], note))
    nfail = statuses.count("FAIL")
    nwarn = statuses.count("WARN")
    summary = {"OK": "everything fits and should print well", "WARN": "%d thing(s) to look at" % nwarn,
               "FAIL": "%d problem(s) must be fixed" % nfail}[verdict]
    print("RESULT: %s - %s" % (verdict, summary))

    title = parts[0]["name"] if mode == "single" else "%d-part assembly" % len(parts)
    out = a.out or os.path.join(OUT_DIR, "fitcheck_%s.html" % "".join(
        ch for ch in title.replace(" ", "_") if ch.isalnum() or ch in "_-")[:40])
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    write_report(out, title, mode, parts, checks, pairs, verdict, shift)
    print("REPORT: %s" % out)
    if not a.no_open:
        webbrowser.open("file:///" + os.path.abspath(out).replace("\\", "/"))
    return 0 if verdict != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
