"""Optional local OCR (RapidOCR on onnxruntime, CPU, ~15 MB of bundled models).

Reads handwritten-style wireframe text lines with their boxes so that labels are located and read locally and the
vision model only has to decide *what each element is*. Everything degrades gracefully: when the package is not
installed (or NGUI_OCR=0) `read_lines` returns None and the pipeline behaves exactly as before."""
from __future__ import annotations

import os
import threading

import cv2
import numpy as np

_lock = threading.Lock()
_engine = None
_failed = False


def available() -> bool:
    global _engine, _failed
    if os.environ.get("NGUI_OCR", "1").strip().lower() in ("0", "false", "no", "off") or _failed:
        return False
    with _lock:
        if _engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR  # noqa: PLC0415 - optional dependency
                _engine = RapidOCR()
            except Exception:  # missing wheel, missing model, broken onnxruntime: run without OCR
                _failed = True
                return False
    return True


WORD_GAP = 0.3  # blank run / ink height that separates two words
CERTAIN_GAP = 0.4  # a gap this wide is a space even inside a known word ("Log out")
DIGIT_GAP = 0.45  # between two digits only a clearly wider run is a space (numbers are written with gaps: 1,240)
# common single words of UI wireframes: a line that reads as one of these is never split by a letter gap
UI_WORDS = frozenset("""
about account log out add address all amount and app apply back balance bank bill bills book booking buy call cancel cart change check checkout
city clear close code company confirm contact continue copy country create dark date delete deals description details discard done
download edit email enter error events exit explore feed filter first flights follow followers following forgot friends from gender get
help home hotels hours inbox info interest invoice join keep language last lamp learn left light loan login logout mail main map menu
message messages mode more my name new news newsletter next night notes notifications now number of off offers ok on open order orders
or orders overview page password pay payment phone photo photos plan post posts price pricing pro privacy profile pulse quantity rate
read recent recipient register remember remove reply report reset results review reviews save search select send service services
settings share shop sign signin signup size skip sneakers sort start status step stores submit subject subscribe summary support tag
tags tickets time title to today total transfer try type update upload user username venue view visa visibility weather welcome
what when where why with year yes your
the an at by for in is it of our up us we club issue describe
""".split())

_NARROW = set("iljtfI1.,:;'!|()")
_WIDE = set("mwMW@%")


def _char_weights(text: str) -> list[float]:
    """Rough relative advance width of every character (proportional sans-serif / handwriting)."""
    return [0.4 if ch in _NARROW else 1.55 if ch in _WIDE else 1.2 if ch.isupper() or ch.isdigit() else 1.0 for ch in text]


def word_gaps(img: np.ndarray, px: tuple[int, int, int, int]) -> tuple[list[tuple[float, float]], float, float]:
    """Wide blank columns inside the ink of one text line: ([(centre_x, width / ink height)], ink_left, ink_right), x relative to the
    crop. On the dev set real word gaps are >= ~0.3 of the ink height, gaps between letters of handwriting reach ~0.27."""
    x, y, w, h = px
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    crop = gray[max(0, y):y + h, max(0, x):x + w]
    if crop.size == 0:
        return [], 0.0, 0.0
    _, mask = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    rows, cols = np.where(mask.any(axis=1))[0], mask.any(axis=0)
    if len(rows) == 0 or not cols.any():
        return [], 0.0, 0.0
    ink_h = float(rows[-1] - rows[0] + 1)
    idx = np.where(cols)[0]
    left, right = int(idx[0]), int(idx[-1])
    runs, start = [], None
    for i in range(left, right + 2):
        blank = i <= right and not cols[i]
        if blank and start is None:
            start = i
        elif not blank and start is not None:
            runs.append((start, i - start))
            start = None
    if not runs:
        return [], float(left), float(right + 1)
    wide = [(s + n / 2.0, n / ink_h) for s, n in runs if n / ink_h >= WORD_GAP and n >= 3]
    return wide, float(left), float(right + 1)


def _is_word(token: str, vocab) -> bool:
    return token.lower().strip(" .,:;?!$+()") in vocab


def _natural_boundary(text: str, c: int) -> bool:
    """A boundary where words usually meet: lower->Upper, letter<->digit, next to a symbol or after a comma."""
    a, b = text[c], text[c + 1]
    return ((a.islower() and b.isupper()) or (a.isalpha() and b.isdigit()) or (a.isdigit() and b.isalpha())
            or a in ",;-/&|+" or b in "-/&|+$(" )


def _refine_cuts(text: str, cuts: list[int], vocab) -> list[int]:
    """Move each cut up to 2 characters so that more of the words around it are known words (the width model is only approximate)."""
    cuts = list(cuts)
    for k in range(len(cuts)):
        lo = cuts[k - 1] + 2 if k else 1
        hi = (cuts[k + 1] if k + 1 < len(cuts) else len(text)) - 1

        def score(c: int) -> int:
            left_start = (cuts[k - 1] + 1) if k else 0
            right_end = (cuts[k + 1] + 1) if k + 1 < len(cuts) else len(text)
            return (_is_word(text[left_start:c + 1], vocab) + _is_word(text[c + 1:right_end], vocab)
                    + 0.9 * _natural_boundary(text, c))
        options = [c for c in range(cuts[k] - 2, cuts[k] + 3) if lo <= c + 1 <= hi and 0 <= c < len(text) - 1]
        if options:
            cuts[k] = max(options, key=lambda c: (score(c), -abs(c - cuts[k])))
    return cuts


def tidy_spaces(text: str, vocab: set[str] | None = None) -> str:
    """Join fragments the recogniser split inside a known word ("Sub scribe" -> "Subscribe")."""
    vocab = (vocab or set()) | UI_WORDS
    words = text.split()
    out: list[str] = []
    for word in words:
        if out and _is_word(out[-1] + word, vocab) and not (_is_word(out[-1], vocab) and _is_word(word, vocab)):
            out[-1] += word
        else:
            out.append(word)
    return " ".join(out)


def insert_spaces(text: str, gaps: list[tuple[float, float]], left: float, right: float, vocab: set[str] | None = None) -> str:
    """Put a space at the character boundary closest to every wide gap (positions from a per-character width model).
    With a vocabulary (words of the user's description), a boundary within 2 characters that splits the text into known words wins."""
    if " " in text or not gaps or len(text) < 3 or right <= left:
        return text
    vocab = (vocab or set()) | UI_WORDS
    known_word = text.lower().strip(" .,:;?!") in vocab and max(r for _, r in gaps) < CERTAIN_GAP
    weights = _char_weights(text)
    total = sum(weights)
    edges, acc = [], 0.0
    for wgt in weights[:-1]:
        acc += wgt
        edges.append(left + (right - left) * acc / total)  # edges[i] sits between char i and i+1
    cuts: list[int] = []
    for cx, ratio in sorted(gaps):
        near = min(range(len(edges)), key=lambda i: abs(edges[i] - cx))
        a, b = text[near], text[near + 1]
        if (a in ",." and b.isdigit()) or (a.isdigit() and b in ",.") or (a.isdigit() and b.isdigit() and ratio < DIGIT_GAP):
            continue  # inside a number
        if cuts and near <= cuts[-1]:
            near = cuts[-1] + 1
        if near < len(edges) and near not in cuts:
            cuts.append(near)
    cuts = _refine_cuts(text, cuts, vocab)
    while True:  # a one-letter fragment ("S earch") is a letter gap, not a word: drop the cut next to it
        bounds = [0] + [c + 1 for c in cuts] + [len(text)]
        bad = next((k for k in range(len(bounds) - 1)
                    if sum(ch.isalnum() for ch in text[bounds[k]:bounds[k + 1]]) == 1
                    and text[bounds[k]:bounds[k + 1]].strip().isalpha() and text[bounds[k]:bounds[k + 1]].strip() not in ("a", "A", "I")), None)
        if bad is None or not cuts:
            break
        cuts.pop(bad if bad < len(cuts) else bad - 1)
    out = [text[a:b] for a, b in zip([0] + [c + 1 for c in cuts], [c + 1 for c in cuts] + [len(text)])]
    if known_word and not all(_is_word(p, vocab) for p in out):
        return text  # a known single word whose pieces are not words: the gap is between its letters ("Sub scribe")
    return " ".join(p for p in out if p)


def read_lines(img: np.ndarray, min_score: float = 0.5, vocab: set[str] | None = None) -> list[dict] | None:
    """Text lines of a BGR image: [{"text", "score", "px": (x, y, w, h)}] or None when OCR is unavailable.
    Multi-word labels keep their spaces: the image is read at NGUI_OCR_SCALE (default 2), and lines that still come back without
    spaces are split at the wide blank gaps of the ink (`word_gaps` / `insert_spaces`; `vocab` = known words, e.g. of the description)."""
    if not available():
        return None
    # the recogniser drops spaces between words on small handwriting; reading an enlarged copy keeps most of them
    # (dev set, 153 multi-word labels: 60% of them with correct spaces at scale 1, 84% at scale 2)
    scale = float(os.environ.get("NGUI_OCR_SCALE", "2.0") or 2.0)
    big = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale != 1.0 else img
    try:
        with _lock:
            result, _ = _engine(big)
    except Exception:
        return None
    lines = []
    for box, text, score in result or []:
        text = (text or "").strip()
        if not text or float(score) < min_score:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x0, y0 = max(0, int(min(xs) / scale)), max(0, int(min(ys) / scale))
        px = (x0, y0, int(max(xs) / scale) - x0, int(max(ys) / scale) - y0)
        if " " in text:
            text = tidy_spaces(text, vocab)
        elif len(text) >= 4 and os.environ.get("NGUI_OCR_SPLIT", "1").strip().lower() not in ("0", "false", "no", "off"):
            gaps, left, right = word_gaps(img, px)
            text = insert_spaces(text, gaps, left, right, vocab)
        lines.append({"text": text, "score": round(float(score), 3),
                      "px": px})
    return lines
