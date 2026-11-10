# Voice refinement and repair: failure analysis and fixes (dev set, 2026-11-02)

Dev set only (40 sketches, 80 commands). The hold-out set was not looked at. "Before" = `results/latest` (run 20261101-130238).
Runs: `results/20261102-refine` (refine/intent/repair/validate fixes, cached sketch analyses and create-ops, new interpretation of all 160
command strings, full faults), `results/20261102-create` (adds the create-prompt completeness change; sketches/requirements only),
`results/20261102-final` (everything; **its command stages are void**, see "Limits"). `results/latest` was not overwritten.

## 1. What failed and why (before)

| Area | Failures | Root cause |
|---|---|---|
| Resize (interpretation 70% text / 60% Whisper) | cmd_043, 044 returned `style` ops instead of `resize`; cmd_048 returned `rows: 8` (no direction); cmd_046 (Whisper) returned `width: null`; cmd_042 (Whisper) hit two buttons | prompt had no rule for relative wording: the model picked an op kind, a size word or rows at random. "full width" and "wider" were conflated. `apply_ops` had no notion of axis. |
| Resize refinement (90 / 80%) | cmd_046 (Whisper) no area change; cmd_049 | op accepted without visible effect; cmd_049: "MyBank" text absent from the base IR (detection) |
| Modify cmd_029 | "email field" resolved to text `Email`, no input exists | sketch labelled the drawn input as text; resolver correctly refused the text, op dropped |
| Move cmd_040 | "below the time slots" anchored on one radio, date field landed mid-group | plural reference means the group |
| Move cmd_036 | "amount field" not in IR | detection (not fixable here) |
| Navigation cmd_071 (interpretation) | model emitted `interaction` with only a `navigate` action | two encodings of the same intent |
| Hidden-node repair 42.5% | 23/23 failures: repair did `unhide` **and** `reinsert_from_sketch` (duplicate node) | coverage fix ran after/independently of the presence fix |
| Zero-size repair 75% | 8 detected only as a soft `layout:` check, so the loop (hard checks only) did nothing; 2 undetected | no check for a collapsed box |
| Deleted-node repair 55% | 9 undetected (no sketch component of its own: caption text absorbed by a checkbox, voice-made nodes), 9 repaired but with a misplaced/duplicated node (checkbox plus caption text re-inserted twice; row children ordered by y) | coverage-only recovery |
| Requirement satisfaction 87.5% | 52 failing checks: of 43 `node_exists`, 37 are the **right label with the wrong type** (13 text, 7 card, 5 nav_item where a heading was required, ...), 6 absent labels; the rest input_type / count / interaction | create-op listed containers ("stat cards") instead of the named leaves; typing happens in fusion |

## 2. Fixes (all general, no per-test code)

* `refine.py`: `parse_resize_phrase` (documented RELATIVE SIZES table: bigger 1.3, a bit 1.15, a lot 1.6, twice 2, half 0.5, N%, full width; axis from wider/taller);
  `resize` rewritten: `scale`+`axis`, current extent = explicit style, else drawn sketch size, else per-type default; width reaching the page becomes `full`; textarea uses rows;
  size words become factors; plural anchors ("the time slots") use the edge of the option group; a text caption becomes the input when the user addresses a field and none exists (only for field-only props);
  `remove` records `meta.removed_ids`.
* `intent.py`: new `ir_summary` (ids, size hints, nodes per type in reading order, shared-label notes), disambiguation rules and resize examples in the prompt, `axis` in the schema,
  `_normalise_resize` (every size change is a `resize`; magnitude from the utterance, target from the model), navigate-only interaction becomes a `navigation` op,
  create prompt lists every named component with the right type.
* `validate.py`: `size:<id>` hard check (explicit 0 size or collapsed sliver), optional `reference` snapshot (`missing:<id>`, `snapshot_hidden:<id>`).
* `repair.py`: fixes ordered (restore/unhide before coverage), coverage skipped when already represented, row-aware insertion, checkbox/radio caption merged, `reset_size`, `restore_from_snapshot`, optional `reference`.
* Tests: `backend/tests/test_refine_repair_v2.py` (30 tests). Backend suite: 109 passed, 2 skipped.

## 3. Measured results (dev set, real runs)

Interpretation (all correct, `scoring.score_interpretation` on the new raw outputs of run `20261102-refine`; the run's own summary reports the same):

| | before | after |
|---|---|---|
| overall, text / Whisper | 93.8 / 91.2 | 96.2 / 96.2 |
| resize, text / Whisper | 70 / 60 | 100 / 100 |

Refinement success (rendered post-condition), run `20261102-refine`: overall 95.0 -> 97.5 (Whisper 93.8 -> 96.2); resize 90 -> 90 (text), 80 -> 90 (Whisper); modify 90 -> 100 (text); move 80 -> 90.
Baseline unchanged at 90.0. Preservation 99.8 -> 99.7. Remaining failures: cmd_036 and cmd_049 (target absent from the base IR), cmd_029 Whisper (model picked another node).
Two later code changes (navigate-only -> navigation, caption merge in repair, create prompt) are not covered by a command re-run, see Limits.

Fault injection, repaired % (final run, same seeds, 40 sketches each):

| source / fault | before | after |
|---|---|---|
| pipeline hide_node | 42.5 | 100 |
| pipeline zero_size | 75.0 | 100 (detected 95 -> 100) |
| pipeline delete_node | 55.0 (detected 75) | 70.0 (detected 72.5) |
| pipeline all | 73.7 | 93.5 |
| oracle all | 73.1 | 98.1 |
| pipeline+snapshot delete / hide | n/a | 100 / 100 |
| oracle+snapshot delete / hide | n/a | 100 / 100 |

"+snapshot" gives validate/repair the pre-fault IR as the previous version (what a real refinement step has). Without it, deletions of nodes with no sketch component of their own
(11 of 40) stay undetectable; that is why the plain `pipeline delete_node` number stays at 70%. The headline `fault_repair_rate` is now 96.9 (it also pools the snapshot rows); the like-for-like figure is the `pipeline` row, 93.5.
`break_event` detection moved 100 -> 94.9 (one new case, repaired 100%).

Sketch-level (run `20261102-create`, proposed pipeline only): requirement satisfaction 87.5 -> 88.0 (+2 requirements, create-op completeness), functional 94.8 -> 98.3, DOM F1 42.9 -> 44.5, layout IoU 0.399 -> 0.408.
Validation pass rate before repair 100 -> 97.5 (one generated UI now fails a check, and repair does not clear it; not investigated). Requirement gain is small and within what one extra
LLM sample could change; the 37 wrong-type labels need fusion-side retyping (BACKEND_ISSUES.md).

## 4. Limits (honest)

* The OpenAI account ran out of credits (HTTP 429, "no credits remaining") during the last run, so the command stages of `results/20261102-final` failed and are void. Nothing was fabricated; those tables are 0/dashes.
  The valid command numbers are from `20261102-refine`, which predates the navigate canonicalisation, the create-prompt change and the caption merge, and was run on the old create-ops (base IRs). The create-prompt change therefore has no end-to-end refinement measurement.
* Resize success on the rendered UI is 90% in both modes; the two remaining misses are not resize logic.
* Dev-set numbers, tuned on this set; expect lower on the hold-out. Several prompt examples were deliberately written with different wording/components than the dev commands.
* Snapshot recovery: now wired in the orchestrator (section 5).

## 5. Follow-up fixes (2026-11-06, offline only, no API calls)

* OCR spaces (`ocr.py`, `sketch.py`): default `NGUI_OCR_SCALE` is now 2, plus a gap-based post-pass (`word_gaps`/`insert_spaces`/`tidy_spaces`, `NGUI_OCR_SPLIT=0` disables it). Dev set, 153 multi-word labels: correct spaces 60.1% (old default, scale 1) -> 83.7% (scale 2) -> 88.9% (scale 2 + post-pass; 94.4% of the labels whose letters were read right). Thresholds were tuned on this set.
* shop_01 / book_01 (run `20261102-detect`) reproduced from the cached analysis + ops: (1) a handler `show_message` then `navigate` lost its message with the page (now carried as a notice, `ui.notice`); (2) geometry offsets/widths of overlapping siblings overflowed their row and covered the next box (offsets clamped to the parent, percentage widths may shrink). The same pipeline_build, re-run on the cached raw outputs: pass rate before and after repair 38/40 -> 40/40 (95 -> 100%).
* The "97.5%" case (contact_03, run `20261102-create`): a required `select` with no options can never be filled (validator `select_option` times out, so a real user could not submit). Fusion now gives option-less selects placeholder options; repair has `default_options`. Re-run: 39/40 -> 40/40. Run `20261102-refine` was already 40/40 and stays 40/40.
* Repair no longer gives up on a hard check after one failed fix: covered controls (`covered:` detail from Playwright) trigger a re-layout, and a check that keeps failing escalates (`relayout` of 3 ancestor levels, then `relayout_page`).
* Snapshot recovery is wired: `run_modify` passes the base version's IR as `reference` to validate/repair; `run_validate(do_repair)` uses the parent IR of a modify version.
* Not re-measured: end-to-end requirement/refinement numbers (they need API calls); the cached analyses predate the OCR change.
