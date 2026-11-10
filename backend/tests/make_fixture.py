"""Draw a rough hand-drawn style login sketch (wobbly, partly open strokes) for tests.

Run: python tests/make_fixture.py  ->  tests/fixtures/login_sketch.png (+ login_sketch.json ground truth)
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

W, H = 1000, 1100
rng = np.random.default_rng(7)
FIXTURES = Path(__file__).parent / "fixtures"


def wobble_line(img, p0, p1, thickness=3, amp=2.5):
    n = max(8, int(np.hypot(p1[0] - p0[0], p1[1] - p0[1]) / 12))
    t = np.linspace(0, 1, n)
    xs = p0[0] + (p1[0] - p0[0]) * t
    ys = p0[1] + (p1[1] - p0[1]) * t
    nx, ny = -(p1[1] - p0[1]), (p1[0] - p0[0])
    norm = max(1e-6, np.hypot(nx, ny))
    offs = np.cumsum(rng.normal(0, amp * 0.5, n))
    offs -= np.linspace(offs[0], offs[-1], n)
    pts = np.stack([xs + nx / norm * offs, ys + ny / norm * offs], 1).astype(np.int32)
    cv2.polylines(img, [pts], False, 0, thickness, cv2.LINE_AA)


def rough_rect(img, x, y, w, h, gap=False):
    j = lambda: rng.integers(-4, 5)
    corners = [(x + j(), y + j()), (x + w + j(), y + j()), (x + w + j(), y + h + j()), (x + j(), y + h + j())]
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        if gap and i == 0:  # leave a gap in the top edge, like a quick pen stroke
            mid = (a[0] + (b[0] - a[0]) * 0.55, a[1])
            wobble_line(img, a, (int(mid[0]), b[1]))
            continue
        # overshoot a little past the corner
        b2 = (b[0] + int(np.sign(b[0] - a[0]) * 6), b[1] + int(np.sign(b[1] - a[1]) * 6))
        wobble_line(img, a, b2)


def scribble_text(img, x, y, text, scale=1.1, thickness=2):
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, scale, 0, thickness, cv2.LINE_AA)


def main():
    img = np.full((H, W), 255, np.uint8)
    comps = []

    def add(t, label, x, y, w, h, parent=None):
        comps.append({"type": t, "label": label, "bbox": {"x": x / W, "y": y / H, "w": w / W, "h": h / H}, "parent": parent})
        return len(comps) - 1

    card = add("card", "", 250, 150, 500, 760)
    rough_rect(img, 250, 150, 500, 760)
    scribble_text(img, 400, 250, "Login", 2.0, 3)
    add("heading", "Login", 395, 205, 170, 60, card)
    scribble_text(img, 300, 340, "Email", 1.0)
    add("text", "Email", 298, 315, 95, 32, card)
    rough_rect(img, 300, 360, 400, 60, gap=True)
    add("input", "", 300, 360, 400, 60, card)
    scribble_text(img, 300, 470, "Password", 1.0)
    add("text", "Password", 298, 445, 150, 32, card)
    rough_rect(img, 300, 490, 400, 60)
    add("input", "", 300, 490, 400, 60, card)
    rough_rect(img, 300, 590, 32, 32)
    add("checkbox", "", 300, 590, 32, 32, card)
    scribble_text(img, 350, 616, "Remember me", 0.9)
    rough_rect(img, 300, 660, 400, 64)
    scribble_text(img, 440, 704, "Login", 1.1)
    add("button", "Login", 300, 660, 400, 64, card)
    rough_rect(img, 300, 760, 400, 120)
    wobble_line(img, (300, 760), (700, 880))
    wobble_line(img, (700, 760), (300, 880))
    add("image", "", 300, 760, 400, 120, card)
    blur = cv2.GaussianBlur(img, (3, 3), 0)
    noise = rng.normal(0, 4, blur.shape)
    out = np.clip(blur.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    FIXTURES.mkdir(exist_ok=True)
    cv2.imwrite(str(FIXTURES / "login_sketch.png"), out)
    (FIXTURES / "login_sketch.json").write_text(json.dumps({"width": W, "height": H, "components": comps}, indent=1))


if __name__ == "__main__":
    main()
