"""Save AI answers on disk, so the exact same request is never sent twice.
The cache key is a hash of everything sent to the model (model name, instructions,
prompt and schema). The prompt contains the file's code, so when a file, a prompt
or the model changes, the key changes and a fresh answer is requested automatically.
"""

import hashlib
import json
from pathlib import Path

CACHE_DIR = Path.home() / ".repomentor" / "cache" / "ai"


def make_key(request: dict) -> str:
    """Return a SHA-256 hash that identifies this exact request."""
    text = json.dumps(request, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(key: str) -> dict | None:
    """Return the saved answer for this key, or None if there is no usable one."""
    path = CACHE_DIR / f"{key}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save(key: str, answer: dict) -> None:
    """Save an answer. It is written to a temporary file first, so a crash never leaves a half-written entry."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(answer, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(path)