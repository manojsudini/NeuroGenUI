# NeuroGenUI evaluation results

Generated 2026-11-01T01:35:57 | 40 sketches, 80 commands | run 1211.3 s | models {"OPENAI_TEXT_MODEL": "gpt-4.1-mini", "OPENAI_VISION_MODEL": "gpt-4.1-mini", "OPENAI_STT_MODEL": "whisper-1", "OPENAI_TTS_MODEL": "tts-1"}

### Headline results: proposed pipeline vs baseline

| Metric | Proposed | Baseline | Unit |
|---|---|---|---|
| component_detection_f1 | 42.9 | 25.6 | % |
| component_detection_f1_dom | 16.5 | 25.6 | % |
| whisper_wer | 4.0 | – | % |
| voice_command_accuracy | 95.0 | – | % |
| visual_similarity_layout_iou | 20.5 | 28.3 | IoU×100 |
| visual_similarity_edge_ssim | 51.6 | 50.9 | SSIM×100 |
| functional_correctness | 91.4 | 86.2 | % |
| requirement_satisfaction | 86.0 | 86.0 | % |
| refinement_success_rate | 81.2 | 90.0 | % |
| preservation_rate | 97.7 | 98.2 | % |
| validation_pass_rate_before_repair | 42.5 | – | % |
| validation_pass_rate_after_repair | 42.5 | – | % |
| fault_detection_rate | 83.6 | – | % |
| fault_repair_rate | 60.7 | – | % |
| generation_time_ms | 21877 | 23968 | ms |
| modification_time_ms | 2674 | 15360 | ms |
| code_parse_rate | 100.0 | 100.0 | % |
| code_eslint_messages | 0.1 | 0.0 | count/UI |
| code_reuse_ratio | 2.02 | 1.01 | usages/definition |
| code_max_function_lines | 57.3 | 206.1 | lines |

### Component detection (micro-averaged over sketches; match = Hungarian, IoU ≥ 0.3, correct type)

| Detector / output | Sketches | Precision % | Recall % | F1 % | F1 lenient % | Type acc. of matched % | Mean IoU of matched | Label acc. % |
|---|---|---|---|---|---|---|---|---|
| analysis: OpenCV only | 40 | 33.1 | 42.0 | 37.0 | 38.6 | 50.1 | 0.721 | 0.0 |
| analysis: Vision LLM only | 40 | 8.6 | 9.0 | 8.8 | 11.8 | 40.2 | 0.434 | 35.0 |
| analysis: Hybrid (CV + vision) | 40 | 37.0 | 51.0 | 42.9 | 46.2 | 61.7 | 0.720 | 88.8 |
| rendered DOM: Proposed (NeuroGenUI) | 40 | 14.6 | 19.0 | 16.5 | – | 77.1 | 0.507 | – |
| rendered DOM: Baseline (sketch→AI→UI) | 40 | 25.9 | 25.3 | 25.6 | – | 74.1 | 0.580 | – |
| rendered DOM: Oracle (GT IR) | 40 | 38.5 | 33.7 | 35.9 | – | 89.5 | 0.557 | – |

_Lenient = nav_item≈link, container≈card≈form, input≈textarea. DOM rows use validate.extract_dom on the rendered UI with both sides normalised to their content box._

### Detection F1 % per category

| Category | CV | Vision | Hybrid | Baseline (DOM) | Proposed (DOM) |
|---|---|---|---|---|---|
| login | 41.1 | 15.6 | 61.3 | 43.1 | 21.1 |
| registration | 44.9 | 23.0 | 51.5 | 60.8 | 20.2 |
| dashboard | 17.1 | 6.6 | 24.7 | 10.4 | 5.6 |
| profile | 55.9 | 7.2 | 58.0 | 29.2 | 16.3 |
| ecommerce | 56.5 | 6.6 | 59.7 | 26.5 | 12.6 |
| banking | 44.7 | 6.2 | 54.7 | 8.0 | 15.4 |
| booking | 33.6 | 2.0 | 34.4 | 35.1 | 26.3 |
| contact | 28.8 | 8.1 | 39.7 | 28.0 | 15.9 |
| settings | 25.5 | 8.7 | 28.3 | 16.7 | 24.4 |
| landing | 33.8 | 8.7 | 33.3 | 16.4 | 15.2 |

### Per-type detection recall % (GT component found with IoU ≥ 0.3 and the right type)

| Type | GT count | CV | Vision | Hybrid |
|---|---|---|---|---|
| heading | 92 | 21.7 | 3.3 | 33.7 |
| text | 61 | 72.1 | 1.6 | 75.4 |
| button | 61 | 82.0 | 3.3 | 88.5 |
| input | 57 | 57.9 | 28.1 | 73.7 |
| nav_item | 42 | 0.0 | 0.0 | 2.4 |
| card | 37 | 54.1 | 21.6 | 56.8 |
| image | 33 | 63.6 | 27.3 | 66.7 |
| radio | 15 | 6.7 | 0.0 | 6.7 |
| checkbox | 15 | 0.0 | 0.0 | 20.0 |
| select | 14 | 0.0 | 14.3 | 28.6 |
| icon | 14 | 0.0 | 0.0 | 35.7 |
| navbar | 14 | 71.4 | 0.0 | 71.4 |
| link | 9 | 0.0 | 11.1 | 22.2 |
| divider | 7 | 100.0 | 0.0 | 85.7 |
| list | 7 | 0.0 | 0.0 | 0.0 |
| header | 6 | 0.0 | 16.7 | 0.0 |
| textarea | 5 | 0.0 | 20.0 | 40.0 |
| form | 1 | 0.0 | 0.0 | 0.0 |

### Voice command interpretation accuracy % (intent.parse_commands on the base IR)

| Input | Commands | Op type | Target | Parameters | All correct |
|---|---|---|---|---|---|
| Ground-truth text | 80 | 98.8 | 98.7 | 98.6 | 96.2 |
| Whisper transcript | 80 | 97.5 | 98.7 | 98.6 | 95.0 |

_Whisper corpus WER 4.0% ; target n/a for create, params n/a for remove._

### Voice results per command category

| Category | n | Mean WER % | All-correct (text) % | All-correct (Whisper) % |
|---|---|---|---|---|
| add | 10 | 0.0 | 100.0 | 100.0 |
| remove | 10 | 2.9 | 100.0 | 100.0 |
| modify | 10 | 6.2 | 90.0 | 90.0 |
| move | 10 | 6.5 | 100.0 | 100.0 |
| resize | 10 | 10.2 | 80.0 | 80.0 |
| style | 10 | 0.0 | 100.0 | 100.0 |
| interaction | 10 | 0.0 | 100.0 | 100.0 |
| navigation | 10 | 6.9 | 100.0 | 90.0 |

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
| Proposed (NeuroGenUI) | 40 | 100.0 | 0.205 | 0.516 | 91.4 (58) | 86.0 (407) |
| Proposed, before repair | 40 | 100.0 | 0.205 | 0.516 | 91.4 (58) | 86.0 (407) |
| Baseline (sketch→AI→UI) | 40 | 100.0 | 0.283 | 0.509 | 86.2 (58) | 86.0 (407) |
| Oracle (GT IR) | 40 | 100.0 | 0.277 | 0.558 | 6.9 (58) | 85.3 (407) |

_Same generic DOM procedure for every system. Oracle = deterministic compiler on GT layout with no voice semantics (no events), so its functional score is a floor, not a ceiling._

### Requirement satisfaction % by requirement kind

| Kind | Proposed (NeuroGenUI) | Baseline (sketch→AI→UI) | Oracle (GT IR) |
|---|---|---|---|
| node_exists | 83.4 | 84.4 | 100.0 |
| input_type | 97.1 | 97.1 | 82.4 |
| count_at_least | 90.0 | 90.0 | 100.0 |
| interaction | 91.4 | 86.2 | 6.9 |

### Functional correctness % by interaction type

| Interaction | n | Proposed (NeuroGenUI) | Baseline (sketch→AI→UI) | Oracle (GT IR) |
|---|---|---|---|---|
| navigate | 25 | 88.0 | 72.0 | 0.0 |
| show_message | 13 | 92.3 | 92.3 | 0.0 |
| validate_format | 4 | 100.0 | 100.0 | 100.0 |
| validate_required | 16 | 93.8 | 100.0 | 0.0 |

### Refinement success % and preservation % per command category

| Category | Success: Proposed (NeuroGenUI) | Success: Proposed, Whisper transcript | Success: Baseline (sketch→AI→UI) | Preserved: Proposed (NeuroGenUI) | Preserved: Proposed, Whisper transcript | Preserved: Baseline (sketch→AI→UI) |
|---|---|---|---|---|---|---|
| add | 100.0 | 100.0 | 80.0 | 100.0 | 100.0 | 96.3 |
| remove | 100.0 | 100.0 | 100.0 | 91.9 | 91.9 | 98.9 |
| modify | 80.0 | 80.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| move | 80.0 | 80.0 | 100.0 | 90.2 | 90.2 | 94.1 |
| resize | 60.0 | 60.0 | 70.0 | 100.0 | 99.0 | 99.2 |
| style | 100.0 | 100.0 | 90.0 | 100.0 | 100.0 | 97.1 |
| interaction | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 |
| navigation | 30.0 | 50.0 | 80.0 | 100.0 | 100.0 | 100.0 |
| all | 81.2 | 83.8 | 90.0 | 97.7 | 97.6 | 98.2 |

_Success = the command's post-condition holds on the rendered UI after the command. Preservation = non-target elements with unchanged type, text, colours, font size and size (±15%)._

### Commands whose post-condition already held on the base UI (before the command)

| System | Checkable commands | Already satisfied | Of which counted as success |
|---|---|---|---|
| Proposed (NeuroGenUI) | 49 | 2 | 2 |
| Proposed, Whisper transcript | 49 | 2 | 2 |
| Baseline (sketch→AI→UI) | 49 | 1 | 1 |

_Reported for transparency; event/navigation/resize checks are excluded (they need the after-UI). style checks additionally require the colour to have changed._

### Validation before vs after the repair loop (proposed pipeline)

|  | Pass rate % | Mean score | Mean failing checks |
|---|---|---|---|
| Before repair | 42.5 | 0.889 | 10.90 |
| After repair | 42.5 | 0.889 | 10.90 |

### Repair actions applied during generation (by type)

| Action | Count |
|---|---|
| reset_style | 40 |
| rebuild_handler | 3 |

### Fault injection: validator detection and repair-loop recovery

| IR source | Fault | Cases | Detected % | Localised % | Repaired % |
|---|---|---|---|---|---|
| oracle | delete_node | 40 | 95.0 | 95.0 | 82.5 |
| oracle | hide_node | 40 | 37.5 | 0.0 | 0.0 |
| oracle | zero_size | 40 | 85.0 | 85.0 | 72.5 |
| oracle | swap_order | 38 | 100.0 | 36.8 | 92.1 |
| oracle | code_error | 40 | 100.0 | 100.0 | – |
| oracle | all | 198 | 83.3 | 63.6 | 61.4 |
| pipeline | delete_node | 40 | 90.0 | 65.0 | 37.5 |
| pipeline | hide_node | 40 | 35.0 | 12.5 | 0.0 |
| pipeline | zero_size | 40 | 82.5 | 80.0 | 77.5 |
| pipeline | swap_order | 38 | 100.0 | 21.1 | 89.5 |
| pipeline | break_event | 38 | 97.4 | 97.4 | 100.0 |
| pipeline | code_error | 40 | 100.0 | 100.0 | – |
| pipeline | all | 236 | 83.9 | 62.7 | 60.2 |

_One fault per case. Detected = a new failing check vs the clean UI; localised = it targets the faulted node; repaired = no new failing check after repair_loop and the fault undone. code_error is detection-only (repair recompiles from the IR)._

### Latency (ms) per stage and end to end

| System | Stage | n | Mean | Median | p95 |
|---|---|---|---|---|---|
| pipeline | analyze_sketch | 40 | 14375 | 9013 | 36104 |
| pipeline | interpret | 40 | 7496 | 5651 | 10341 |
| pipeline | fuse | 40 | 5 | 4 | 10 |
| pipeline | codegen | 40 | 1 | 1 | 2 |
| pipeline | total_generate | 40 | 21877 | 16037 | 57482 |
| pipeline | validate | 40 | 553 | 542 | 777 |
| pipeline | repair | 40 | 852 | 783 | 1418 |
| pipeline | total_with_validation | 40 | 23282 | 17407 | 58394 |
| baseline | total_generate | 40 | 23968 | 16976 | 65240 |
| analyze_cv | analyze_cv | 40 | 67 | 59 | 123 |
| analyze_vision | analyze_vision | 40 | 8884 | 7463 | 16306 |
| analyze_hybrid | analyze_hybrid | 40 | 14375 | 9013 | 36104 |
| pipeline | modify_total | 80 | 2674 | 2096 | 5868 |
| pipeline_voice | modify_total | 80 | 2898 | 2381 | 6124 |
| baseline | modify_total | 80 | 15360 | 13883 | 23314 |

_Wall-clock times measured around each call in-process; API calls ran with bounded concurrency (same for both systems). modify_total for the pipeline = interpret + apply_ops + codegen._

### Code quality of generated React (static analysis, mean per UI)

| Code | UIs | Parses % | LOC | Components | Reuse ratio | Max function lines | ESLint msgs | Files |
|---|---|---|---|---|---|---|---|---|
| Proposed (NeuroGenUI) [project] | 40 | 100.0 | 360.6 | 14.5 | 2.02 | 57.3 | 0.0 | 18.5 |
| Proposed (NeuroGenUI) [preview] | 40 | 100.0 | 327.4 | 14.5 | 2.02 | 57.3 | 0.1 | 1.0 |
| Baseline (sketch→AI→UI) [preview] | 40 | 100.0 | 246.3 | 1.4 | 1.01 | 206.1 | 0.0 | 1.0 |
| Oracle (GT IR) [preview] | 40 | 100.0 | 254.1 | 11.4 | 1.56 | 41.4 | 1.0 | 1.0 |

_Parsed with @babel/parser (JSX); ESLint 9 recommended + react + react-hooks (prop-types/react-in-jsx-scope off for both). Reuse ratio = JSX usages of user-defined components / their definitions. [preview] = single-script runtime form used by both systems._
