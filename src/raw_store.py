"""
Append-only raw store, partitioned by day (NDJSON).

Why this exists (storage design / Betriebskonzept):
Previously every fetch wrote its own timestamped .json file, which produced
hundreds of tiny files per day and bloated the git repo. We keep the exact same
append-only, immutable philosophy — but instead of one file per fetch, we append
one JSON *line* per snapshot to a per-day, per-source partition file:

    weather_2026-06-21.ndjson
    polymarket_2026-06-21.ndjson

Benefits:
- ~2 files/day instead of ~288, so the repo stays tidy.
- Still append-only: we only ever add lines, never rewrite existing ones, so the
  immutability/auditability guarantee is preserved and git diffs are clean
  (added lines), which git also stores far more efficiently than new blobs.
- Each line is a complete, self-describing record (same `_meta` + payload
  envelope as before), so no information is lost vs the old format.

NDJSON = "newline-delimited JSON": one independent JSON object per line. Read it
back with `for line in f: rec = json.loads(line)`.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib


def utc_date() -> str:
    """Current UTC calendar date, e.g. 2026-06-21 (the partition key)."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def append_record(directory: pathlib.Path, source: str, record: dict) -> pathlib.Path:
    """Append one record as a line to today's NDJSON partition for `source`.

    `source` is the filename stem, e.g. "weather" or "polymarket". Returns the
    path of the partition file written to. Append mode never touches existing
    lines, so this stays crash-safe and idempotent-friendly.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{source}_{utc_date()}.ndjson"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
