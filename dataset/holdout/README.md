# NeuroGenUI held-out test set

Synthetic (labels `"synthetic": true`, `"split": "holdout"`). Never used to tune prompts, thresholds or code:
run it once, after tuning, to report one unbiased number.

- 20 sketches (2 per category, ids `hold_<cat>_0N`) in `sketches/`, labels in `labels/` (same format as `dataset/labels`).
  Layouts are new (see `tools/specs_holdout.py`), not variants of the 40 dev screens.
- Harsher style than dev: stronger drift/jitter, per-stroke pen width 0.6-1.9x, slanted lines, long overshoots,
  unclosed/short-sided rectangles, re-stroked boxes, scratch-out scribbles in free space (unlabelled), per-glyph
  rotation and sloped baselines, page rotation 1-3 degrees + mild perspective, uneven lighting, fibres, crease,
  JPEG round trip. Boxes in the labels are pushed through the same homography.
- Fonts (OFL, in `tools/fonts/`): Indie Flower, Kalam, Shadows Into Light (none used in dev). The machine has no
  other handwriting fonts (only Z003, a calligraphic face, which was not used).
- 30 voice commands, `commands/commands.jsonl` (ids `cmd_h001`-`cmd_h030`; add 4, remove 4, modify 4, move 4,
  resize 4, style 4, interaction 3, navigation 3), audio `commands/audio/*.mp3` from `tts-1`, voices nova / onyx / fable
  (per-command in `commands/audio_meta.json`).

Regenerate: `make_sketches_holdout.py`, `make_commands_holdout.py`, `make_audio_holdout.py` (in `tools/`, run with the
evaluation venv). Evaluate: `python evaluation/run_all.py --dataset holdout` -> `evaluation/results/<ts>-holdout/`
and `results/latest-holdout/`.
