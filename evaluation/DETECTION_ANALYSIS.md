# Sketch component detection: error analysis and what changed

Dev set only (40 synthetic sketches, 490 GT components). Holdout was not looked at, run or tuned on.
Metric = `checks.match` (Hungarian, IoU >= 0.3, strict type), micro-averaged. Before = run `20261101-130238`.
After = run `20261102-detect` (official harness, `--skip-commands --skip-faults`, gpt-4.1-mini vision) unless marked "dev harness".

## 1. Error analysis of the starting point (hybrid, run 20261101-130238)

Localisation was mostly fine (436 of 490 GT boxes matched at IoU 0.3, 53.9 F1 in a replay). The loss was typing and structure:

| GT type | Dominant error (hybrid) |
|---|---|
| heading (92) | 38 labelled `text`, others button/nav_item/input (size not used) |
| nav_item (42) | 19 `text`, 6 `link`: menu words not tied to their bar; brand typed as nav_item |
| checkbox / radio (30) | 21 typed `text`: the GT box is mark + option text, we output them separately (mark = FP, text = wrong type) |
| divider (7) | all 7 `text` (wavy rule read as a squiggle placeholder) |
| list (7) | 6 missed (no outline, items detected as separate texts) |
| select (14) | 6 `input`, 3 `button`/`text` (chevron ignored) |
| header/navbar (20) | `card`/`container` for most bars; sidebar nav missed |
| card (37) | 9 not found (big boxes fused to children), 4 typed `container` (GT has no container) |
| image (33) | chart boxes with double border typed card/container |

False positives (583 predictions for 490 GT): 72 `text` (word fragments, text inside fields, list items, labels of boxes
that were not found), 21 `icon` (radio circles, glyph inside fields, letters read as circles), 26 checkbox/radio marks without their text,
divider = underline strokes, `rect` loops between the letters of a word.
Also: ink-tight text boxes are ~1.5x shorter than the line box GT uses and hand-drawn rectangles overshoot by 6-19 px.

CV-only had the same pattern (42.9 F1, type accuracy 52.9%).

## 2. Changes (all general rules, no per-sketch logic)

Files: `backend/app/pipeline/sketch.py`, new `sketch_refine.py`, new optional `ocr.py`, `fusion.py` (list items), `codegen.py` (geometry), `llm.py` (reasoning-model params).

Proposals (sketch.py)
- Text grouping into words then lines with a gap rule relative to text height; menu items stay separate; unlabeled fragments in the same bar are not glued.
- Long sparse strokes (a box edge that survived outline removal) no longer glue words together (this had made "Nimbus" and the menu disappear).
- Wide-short closed loops (the gap between letters, under an underline) and short open "boxes" (< 32 px) are no longer proposed as controls.
- Bullet marks + stacked lines become a `list` proposal.
- Box calibration: text boxes padded to a line box; rectangles pulled to the stroke centre line (median of stroke positions per side).
- Background flattening in `ink_mask` (division by a dilated+blurred background estimate).
Typing / structure (sketch_refine.py): marker + option text union (and OCR lines that swallowed the mark: "OLow"); chevron or glyph in a field removed, chevron => select; top bars navbar/header, tall menu strip => navbar, empty frame / stroke-only box => image, other boxes => card; brand = first word of a bar, rest nav_item; heading/text by size (OCR boxes: >= 40 px heading, < 30 px text, between = reader's opinion); thin stroke under text = underline (link) else divider; list items folded into the list (`items`, used by fusion); fields whose outline is missing are completed from a caption in the siblings' column or a caption plus a lone far-end glyph.
Vision prompt: pixel size and OCR reading in the numbered-box list, an explicit vocabulary rule list (checkbox/radio, select, bars, picture vs card, list, divider, heading vs text), `none` only if OCR sees no words; optional second pass `NGUI_SKETCH_VERIFY=1` (detector output drawn as `n:type` boxes, model returns only retype/remove/missing fixes).
Local OCR (RapidOCR/onnxruntime, ~16 MB models in the wheel, ~1 s per sketch on CPU, optional, `NGUI_OCR=0` or a missing wheel falls back): reads text lines with boxes; `backend/requirements-ocr.txt`, `setup.bat` and `Dockerfile` install it without failing the setup if it cannot. Known quirk: it drops spaces in small handwriting; `NGUI_OCR_SCALE=2` keeps ~85% instead of ~65% of multi-word labels (default stays 1.0 because all numbers below were measured at 1.0; the vision label is preferred whenever it matches the OCR text ignoring spaces).

## 3. Results (dev set)

Official harness, gpt-4.1-mini, before -> after
| Output | F1 before | F1 after | type acc. before -> after |
|---|---|---|---|
| OpenCV only | 42.9 | 69.5 (with OCR) | 52.9 -> 75.8 |
| Vision only | 33.5 | 43.4 | 69.0 -> 87.6 |
| Hybrid | 53.1 | 74.9 | 68.1 -> 81.8 |
| Rendered DOM, proposed | 42.9 | 52.0 | 82.3 -> 84.5 |
| Rendered DOM, oracle (GT IR) | 77.5 | 82.7 | 95.5 -> 96.2 |
Per-category hybrid F1: dashboard 33.8 -> 64.5, settings 34.0 -> 69.0, booking 47.4 -> 72.4, banking 52.8 -> 80.4, login 71.6 -> 85.7.
Replaying the unchanged old code with the same API gave 53.9 (vs 53.1 official), so vision noise at temperature 0 is about +-1 F1.

Ablation (dev harness, same code, vision gpt-4.1-mini; each row adds one thing)
| Configuration | P | R | F1 |
|---|---|---|---|
| Old code, hybrid (replay) | 49.6 | 59.0 | 53.9 |
| + post rules only (cached vision, no prompt change) | 64.8 | 74.1 | 69.1 |
| + proposal fixes + new prompt + list/field rules (no OCR), hybrid | 68.2 | 75.7 | 71.8 |
| same, CV only, no OCR | 52.3 | 56.3 | 54.2 |
| + OCR, CV only | 68.1 | 71.0 | 69.5 |
| + OCR, hybrid | 72.4 | 76.1 | 74.2 |
OCR lifts CV-only by +15 F1 and gives local text with no API, but adds only +2.4 F1 on top of the vision hybrid (labels are read well by the vision model already; OCR's gain there is mainly label accuracy and placing text).

Vision model (hybrid, OCR on, dev harness, one run each; latency = mean per vision call, tokens per call in/out ~3.0k/0.4k)
| Model | F1 | type acc. | latency |
|---|---|---|---|
| gpt-4.1-mini | 74.2 | 81.1 | 7.7 s |
| gpt-4o | 77.8 | 84.9 | 5.7 s |
| gpt-4.1 | 80.6 | 87.5 | 5.1 s |
| gpt-5.4 | 84.8 | 90.3 | 6.9 s |
| gpt-5.2 | 87.1 | 91.7 | 7.4 s |
| gpt-5.2 + verify pass (2 calls, mean 5.8 s each) | 89.0 | 94.2 | ~12 s per sketch |
gpt-5 (full reasoning) took ~12 s for a trivial JSON request, so it was not run (over the 30 s budget). gpt-5.x need no `temperature` (handled in `llm.py`). Cost was not measured from billing; token counts above are real, list prices were not applied. The verify pass only exists in the gpt-5.2 row (and its cache); a gpt-4.1-mini verify run and the gpt-5.2 no-OCR / vision-only runs were cut off when the API returned 429 "no credits remaining" and are NOT reported.
Recommendation: set `OPENAI_VISION_MODEL=gpt-5.2` (+0 s latency vs mini, +12.9 F1); `NGUI_SKETCH_VERIFY=1` adds ~5 s and +1.9 F1. The default in config remains gpt-4.1-mini: the official headline above was measured with it, and changing the default is for the orchestrator to decide.

## 4. Why a correct IR loses points on the rendered DOM (oracle 77.5)

1. The measured extractor (`validate.extract_dom`) cannot emit `card`, `list`, `container` or `icon`; 58 of 490 GT components can never match. The richer `dom.py` extractor (cards, lists, icons) scores the same oracle UIs 83.3 vs 77.5 before codegen changes. This is an extractor limit, not a compiler fault. Not changed (not my file).
2. Compiler geometry: small controls (checkbox/radio/link/nav_item) rendered shorter than drawn, so rows below drifted up; dividers were 1 px high boxes (IoU ~0 with the drawn band); icons were 32 px spans. Fixed in `codegen.py`: drawn min-height for those controls, divider band via padding, icon size capped at 38 px. Oracle DOM F1: 77.5 -> 83.6 (validate extractor, before the 38 px icon cap) / 82.7 final with the icon cap, 83.3 -> 89.6 with `dom.py`.
3. Remaining: text boxes are rendered tighter than the GT line boxes, radio rows still off by a few px, 4 lists / 4 radios unmatched.

## 5. Robustness to real photographs (augmented dev set)

Augmentations on the dev sketches only (never holdout): rotation +-3 deg (GT boxes transformed), shadow gradient, faint strokes (0.55x), ruled+grid paper, blur sigma 1.6, and all of them plus noise. CV mode F1 (no-OCR / OCR), measured with the current proposals:
| Condition | before bg-flattening | after bg-flattening |
|---|---|---|
| clean | 54.2 / 69.5 | 54.2 / 69.3 |
| rotation | 48.4 / 64.0 | not rerun (no deskew implemented) |
| shadow | 57.3 / 70.7 | 54.8 / 69.7 |
| faint | 53.0 / 70.7 | 53.2 / 71.0 |
| ruled paper | 54.9 / 69.5 | 54.6 / 68.8 |
| blur | 55.1 / 68.1 | not rerun |
| all combined | 38.9 / 46.8 | 45.8 / 48.6 |
Honest reading: single augmentations barely move CV F1 (the adaptive threshold already copes with shadows/faint ink); rotation costs ~5 points; the combination costs ~21 points with OCR (69 -> 49). Background flattening helps only the combined case (+2 to +7) and is neutral or slightly negative elsewhere. NOT done: deskew, the semantic-first pass (model lists components with coarse cells, boxes snapped to CV clusters, boxes synthesised where CV found nothing) and a re-run of the hybrid on augmented images, because the OpenAI account ran out of credits during the vision-model ablation. Real hand drawings with unclosed boxes, strong perspective or heavy scribbles are expected to score clearly lower than these synthetic numbers; the field-completion and OCR rules are the pieces most likely to help there, the outline-based card/box detection the least (9 big cards are still missed even on clean synthetic sketches).

## 6. Remaining errors (clean dev set, hybrid + OCR)
heading<->text in the ambiguous 30-40 px band, 9 large cards fused with their content, unmatched inputs with two missing edges, select vs input without a visible chevron, header vs navbar for 2-item bars, checkbox drawn as circle typed radio.
