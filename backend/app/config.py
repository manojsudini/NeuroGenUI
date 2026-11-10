"""Settings read from project/.env (one level above backend/)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
ENV_FILE = PROJECT_DIR / ".env"

DATA_DIR = Path(os.environ.get("NGUI_DATA_DIR", BACKEND_DIR / "data"))
STATIC_DIR = BACKEND_DIR / "app" / "static"
RUNTIME_DIR = STATIC_DIR / "runtime"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
DATASET_DIR = PROJECT_DIR / "dataset"
EVAL_LATEST_DIR = PROJECT_DIR / "evaluation" / "results" / "latest"

DEFAULTS = {
    "OPENAI_TEXT_MODEL": "gpt-4.1-mini",
    "OPENAI_VISION_MODEL": "gpt-4.1-mini",
    "OPENAI_STT_MODEL": "whisper-1",
    "OPENAI_TTS_MODEL": "tts-1",
    "NGUI_PORT": "8200",
}


class OpenAIUnavailable(RuntimeError):
    """Raised when a stage needs OpenAI but no key is configured (mapped to HTTP 503)."""

    def __init__(self) -> None:
        super().__init__("OPENAI_API_KEY not configured")


def reload_env() -> None:
    """Re-read project/.env so a key added while the server runs is picked up."""
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)


def get(name: str) -> str:
    return os.environ.get(name) or DEFAULTS.get(name, "")


def openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        reload_env()
        key = os.environ.get("OPENAI_API_KEY", "").strip()
    return key


def openai_configured() -> bool:
    return bool(openai_key())


def models() -> dict:
    return {
        "text": get("OPENAI_TEXT_MODEL"),
        "vision": get("OPENAI_VISION_MODEL"),
        "stt": get("OPENAI_STT_MODEL"),
    }


reload_env()
for sub in ("sketches", "overlays", "shots", "audio"):
    (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
