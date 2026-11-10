"""Generate the NeuroGenUI synthetic hand-drawn sketch dataset.

    python dataset/tools/make_sketches.py            # all 40 screens
    python dataset/tools/make_sketches.py login_01   # just some

For each screen in specs.py:
  1. lay out the component tree (simple flex-like column/row layout, 1000 px wide frame),
  2. render it in a hand-drawn style (wobbly multi-segment strokes with low-frequency drift,
     jitter, overshoot and gaps at corners, slightly rotated rectangles, varying pen width,
     handwriting fonts with per-glyph rotation/baseline jitter, scribbles for paragraphs,
     X-crossed image boxes, circles for radios, squares for checkboxes, paper noise),
  3. write sketches/<id>.png and labels/<id>.json (ground truth derived from the same tree).

Everything is deterministic: the RNG is seeded from the screen id.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from specs import SCREENS  # noqa: E402

GENERATOR = "make_sketches.py v1"
ROOT = Path(__file__).resolve().parents[1]
FONTS = Path(__file__).parent / "fonts"
W = 1000          # output width (px)
SS = 2            # supersampling factor for antialiasing
CONTAINERS = {"page", "container", "card", "form", "header", "navbar", "list"}

# handwriting fonts and the size multiplier that makes them look comparable
FONT_CHOICES = [("ArchitectsDaughter-Regular.ttf", 0.92), ("PatrickHand-Regular.ttf", 1.05),
                ("Caveat.ttf", 1.28)]
INKS = [(30, 30, 34), (24, 40, 92), (55, 55, 60), (20, 20, 20), (35, 52, 110)]

SIZES = {"h1": 42, "h2": 34, "h3": 28, "h4": 24, "body": 24, "field": 23, "button": 25, "small": 21}


# ===================================================================== layout
class Ctx:
    def __init__(self, sid: str):
        seed = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16)
        self.rng = np.random.default_rng(seed)
        fname, mult = FONT_CHOICES[seed % len(FONT_CHOICES)]
        self.font_file = str(FONTS / fname)
        self.font_mult = mult
        self.font_name = fname
        self._fonts = {}

    def font(self, key: str, scale: float = 1.0) -> ImageFont.FreeTypeFont:
        size = int(round(SIZES[key] * self.font_mult * scale))
        if size not in self._fonts:
            self._fonts[size] = ImageFont.truetype(self.font_file, size * SS)
        return self._fonts[size]

    def text_w(self, text: str, key: str) -> float:
        return self.font(key).getlength(text) / SS

    def text_h(self, key: str) -> float:
        f = self.font(key)
        a, d = f.getmetrics()
        return (a + d) / SS * 0.82


def heading_key(n):
    return f"h{min(4, max(1, n.get('level', 1)))}"


def natural_size(n, ctx: Ctx, avail: float):
    """(width, height) of a leaf when it is not stretched."""
    t = n["t"]
    if t == "heading":
        k = heading_key(n)
        return ctx.text_w(n["label"], k) + 4, ctx.text_h(k) + 6
    if t == "text":
        if n.get("scribble"):
            lines = n["scribble"]
            return avail * n.get("wfrac", 1.0), lines * 26 - 6
        return ctx.text_w(n["label"], "body") + 4, ctx.text_h("body") + 4
    if t in ("link", "nav_item"):
        return ctx.text_w(n["label"], "body") + 4, ctx.text_h("body") + 8
    if t == "input":
        return avail, 54
    if t == "select":
        return avail, 54
    if t == "textarea":
        return avail, 34 + 26 * n.get("rows", 3)
    if t == "button":
        return max(120, ctx.text_w(n["label"], "button") + 56), 54
    if t in ("checkbox", "radio"):
        glyph = 50 if n.get("toggle") else 30
        return glyph + 12 + ctx.text_w(n["label"], "body"), 32
    if t == "image":
        return avail, n.get("h", 160)
    if t == "divider":
        return avail, 14
    if t == "icon":
        return 44, 44
    if t == "list":
        widest = max(ctx.text_w(s, "body") for s in n["items"])
        return widest + 34, len(n["items"]) * 34 - 4
    raise ValueError(t)


def resolve_width(spec_w, nat_w, avail):
    if spec_w in (None,):
        return min(nat_w, avail)
    if spec_w == "full":
        return avail
    if isinstance(spec_w, float) and spec_w <= 1.0:
        return avail * spec_w
    return min(float(spec_w), avail)


def layout(n, x, y, w, ctx: Ctx) -> float:
    """Assign n['box']=(x,y,w,h) recursively; return the height used."""
    t = n["t"]
    if t == "_sp":
        n["box"] = (x, y, w, n["h"])
        return n["h"]
    if t == "_col":
        cy = y
        for i, c in enumerate(n["children"]):
            if i:
                cy += n["gap"]
            cy += layout(c, x, cy, w, ctx)
        n["box"] = (x, y, w, cy - y)
        return cy - y
    if t == "_row":
        ch = n["children"]
        weights = n.get("weights") or [1] * len(ch)
        gap = n["gap"]
        avail = w - gap * (len(ch) - 1)
        tot = sum(weights)
        cx, hs = x, []
        for c, wt in zip(ch, weights):
            cw = avail * wt / tot
            hs.append(layout(c, cx, y, cw, ctx))
            cx += cw + gap
        rh = max(hs)
        if n.get("valign") == "center":
            for c, h in zip(ch, hs):
                shift(c, 0, (rh - h) / 2)
        n["box"] = (x, y, w, rh)
        return rh
    if t == "navbar":
        return layout_navbar(n, x, y, w, ctx)
    if t in ("card", "form", "container", "header"):
        pad = 18 if t == "header" else 22
        inner = dict(t="_row" if n.get("dir") == "row" else "_col", children=n["children"],
                     gap=n.get("gap", 14), weights=None, valign="center")
        if inner["t"] == "_row":   # header: children at natural width, packed left; last one right
            h = layout_packed_row(n["children"], x + pad, y + pad, w - 2 * pad, ctx, n.get("gap", 20))
        else:
            h = layout(inner, x + pad, y + pad, w - 2 * pad, ctx)
        h = max(h + 2 * pad, n.get("minh", 0))
        n["box"] = (x, y, w, h)
        return h
    # leaves
    nw, nh = natural_size(n, ctx, w)
    if t in ("input", "select", "image", "button"):
        nw = resolve_width(n.get("w"), nw, w) if n.get("w") is not None else (nw if t == "button" else w)
    nw = min(nw, w)
    align = n.get("align", "left")
    ox = x if align == "left" else (x + (w - nw) / 2 if align == "center" else x + w - nw)
    n["box"] = (ox, y, nw, nh)
    return nh


def layout_packed_row(children, x, y, w, ctx, gap):
    """Children at natural widths; the last child is pushed to the right edge if it is an icon/button
    with align right, otherwise everything packs left. Vertically centred."""
    sizes = []
    for c in children:
        nw, nh = natural_size(c, ctx, w) if c["t"] not in ("input", "select") else (c.get("w") or 240, 54)
        if c["t"] == "button" and c.get("w") not in (None, "full"):
            nw = c["w"]
        sizes.append((min(nw, w), nh))
    rh = max(h for _, h in sizes)
    cx = x
    for c, (cw, ch) in zip(children, sizes):
        if c.get("align") == "right":
            cx = max(cx, x + w - cw)
        c["box"] = (cx, y + (rh - ch) / 2, cw, ch)
        cx += cw + gap
    return rh


def layout_navbar(n, x, y, w, ctx):
    pad = 14
    if n.get("vertical"):
        cy = y + pad + 6
        for i, c in enumerate(n["children"]):
            if i:
                cy += 20
            nw, nh = natural_size(c, ctx, w - 2 * pad)
            c["box"] = (x + pad + 4, cy, nw, nh)
            cy += nh
        h = max(cy - y + pad + 40, 360)
        n["box"] = (x, y, w, h)
        n["children"] = n["children"]
        return h
    items = n["left"] + n["right"]
    sizes = []
    for c in items:
        if c["t"] == "input":
            sizes.append((c.get("w") or 240, 46))
        else:
            sizes.append(natural_size(c, ctx, w))
    rh = max(h for _, h in sizes)
    h = rh + 2 * pad
    cx = x + pad + 6
    for c, (cw, ch) in zip(n["left"], sizes[:len(n["left"])]):
        c["box"] = (cx, y + (h - ch) / 2, cw, ch)
        cx += cw + 28
    rs = sizes[len(n["left"]):]
    tot = sum(cw for cw, _ in rs) + 30 * (len(rs) - 1)
    cx = x + w - pad - 6 - tot
    for c, (cw, ch) in zip(n["right"], rs):
        c["box"] = (cx, y + (h - ch) / 2, cw, ch)
        cx += cw + 30
    n["children"] = items
    n["box"] = (x, y, w, h)
    return h


def shift(n, dx, dy):
    if "box" in n:
        x, y, w, h = n["box"]
        n["box"] = (x + dx, y + dy, w, h)
    for c in n.get("children", []):
        shift(c, dx, dy)


# ===================================================================== hand-drawn primitives
class Pen:
    def __init__(self, ctx: Ctx, size):
        self.ctx = ctx
        self.rng = ctx.rng
        self.ink = Image.new("L", size, 0)
        self.d = ImageDraw.Draw(self.ink)
        self.base_w = float(self.rng.uniform(2.0, 3.1))   # pen width in output px

    # ---- core: draw a polyline as a wobbly stroke
    def stroke(self, pts, wobble=1.0, width=None, jitter=0.45, pressure=True):
        pts = np.asarray(pts, float)
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        L = seg.sum()
        if L < 1:
            return
        n = max(4, int(L / 5))
        cum = np.concatenate([[0], np.cumsum(seg)])
        s = np.linspace(0, L, n)
        xs = np.interp(s, cum, pts[:, 0])
        ys = np.interp(s, cum, pts[:, 1])
        # tangent/normal
        dx, dy = np.gradient(xs), np.gradient(ys)
        nl = np.hypot(dx, dy) + 1e-9
        nx, ny = -dy / nl, dx / nl
        # low-frequency drift: sum of two sines with random phase, amplitude grows with length
        amp = wobble * min(4.6, 1.1 + L / 170)
        t = s / L
        k1, k2 = self.rng.uniform(0.6, 1.6), self.rng.uniform(2.0, 4.5)
        drift = amp * (np.sin(2 * np.pi * k1 * t + self.rng.uniform(0, 6.3)) * 0.7 +
                       np.sin(2 * np.pi * k2 * t + self.rng.uniform(0, 6.3)) * 0.3)
        drift += np.cumsum(self.rng.normal(0, jitter * 0.35, n))  # random walk
        drift -= np.linspace(drift[0], drift[-1], n) * 0.45          # keep the ends roughly put
        xs, ys = xs + nx * drift, ys + ny * drift
        xs += self.rng.normal(0, jitter * 0.3, n)
        ys += self.rng.normal(0, jitter * 0.3, n)
        bw = width or self.base_w
        if pressure:
            press = bw * (0.78 + 0.32 * np.sin(np.pi * t) + self.rng.normal(0, 0.05, n))
        else:
            press = np.full(n, bw)
        inten = int(self.rng.uniform(205, 255))
        P = np.stack([xs, ys], 1) * SS
        for i in range(n - 1):
            wi = max(1, int(round(press[i] * SS)))
            self.d.line([tuple(P[i]), tuple(P[i + 1])], fill=inten, width=wi)
            r = wi / 2
            self.d.ellipse([P[i + 1][0] - r, P[i + 1][1] - r, P[i + 1][0] + r, P[i + 1][1] + r], fill=inten)

    def line(self, x0, y0, x1, y1, overshoot=True, **kw):
        if overshoot:
            L = math.hypot(x1 - x0, y1 - y0) or 1
            ux, uy = (x1 - x0) / L, (y1 - y0) / L
            a = self.rng.uniform(-3, 7)
            b = self.rng.uniform(-3, 8)
            x0, y0, x1, y1 = x0 - ux * a, y0 - uy * a, x1 + ux * b, y1 + uy * b
        # slight curvature via a midpoint
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        L = math.hypot(x1 - x0, y1 - y0) or 1
        bend = self.rng.normal(0, min(4.5, L / 90))
        mx += -(y1 - y0) / L * bend
        my += (x1 - x0) / L * bend
        self.stroke([(x0, y0), (mx, my), (x1, y1)], **kw)

    def rect(self, x, y, w, h, rounded=0.0, double=False, **kw):
        ang = math.radians(self.rng.normal(0, 0.9))
        cx, cy = x + w / 2, y + h / 2

        def rot(px, py):
            px, py = px - cx, py - cy
            return (cx + px * math.cos(ang) - py * math.sin(ang),
                    cy + px * math.sin(ang) + py * math.cos(ang))

        style = self.rng.random()
        passes = 2 if double else 1
        for p in range(passes):
            o = self.rng.normal(0, 2.2, 8) if p else self.rng.normal(0, 1.3, 8)
            if rounded > 0 or style < 0.35:
                # one continuous stroke around a (rounded) rectangle, start/end not quite closed
                r = rounded if rounded > 0 else min(8, h / 4)
                path = rounded_rect_path(x + o[0], y + o[1], w + o[2], h + o[3], r)
                start = int(self.rng.integers(0, len(path)))
                path = path[start:] + path[:start]
                extra = int(self.rng.integers(-3, 5))
                path = path + path[1:max(1, extra)] if extra > 0 else path[:len(path) + extra]
                self.stroke([rot(*q) for q in path], **kw)
            else:
                corners = [(x + o[0], y + o[1]), (x + w + o[2], y + o[3]),
                           (x + w + o[4], y + h + o[5]), (x + o[6], y + h + o[7])]
                for i in range(4):
                    a, b = corners[i], corners[(i + 1) % 4]
                    a, b = rot(*a), rot(*b)
                    self.line(a[0], a[1], b[0], b[1], **kw)

    def circle(self, cx, cy, r, **kw):
        n = 40
        start = self.rng.uniform(0, 2 * math.pi)
        sweep = 2 * math.pi * self.rng.uniform(0.93, 1.08)
        rr = r * (1 + self.rng.normal(0, 0.04))
        ex = self.rng.uniform(0.94, 1.06)
        pts = [(cx + rr * ex * math.cos(start + sweep * i / n), cy + rr / ex * math.sin(start + sweep * i / n))
               for i in range(n + 1)]
        self.stroke(pts, wobble=0.35, **kw)

    def text(self, s, x, y, key, scale=1.0):
        """Handwriting: per-glyph rotation and baseline jitter. (x,y) = top-left."""
        f = self.ctx.font(key, scale)
        cx = x * SS
        drift = 0.0
        for ch in s:
            adv = f.getlength(ch)
            if ch != " ":
                gw, gh = int(adv + f.size), int(f.size * 1.6)
                g = Image.new("L", (gw, gh), 0)
                ImageDraw.Draw(g).text((f.size * 0.3, f.size * 0.2), ch, font=f,
                                       fill=int(self.rng.uniform(210, 255)))
                g = g.rotate(self.rng.normal(0, 3.5), resample=Image.BICUBIC, center=(gw / 2, gh / 2))
                drift += self.rng.normal(0, 0.25)
                drift = max(-2.5, min(2.5, drift))
                px = int(cx - f.size * 0.3 + self.rng.normal(0, 0.4) * SS)
                py = int(y * SS - f.size * 0.2 - f.size * 0.08 + (drift + self.rng.normal(0, 0.5)) * SS)
                self._paste(g, px, py)
            cx += adv * self.rng.uniform(0.96, 1.05)

    def _paste(self, g, px, py):
        W_, H_ = self.ink.size
        x0, y0 = max(0, px), max(0, py)
        x1, y1 = min(W_, px + g.width), min(H_, py + g.height)
        if x1 <= x0 or y1 <= y0:
            return
        crop = g.crop((x0 - px, y0 - py, x1 - px, y1 - py))
        region = self.ink.crop((x0, y0, x1, y1))
        self.ink.paste(ImageChops.lighter(region, crop), (x0, y0))

    def scribble(self, x, y, w, lines):
        """Paragraph placeholder: wavy handwriting-like lines, the last one shorter."""
        for i in range(lines):
            lw = w * (self.rng.uniform(0.45, 0.75) if i == lines - 1 and lines > 1 else self.rng.uniform(0.86, 1.0))
            yy = y + 10 + i * 26
            n = max(8, int(lw / 6))
            xs = np.linspace(x, x + lw, n)
            freq = self.rng.uniform(0.18, 0.28)
            amp = self.rng.uniform(3.0, 5.0)
            ys = yy + amp * np.sin(xs * freq + self.rng.uniform(0, 6)) * (0.6 + 0.4 * self.rng.random(n))
            # small gaps between "words"
            cut = 0
            for j in range(1, n):
                if self.rng.random() < 0.06 and j - cut > 6:
                    self.stroke(list(zip(xs[cut:j], ys[cut:j])), wobble=0.3, width=self.base_w * 0.8)
                    cut = j + 1
            if n - cut > 2:
                self.stroke(list(zip(xs[cut:], ys[cut:])), wobble=0.3, width=self.base_w * 0.8)


def rounded_rect_path(x, y, w, h, r, step=8):
    r = max(0.0, min(r, w / 2, h / 2))
    pts = []

    def arc(cx, cy, a0, a1):
        k = max(2, int(abs(a1 - a0) * r / step) + 1)
        for i in range(k + 1):
            a = a0 + (a1 - a0) * i / k
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    arc(x + w - r, y + r, -math.pi / 2, 0)
    arc(x + w - r, y + h - r, 0, math.pi / 2)
    arc(x + r, y + h - r, math.pi / 2, math.pi)
    arc(x + r, y + r, math.pi, 1.5 * math.pi)
    pts.append(pts[0])
    return pts


# ===================================================================== component renderers
def draw_node(n, pen: Pen, ctx: Ctx):
    t = n["t"]
    if t.startswith("_"):
        for c in n.get("children", []):
            draw_node(c, pen, ctx)
        return
    x, y, w, h = n["box"]
    rng = ctx.rng
    if t in ("card", "container", "form"):
        pen.rect(x, y, w, h, rounded=rng.choice([0, 0, 10, 16]) if t == "card" else 0)
    elif t == "header":
        pen.rect(x, y, w, h)
    elif t == "navbar":
        if n.get("vertical"):
            pen.rect(x, y, w, h)
        else:
            pen.rect(x, y, w, h, rounded=0)
    elif t == "heading":
        k = heading_key(n)
        pen.text(n["label"], x + 2, y + 3, k)
        if n.get("level", 1) == 1 and rng.random() < 0.3:
            pen.line(x, y + h + 2, x + w, y + h + 1, width=pen.base_w * 0.9)
    elif t == "text":
        if n.get("scribble"):
            pen.scribble(x, y, w, n["scribble"])
        else:
            pen.text(n["label"], x + 2, y + 2, "body")
    elif t in ("link", "nav_item"):
        pen.text(n["label"], x + 2, y + 1, "body")
        if t == "link" or rng.random() < 0.15:
            pen.line(x, y + h - 2, x + w, y + h - 3, width=pen.base_w * 0.8)
    elif t == "input":
        pen.rect(x, y, w, h, rounded=rng.choice([0, 0, 6]))
        label_inside(n["label"], x, y, w, h, pen, ctx, key="field")
        if n.get("kind") == "search":
            pen.circle(x + w - 26, y + h / 2 - 3, 8)
            pen.line(x + w - 20, y + h / 2 + 3, x + w - 12, y + h / 2 + 11, overshoot=False)
        if n.get("kind") == "date":
            ix = x + w - 40
            pen.rect(ix, y + 14, 24, 24, wobble=0.4)
            pen.line(ix, y + 21, ix + 24, y + 21, overshoot=False, width=pen.base_w * 0.7)
    elif t == "textarea":
        pen.rect(x, y, w, h)
        pen.text(n["label"], x + 14, y + 10, "field")
        pen.line(x + w - 20, y + h - 6, x + w - 6, y + h - 20, overshoot=False, width=pen.base_w * 0.7)
        pen.line(x + w - 12, y + h - 6, x + w - 6, y + h - 12, overshoot=False, width=pen.base_w * 0.7)
    elif t == "select":
        pen.rect(x, y, w, h)
        label_inside(n["label"], x, y, w - 40, h, pen, ctx, key="field")
        vx, vy = x + w - 32, y + h / 2 - 5
        pen.stroke([(vx, vy), (vx + 9, vy + 10), (vx + 18, vy)], wobble=0.3)
    elif t == "button":
        style = n.get("style", "plain")
        rounded = rng.choice([0, 10, 14, 26]) if style != "double" else 6
        pen.rect(x, y, w, h, rounded=rounded, double=(style == "double"),
                 width=pen.base_w * (1.25 if style == "plain" and rng.random() < 0.5 else 1.0))
        tw = ctx.text_w(n["label"], "button")
        pen.text(n["label"], x + (w - tw) / 2, y + (h - ctx.text_h("button")) / 2 - 2, "button")
    elif t == "checkbox":
        if n.get("toggle"):
            pen.rect(x, y + 4, 46, 24, rounded=12)
            on = rng.random() < 0.5
            pen.circle(x + (33 if on else 13), y + 16, 8)
            lx = x + 58
        else:
            s = 22
            pen.rect(x, y + 5, s, s, wobble=0.35)
            if rng.random() < 0.3:
                pen.stroke([(x + 4, y + 16), (x + 10, y + 23), (x + 22, y + 3)], wobble=0.2)
            lx = x + 34
        pen.text(n["label"], lx, y + 2, "body")
    elif t == "radio":
        pen.circle(x + 12, y + 16, 11)
        if rng.random() < 0.25:
            pen.circle(x + 12, y + 16, 4, width=pen.base_w * 1.4)
        pen.text(n["label"], x + 34, y + 2, "body")
    elif t == "image":
        draw_image(n, x, y, w, h, pen)
    elif t == "divider":
        pen.line(x, y + h / 2, x + w, y + h / 2 + rng.normal(0, 1.5))
    elif t == "icon":
        draw_icon(n.get("glyph", "circle"), x, y, w, h, pen)
    elif t == "list":
        for i, item in enumerate(n["items"]):
            yy = y + i * 34
            pen.circle(x + 7, yy + 15, 3.0, width=pen.base_w * 0.9)
            pen.text(item, x + 24, yy + 2, "body")
    for c in n.get("children", []):
        draw_node(c, pen, ctx)


def label_inside(text, x, y, w, h, pen, ctx, key="field"):
    th = ctx.text_h(key)
    pen.text(text, x + 14, y + (h - th) / 2 - 2, key)


def draw_image(n, x, y, w, h, pen: Pen):
    rng = pen.rng
    if n.get("shape") == "circle":
        r = min(w, h) / 2
        cx, cy = x + w / 2, y + h / 2
        pen.circle(cx, cy, r)
        k = r * 0.62
        pen.line(cx - k, cy - k, cx + k, cy + k, overshoot=False)
        pen.line(cx - k, cy + k, cx + k, cy - k, overshoot=False)
        return
    pen.rect(x, y, w, h)
    glyph = n.get("glyph", "x")
    if glyph == "x":
        pen.line(x + 3, y + 3, x + w - 3, y + h - 3, overshoot=False)
        pen.line(x + 3, y + h - 3, x + w - 3, y + 3, overshoot=False)
    elif glyph == "mountain":
        base = y + h - 10
        pts = [(x + 10, base), (x + w * 0.33, y + h * 0.42), (x + w * 0.5, y + h * 0.65),
               (x + w * 0.68, y + h * 0.3), (x + w - 10, base)]
        pen.stroke(pts, wobble=0.6)
        pen.circle(x + w * 0.2, y + h * 0.25, min(w, h) * 0.08)
    elif glyph == "chart":
        ax, ay = x + 22, y + h - 18
        pen.line(ax, y + 14, ax, ay, overshoot=False)
        pen.line(ax, ay, x + w - 14, ay, overshoot=False)
        k = 7
        xs = np.linspace(ax + 10, x + w - 24, k)
        ys = ay - 12 - rng.uniform(0.15, 0.85, k) * (h - 50)
        pen.stroke(list(zip(xs, ys)), wobble=0.4)


def draw_icon(glyph, x, y, w, h, pen: Pen):
    cx, cy, r = x + w / 2, y + h / 2, min(w, h) / 2 - 2
    if glyph == "menu":
        for k in (-9, 0, 9):
            pen.line(cx - 14, cy + k, cx + 14, cy + k, overshoot=False)
        return
    if glyph == "back":
        pen.stroke([(cx + 8, cy - 14), (cx - 8, cy), (cx + 8, cy + 14)], wobble=0.3)
        return
    pen.circle(cx, cy, r)
    if glyph == "user":
        pen.circle(cx, cy - 5, r * 0.32)
        pen.stroke([(cx - r * 0.55, cy + r * 0.6), (cx, cy + r * 0.2), (cx + r * 0.55, cy + r * 0.6)], wobble=0.2)
    elif glyph == "bell":
        pen.stroke([(cx - 8, cy + 6), (cx - 6, cy - 8), (cx, cy - 11), (cx + 6, cy - 8), (cx + 8, cy + 6),
                    (cx - 8, cy + 6)], wobble=0.2)
    elif glyph in ("bolt", "star"):
        pen.stroke([(cx + 2, cy - 12), (cx - 6, cy + 2), (cx + 4, cy + 1), (cx - 3, cy + 13)], wobble=0.2)
    elif glyph in ("phone", "mail", "lock", "cloud", "pin", "heart"):
        pen.rect(cx - 8, cy - 7, 16, 14, wobble=0.3)


# ===================================================================== labels
def collect(n, out, parent_idx):
    t = n["t"]
    if t.startswith("_"):
        for c in n.get("children", []):
            collect(c, out, parent_idx)
        return
    idx = len(out)
    comp = {"type": t, "label": n.get("label", ""), "box_px": n["box"], "parent": parent_idx}
    props = {}
    if t == "heading":
        props["level"] = n.get("level", 1)
    if t == "input":
        props["inputType"] = n.get("kind", "text")
    if t == "select" and n.get("options"):
        props["options"] = n["options"]
    if t == "list":
        props["items"] = n["items"]
    if t == "image":
        props["alt"] = n.get("alt", "")
        props["shape"] = n.get("shape", "rect")
    if t == "icon":
        props["glyph"] = n.get("glyph", "")
    if t == "checkbox" and n.get("toggle"):
        props["toggle"] = True
    if t == "text" and n.get("scribble"):
        props["scribble_lines"] = n["scribble"]
    if t == "button" and n.get("style") == "double":
        props["variant_hint"] = "secondary"
    if props:
        comp["props"] = props
    out.append(comp)
    if t in CONTAINERS:
        for c in n.get("children", []):
            collect(c, out, idx)


def norm(s):
    return re.sub(r"[^a-z0-9$ ]+", " ", s.lower()).split()


def mentioned(label, instruction):
    """True if every word of the label occurs in the instruction (case/punctuation-insensitive)."""
    if not label:
        return False
    words = set(norm(instruction))
    lw = [w for w in norm(label) if w not in ("a", "the")]
    return bool(lw) and all(w in words for w in lw)


def requirements_from(scr, comps):
    """Machine-checkable requirements derived from the instruction + labels: every labelled
    component the instruction names must exist (type + label), named input types must match,
    and every stated interaction must work."""
    req = []
    ins = scr["instruction"]
    seen = set()
    for c in comps:
        if c["type"] in ("text", "card", "container", "form", "header", "navbar", "list", "divider", "image", "icon"):
            continue
        if not mentioned(c["label"], ins):
            continue
        key = (c["type"], c["label"].lower())
        if key in seen:
            continue
        seen.add(key)
        req.append({"kind": "node_exists", "type": c["type"], "label_contains": c["label"],
                    "source": "instruction names this component"})
        it = c.get("props", {}).get("inputType")
        if c["type"] == "input" and it in ("email", "password", "date", "number", "tel"):
            req.append({"kind": "input_type", "label_contains": c["label"], "input_type": it,
                        "source": "instruction implies the input type"})
    for k, img in enumerate([c for c in comps if c["type"] == "image"]):
        pass
    n_img = sum(1 for c in comps if c["type"] == "image")
    if n_img and re.search(r"\b(image|photo|picture|illustration|banner|avatar|chart|poster|map|logos?|thumbnail)s?\b", ins, re.I):
        req.append({"kind": "count_at_least", "type": "image", "n": 1,
                    "source": "instruction mentions an image"})
    for it in scr["interactions"]:
        req.append({"kind": "interaction", **it, "source": "instruction states this behaviour"})
    return req


# ===================================================================== paper
def finish(ink: Image.Image, ctx: Ctx, size):
    rng = ctx.rng
    ink = ink.resize(size, Image.LANCZOS)
    a = np.asarray(ink, np.float32) / 255.0
    pencil = rng.random() < 0.3
    if pencil:   # grainy pencil texture
        a = a * np.clip(rng.normal(0.85, 0.18, a.shape), 0.35, 1.0)
    h, w = a.shape
    paper_tone = np.array([rng.uniform(248, 255), rng.uniform(246, 254), rng.uniform(240, 252)])
    paper = np.ones((h, w, 3), np.float32) * paper_tone
    paper += rng.normal(0, 2.2, (h, w, 1))
    # low-frequency blotches / uneven lighting
    small = rng.normal(0, 1, (max(2, h // 120), max(2, w // 120)))
    blot = np.asarray(Image.fromarray(((small - small.min()) / (np.ptp(small) + 1e-6) * 255).astype(np.uint8))
                      .resize((w, h), Image.BICUBIC), np.float32) / 255.0
    paper -= (blot[..., None] * rng.uniform(3, 9))
    # a few specks
    for _ in range(int(rng.integers(8, 30))):
        sx, sy = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = int(rng.integers(1, 3))
        paper[max(0, sy - r):sy + r, max(0, sx - r):sx + r] -= rng.uniform(25, 80)
    ink_rgb = np.array(INKS[int(rng.integers(0, len(INKS)))], np.float32)
    if pencil:
        ink_rgb = np.array([70, 70, 74], np.float32)
    out = paper * (1 - a[..., None]) + ink_rgb * a[..., None]
    img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
    if rng.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(0.35))
    return img, ("pencil" if pencil else "pen")


# ===================================================================== main
def build(scr):
    ctx = Ctx(scr["id"])
    rng = ctx.rng
    mode = scr["mode"]
    if mode == "mobile":
        cw = float(rng.uniform(440, 540))
    elif mode == "narrow":
        cw = float(rng.uniform(600, 700))
    else:
        cw = float(rng.uniform(860, 910))
    x0 = (W - cw) / 2 + float(rng.uniform(-25, 25)) if mode != "desktop" else float(rng.uniform(40, 1000 - cw - 40))
    y0 = float(rng.uniform(40, 70))
    h = layout(scr["root"], x0, y0, cw, ctx)
    H = int(max(560, y0 + h + rng.uniform(40, 80)))
    pen = Pen(ctx, (W * SS, H * SS))
    draw_node(scr["root"], pen, ctx)
    img, tool = finish(pen.ink, ctx, (W, H))

    comps = []
    collect(scr["root"], comps, None)
    for c in comps:
        x, y, w, hh = c.pop("box_px")
        c["bbox"] = {"x": round(x / W, 4), "y": round(y / H, 4), "w": round(w / W, 4), "h": round(hh / H, 4)}
    label = {
        "id": scr["id"], "category": scr["category"], "title": scr["title"], "synthetic": True,
        "generator": GENERATOR, "seed_source": f"sha256('{scr['id']}')",
        "render": {"font": ctx.font_name, "tool": tool, "layout": mode},
        "width": W, "height": H,
        "instruction": scr["instruction"],
        "components": [{k: c[k] for k in ("type", "label", "bbox", "parent")} |
                       ({"props": c["props"]} if "props" in c else {}) for c in comps],
        "interactions": scr["interactions"],
        "requirements": requirements_from(scr, comps),
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
        print(f"{scr['id']:<12} {img.size[0]}x{img.size[1]}  {len(label['components']):>3} components  "
              f"{label['render']['font']:<32} {label['render']['tool']}")


if __name__ == "__main__":
    main(sys.argv[1:])
