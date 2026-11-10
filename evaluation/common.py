"""Shared paths, dataset loading, raw-output cache and logging for the evaluation harness."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

EVAL = Path(__file__).resolve().parent
PROJECT = EVAL.parent
DATASET = PROJECT / "dataset"
HOLDOUT = DATASET / "holdout"
BACKEND = PROJECT / "backend"
RUNTIME = BACKEND / "app" / "static" / "runtime"
RESULTS = EVAL / "results"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(EVAL) not in sys.path:
    sys.path.insert(0, str(EVAL))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT / ".env")

log = logging.getLogger("eval")

CATEGORIES = ["login", "registration", "dashboard", "profile", "ecommerce", "banking", "booking",
              "contact", "settings", "landing"]
CMD_CATEGORIES = ["add", "remove", "modify", "move", "resize", "style", "interaction", "navigation"]


def set_dataset(name: str) -> Path:
    """Select the dataset root: "dev" (dataset/) or "holdout" (dataset/holdout/, never used for tuning)."""
    global DATASET
    if name not in ("dev", "holdout"):
        raise ValueError(f"unknown dataset {name!r}")
    DATASET = HOLDOUT if name == "holdout" else PROJECT / "dataset"
    return DATASET


def setup_logging(run_dir: Path):
    run_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fh = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)
    for noisy in ("httpx", "httpx2", "openai", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def load_sketches(only: list[str] | None = None, limit: int | None = None) -> list[dict]:
    out = []
    for p in sorted((DATASET / "labels").glob("*.json")):
        lab = json.loads(p.read_text())
        if only and lab["id"] not in only and lab["category"] not in only:
            continue
        lab["image_path"] = str(DATASET / "sketches" / f"{lab['id']}.png")
        out.append(lab)
    order = {c: i for i, c in enumerate(CATEGORIES)}
    out.sort(key=lambda l: (order.get(l["category"], 99), l["id"]))
    if limit:
        # keep categories balanced when limiting: take round-robin over categories
        by = {}
        for l in out:
            by.setdefault(l["category"], []).append(l)
        rr, i = [], 0
        while len(rr) < min(limit, len(out)):
            for c in CATEGORIES:
                if c in by and i < len(by[c]) and len(rr) < limit:
                    rr.append(by[c][i])
            i += 1
        out = rr
    return out


def load_commands(sketch_ids: set[str] | None = None, only: list[str] | None = None) -> list[dict]:
    out = []
    for line in (DATASET / "commands" / "commands.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        if sketch_ids is not None and c["sketch_id"] not in sketch_ids:
            continue
        if only and c["id"] not in only and c["category"] not in only:
            continue
        c["audio_path"] = str(DATASET / "commands" / c["audio"])
        out.append(c)
    return out


class RawCache:
    """Raw API outputs, keyed by stage + content hash, stored as JSON under <run>/raw/<stage>/.
    Re-running metrics on the same run directory never repeats an API call."""

    def __init__(self, run_dir: Path, enabled: bool = True):
        self.dir = run_dir / "raw"
        self.enabled = enabled
        self.hits = 0
        self.misses = 0
        self.api_calls = {}

    def key(self, *parts) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(p if isinstance(p, bytes) else json.dumps(p, sort_keys=True, default=str).encode())
        return h.hexdigest()[:20]

    def path(self, stage, name):
        return self.dir / stage / f"{name}.json"

    def get(self, stage, name):
        p = self.path(stage, name)
        if self.enabled and p.exists():
            self.hits += 1
            return json.loads(p.read_text())
        return None

    def put(self, stage, name, value):
        p = self.path(stage, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, indent=1, default=str))
        return value

    def call(self, stage, name, fn, api_calls=1):
        """Return cached value or compute it (recording wall time and errors). Errors are cached too,
        so a failing case is reported, not silently retried forever; pass --retry-errors to redo them."""
        v = self.get(stage, name)
        if v is not None and not (v.get("_error") and getattr(self, "retry_errors", False)):
            return v
        self.misses += 1
        self.api_calls[stage] = self.api_calls.get(stage, 0) + api_calls
        t0 = time.perf_counter()
        try:
            out = fn()
            v = {"_ok": True, "_wall_ms": round((time.perf_counter() - t0) * 1000, 1), "value": out}
        except Exception as e:  # noqa: BLE001 - recorded and reported per case
            log.exception("%s/%s failed", stage, name)
            v = {"_ok": False, "_error": f"{type(e).__name__}: {e}",
                 "_wall_ms": round((time.perf_counter() - t0) * 1000, 1), "value": None}
        return self.put(stage, name, v)


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def openai_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))
