"""Rotating debug transcript for the interactive session.

Each calendar day gets its own JSONL file next to the YAML status file,
one line per logged turn. On session start, files outside the last
KEEP_DAYS calendar days (today included) are deleted.
"""

import json
from datetime import date, timedelta
from pathlib import Path

KEEP_DAYS = 5


def transcript_dir(yaml_path: str) -> str:
    return str(Path(yaml_path).with_name("rrm-transcripts"))


def transcript_path(yaml_path: str, day: date | None = None) -> str:
    day = day or date.today()
    return str(Path(transcript_dir(yaml_path)) / f"{day.isoformat()}.jsonl")


def log_turn(yaml_path: str, entry: dict, day: date | None = None) -> None:
    path = Path(transcript_path(yaml_path, day))
    path.parent.mkdir(exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def prune(yaml_path: str, keep_days: int = KEEP_DAYS) -> None:
    """Delete transcript files dated before the last keep_days days."""
    cutoff = date.today() - timedelta(days=keep_days - 1)
    for f in Path(transcript_dir(yaml_path)).glob("*.jsonl"):
        if date.fromisoformat(f.stem) < cutoff:
            f.unlink()
