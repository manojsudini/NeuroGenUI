# Raw outputs reused from run 20261101-002519 (Run 1)

raw/baseline_generate (40) and raw/baseline_modify (80) were copied from run 20261101-002519.
backend/app/pipeline/baseline.py (mtime 2026-11-01 00:15:31) and llm.py (00:14:10) are unchanged since Run 1, and
both runs gave baseline_modify the same baseline_generate output as input. Every pipeline stage (analyze_cv/vision/
hybrid, interpret_instruction, transcribe, interpret_cmd_text/asr, pipeline_build, oracle_build, fault injection)
was recomputed in this run, against the backend as of 2026-11-01 13:00 (backend tests: 66 passed with NGUI_LIVE_TESTS=1).
