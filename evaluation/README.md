# NeuroGenUI evaluation harness

This harness measures the proposed pipeline (sketch + voice → IR → React → validation/repair → voice
refinement) and the RR-04 baseline (sketch → one vision call → React) on the same 40 sketches and 80 voice
commands (see `../dataset/README.md`). Every number comes from an actual run. Raw API outputs, per-case
CSVs and logs are kept with each run.

## Run it

```bash
cd project
uv venv evaluation/.venv --python 3.13          # once
uv pip install --python evaluation/.venv/bin/python -r backend/requirements.txt pillow scipy matplotlib jiwer scikit-image
(cd evaluation && npm install)                   # @babel/parser + eslint + react plugins for code-quality metrics
evaluation/.venv/bin/playwright install chromium # once (on Windows the validator uses Edge if present)

evaluation/.venv/bin/python evaluation/run_all.py                    # FULL: 40 sketches, 80 commands, pipeline + baseline
evaluation/.venv/bin/python evaluation/run_all.py --limit 5          # 5 sketches (one per category round-robin) + their commands
evaluation/.venv/bin/python evaluation/run_all.py --only login,dash_02   # sketch ids or categories
evaluation/.venv/bin/python evaluation/run_all.py --only-commands style  # command ids or categories
evaluation/.venv/bin/python evaluation/run_all.py --skip-baseline    # proposed system only
evaluation/.venv/bin/python evaluation/run_all.py --keyfree          # no API calls: OpenCV detection, oracle UIs, fault injection
evaluation/.venv/bin/python evaluation/run_all.py --run-dir results/20261101-0100   # recompute metrics from cached raw outputs
```

Other flags: `--skip-commands`, `--skip-faults`, `--modes cv,vision,hybrid`, `--workers N` (parallel API calls,
default 4), `--retry-errors` (redo cached stages that raised), `--no-latest`.

The OpenAI key is read from `project/.env` (`OPENAI_API_KEY`, `OPENAI_TEXT_MODEL`, `OPENAI_VISION_MODEL`,
`OPENAI_STT_MODEL`). The backend pipeline is imported in-process from `project/backend`.

## Outputs: `results/<timestamp>/` (copied to `results/latest/` without `raw/`)

| Path | What |
|---|---|
| `summary.json` | `{"generated_at","config":{models,counts,run},"metrics":{name:{pipeline,baseline,unit,description}},"tables":[...],"charts":[...],"plots":[...]}`. The app serves it at `/api/eval`. |
| `tables.md` | Every table in Markdown, ready for the paper. |
| `csv/*.csv` | Per-case rows: `detection_analysis`, `detection_types`, `detection_dom`, `voice`, `visual`, `functional`, `requirements`, `refinement`, `repair`, `repair_actions`, `faults`, `timing`, `code_quality`. |
| `plots/*.png` / `*.pdf` | Matplotlib figures (PNG at 300 dpi, PDF vector) in one validated colour-blind-safe palette. |
| `shots/<system>/<sketch>.png` | Screenshot of every generated UI. |
| `raw/<stage>/<id>.json` | Raw output of every API-backed stage plus its wall time (`_wall_ms`) and any error. Rerunning with `--run-dir` reuses these and makes no API calls. `raw/faults.json` caches the fault-injection cases. |
| `run.log` | Full log of the run. |

## Systems compared

| Name | What it is |
|---|---|
| `pipeline` | The proposed system: `sketch.analyze_sketch(mode="hybrid")` → `intent.parse_commands(instruction)` → `fusion.fuse` → `codegen.generate_code` → `validate.validate` → `repair.repair_loop`. Measured on the final (repaired) UI. |
| `pipeline_norepair` | The same UI before the repair loop (an ablation). |
| `pipeline_voice` | Refinement only: the command's Whisper transcript instead of its text (end-to-end voice). |
| `baseline` | `baseline.baseline_generate(sketch, instruction)` (one vision call returns the whole React program) and `baseline.baseline_modify(code, command)` (regenerates everything). |
| `oracle` | The ground-truth layout as a perfect SketchAnalysis → `fuse` → `generate_code`, with no voice and no API. A reference for the deterministic back half: it has no events, so its functional score is not an upper bound. |

Both systems emit single-script JSX on the React globals, and all measurement runs on that code in the backend's
own runtime page (`backend/app/static/runtime/preview.html`, loaded offline through Playwright request routing).
**Measurement never uses the pipeline's `data-ngid` / `data-ngtype` attributes.** Components are recovered
generically from tags, ARIA roles, input types and visual cues, with the same code for both systems.

## Metrics (brief §15)

### 1. Component detection accuracy

- **Matching.** Hungarian assignment that maximises IoU over (GT, predicted) box pairs with IoU ≥ 0.3,
  type-agnostic, with a small tie-break bonus for same-type pairs. A matched pair is a true positive when the
  types agree. Precision = TP / predicted, recall = TP / GT, F1 = their harmonic mean. All are **micro-averaged**
  (TP and counts pooled over sketches).
- *Lenient* F1 also accepts nav_item≈link, container≈card≈form and input≈textarea.
- *Type accuracy* = share of IoU-matched pairs whose type is right. *Mean IoU* = mean IoU of matched pairs.
  *Label accuracy* = share of type-correct matches whose predicted label equals the GT label (normalised).
- **Analysis level:** `analyze_sketch` output for modes `cv` (OpenCV only), `vision` (vision LLM only) and
  `hybrid` (proposed), against GT boxes normalised to the sketch frame. Reported per category and per type.
- **DOM level:** `validate.extract_dom(preview)` on each system's rendered UI. Both the DOM boxes and the GT boxes
  are normalised to their own content (union) box, because rendered pages and sketches have different
  margins and sizes. This is the only detection measure that exists for the baseline.
- The headline `component_detection_f1` compares the proposed hybrid analysis with the baseline's DOM.
  `component_detection_f1_dom` compares the two DOMs like for like.

### 2. Voice command accuracy

- **WER:** Whisper (`speech.transcribe`) on the TTS audio of each command, against the command text, after
  lower-casing and removing punctuation (jiwer). Corpus WER = total substitutions + deletions + insertions /
  total reference words. The mean per-command WER and a per-voice breakdown are also reported.
- **Interpretation:** `intent.parse_commands(text, base_IR)` on the ground-truth text and on the Whisper
  transcript, where the base IR is the pipeline's generated IR for the command's sketch.
  - *Op* is correct when an op has the expected type.
  - *Target* is correct when the op's target (or, for `add`, the anchor) resolves in the base IR (given id,
    else `refine.resolve_target`) to a node whose label contains the expected label and whose type is
    compatible. This is not applicable to create.
  - *Params* are scored per op type: added component type + label + relation; new label or placeholder; move
    relation + anchor; resize direction (scale, size step, `full` width, or a value larger/smaller than the
    current one); colour hue of the style value; event action type plus message text or format; navigation page
    name. This is not applicable to remove.
  - *All correct* = op + target + params, and is the headline `voice_command_accuracy` (from the Whisper transcript).

### 3. Visual similarity

- **Layout IoU:** for each GT component, the IoU with its Hungarian-assigned rendered element (type-agnostic,
  content-box normalised, from `extract_dom`). Unassigned GT components count 0. The mean is taken over GT
  components and then over sketches.
- **Edge SSIM:** the screenshot (1000 px wide viewport, sketch height) is cropped or padded to the sketch's
  aspect ratio. Both images are resized to 500 px wide, then Canny edges are taken, dilated (3×3) and
  Gaussian-blurred (9×9), and SSIM is computed between the two edge maps.

### 4. Functional correctness

Every `labels.interactions` expectation is simulated on a fresh render (`dom.Renderer.simulate`), with the same
procedure for both systems:

| Expectation | Procedure | Pass when |
|---|---|---|
| `validate_required` | Leave all fields empty and click the target. | An error-like message appears (new visible text, `role=alert` or an `alert()` dialog), or native constraint validation blocks the submit. |
| `validate_format` | Fill every field validly except the named one (`not-an-email`), then click. | An error-like message appears or the field is `:invalid`. |
| `show_message` | Fill every field validly, then click. | Text containing the expected words appears (DOM or dialog). |
| `navigate` | Fill validly, then click. | A new non-clickable element mentioning the page name appears and the view changes (element-set Jaccard < 0.85). |

The score is passed / specified, pooled over all sketches.

### 5. Requirement satisfaction

These are the `labels.requirements` derived from each instruction: every component it names (type + label) must
exist, named email/password/date/number/tel fields must have that input type, at least one image must exist
when an image is mentioned, and every stated behaviour must work (simulated as in metric 4). The score is
satisfied / total, pooled.

### 6. Refinement success and preservation

Each command is applied independently to the UI generated from its sketch, or to a blank page for the create
command.

- **Pipeline:** `parse_commands` → `refine.apply_ops` → `generate_code` (the before UI is recompiled from the
  base IR by the same compiler build).
- **Baseline:** `baseline_modify(base code, text)`.
- **Success:** the command's `check` post-condition holds on the rendered after-UI (DOM-level, see
  `checks.py`) and the UI renders. Style checks additionally require the colour to have changed. Commands
  whose post-condition already held before the command are counted and reported in their own table.
- **Preservation:** among the before-UI's non-container elements, excluding the command's target and anything
  drawn inside it, the share still present after the command with the same type, text, text colour,
  background, font size and size (±15%). Positions may shift through reflow.

### 7. Validation and repair

- **Pass rate:** the share of generated UIs where `validate()` passes before `repair_loop` and after it. The
  table also gives the mean validation score, the mean number of failing checks and the count of repair
  actions by type.
- **Fault injection** (`faults.py`): one fault per case on clean IRs from the pipeline and from the oracle.
  - Fault types are `delete_node`, `hide_node`, `zero_size`, `swap_order`, `break_event` (where events exist)
    and `code_error` (a `throw` injected into the compiled App).
  - *Detected* means a new failing check compared with the clean UI.
  - *Localised* means a new failing check targets the faulted node, or for deletions, the sketch component it
    came from.
  - *Repaired* means that after `repair_loop` no new failing check remains and the fault is undone.
  - `code_error` is scored for detection only, because repair recompiles from the IR.

### 8. Generation time

- Wall-clock time around each in-process call, in ms. Pipeline stages are `analyze_sketch`, `interpret`,
  `fuse`, `codegen`, `validate` and `repair`.
- *total_generate* = analyze + interpret + fuse + codegen. *total_with_validation* adds validate + repair.
- The baseline's total is its single `baseline_generate` call.
- Refinement latency: pipeline = interpret + apply_ops + codegen; baseline = `baseline_modify`.
- Mean, median and p95 are reported. API calls ran with the same bounded concurrency for both systems.

### 9. Code quality

`tools/codequality.mjs` (Node) runs on the single-script preview that both systems produce, and additionally on
the pipeline's multi-file Vite project. It reports:

- parse success (`@babel/parser`, JSX), non-blank LOC, and the number of user-defined components
  (capitalised functions or classes returning JSX);
- the reuse ratio (JSX usages of those components / definitions) and the longest function in lines;
- ESLint 9 messages from `recommended` + `react/recommended` + `react-hooks/recommended`. `react/prop-types`
  and `react/react-in-jsx-scope` are turned off for both systems because the runtime contract uses React globals.

## Files

| File | Role |
|---|---|
| `run_all.py` | CLI and orchestration: phases, per-case rows, metric 1a, timing, fault loop, code quality. |
| `generate.py` | Phase A: calls the systems under test through the raw cache. |
| `dom.py` | Playwright renderer, generic DOM extractor and interaction simulator, the same for every system. |
| `checks.py` | Hungarian matching, layout IoU, colour hues, command post-conditions, requirements, preservation. |
| `scoring.py` | Interpretation scoring and WER. |
| `measure.py` | Per-sketch and per-command browser measurements, edge SSIM. |
| `faults.py` | Fault injection for validate/repair. |
| `report.py` | `summary.json`, `tables.md`, CSVs and plots. |
| `tools/codequality.mjs` | Static code metrics (Babel + ESLint). |
| `BACKEND_ISSUES.md` | Problems found in the backend pipeline during evaluation (not patched here). |

## Known limitations

- The sketches and the speech are synthetic (see the dataset README), so results on real hand drawings and
  real voices are expected to be lower.
- The generic DOM extraction is heuristic. Cards are detected from borders, shadows or backgrounds; text from
  own text nodes. It is applied identically to both systems, but some components of either system can be
  missed or mis-typed.
- Message checks match words (`text_contains`) and error-like vocabulary. A UI that signals an error only by
  colour would not be counted.
- Latencies include network time to the OpenAI API and depend on the time of day and on concurrency.
- The oracle has no voice semantics (no events), so its functional score is not an upper bound.
- DOM-level measurements are not perfectly deterministic. Re-measuring the identical cached baseline code
  changed baseline DOM detection F1 from 25.8 to 25.6 and layout IoU from 28.4 to 28.3 (run 20261101-002519),
  most likely from asynchronous image/font loading in some baseline programs. All other metrics reproduced exactly.
- `config.run.duration_s` in `summary.json` is the duration of the invocation that wrote it. A metrics recompute
  from cache overwrites it, and `run.log` keeps every invocation (the full API run of 20261101-002519 took 48.8 min).
