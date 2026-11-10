"""Thin wrapper around the OpenAI SDK: one client, JSON-schema structured output, no fallbacks or fakes."""
from __future__ import annotations

import base64
import json
import threading
import time

import openai

from .. import config

_lock = threading.Lock()
_client: openai.OpenAI | None = None
_client_key = ""


def client() -> openai.OpenAI:
    """Return a shared client; raises OpenAIUnavailable if the key is missing."""
    global _client, _client_key
    key = config.openai_key()
    if not key:
        raise config.OpenAIUnavailable()
    with _lock:
        if _client is None or key != _client_key:
            _client = openai.OpenAI(api_key=key, timeout=60, max_retries=2)
            _client_key = key
        return _client


def image_part(png_bytes: bytes, mime: str = "image/png", detail: str = "high") -> dict:
    b64 = base64.b64encode(png_bytes).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": detail}}


def _is_reasoning(model: str) -> bool:
    m = (model or "").lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


def chat_json(messages: list[dict], schema: dict, name: str, model: str, temperature: float = 0.0) -> tuple[dict, dict]:
    """Call chat completions with a strict JSON schema. Returns (parsed, info{model, latency_ms, raw, usage})."""
    started = time.perf_counter()
    kwargs = dict(model=model, messages=messages,
                  response_format={"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}})
    if not _is_reasoning(model):  # gpt-5 / o-series accept only the default temperature
        kwargs["temperature"] = temperature
    try:
        resp = client().chat.completions.create(**kwargs)
    except openai.BadRequestError as exc:
        if "temperature" not in str(exc) or "temperature" not in kwargs:
            raise
        kwargs.pop("temperature")
        resp = client().chat.completions.create(**kwargs)
    raw = resp.choices[0].message.content or "{}"
    info = {
        "model": resp.model or model,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "raw": raw,
        "usage": resp.usage.model_dump() if resp.usage else None,
    }
    return json.loads(raw), info


def nullable(schema: dict) -> dict:
    """Make a JSON schema fragment nullable (strict mode needs every key present)."""
    if "enum" in schema:
        return {**schema, "type": [schema.get("type", "string"), "null"], "enum": [*schema["enum"], None]}
    t = schema.get("type")
    if isinstance(t, str) and t not in ("object", "array"):
        return {**schema, "type": [t, "null"]}
    return {"anyOf": [schema, {"type": "null"}]}


def obj(properties: dict) -> dict:
    """Strict object: all keys required, no extras."""
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def strip_nulls(value):
    """Remove null values and empty containers produced by strict-schema nullable fields."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            v = strip_nulls(v)
            if v is None or v == {}:
                continue
            out[k] = v
        return out
    if isinstance(value, list):
        return [strip_nulls(v) for v in value if v is not None]
    return value
