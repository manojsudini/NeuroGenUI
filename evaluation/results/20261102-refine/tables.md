# NeuroGenUI evaluation results

Generated 2026-11-02T13:07:08 | 40 sketches, 80 commands | run 2900.3 s | models {"OPENAI_TEXT_MODEL": "gpt-4.1-mini", "OPENAI_VISION_MODEL": "gpt-4.1-mini", "OPENAI_STT_MODEL": "whisper-1", "OPENAI_TTS_MODEL": "tts-1"}

### Headline results: proposed pipeline vs baseline

| Metric | Proposed | Baseline | Unit |
|---|---|---|---|
| component_detection_f1 | 53.1 | 25.8 | % |
| component_detection_f1_dom | 42.9 | 25.8 | % |
| whisper_wer | 4.0 | – | % |
| voice_command_accuracy | 96.2 | – | % |
| visual_similarity_layout_iou | 39.9 | 28.4 | IoU×100 |
| visual_similarity_edge_ssim | 52.2 | 50.9 | SSIM×100 |
| functional_correctness | 94.8 | 86.2 | % |
| requirement_satisfaction | 87.5 | 86.0 | % |
| refinement_success_rate | 97.5 | 90.0 | % |
| preservation_rate | 99.7 | 98.2 | % |
| validation_pass_rate_before_repair | 100.0 | – | % |
| validation_pass_rate_after_repair | 100.0 | – | % |
| fault_detection_rate | 98.0 | – | % |
| fault_repair_rate | 95.6 | – | % |
| generation_time_ms | 15472 | 23968 | ms |
| modification_time_ms | 1997 | 15360 | ms |
| code_parse_rate | 100.0 | 100.0 | % |
| code_eslint_messages | 0.1 | 0.0 | count/UI |
| code_reuse_ratio | 1.85 | 1.01 | usages/definition |
| code_max_function_lines | 105.6 | 206.1 | lines |

### Component detection (micro-averaged over sketches; match = Hungarian, IoU ≥ 0.3, correct type)

| Detector / output | Sketches | Precision % | Recall % | F1 % | F1 lenient % | Type acc. of matched % | Mean IoU of matched | Label acc. % |
|---|---|---|---|---|---|---|---|---|
| analysis: OpenCV only | 40 | 40.7 | 45.3 | 42.9 | 43.8 | 52.9 | 0.724 | 0.0 |
| analysis: Vision LLM only | 40 | 32.3 | 34.9 | 33.5 | 39.0 | 69.0 | 0.521 | 87.7 |
| analysis: Hybrid (CV + vision) | 40 | 48.9 | 58.2 | 53.1 | 55.2 | 68.1 | 0.717 | 95.3 |
| rendered DOM: Proposed (NeuroGenUI) | 40 | 40.6 | 45.5 | 42.9 | – | 82.3 | 0.580 | – |
| rendered DOM: Baseline (sketch→AI→UI) | 40 | 26.1 | 25.5 | 25.8 | – | 73.9 | 0.579 | – |
| rendered DOM: Oracle (GT IR) | 40 | 79.0 | 76.1 | 77.5 | – | 95.5 | 0.692 | – |

_Lenient = nav_item≈link, container≈card≈form, input≈textarea. DOM rows use validate.extract_dom on the rendered UI with both sides normalised to their content box._

### Detection F1 % per category

| Category | CV | Vision | Hybrid | Baseline (DOM) | Proposed (DOM) |
|---|---|---|---|---|---|
| login | 52.3 | 44.4 | 71.6 | 43.1 | 64.7 |
| registration | 47.1 | 30.0 | 65.1 | 60.8 | 63.4 |
| dashboard | 24.5 | 19.4 | 33.8 | 10.4 | 4.3 |
| profile | 54.9 | 36.1 | 68.1 | 29.2 | 70.3 |
| ecommerce | 56.4 | 30.0 | 59.5 | 26.5 | 52.2 |
| banking | 47.5 | 34.0 | 52.8 | 8.0 | 28.3 |
| booking | 34.0 | 56.9 | 47.4 | 37.1 | 46.6 |
| contact | 34.9 | 35.8 | 51.9 | 28.0 | 52.9 |
| settings | 23.9 | 21.7 | 34.0 | 16.7 | 36.0 |
| landing | 58.0 | 34.3 | 60.9 | 16.4 | 38.6 |

### Per-type detection recall % (GT component found with IoU ≥ 0.3 and the right type)

| Type | GT count | CV | Vision | Hybrid |
|---|---|---|---|---|
| heading | 92 | 21.7 | 10.9 | 38.0 |
| button | 61 | 82.0 | 47.5 | 90.2 |
| text | 61 | 88.5 | 37.7 | 91.8 |
| input | 57 | 57.9 | 54.4 | 78.9 |
| nav_item | 42 | 0.0 | 23.8 | 26.2 |
| card | 37 | 64.9 | 37.8 | 64.9 |
| image | 33 | 78.8 | 72.7 | 84.8 |
| radio | 15 | 0.0 | 13.3 | 6.7 |
| checkbox | 15 | 0.0 | 0.0 | 0.0 |
| icon | 14 | 35.7 | 14.3 | 78.6 |
| select | 14 | 0.0 | 64.3 | 14.3 |
| navbar | 14 | 71.4 | 57.1 | 71.4 |
| link | 9 | 0.0 | 11.1 | 44.4 |
| list | 7 | 0.0 | 28.6 | 0.0 |
| divider | 7 | 0.0 | 0.0 | 0.0 |
| header | 6 | 0.0 | 16.7 | 0.0 |
| textarea | 5 | 0.0 | 100.0 | 60.0 |
| form | 1 | 0.0 | 0.0 | 0.0 |

### Voice command interpretation accuracy % (intent.parse_commands on the base IR)

| Input | Commands | Op type | Target | Parameters | All correct |
|---|---|---|---|---|---|
| Ground-truth text | 80 | 98.8 | 97.5 | 100.0 | 96.2 |
| Whisper transcript | 80 | 98.8 | 97.5 | 98.6 | 96.2 |

_Whisper corpus WER 4.0% ; target n/a for create, params n/a for remove._

### Voice results per command category

| Category | n | Mean WER % | All-correct (text) % | All-correct (Whisper) % |
|---|---|---|---|---|
| add | 10 | 0.0 | 100.0 | 100.0 |
| remove | 10 | 2.9 | 100.0 | 100.0 |
| modify | 10 | 6.2 | 90.0 | 90.0 |
| move | 10 | 6.5 | 90.0 | 90.0 |
| resize | 10 | 10.2 | 100.0 | 100.0 |
| style | 10 | 0.0 | 100.0 | 100.0 |
| interaction | 10 | 0.0 | 100.0 | 100.0 |
| navigation | 10 | 6.9 | 90.0 | 90.0 |

### Whisper WER by TTS voice

| TTS voice | Commands | Corpus WER % |
|---|---|---|
| alloy | 14 | 3.4 |
| echo | 14 | 6.8 |
| fable | 13 | 0.0 |
| nova | 13 | 7.6 |
| onyx | 13 | 1.9 |
| shimmer | 13 | 4.7 |

### Generated UI quality: visual similarity, functional correctness, requirement satisfaction

| System | Sketches | Renders % | Layout IoU | Edge SSIM | Functional % (n) | Requirements % (n) |
|---|---|---|---|---|---|---|
| Proposed (NeuroGenUI) | 40 | 100.0 | 0.399 | 0.522 | 94.8 (58) | 87.5 (407) |
| Proposed, before repair | 40 | 100.0 | 0.399 | 0.522 | 94.8 (58) | 87.5 (407) |
| Baseline (sketch→AI→UI) | 40 | 100.0 | 0.284 | 0.509 | 86.2 (58) | 86.0 (407) |
| Oracle (GT IR) | 40 | 100.0 | 0.593 | 0.551 | 6.9 (58) | 85.3 (407) |

_Same generic DOM procedure for every system. Oracle = deterministic compiler on GT layout with no voice semantics (no events), so its functional score is a floor, not a ceiling._

### Requirement satisfaction % by requirement kind

| Kind | Proposed (NeuroGenUI) | Baseline (sketch→AI→UI) | Oracle (GT IR) |
|---|---|---|---|
| node_exists | 85.8 | 84.4 | 100.0 |
| input_type | 91.2 | 97.1 | 82.4 |
| count_at_least | 85.0 | 90.0 | 100.0 |
| interaction | 94.8 | 86.2 | 6.9 |

### Functional correctness % by interaction type

| Interaction | n | Proposed (NeuroGenUI) | Baseline (sketch→AI→UI) | Oracle (GT IR) |
|---|---|---|---|---|
| navigate | 25 | 92.0 | 72.0 | 0.0 |
| show_message | 13 | 92.3 | 92.3 | 0.0 |
| validate_format | 4 | 100.0 | 100.0 | 100.0 |
| validate_required | 16 | 100.0 | 100.0 | 0.0 |

### Refinement success % and preservation % per command category

| Category | Success: Proposed (NeuroGenUI) | Success: Proposed, Whisper transcript | Success: Baseline (sketch→AI→UI) | Preserved: Proposed (NeuroGenUI) | Preserved: Proposed, Whisper transcript | Preserved: Baseline (sketch→AI→UI) |
|---|---|---|---|---|---|---|
| add | 100.0 | 100.0 | 80.0 | 100.0 | 100.0 | 96.3 |
| remove | 100.0 | 100.0 | 100.0 | 99.4 | 99.4 | 98.9 |
| modify | 100.0 | 90.0 | 100.0 | 99.2 | 99.2 | 100.0 |
| move | 90.0 | 90.0 | 100.0 | 100.0 | 100.0 | 94.1 |
| resize | 90.0 | 90.0 | 70.0 | 99.1 | 98.2 | 99.2 |
| style | 100.0 | 100.0 | 90.0 | 100.0 | 100.0 | 97.1 |
| interaction | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| navigation | 100.0 | 100.0 | 80.0 | 100.0 | 100.0 | 100.0 |
| all | 97.5 | 96.2 | 90.0 | 99.7 | 99.6 | 98.2 |

_Success = the command's post-condition holds on the rendered UI after the command. Preservation = non-target elements with unchanged type, text, colours, font size and size (±15%)._

### Commands whose post-condition already held on the base UI (before the command)

| System | Checkable commands | Already satisfied | Of which counted as success |
|---|---|---|---|
| Proposed (NeuroGenUI) | 49 | 1 | 1 |
| Proposed, Whisper transcript | 49 | 1 | 1 |
| Baseline (sketch→AI→UI) | 49 | 1 | 1 |

_Reported for transparency; event/navigation/resize checks are excluded (they need the after-UI). style checks additionally require the colour to have changed._

### Validation before vs after the repair loop (proposed pipeline)

|  | Pass rate % | Mean score | Mean failing checks |
|---|---|---|---|
| Before repair | 100.0 | 0.947 | 2.30 |
| After repair | 100.0 | 0.947 | 2.30 |

### Repair actions applied during generation (by type)

| Action | Count |
|---|---|

### Fault injection: validator detection and repair-loop recovery

| IR source | Fault | Cases | Detected % | Localised % | Repaired % |
|---|---|---|---|---|---|
| oracle | delete_node | 40 | 95.0 | 95.0 | 95.0 |
| oracle | hide_node | 40 | 100.0 | 100.0 | 100.0 |
| oracle | zero_size | 40 | 100.0 | 100.0 | 100.0 |
| oracle | swap_order | 40 | 100.0 | 62.5 | 97.5 |
| oracle | code_error | 40 | 100.0 | 100.0 | – |
| oracle | all | 200 | 99.0 | 91.5 | 98.1 |
| oracle+snapshot | delete_node | 40 | 100.0 | 100.0 | 100.0 |
| oracle+snapshot | hide_node | 40 | 100.0 | 100.0 | 100.0 |
| oracle+snapshot | all | 80 | 100.0 | 100.0 | 100.0 |
| pipeline | delete_node | 40 | 75.0 | 60.0 | 62.5 |
| pipeline | hide_node | 40 | 100.0 | 100.0 | 97.5 |
| pipeline | zero_size | 40 | 100.0 | 100.0 | 100.0 |
| pipeline | swap_order | 40 | 100.0 | 50.0 | 97.5 |
| pipeline | break_event | 38 | 100.0 | 100.0 | 100.0 |
| pipeline | code_error | 40 | 100.0 | 100.0 | – |
| pipeline | all | 238 | 95.8 | 84.9 | 91.4 |
| pipeline+snapshot | delete_node | 40 | 100.0 | 100.0 | 95.0 |
| pipeline+snapshot | hide_node | 40 | 100.0 | 100.0 | 97.5 |
| pipeline+snapshot | all | 80 | 100.0 | 100.0 | 96.2 |

_One fault per case. Detected = a new failing check vs the clean UI; localised = it targets the faulted node; repaired = no new failing check after repair_loop and the fault undone. code_error is detection-only (repair recompiles from the IR)._

### Latency (ms) per stage and end to end

| System | Stage | n | Mean | Median | p95 |
|---|---|---|---|---|---|
| pipeline | analyze_sketch | 40 | 10350 | 5890 | 10705 |
| pipeline | interpret | 40 | 5114 | 4987 | 7215 |
| pipeline | fuse | 40 | 5 | 5 | 10 |
| pipeline | codegen | 40 | 2 | 2 | 3 |
| pipeline | total_generate | 40 | 15472 | 10658 | 18349 |
| pipeline | validate | 40 | 631 | 595 | 912 |
| pipeline | repair | 40 | 584 | 582 | 832 |
| pipeline | total_with_validation | 40 | 16687 | 11872 | 19732 |
| baseline | total_generate | 40 | 23968 | 16976 | 65240 |
| analyze_cv | analyze_cv | 40 | 66 | 55 | 103 |
| analyze_vision | analyze_vision | 40 | 6445 | 6237 | 8711 |
| analyze_hybrid | analyze_hybrid | 40 | 10350 | 5890 | 10705 |
| pipeline | modify_total | 80 | 1997 | 1947 | 2398 |
| pipeline_voice | modify_total | 80 | 2014 | 1979 | 2669 |
| baseline | modify_total | 80 | 15360 | 13883 | 23314 |

_Wall-clock times measured around each call in-process; API calls ran with bounded concurrency (same for both systems). modify_total for the pipeline = interpret + apply_ops + codegen._

### Code quality of generated React (static analysis, mean per UI)

| Code | UIs | Parses % | LOC | Components | Reuse ratio | Max function lines | ESLint msgs | Files |
|---|---|---|---|---|---|---|---|---|
| Proposed (NeuroGenUI) [project] | 40 | 100.0 | 410.8 | 13.9 | 1.85 | 105.6 | 0.0 | 17.9 |
| Proposed (NeuroGenUI) [preview] | 40 | 100.0 | 379.0 | 13.9 | 1.85 | 105.6 | 0.1 | 1.0 |
| Baseline (sketch→AI→UI) [preview] | 40 | 100.0 | 246.3 | 1.4 | 1.01 | 206.1 | 0.0 | 1.0 |
| Oracle (GT IR) [preview] | 40 | 100.0 | 307.6 | 11.6 | 1.60 | 76.1 | 1.0 | 1.0 |

_Parsed with @babel/parser (JSX); ESLint 9 recommended + react + react-hooks (prop-types/react-in-jsx-scope off for both). Reuse ratio = JSX usages of user-defined components / their definitions. [preview] = single-script runtime form used by both systems._
