# Backend issues found during evaluation

Evaluation does not patch backend files. Each item below was reproduced in-process against
`project/backend/app/pipeline` on 2026-11-01. The reproduction scripts are inline so the backend owner can rerun them.

## 1. A sketch-detected `list` renders invisibly and always fails validation

**Where:** `fusion.fuse` → `codegen` (List component) → `validate` presence check.

`SketchAnalysis` components carry no `props.items`, so a list detected from a sketch (or given as GT) becomes a
`list` node with `items` missing and `children: []`. The compiled `<ul>` has zero height, and `validate` reports
`presence:<list id> — not visible` as a **hard** failure. `repair_loop` cannot fix it: `reset_style` has nothing
to reset. Any sketch with a drawn list therefore fails validation even after repair. In the dataset that is
dash_01, dash_03, bank_01, shop_04 and land_04, unless the voice instruction happens to supply the items.

```python
from app.pipeline import fusion, codegen, validate
an = {"components": [{"type": "heading", "label": "Recent orders", "bbox": {"x": .1, "y": .1, "w": .3, "h": .05},
                      "confidence": 1, "source": "gt", "parent": None},
                     {"type": "list", "label": "", "bbox": {"x": .1, "y": .2, "w": .3, "h": .2},
                      "confidence": 1, "source": "gt", "parent": None}],
      "width": 1000, "height": 600, "mode": "gt", "timings": {}}
ir = fusion.fuse(an, [], title="t")
rep = validate.validate(ir, codegen.generate_code(ir)["preview"], an)
# -> failing: ('presence:list_2', 'not visible')
```

**Suggested fix:** give a list without items placeholder items (for example "Item 1…3", or the line count from the
sketch box height) in fusion or codegen. Alternatively, treat an empty list as a soft check.

## 2. A component hidden through `style.hidden` is not detected, even when the sketch shows it

**Where:** `validate` presence and sketch-coverage checks.

If a node that came from the sketch gets `style.hidden = true` (a wrong voice op, a bad repair, a manual edit),
`validate` does not report it. The presence check skips intentionally hidden nodes, and the sketch-coverage
check still counts the hidden node as covering its sketch component. In the fault-injection experiment
(`csv/faults.csv`, fault `hide_node`) this fault is never detected and therefore never repaired. In the
reproduction below, hiding the only heading produces no failing check for the heading:

```python
ir2 = copy.deepcopy(ir); h = next(n for n, _, _ in irm.walk(ir2) if n["type"] == "heading")
h["style"]["hidden"] = True
rep2 = validate.validate(ir2, codegen.generate_code(ir2)["preview"], an)
# failing checks: presence:page_main, presence:list_2   (nothing for h_recent_orders)
```

**Suggested fix:** in the coverage check, do not count hidden nodes as covering a sketch component. A sketch
component whose only match is hidden should fail coverage, and `reset_style` should then unhide it.
`toggle_visibility` targets that start hidden on purpose could be exempted using the IR's events.

## 3. Navigation ops from `intent.parse_commands` are rejected by `refine.apply_ops` ("no page name")

**Impact:** pipeline navigation refinement succeeded on only 3/10 commands (text) and 5/10 (Whisper) in run
`results/20261101-002519`, while the interpreter itself got the page right (interpretation all-correct 100% from text, 90% from Whisper).

The intent LLM often returns a navigation op with the destination only inside `event.actions`:

```json
{"op": "navigation", "target": {"ref": "Cancel button", "id": "btn_cancel"},
 "event": {"on": "click", "actions": [{"type": "navigate", "page": "Home"}]}}
```

`refine.apply_ops` requires `op["page"]["name"]` and records
`{'op': 'navigation', 'target': 'btn_cancel', 'ok': False, 'error': 'no page name'}`, so no page and no handler are
created (cmd_071, 072, 074, 075, 076, 079, 080). Reproduce with
`raw/interpret_cmd_text/cmd_071.json` + `raw/pipeline_build/reg_03.json`.
**Fix:** in `refine` (navigation), fall back to the first `navigate` action's `page` when `op.page` is missing, or
make the intent schema require `page.name` for navigation ops.

## 4. Resize ops that `apply_ops` accepts have no visible effect, or are rejected

| Command | Op from intent | Result |
|---|---|---|
| cmd_045 "make the avatar smaller" (prof_01) | `style.size: "sm"` on an image whose style has `height: 159` | accepted, rendered size unchanged (ratio 1.00) |
| cmd_046 "Make the product image smaller" (shop_02) | `style.size: "sm"`, image has `height: 420` | accepted, unchanged |
| cmd_044 "Make the search box wider" (dash_02) | `style.width: "full"` on an input inside a header row | accepted, rendered width unchanged |
| cmd_048 "Make the message box taller" (contact_01) | `changes.props.rows: 8` on a textarea | rejected: `no size given` |

**Fix:** have resize scale an existing explicit `height`/`width`. Let `size` override the sketch-derived height for
images. Make `width: full` effective inside row containers (`flex: 1`). Accept `props.rows` for textareas.

## 5. `move ... below X` keeps the node inside a row container, so it ends up to the right, not below

cmd_031, brief §4.4 "Move the button below the password field." (login_02): the Log In button and the password
field share the header row. `apply_ops` reports `moved below inp_password`, but in a row-direction container
"after" renders to the right (button centre y=80 vs password y=93). **Fix:** for `below`/`above` relations whose
anchor sits in a row container, wrap the anchor and the moved node in a column box, or move the node out to the
row's parent right after the row.

## 6. The repair loop never fixed a real generation failure (0 of 43 repair actions effective)

In run `results/20261101-002519`, 23/40 generated UIs fail validation. All failing hard checks are `presence`
(not visible) on nodes that have nothing to render:

- empty-label `text` nodes (the sketch's scribbled paragraphs, e.g. `txt_5`, `txt_23`);
- wrapper containers with no visible content (`box_hero_section`, `box_login_form_container`, ...);
- lists without items (issue 1).

There are also 3 `event:*:click` failures (on a select and a container). `repair_loop` applies `reset_style` (40×) and
`rebuild_handler` (3×). Every one returns `still failing`, so the pass rate is 42.5% both before and after repair, and
the repaired code is identical to the unrepaired code for 39/40 sketches.

**Fix:** have fusion give unlabeled sketch text a placeholder sentence (or render scribbles as a muted
placeholder paragraph), drop or collapse empty wrapper containers, and use a repair action for "not visible because
empty" that fills or removes the node instead of resetting style.

In the fault-injection experiment, by contrast, the loop does repair what it targets: re-insert deleted nodes
82.5% (oracle IRs), zero-size 72.5%, swap order 92.1%, broken handlers 100% (pipeline IRs).

## 7. Fusion artefacts seen in generated IRs (for information)

- dash_01: two `Dashboard` headings (`h_dashboard`, `h_dashboard_2`), from the sketch heading plus a voice heading
  that was not merged. Renaming one leaves the other (cmd_024 fails). The banner-like image was also placed inside
  the navbar.
- book_02: the radio drawn as "9:00" was labelled `Time slot`, the label of the text above it, so no 9:00 option
  exists.
- set_02: "the email field" resolved to `txt_email` (a text label node) instead of the input, so the
  placeholder change is applied to a text node and has no effect (cmd_029). `resolve_target` and the intent prompt
  should prefer field types for "field/box/input" references.

## Status after fixes (final run, results/latest)

The defects above were fixed in a second pass and the full evaluation was re-run on the same test set.

Resolved (as measured in the final run):
- Navigation refinement: 10/10 navigation commands succeed (was 3/10).
- Invisible nodes / validation: 100% of generated UIs pass validation before repair (was 42.5%).
- Layout fidelity: layout IoU 0.399 (was 0.205); detection F1 on the rendered DOM 42.9% (was 16.5%).
- Hidden-component detection: the validator now flags a drawn component that is hidden.

Still open:
- Repair is weak on hidden nodes (42.5% repaired on pipeline UIs) and deleted nodes (55%); deleted nodes are also the least-detected fault (75%).
- Resize commands are the least reliable: refinement success 90% from text and 80% from the Whisper transcript; only 70% (text) / 60% (transcript) are interpreted fully correctly, because relative sizes such as "a bit bigger" are ambiguous.
- Move: 8/10 commands succeed. Modify: 9/10.
- Sketch detection recall is 58.2% at the analysis stage; it remains the main bottleneck.
- Two requests timed out against the model API in the first attempt of the final run (shop_04 hybrid analysis, cmd_076); they were retried and are included.

Because these fixes were guided by this test set, the final numbers are development-set results (see the paper, Section VI-A).

## Refinement / repair pass (2026-11-02): requests to the owners of other files

Done in refine/intent/repair/validate (see REFINE_ANALYSIS.md). Open items that need changes elsewhere:

1. **orchestrator.py: pass the previous version as `reference`.** `validate.validate(ir, preview, analysis, reference=None)` and
   `repair.repair_loop(..., reference=None)` now accept an earlier IR snapshot. After a refinement, call both with
   `reference=<parent version's ir>`: components that vanished without a user `remove` (tracked in `meta.removed_ids`) fail as
   `missing:<id>` and are restored in place (`restore_from_snapshot`); components hidden but visible before fail as
   `snapshot_hidden:<id>`. Without it, deletions of nodes that have no distinct sketch component are undetectable.
2. **codegen: a `width: "full"` or integer width on a node inside a row** is honoured only through `child_style` (flex 1 / px).
   Verified working for inputs in header rows; keep that path when geometry changes.
3. **codegen: textarea `rows`** replaces the drawn `minHeight` (good); a textarea with neither `rows` nor `height` ignores
   `style.height`. Resize uses `rows` for textareas, so nothing is needed unless that changes.
4. **fusion: unlabeled-text drops and caption absorption.** A checkbox/radio drawn with a separate caption text yields two
   sketch components; fusion sometimes keeps both (a duplicate label node). Repair merges the caption on re-insertion only.
5. **fusion/sketch: type of named labels.** 37 of the 43 failed `node_exists` requirements in the final run were the right label
   with the wrong type (brand/card/section titles kept as `text`, `card` or `nav_item` where the instruction implies a heading),
   only 6 were absent labels. Retyping by the instruction's named components belongs in fusion.
