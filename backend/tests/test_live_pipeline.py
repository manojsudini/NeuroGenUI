"""Real end-to-end run against OpenAI (no mocks). Runs only with NGUI_LIVE_TESTS=1 and a configured key."""
import os

import pytest

from app import config
from app.pipeline import codegen, fusion, intent, refine, repair, sketch, speech, validate

pytestmark = pytest.mark.skipif(os.environ.get("NGUI_LIVE_TESTS") != "1" or not config.openai_configured(),
                                reason="set NGUI_LIVE_TESTS=1 and OPENAI_API_KEY to run live tests")


def test_demo_scenario(fixture_png):
    analysis = sketch.analyze_sketch(fixture_png, mode="hybrid")
    types = [c["type"] for c in analysis["components"]]
    assert types.count("input") >= 2 and "button" in types
    ops = intent.parse_commands("Create a login page with email and password. When login is clicked with empty "
                                "fields show an error, otherwise go to the dashboard.")["ops"]
    ir = fusion.fuse(analysis, ops)
    result = repair.repair_loop(ir, analysis)
    assert result["report"]["passed"]
    ir = result["ir"]
    blue = refine.apply_ops(ir, intent.parse_commands("make the login button blue", ir)["ops"])
    assert all(c["ok"] for c in blue["changes"])
    assert any(c["detail"].startswith("style=") and "#2563eb" in c["detail"] for c in blue["changes"])
    err = refine.apply_ops(blue["ir"], intent.parse_commands("show an error when login is clicked with empty fields",
                                                             blue["ir"])["ops"])
    assert all(c["ok"] for c in err["changes"])
    report = validate.validate(err["ir"], codegen.generate_code(err["ir"])["preview"], analysis)
    assert report["passed"] and report["functional"]["interactions_passed"] >= 1


def test_whisper_roundtrip():
    from app.pipeline import llm
    audio = llm.client().audio.speech.create(model=config.get("OPENAI_TTS_MODEL"), voice="alloy",
                                             input="Make the login button blue").read()
    text = speech.transcribe(audio, "cmd.mp3")["text"].lower()
    assert "login button" in text and "blue" in text
