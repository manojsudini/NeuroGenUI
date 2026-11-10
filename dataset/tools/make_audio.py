"""Synthesize every command in commands/commands.jsonl to real speech with OpenAI TTS.

    python dataset/tools/make_audio.py        # skips files that already exist

Model = OPENAI_TTS_MODEL from project/.env (tts-1 on the project key). Voices rotate over the six
built-in voices so Whisper is tested on different speakers. The model/voice used for each command is
written to commands/audio_meta.json and merged into commands.jsonl by make_commands.py.
"""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env")
MODEL = os.environ.get("OPENAI_TTS_MODEL", "tts-1")
VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


def main():
    client = OpenAI()
    meta_path = ROOT / "commands" / "audio_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    cmds = [json.loads(l) for l in (ROOT / "commands" / "commands.jsonl").read_text().splitlines() if l.strip()]
    (ROOT / "commands" / "audio").mkdir(exist_ok=True)
    for i, c in enumerate(cmds):
        out = ROOT / "commands" / c["audio"]
        if out.exists() and c["id"] in meta and meta[c["id"]]["text"] == c["text"]:
            continue
        voice = VOICES[i % len(VOICES)]
        t0 = time.time()
        r = client.audio.speech.create(model=MODEL, voice=voice, input=c["text"], response_format="mp3")
        out.write_bytes(r.content)
        meta[c["id"]] = {"model": MODEL, "voice": voice, "format": "mp3", "text": c["text"],
                         "bytes": out.stat().st_size, "latency_ms": round((time.time() - t0) * 1000)}
        meta_path.write_text(json.dumps(meta, indent=1))
        print(c["id"], voice, out.stat().st_size, "bytes", flush=True)


if __name__ == "__main__":
    main()
