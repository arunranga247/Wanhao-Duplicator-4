"""
Quick shaded picture of a 3D model (STL / 3MF / OBJ) - shown in the Prepare tab as soon as a
model is chosen, before anything is sliced.

    python tools/model_preview.py model.stl [--out picture.png] [--bg #rrggbb]

Fast enough for big meshes (numpy maths + one PIL polygon per triangle, far ones first).
Also reports size, triangle count and whether it fits the Duplicator 4 bed.
"""

__author__ = "ARUN"
__copyright__ = "Copyright (c) 2026 ARUN"

import argparse
import os

import numpy as np
from PIL import Image, ImageDraw

from fit_check import load_any

BED_X, BED_Y, BED_Z = 225.0, 145.0, 140.0
MAX_TRIS = 400000                       # above this, draw an even sample (preview only)
MODEL_RGB = np.array([235, 140, 45], dtype=np.float64)         # orange, like most slicers


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def model_info(V):
    lo, hi = V.min(axis=0), V.max(axis=0)
    size = hi - lo
    fits = size[0] <= BED_X and size[1] <= BED_Y and size[2] <= BED_Z
    turned = (not fits) and size[1] <= BED_X and size[0] <= BED_Y and size[2] <= BED_Z
    return size, fits, turned


def _raster(sx, sy, sd, W, H, budget=3000000):
    """Z-buffer rasteriser in numpy. sx, sy, sd: (n, 3) screen x / y / depth per corner.
    Triangles are grouped by bounding-box size so each group is tested in one vector step."""
    zbuf = np.full(W * H, np.inf)
    ibuf = np.full(W * H, -1, dtype=np.int64)
    ax, bx, cx = sx[:, 0], sx[:, 1], sx[:, 2]
    ay, by, cy = sy[:, 0], sy[:, 1], sy[:, 2]
    den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    x0 = np.floor(sx.min(axis=1)).astype(np.int64)
    y0 = np.floor(sy.min(axis=1)).astype(np.int64)
    x1 = np.ceil(sx.max(axis=1)).astype(np.int64)
    y1 = np.ceil(sy.max(axis=1)).astype(np.int64)
    good = (np.abs(den) > 1e-9) & (x1 >= 0) & (y1 >= 0) & (x0 < W) & (y0 < H)
    x0, y0 = np.clip(x0, 0, W - 1), np.clip(y0, 0, H - 1)
    x1, y1 = np.clip(x1, 0, W - 1), np.clip(y1, 0, H - 1)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    # bucket by box size (powers of two) -> fixed-size test grids
    bwb = np.left_shift(1, np.ceil(np.log2(np.maximum(bw, 1))).astype(np.int64))
    bhb = np.left_shift(1, np.ceil(np.log2(np.maximum(bh, 1))).astype(np.int64))
    key = bwb * 100000 + bhb
    big = good & (bwb * bhb > 4096)
    good = good & ~big

    def store(pix, dep, tri):
        o = np.lexsort((dep, pix))                            # per pixel, nearest first
        pix, dep, tri = pix[o], dep[o], tri[o]
        first = np.ones(len(pix), dtype=bool)
        first[1:] = pix[1:] != pix[:-1]
        pix, dep, tri = pix[first], dep[first], tri[first]
        better = dep < zbuf[pix]
        zbuf[pix[better]] = dep[better]
        ibuf[pix[better]] = tri[better]

    # large triangles: fill row spans (cost = pixels covered, not the bounding box)
    acc_p, acc_d, acc_t, acc_n = [], [], [], 0
    for i in np.nonzero(big)[0]:
        ys = np.arange(y0[i], y1[i] + 1)
        yc = ys + 0.5
        lo = np.full(len(ys), np.inf)
        hi = np.full(len(ys), -np.inf)
        for (px, py), (qx, qy) in (((ax[i], ay[i]), (bx[i], by[i])), ((bx[i], by[i]), (cx[i], cy[i])),
                                   ((cx[i], cy[i]), (ax[i], ay[i]))):
            if py == qy:
                continue
            m = (yc >= min(py, qy)) & (yc <= max(py, qy))
            xe = px + (yc - py) * (qx - px) / (qy - py)
            lo = np.where(m, np.minimum(lo, xe), lo)
            hi = np.where(m, np.maximum(hi, xe), hi)
        ok = np.isfinite(lo)
        xa = np.clip(np.ceil(lo[ok] - 0.5), 0, W - 1).astype(np.int64)
        xb = np.clip(np.floor(hi[ok] - 0.5), 0, W - 1).astype(np.int64)
        ys = ys[ok]
        cnt = np.maximum(xb - xa + 1, 0)
        if cnt.sum() == 0:
            continue
        rows = np.repeat(ys, cnt)
        start = np.repeat(xa, cnt)
        offs = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        xs = start + offs
        pxc, pyc = xs + 0.5, rows + 0.5
        w0 = ((by[i] - cy[i]) * (pxc - cx[i]) + (cx[i] - bx[i]) * (pyc - cy[i])) / den[i]
        w1 = ((cy[i] - ay[i]) * (pxc - cx[i]) + (ax[i] - cx[i]) * (pyc - cy[i])) / den[i]
        acc_p.append(rows * W + xs)
        acc_d.append(w0 * sd[i, 0] + w1 * sd[i, 1] + (1 - w0 - w1) * sd[i, 2])
        acc_t.append(np.full(len(xs), i, dtype=np.int64))
        acc_n += len(xs)
        if acc_n > budget:
            store(np.concatenate(acc_p), np.concatenate(acc_d), np.concatenate(acc_t))
            acc_p, acc_d, acc_t, acc_n = [], [], [], 0
    if acc_p:
        store(np.concatenate(acc_p), np.concatenate(acc_d), np.concatenate(acc_t))

    for k in np.unique(key[good]):
        idx = np.nonzero(good & (key == k))[0]
        BW, BH = int(k // 100000), int(k % 100000)
        step = max(1, budget // (BW * BH))
        gx_off = np.arange(BW)[None, None, :]
        gy_off = np.arange(BH)[None, :, None]
        for s in range(0, len(idx), step):
            t = idx[s:s + step]
            gx = x0[t][:, None, None] + gx_off                # (n, 1, BW)
            gy = y0[t][:, None, None] + gy_off                # (n, BH, 1)
            px, py = gx + 0.5, gy + 0.5
            A = lambda v: v[t][:, None, None]                 # noqa: E731
            dn = A(den)
            w0 = ((A(by) - A(cy)) * (px - A(cx)) + (A(cx) - A(bx)) * (py - A(cy))) / dn
            w1 = ((A(cy) - A(ay)) * (px - A(cx)) + (A(ax) - A(cx)) * (py - A(cy))) / dn
            w2 = 1.0 - w0 - w1
            e = -1e-4
            inside = (w0 >= e) & (w1 >= e) & (w2 >= e) & (gx <= A(x1)) & (gy <= A(y1))
            if not inside.any():
                continue
            dep = (w0 * A(sd[:, 0]) + w1 * A(sd[:, 1]) + w2 * A(sd[:, 2]))[inside]
            ti, yy, xx = np.nonzero(inside)
            store((y0[t][ti] + yy) * W + (x0[t][ti] + xx), dep, t[ti])
    return ibuf


class Scene:
    """A model loaded once, ready to be drawn from any angle (the Prepare-tab 3D viewer)."""
    tri_rgb = None                      # per-triangle colours (two-part prints), else orange

    def __init__(self, path):
        V, T = load_any(path)
        if len(T) == 0:
            raise ValueError("the file has no triangles")
        self.size, self.fits, self.turned = model_info(V)
        self.n_tris = len(T)
        if len(T) > MAX_TRIS:
            T = T[np.linspace(0, len(T) - 1, MAX_TRIS).astype(np.int64)]
        lo, hi = V.min(axis=0), V.max(axis=0)
        self.P = V - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])   # on the bed, centred
        tri = self.P[T]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        ln = np.linalg.norm(n, axis=1)
        ok = ln > 1e-12
        self.T, self.n = T[ok], n[ok] / ln[ok, None]
        self.zc = self.size[2] / 2
        self.radius = max(float(np.linalg.norm(self.size)) / 2, 1e-3)     # fits every view angle
        lo2, hi2 = self.P.min(axis=0), self.P.max(axis=0)
        self.footprint = np.array([[lo2[0], lo2[1], 0], [hi2[0], lo2[1], 0],
                                   [hi2[0], hi2[1], 0], [lo2[0], hi2[1], 0]])
        txt = "%.1f × %.1f × %.1f mm  ·  %s triangles" % (
            self.size[0], self.size[1], self.size[2], format(self.n_tris, ","))
        if self.fits:
            txt += "  ·  fits the bed"
        elif self.turned:
            txt += "  ·  fits if turned 90° (Y is only 145 mm)"
        else:
            txt += "  ·  TOO BIG for the bed (225 × 145 × 140 mm) - lower Scale %"
        self.info = txt

    def image(self, W, H, yaw=-35.0, pitch=28.0, zoom=1.0, bg="#d6d9df", S=2, outlines=True, fast=False):
        """PIL image W x H of the model seen from (yaw, pitch) degrees; zoom 1 = whole model.
        S = supersampling (2 = smooth edges). fast=True: quick frame while the mouse drags
        (back faces skipped, no outlines, drawn smaller and stretched)."""
        if fast:
            k = 0.5 if self.n_tris < 60000 else 0.33
            small = self._image(W * k, H * k, yaw, pitch, zoom, bg, 1, False, True)
            return small.resize((max(16, int(W)), max(16, int(H))), Image.BILINEAR)
        return self._image(W, H, yaw, pitch, zoom, bg, S, outlines, False)

    def _image(self, W, H, yaw, pitch, zoom, bg, S, outlines, _cull):
        W, H = max(16, int(W)), max(16, int(H))
        a, b = np.radians(yaw), np.radians(pitch)
        Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        Rx = np.array([[1, 0, 0], [0, np.cos(b), -np.sin(b)], [0, np.sin(b), np.cos(b)]])
        R = Rx @ Rz
        zc = self.zc
        WS, HS = W * S, H * S
        sc = zoom * 0.92 * min(W, H) / (2 * self.radius) * S

        def cam(pts):                                         # -> screen x, screen y (pixels), depth
            q = (np.asarray(pts, dtype=np.float64) - [0, 0, zc]) @ R.T
            return WS / 2 + q[:, 0] * sc, HS / 2 - q[:, 2] * sc, q[:, 1]

        img = Image.new("RGB", (WS, HS), _hex(bg))
        d = ImageDraw.Draw(img)
        bgc = np.array(_hex(bg), dtype=np.float64)
        dark_bg = bgc.mean() < 128
        bed_fill = tuple(int(v) for v in (bgc * 0.85 + (40 if dark_bg else 0)))
        bed_line = tuple(int(v) for v in (bgc * 0.6 + (90 if dark_bg else 0)))
        hx, hy = BED_X / 2, BED_Y / 2
        x, y, _ = cam([[-hx, -hy, 0], [hx, -hy, 0], [hx, hy, 0], [-hx, hy, 0]])
        d.polygon(list(zip(x, y)), fill=bed_fill, outline=bed_line)
        for gx in np.arange(-hx, hx + 0.1, 25.0):            # bed grid every 25 mm
            x, y, _ = cam([[gx, -hy, 0], [gx, hy, 0]])
            d.line(list(zip(x, y)), fill=bed_line, width=S)
        for gy in np.arange(-hy, hy + 0.1, 25.0):
            x, y, _ = cam([[-hx, gy, 0], [hx, gy, 0]])
            d.line(list(zip(x, y)), fill=bed_line, width=S)
        if pitch > 0:                                         # footprint shadow (seen from above)
            x, y, _ = cam(self.footprint)
            d.polygon(list(zip(x, y)), fill=tuple(int(v * 0.8) for v in bed_fill))

        # triangles: flat shading, depth buffer (nearest surface wins at every pixel)
        nc = self.n @ R.T                                     # normals in camera space
        facing = nc[:, 1] < 0                                 # camera looks along +y'
        light = np.array([-0.4, -0.75, 0.55])                 # light moves with the camera
        light /= np.linalg.norm(light)
        shade = 0.32 + 0.68 * np.abs(nc @ light)              # two-sided: open meshes still look right
        shade = np.where(facing, shade, shade * 0.55)         # inside faces seen through holes: darker
        base = self.tri_rgb if self.tri_rgb is not None else MODEL_RGB[None, :]
        cols = np.clip(base * shade[:, None], 0, 255).astype(np.uint8)
        vx, vy, vd = cam(self.P)
        if _cull:                                             # quick frame: only faces turned to us
            sel = np.nonzero(facing)[0]
            ib = _raster(vx[self.T[sel]], vy[self.T[sel]], vd[self.T[sel]], WS, HS)
            ibuf = np.where(ib >= 0, sel[np.maximum(ib, 0)], -1)
        else:
            ibuf = _raster(vx[self.T], vy[self.T], vd[self.T], WS, HS)

        pic = np.asarray(img).reshape(-1, 3).copy()
        hit = ibuf >= 0
        pic[hit] = cols[ibuf[hit]]
        pic = pic.reshape(HS, WS, 3)
        if outlines:                                          # silhouette + sharp creases darker
            nrm = np.zeros((HS * WS, 3), dtype=np.float32)
            nrm[hit] = nc[ibuf[hit]]
            nrm = nrm.reshape(HS, WS, 3)
            hit2 = hit.reshape(HS, WS)
            edge = np.zeros((HS, WS), dtype=bool)
            for dy, dx in ((0, 1), (1, 0)):
                a_n, b_n = nrm[:HS - dy, :WS - dx], nrm[dy:, dx:]
                a_h, b_h = hit2[:HS - dy, :WS - dx], hit2[dy:, dx:]
                e = (a_h & b_h & ((a_n * b_n).sum(axis=2) < 0.82)) | (a_h != b_h)
                edge[:HS - dy, :WS - dx] |= e
                edge[dy:, dx:] |= e & b_h
            m = edge & hit2
            pic[m] = (pic[m] * 0.55).astype(np.uint8)
        img = Image.fromarray(pic, "RGB")
        return img.resize((W, H), Image.LANCZOS) if S > 1 else img


class PartsScene(Scene):
    """Two parts for a two-colour print, laid out exactly as the slicer will place them
    (two_part.layout): part 1 blue (left nozzle), part 2 red (right nozzle), purge tower grey."""
    PART_RGB = (np.array([66.0, 133.0, 244.0]), np.array([234.0, 67.0, 53.0]))
    TOWER_RGB = np.array([150.0, 150.0, 150.0])

    def __init__(self, path1, path2, scale_pct=100.0, brim=5.0):
        import two_part
        meshes = [two_part.load_part(p, scale_pct) for p in (path1, path2)]
        sizes = [(float(V[:, 0].max()), float(V[:, 1].max())) for V, T in meshes]
        heights = [float(V[:, 2].max()) for V, T in meshes]
        try:
            lay = two_part.layout(sizes, brim)
        except two_part.LayoutError as e:
            raise ValueError(str(e))
        Vs, Ts, cols, off = [], [], [], 0
        for (V, T), (ox, oy), rgb in zip(meshes, lay["parts"], self.PART_RGB):
            Vs.append(V + [ox, oy, 0.0])
            Ts.append(T + off)
            cols.append(np.repeat(rgb[None, :], len(T), axis=0))
            off += len(V)
        tx, ty = lay["tower"]                                 # purge tower: as tall as the shorter part
        th = max(1.0, min(heights))
        box = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
        box = box * [two_part.TOWER_W, 6.0, th] + [tx, ty + two_part.TOWER_D / 2 - 3.0, 0]
        bt = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                       [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
        Vs.append(box)
        Ts.append(bt + off)
        cols.append(np.repeat(self.TOWER_RGB[None, :], len(bt), axis=0))
        V = np.vstack(Vs)
        T = np.vstack(Ts)
        rgb = np.vstack(cols)
        self.n_tris = len(T)
        self.P = V - np.array([two_part.BED_W / 2, two_part.BED_D / 2, 0.0])     # bed centre = origin
        tri = self.P[T]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        ln = np.linalg.norm(n, axis=1)
        ok = ln > 1e-12
        self.T, self.n, self.tri_rgb = T[ok], n[ok] / ln[ok, None], rgb[ok]
        lo, hi = self.P.min(axis=0), self.P.max(axis=0)
        self.size = hi - lo
        self.fits, self.turned = True, False
        self.center = (lo + hi) / 2
        self.zc = float(self.center[2])
        self.radius = max(float(np.linalg.norm(self.size)) / 2, 1e-3)
        self.footprint = np.array([[lo[0], lo[1], 0], [hi[0], lo[1], 0], [hi[0], hi[1], 0], [lo[0], hi[1], 0]])
        (w1, d1), (w2, d2) = sizes
        self.info = ("Part 1 · left nozzle (blue): %.1f × %.1f × %.1f mm   ·   Part 2 · right nozzle (red): "
                     "%.1f × %.1f × %.1f mm   ·   %s + purge tower (grey)"
                     % (w1, d1, heights[0], w2, d2, heights[1], "side by side" if lay["rows"] == 1 else "one behind the other"))


def render(path, out, W=960, H=720, bg="#d6d9df", yaw_deg=-35.0, pitch_deg=28.0):
    """Render `path` to `out` (PNG). Returns a one-line description."""
    sc = Scene(path)
    img = sc.image(W, H, yaw_deg, pitch_deg, bg=bg)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out)
    return sc.info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--out", default=None)
    ap.add_argument("--bg", default="#d6d9df")
    a = ap.parse_args()
    out = a.out or os.path.splitext(a.model)[0] + "_preview.png"
    print(render(a.model, out, bg=a.bg))
    print("-> %s" % out)


if __name__ == "__main__":
    main()
