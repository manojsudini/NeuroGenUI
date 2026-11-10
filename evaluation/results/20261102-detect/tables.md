# NeuroGenUI evaluation results

Generated 2026-11-02T13:20:02 | 40 sketches, 0 commands | run 1338.2 s | models {"OPENAI_TEXT_MODEL": "gpt-4.1-mini", "OPENAI_VISION_MODEL": "gpt-4.1-mini", "OPENAI_STT_MODEL": "whisper-1", "OPENAI_TTS_MODEL": "tts-1"}

### Headline results: proposed pipeline vs baseline

| Metric | Proposed | Baseline | Unit |
|---|---|---|---|
| component_detection_f1 | 74.9 | 25.8 | % |
| component_detection_f1_dom | 52.0 | 25.8 | % |
| visual_similarity_layout_iou | 46.0 | 28.4 | IoU×100 |
| visual_similarity_edge_ssim | 51.8 | 50.9 | SSIM×100 |
| functional_correctness | 87.9 | 86.2 | % |
| requirement_satisfaction | 87.0 | 85.7 | % |
| validation_pass_rate_before_repair | 95.0 | – | % |
| validation_pass_rate_after_repair | 95.0 | – | % |
| generation_time_ms | 18431 | 23968 | ms |
| modification_time_ms | – | – | ms |
| code_parse_rate | 100.0 | 100.0 | % |
| code_eslint_messages | 0.1 | 0.0 | count/UI |
| code_reuse_ratio | 1.75 | 1.01 | usages/definition |
| code_max_function_lines | 100.2 | 206.1 | lines |

### Component detection (micro-averaged over sketches; match = Hungarian, IoU ≥ 0.3, correct type)

| Detector / output | Sketches | Precision % | Recall % | F1 % | F1 lenient % | Type acc. of matched % | Mean IoU of matched | Label acc. % |
|---|---|---|---|---|---|---|---|---|
| analysis: OpenCV only | 40 | 68.1 | 71.0 | 69.5 | 70.1 | 75.8 | 0.825 | 79.8 |
| analysis: Vision LLM only | 40 | 42.4 | 44.5 | 43.4 | 43.6 | 87.6 | 0.518 | 87.2 |
| analysis: Hybrid (CV + vision) | 40 | 73.4 | 76.5 | 74.9 | 75.3 | 81.8 | 0.825 | 92.2 |
| rendered DOM: Proposed (NeuroGenUI) | 40 | 50.7 | 53.5 | 52.0 | – | 84.5 | 0.592 | – |
| rendered DOM: Baseline (sketch→AI→UI) | 40 | 26.1 | 25.5 | 25.8 | – | 73.9 | 0.579 | – |
| rendered DOM: Oracle (GT IR) | 40 | 84.3 | 81.2 | 82.7 | – | 96.2 | 0.701 | – |

_Lenient = nav_item≈link, container≈card≈form, input≈textarea. DOM rows use validate.extract_dom on the rendered UI with both sides normalised to their content box._

### Detection F1 % per category

| Category | CV | Vision | Hybrid | Baseline (DOM) | Proposed (DOM) |
|---|---|---|---|---|---|
| login | 69.8 | 47.1 | 85.7 | 43.1 | 76.2 |
| registration | 78.5 | 35.4 | 89.7 | 60.8 | 88.3 |
| dashboard | 61.3 | 40.0 | 64.5 | 10.4 | 39.7 |
| profile | 68.1 | 48.2 | 70.3 | 29.2 | 68.9 |
| ecommerce | 75.9 | 42.7 | 76.5 | 26.5 | 33.6 |
| banking | 78.8 | 35.0 | 80.4 | 8.0 | 49.5 |
| booking | 70.5 | 63.3 | 72.4 | 37.1 | 47.1 |
| contact | 55.8 | 47.1 | 68.6 | 28.0 | 50.0 |
| settings | 57.8 | 35.7 | 69.0 | 16.7 | 50.0 |
| landing | 77.4 | 41.4 | 78.8 | 16.4 | 45.2 |

### Per-type detection recall % (GT component found with IoU ≥ 0.3 and the right type)

| Type | GT count | CV | Vision | Hybrid |
|---|---|---|---|---|
| heading | 92 | 71.7 | 17.4 | 71.7 |
| text | 61 | 77.0 | 41.0 | 80.3 |
| button | 61 | 85.2 | 54.1 | 88.5 |
| input | 57 | 68.4 | 61.4 | 75.4 |
| nav_item | 42 | 90.5 | 31.0 | 90.5 |
| card | 37 | 73.0 | 89.2 | 73.0 |
| image | 33 | 97.0 | 75.8 | 100.0 |
| radio | 15 | 86.7 | 6.7 | 80.0 |
| checkbox | 15 | 6.7 | 6.7 | 46.7 |
| select | 14 | 14.3 | 71.4 | 35.7 |
| navbar | 14 | 85.7 | 92.9 | 85.7 |
| icon | 14 | 35.7 | 7.1 | 71.4 |
| link | 9 | 22.2 | 0.0 | 55.6 |
| list | 7 | 57.1 | 28.6 | 57.1 |
| divider | 7 | 100.0 | 0.0 | 100.0 |
| header | 6 | 16.7 | 83.3 | 16.7 |
| textarea | 5 | 0.0 | 100.0 | 40.0 |
| form | 1 | 0.0 | 0.0 | 0.0 |

### Generated UI quality: visual similarity, functional correctness, requirement satisfaction

| System | Sketches | Renders % | Layout IoU | Edge SSIM | Functional % (n) | Requirements % (n) |
|---|---|---|---|---|---|---|
| Proposed (NeuroGenUI) | 40 | 100.0 | 0.460 | 0.518 | 87.9 (58) | 87.0 (407) |
| Proposed, before repair | 40 | 100.0 | 0.460 | 0.518 | 87.9 (58) | 87.0 (407) |
| Baseline (sketch→AI→UI) | 40 | 100.0 | 0.284 | 0.509 | 86.2 (58) | 85.7 (407) |
| Oracle (GT IR) | 40 | 100.0 | 0.631 | 0.550 | 6.9 (58) | 85.3 (407) |

_Same generic DOM procedure for every system. Oracle = deterministic compiler on GT layout with no voice semantics (no events), so its functional score is a floor, not a ceiling._

### Requirement satisfaction % by requirement kind

| Kind | Proposed (NeuroGenUI) | Baseline (sketch→AI→UI) | Oracle (GT IR) |
|---|---|---|---|
| node_exists | 84.7 | 84.4 | 100.0 |
| input_type | 97.1 | 97.1 | 82.4 |
| count_at_least | 100.0 | 90.0 | 100.0 |
| interaction | 87.9 | 84.5 | 6.9 |

### Functional correctness % by interaction type

| Interaction | n | Proposed (NeuroGenUI) | Baseline (sketch→AI→UI) | Oracle (GT IR) |
|---|---|---|---|---|
| navigate | 25 | 88.0 | 72.0 | 0.0 |
| show_message | 13 | 69.2 | 92.3 | 0.0 |
| validate_format | 4 | 100.0 | 100.0 | 100.0 |
| validate_required | 16 | 100.0 | 100.0 | 0.0 |

### Validation before vs after the repair loop (proposed pipeline)

|  | Pass rate % | Mean score | Mean failing checks |
|---|---|---|---|
| Before repair | 95.0 | 0.949 | 2.35 |
| After repair | 95.0 | 0.949 | 2.35 |

### Repair actions applied during generation (by type)

| Action | Count |
|---|---|
| rebuild_handler | 1 |
| recompile_safe | 1 |

### Latency (ms) per stage and end to end

| System | Stage | n | Mean | Median | p95 |
|---|---|---|---|---|---|
| pipeline | analyze_sketch | 40 | 13293 | 12184 | 22907 |
| pipeline | interpret | 40 | 5114 | 4987 | 7215 |
| pipeline | fuse | 40 | 16 | 11 | 48 |
| pipeline | codegen | 40 | 7 | 7 | 17 |
| pipeline | total_generate | 40 | 18431 | 17399 | 27699 |
| pipeline | validate | 40 | 1095 | 942 | 1824 |
| pipeline | repair | 40 | 1124 | 1007 | 1674 |
| pipeline | total_with_validation | 40 | 20650 | 19575 | 31088 |
| baseline | total_generate | 40 | 23968 | 16976 | 65240 |
| analyze_cv | analyze_cv | 40 | 7951 | 6419 | 17439 |
| analyze_vision | analyze_vision | 40 | 10117 | 6847 | 13896 |
| analyze_hybrid | analyze_hybrid | 40 | 13293 | 12184 | 22907 |

_Wall-clock times measured around each call in-process; API calls ran with bounded concurrency (same for both systems). modify_total for the pipeline = interpret + apply_ops + codegen._

### Code quality of generated React (static analysis, mean per UI)

| Code | UIs | Parses % | LOC | Components | Reuse ratio | Max function lines | ESLint msgs | Files |
|---|---|---|---|---|---|---|---|---|
| Proposed (NeuroGenUI) [project] | 40 | 100.0 | 407.2 | 13.8 | 1.75 | 100.2 | 0.0 | 17.9 |
| Proposed (NeuroGenUI) [preview] | 40 | 100.0 | 375.7 | 13.8 | 1.75 | 100.2 | 0.1 | 1.0 |
| Baseline (sketch→AI→UI) [preview] | 40 | 100.0 | 246.3 | 1.4 | 1.01 | 206.1 | 0.0 | 1.0 |
| Oracle (GT IR) [preview] | 40 | 100.0 | 308.9 | 11.6 | 1.60 | 77.0 | 1.0 | 1.0 |

_Parsed with @babel/parser (JSX); ESLint 9 recommended + react + react-hooks (prop-types/react-in-jsx-scope off for both). Reuse ratio = JSX usages of user-defined components / their definitions. [preview] = single-script runtime form used by both systems._
