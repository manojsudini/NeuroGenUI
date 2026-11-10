"""Generate the HELD-OUT sketch set (20 screens) in a harsher hand-drawn style than the dev set.

    python dataset/holdout/tools/make_sketches_holdout.py            # all 20
    python dataset/holdout/tools/make_sketches_holdout.py hold_login_01

Reuses the dev layout engine and component renderers (dataset/tools/make_sketches.py) but swaps in a rougher
pen (HPen), three handwriting fonts the dev set never used, and a harsher "photo of paper" finish:
  * stronger drift/jitter, per-stroke pen width 0.6x-1.9x, pressure drop-outs, slanted lines (+-2 deg),
    long overshoots, unclosed rectangles (a missing/short side or a gap in the loop), re-stroked edges,
  * glyphs with bigger rotation/size/baseline jitter and a sloped baseline,
  * scratch-out corrections (zigzag scribbles) and stray re-traced lines placed in free space,
  * whole-page rotation of 1-3 degrees plus a mild perspective warp, uneven lighting gradient, shadow,
    fibre noise, specks, blur and a JPEG round trip.
Ground-truth boxes are pushed through the same homography, so they stay exact.
Deterministic: seed = sha256(id).
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "tools"))
import make_sketches as MS  # noqa: E402
from make_sketches import SS, W  # noqa: E402
from specs_holdout import SCREENS  # noqa: E402

GENERATOR = "make_sketches_holdout.py v1 (harsh style)"
ROOT = HERE.parent                        # dataset/holdout
FONTS = HERE / "fonts"
FONT_CHOICES = [("IndieFlower-Regular.ttf", 1.00), ("Kalam-Regular.ttf", 1.00), ("ShadowsIntoLight.ttf", 1.25)]
INKS = [(25, 30, 45), (20, 45, 120), (45, 45, 50), (10, 10, 10), (60, 40, 110), (30, 80, 60)]


class HCtx(MS.Ctx):
    def __init__(self, sid):
        seed = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16)
        self.rng = np.random.default_rng(seed)
        fname, mult = FONT_CHOICES[seed % len(FONT_CHOICES)]
        self.font_file = str(FONTS / fname)
        self.font_mult = mult
        self.font_name = fname
        self._fonts = {}


class HPen(MS.Pen):
    def __init__(self, ctx, size):
        super().__init__(ctx, size)
        self.base_w = float(self.rng.uniform(2.2, 3.6))
        self.tilt = float(self.rng.normal(0, 0.012))     # baseline slope of handwriting

    # ---- rougher stroke
    def stroke(self, pts, wobble=1.0, width=None, jitter=0.45, pressure=True):
        pts = np.asarray(pts, float)
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        L = seg.sum()
        if L < 1:
            return
        rng = self.rng
        n = max(4, int(L / 5))
        cum = np.concatenate([[0], np.cumsum(seg)])
        s = np.linspace(0, L, n)
        xs, ys = np.interp(s, cum, pts[:, 0]), np.interp(s, cum, pts[:, 1])
        dx, dy = np.gradient(xs), np.gradient(ys)
        nl = np.hypot(dx, dy) + 1e-9
        nx, ny = -dy / nl, dx / nl
        amp = wobble * 1.9 * min(6.5, 1.3 + L / 120)
        t = s / L
        k1, k2 = rng.uniform(0.5, 1.8), rng.uniform(2.0, 5.5)
        drift = amp * (np.sin(2 * np.pi * k1 * t + rng.uniform(0, 6.3)) * 0.65 +
                       np.sin(2 * np.pi * k2 * t + rng.uniform(0, 6.3)) * 0.35)
        drift += np.cumsum(rng.normal(0, jitter * 1.0, n))
        drift -= np.linspace(drift[0], drift[-1], n) * 0.3
        xs, ys = xs + nx * drift, ys + ny * drift
        xs += rng.normal(0, jitter * 0.8, n)
        ys += rng.normal(0, jitter * 0.8, n)
        bw = (width or self.base_w) * float(rng.uniform(0.6, 1.9))
        press = bw * (0.7 + 0.45 * np.sin(np.pi * t) + rng.normal(0, 0.1, n)) if pressure else np.full(n, bw)
        inten = np.full(n, rng.uniform(190, 255))
        if rng.random() < 0.35:   # pressure drop-out: part of the stroke gets faint
            a = int(rng.integers(0, n)); b = min(n, a + int(rng.integers(3, 10)))
            inten[a:b] *= rng.uniform(0.45, 0.7)
        P = np.stack([xs, ys], 1) * SS
        for i in range(n - 1):
            wi = max(1, int(round(press[i] * SS)))
            f = int(inten[i])
            self.d.line([tuple(P[i]), tuple(P[i + 1])], fill=f, width=wi)
            r = wi / 2
            self.d.ellipse([P[i + 1][0] - r, P[i + 1][1] - r, P[i + 1][0] + r, P[i + 1][1] + r], fill=f)

    def line(self, x0, y0, x1, y1, overshoot=True, **kw):
        rng = self.rng
        L = math.hypot(x1 - x0, y1 - y0) or 1
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        # slant the line about its middle (+-2 deg, never more than ~12 px at the ends)
        ang = math.radians(rng.normal(0, 1.2)); ang = max(-math.radians(2.5), min(math.radians(2.5), ang))
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ca, sa = math.cos(ang), math.sin(ang)
        def rot(px, py):
            px, py = px - mx, py - my
            return mx + px * ca - py * sa, my + px * sa + py * ca
        (x0, y0), (x1, y1) = rot(x0, y0), rot(x1, y1)
        if overshoot:
            a, b = rng.uniform(-6, 12), rng.uniform(-6, 16)
            x0, y0, x1, y1 = x0 - ux * a, y0 - uy * a, x1 + ux * b, y1 + uy * b
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        L = math.hypot(x1 - x0, y1 - y0) or 1
        bend = rng.normal(0, min(8, L / 55))
        mx += -(y1 - y0) / L * bend
        my += (x1 - x0) / L * bend
        self.stroke([(x0, y0), (mx, my), (x1, y1)], **kw)

    def rect(self, x, y, w, h, rounded=0.0, double=False, **kw):
        rng = self.rng
        ang = math.radians(rng.normal(0, 1.9))
        cx, cy = x + w / 2, y + h / 2
        def rot(px, py):
            px, py = px - cx, py - cy
            return (cx + px * math.cos(ang) - py * math.sin(ang), cy + px * math.sin(ang) + py * math.cos(ang))
        style = rng.random()
        passes = 2 if (double or rng.random() < 0.18) else 1   # some boxes are re-stroked
        for p in range(passes):
            o = rng.normal(0, 3.6, 8) if p else rng.normal(0, 2.4, 8)
            if rounded > 0 or style < 0.4:
                r = rounded if rounded > 0 else min(10, h / 3)
                path = MS.rounded_rect_path(x + o[0], y + o[1], w + o[2], h + o[3], r)
                start = int(rng.integers(0, len(path)))
                path = path[start:] + path[:start]
                if rng.random() < 0.55:          # unclosed: stop early leaving a visible gap
                    path = path[:len(path) - int(rng.integers(2, max(3, len(path) // 7)))]
                else:
                    extra = int(rng.integers(0, 6))
                    path = path + path[1:1 + extra]
                self.stroke([rot(*q) for q in path], **kw)
            else:
                corners = [(x + o[0], y + o[1]), (x + w + o[2], y + o[3]),
                           (x + w + o[4], y + h + o[5]), (x + o[6], y + h + o[7])]
                skip = int(rng.integers(0, 4)) if rng.random() < 0.35 else -1   # one side missing/short
                for i in range(4):
                    a, b = rot(*corners[i]), rot(*corners[(i + 1) % 4])
                    if i == skip:
                        f = rng.uniform(0.45, 0.8)    # draw only part of this side
                        b = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
                    self.line(a[0], a[1], b[0], b[1], **kw)

    def circle(self, cx, cy, r, **kw):
        rng = self.rng
        n = 40
        start = rng.uniform(0, 2 * math.pi)
        sweep = 2 * math.pi * rng.uniform(0.88, 1.18)
        rr = r * (1 + rng.normal(0, 0.07))
        ex = rng.uniform(0.88, 1.12)
        pts = [(cx + rr * ex * math.cos(start + sweep * i / n) * (1 + 0.05 * i / n),
                cy + rr / ex * math.sin(start + sweep * i / n) * (1 + 0.05 * i / n)) for i in range(n + 1)]
        self.stroke(pts, wobble=0.6, **kw)

    # ---- rougher handwriting
    def text(self, s, x, y, key, scale=1.0):
        rng = self.rng
        f = self.ctx.font(key, scale)
        cx = x * SS
        drift = 0.0
        x_start = cx
        for ch in s:
            adv = f.getlength(ch)
            if ch != " ":
                gs = float(rng.uniform(0.9, 1.12))
                gw, gh = int(adv + f.size), int(f.size * 1.6)
                g = Image.new("L", (gw, gh), 0)
                ImageDraw.Draw(g).text((f.size * 0.3, f.size * 0.2), ch, font=f, fill=int(rng.uniform(190, 255)))
                if abs(gs - 1) > 0.02:
                    g2 = g.resize((int(gw * gs), int(gh * gs)), Image.BICUBIC)
                    g = g2
                gw, gh = g.size
                g = g.rotate(rng.normal(0, 6.0), resample=Image.BICUBIC, center=(gw / 2, gh / 2))
                drift += rng.normal(0, 0.55)
                drift = max(-4.5, min(4.5, drift))
                slope = self.tilt * (cx - x_start) / SS
                px = int(cx - f.size * 0.3 + rng.normal(0, 0.9) * SS)
                py = int(y * SS - f.size * 0.2 - f.size * 0.08 + (drift + slope + rng.normal(0, 0.9)) * SS)
                self._paste(g, px, py)
            cx += adv * rng.uniform(0.93, 1.09)


# ---------------------------------------------------------------- corrections
def leaves(n, out):
    if n["t"].startswith("_"):
        for c in n.get("children", []):
            leaves(c, out)
        return
    out.append(n)
    for c in n.get("children", []):
        leaves(c, out)


def scratch(pen, x, y, w, h):
    """Zigzag scratch-out, as if a wrong word had been crossed out."""
    rng = pen.rng
    k = int(rng.integers(5, 9))
    pts = []
    for i in range(k):
        pts.append((x + w * i / (k - 1) + rng.normal(0, 2), y + (h if i % 2 else 0) + rng.normal(0, 2)))
    pen.stroke(pts, wobble=0.3, width=pen.base_w * 1.1, pressure=False)


def add_corrections(root, pen, ctx, H):
    rng = ctx.rng
    ls = []
    leaves(root, ls)
    boxes = [n["box"] for n in ls if "box" in n]
    placed = 0
    tries = 0
    want = int(rng.integers(2, 5))
    marks = []
    while placed < want and tries < 60:
        tries += 1
        n = ls[int(rng.integers(0, len(ls)))]
        if n["t"] in ("image", "divider", "navbar", "list"):
            continue
        x, y, w, h = n["box"]
        sw, sh = float(rng.uniform(36, 70)), float(rng.uniform(12, 20))
        side = rng.choice(["right", "left"])
        sx = x + w + 12 if side == "right" else x - 12 - sw
        sy = y + (h - sh) / 2
        if sx < 12 or sx + sw > W - 12 or sy < 8 or sy + sh > H - 8:
            continue
        r = (sx - 6, sy - 6, sw + 12, sh + 12)
        if any(not (r[0] + r[2] < b[0] or b[0] + b[2] < r[0] or r[1] + r[3] < b[1] or b[1] + b[3] < r[1]) for b in boxes):
            continue
        if any(not (r[0] + r[2] < m[0] or m[0] + m[2] < r[0] or r[1] + r[3] < m[1] or m[1] + m[3] < r[1]) for m in marks):
            continue
        marks.append(r)
        scratch(pen, sx, sy, sw, sh)
        placed += 1
    return placed


# ---------------------------------------------------------------- finish: photo of paper
def homography(src, dst):
    A, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    h = np.linalg.solve(np.array(A, float), np.array(b, float))
    return np.append(h, 1).reshape(3, 3)


def apply_h(Hm, x, y):
    p = Hm @ np.array([x, y, 1.0])
    return p[0] / p[2], p[1] / p[2]


def finish(ink, ctx, size):
    rng = ctx.rng
    w, h = size
    ink = ink.resize(size, Image.LANCZOS)
    a = np.asarray(ink, np.float32) / 255.0
    pencil = rng.random() < 0.4
    if pencil:
        a = a * np.clip(rng.normal(0.8, 0.25, a.shape), 0.25, 1.0)
    paper_tone = np.array([rng.uniform(238, 252), rng.uniform(234, 250), rng.uniform(222, 245)])
    paper = np.ones((h, w, 3), np.float32) * paper_tone
    paper += rng.normal(0, 4.0, (h, w, 1))                         # grain
    # paper fibres: faint random short streaks
    fib = Image.new("L", (w, h), 0)
    fd = ImageDraw.Draw(fib)
    for _ in range(int(w * h / 2500)):
        fx, fy = rng.uniform(0, w), rng.uniform(0, h)
        L = rng.uniform(4, 14); t = rng.uniform(0, math.pi)
        fd.line([(fx, fy), (fx + L * math.cos(t), fy + L * math.sin(t))], fill=int(rng.uniform(10, 40)))
    paper -= np.asarray(fib, np.float32)[..., None] * 0.35
    small = rng.normal(0, 1, (max(2, h // 90), max(2, w // 90)))
    blot = np.asarray(Image.fromarray(((small - small.min()) / (np.ptp(small) + 1e-6) * 255).astype(np.uint8))
                      .resize((w, h), Image.BICUBIC), np.float32) / 255.0
    paper -= blot[..., None] * rng.uniform(8, 18)
    # uneven lighting gradient + corner shadow
    gx = np.linspace(-1, 1, w)[None, :]; gy = np.linspace(-1, 1, h)[:, None]
    ang = rng.uniform(0, 2 * math.pi)
    paper -= ((gx * math.cos(ang) + gy * math.sin(ang)) * rng.uniform(6, 16))[..., None]
    paper -= (np.clip(gx ** 2 + gy ** 2 - 0.6, 0, None) * rng.uniform(14, 34))[..., None]
    for _ in range(int(rng.integers(20, 55))):                      # specks / smudges
        sx, sy = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = int(rng.integers(1, 4))
        paper[max(0, sy - r):sy + r, max(0, sx - r):sx + r] -= rng.uniform(25, 90)
    if rng.random() < 0.6:                                          # a fold / crease line
        cy = int(rng.integers(h // 4, 3 * h // 4))
        paper[max(0, cy - 1):cy + 1, :, :] -= rng.uniform(8, 20)
        paper[cy + 1:cy + 4, :, :] += rng.uniform(2, 6)
    ink_rgb = np.array(INKS[int(rng.integers(0, len(INKS)))], np.float32)
    if pencil:
        ink_rgb = np.array([85, 85, 90], np.float32)
    out = paper * (1 - a[..., None]) + ink_rgb * a[..., None]
    img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")

    # rotation (1-3 deg) + perspective warp
    deg = float(rng.uniform(1.0, 3.0)) * float(rng.choice([-1, 1]))
    th = math.radians(deg)
    cx, cy = w / 2, h / 2
    sc = 0.965
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = []
    for (x, y) in src:
        px, py = (x - cx) * sc, (y - cy) * sc
        rx, ry = px * math.cos(th) - py * math.sin(th), px * math.sin(th) + py * math.cos(th)
        dst.append((cx + rx + rng.uniform(-0.012, 0.012) * w, cy + ry + rng.uniform(-0.012, 0.012) * h))
    Hm = homography(src, dst)
    Hi = np.linalg.inv(Hm)
    bg = tuple(int(v) for v in (paper_tone * 0.93))
    img = img.transform((w, h), Image.PERSPECTIVE, tuple((Hi / Hi[2, 2]).flatten()[:8]), Image.BICUBIC, fillcolor=bg)
    img = img.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.35, 0.8))))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=int(rng.integers(62, 82)))      # phone-photo compression artefacts
    img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    return img, ("pencil" if pencil else "pen"), deg, Hm


def build(scr):
    ctx = HCtx(scr["id"])
    rng = ctx.rng
    mode = scr["mode"]
    cw = {"mobile": rng.uniform(440, 540), "narrow": rng.uniform(600, 700)}.get(mode, rng.uniform(860, 910))
    cw = float(cw)
    x0 = (W - cw) / 2 + float(rng.uniform(-25, 25)) if mode != "desktop" else float(rng.uniform(40, 1000 - cw - 40))
    y0 = float(rng.uniform(50, 80))
    h = MS.layout(scr["root"], x0, y0, cw, ctx)
    Hh = int(max(560, y0 + h + rng.uniform(50, 90)))
    pen = HPen(ctx, (W * SS, Hh * SS))
    MS.draw_node(scr["root"], pen, ctx)
    n_corr = add_corrections(scr["root"], pen, ctx, Hh)
    img, tool, deg, Hm = finish(pen.ink, ctx, (W, Hh))

    comps = []
    MS.collect(scr["root"], comps, None)
    for c in comps:
        x, y, w, hh = c.pop("box_px")
        xs, ys = zip(*[apply_h(Hm, px, py) for px, py in ((x, y), (x + w, y), (x + w, y + hh), (x, y + hh))])
        x1, y1, x2, y2 = max(0, min(xs)), max(0, min(ys)), min(W, max(xs)), min(Hh, max(ys))
        c["bbox"] = {"x": round(x1 / W, 4), "y": round(y1 / Hh, 4), "w": round((x2 - x1) / W, 4),
                     "h": round((y2 - y1) / Hh, 4)}
    label = {
        "id": scr["id"], "category": scr["category"], "title": scr["title"], "synthetic": True,
        "split": "holdout", "generator": GENERATOR, "seed_source": f"sha256('{scr['id']}')",
        "render": {"font": ctx.font_name, "tool": tool, "layout": mode, "style": "harsh",
                   "page_rotation_deg": round(deg, 2), "scratch_outs": n_corr},
        "width": W, "height": Hh,
        "instruction": scr["instruction"],
        "components": [{k: c[k] for k in ("type", "label", "bbox", "parent")} |
                       ({"props": c["props"]} if "props" in c else {}) for c in comps],
        "interactions": scr["interactions"],
        "requirements": MS.requirements_from(scr, comps),
    }
    return img, label


def main(argv):
    ids = set(argv)
    (ROOT / "sketches").mkdir(exist_ok=True)
    (ROOT / "labels").mkdir(exist_ok=True)
    for scr in SCREENS:
        if ids and scr["id"] not in ids:
            continue
        img, label = build(scr)
        img.save(ROOT / "sketches" / f"{scr['id']}.png", optimize=True)
        (ROOT / "labels" / f"{scr['id']}.json").write_text(json.dumps(label, indent=2))
        r = label["render"]
        print(f"{scr['id']:<16} {img.size[0]}x{img.size[1]}  {len(label['components']):>3} comps  "
              f"{r['font']:<24} {r['tool']:<6} rot {r['page_rotation_deg']:+.2f}  scratch {r['scratch_outs']}")


if __name__ == "__main__":
    main(sys.argv[1:])
