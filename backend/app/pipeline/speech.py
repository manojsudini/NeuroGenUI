"""Speech-to-text with OpenAI Whisper (OPENAI_STT_MODEL)."""
from __future__ import annotations

import io
import time

from .. import config
from . import llm

AUDIO_TYPES = {".webm", ".wav", ".mp3", ".m4a", ".mp4", ".mpeg", ".mpga", ".ogg", ".oga", ".flac"}


def transcribe(audio_bytes: bytes, filename: str = "audio.webm", language: str | None = "en") -> dict:
    """Audio -> {"text", "model", "duration_ms"} (duration_ms = transcription latency)."""
    if not audio_bytes:
        raise ValueError("Empty audio")
    name = filename or "audio.webm"
    if "." not in name or "." + name.rsplit(".", 1)[-1].lower() not in AUDIO_TYPES:
        name = name.rsplit(".", 1)[0] + ".webm"
    model = config.get("OPENAI_STT_MODEL")
    started = time.perf_counter()
    buffer = io.BytesIO(audio_bytes)
    buffer.name = name
    kwargs = {"model": model, "file": buffer}
    if language:
        kwargs["language"] = language
    result = llm.client().audio.transcriptions.create(**kwargs)
    return {"text": (result.text or "").strip(), "model": model,
            "duration_ms": int((time.perf_counter() - started) * 1000)}
