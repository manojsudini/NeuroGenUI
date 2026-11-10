"""RR-04 baseline: the direct sketch -> AI -> UI approach.

ONE vision call (same model as the pipeline) turns image + instruction into a complete single-script React app.
Modification regenerates the whole app from the previous code + the instruction (one text call).
The output follows the same runtime contract as the pipeline, so the same validator / DOM extractor measures both.
The prompt is a fair, competent prompt; the baseline is not handicapped.
"""
from __future__ import annotations

import re
import time

from .. import config
from . import llm
from . import sketch as sketch_mod

RUNTIME_RULES = """Runtime contract (must follow exactly):
- Output ONE self-contained JSX script (no import/export statements). React 18 and ReactDOM are available as the
  globals `React` and `ReactDOM`. Get hooks with `const { useState } = React;`.
- Define a component named App and finish with:
  ReactDOM.createRoot(document.getElementById("root")).render(<App />);
- Styling: inline styles or one <style> element you create from the script. No external CSS, fonts, scripts or network calls.
- Images: use real photos from "/runtime/photos/<key>.jpg" with key one of person, product, banner, food, travel,
  building, finance, nature, or a neutral grey placeholder box.
- Make it functional: controlled inputs, buttons with click handlers, form validation with visible error messages
  (use role="alert" for errors), and navigation between pages/views with React state when asked.
- Use semantic HTML (header, nav, main, form, label, input, button, h1-h4, p, a, img) and a clean modern look."""

SCHEMA = llm.obj({"code": {"type": "string"}})


def _clean(code: str) -> str:
    code = code.strip()
    fence = re.match(r"^```[a-zA-Z]*\n(.*?)\n```$", code, re.S)
    if fence:
        code = fence.group(1)
    code = re.sub(r"^\s*import\s.+?;?\s*$", "", code, flags=re.M)
    code = re.sub(r"^\s*export\s+default\s+", "", code, flags=re.M)
    return code.strip() + "\n"


def baseline_generate(image_bytes: bytes, instruction: str) -> dict:
    """Image + instruction -> {"preview", "code", "latency_ms", "model"} in a single vision call."""
    img, _ = sketch_mod._to_work(sketch_mod.decode(image_bytes))
    started = time.perf_counter()
    messages = [
        {"role": "system", "content": "You are an expert React developer. You turn rough hand-drawn UI sketches "
                                      "and spoken instructions into a complete, working React UI.\n\n" + RUNTIME_RULES},
        {"role": "user", "content": [
            {"type": "text", "text": "Build the UI shown in this hand-drawn sketch. Keep the sketch's components, their text "
                                     f"and layout.\nInstruction: {instruction or '(none)'}\nReturn the full script in `code`."},
            llm.image_part(sketch_mod._png(img)),
        ]},
    ]
    result, info = llm.chat_json(messages, SCHEMA, "react_app", config.get("OPENAI_VISION_MODEL"))
    code = _clean(result.get("code", ""))
    return {"preview": code, "code": code, "latency_ms": int((time.perf_counter() - started) * 1000),
            "model": info["model"], "usage": info.get("usage")}


def baseline_modify(preview_code: str, instruction: str) -> dict:
    """Previous code + instruction -> the whole app regenerated (one call)."""
    started = time.perf_counter()
    messages = [
        {"role": "system", "content": "You are an expert React developer who edits existing React UIs.\n\n" + RUNTIME_RULES},
        {"role": "user", "content": f"Here is the current app:\n\n{preview_code}\n\nApply this change: {instruction}\n"
                                    "Keep everything else unchanged. Return the complete updated script in `code`."},
    ]
    result, info = llm.chat_json(messages, SCHEMA, "react_app", config.get("OPENAI_VISION_MODEL"))
    code = _clean(result.get("code", ""))
    return {"preview": code, "code": code, "latency_ms": int((time.perf_counter() - started) * 1000),
            "model": info["model"], "usage": info.get("usage")}
