"""The audit hash chain (T1-PL-02): every row carries the hash of the row before it, so
an altered or removed row breaks the chain at that point and a verifier can say where.

  prev_hash   the previous row's hash, or a genesis marker at the start of a segment
  hash        sha256 over prev_hash and the row's canonical content

A segment starts whenever a gateway process starts: the file sink resumes from the
last row in the file, and the topic sink, which has no file to read, starts a fresh
segment named for the process. The verifier accepts any number of segments. What the
chain cannot detect is the removal of a whole tail after the last row, which needs an
anchor stored elsewhere; the threat model keeps that as the remaining gap.

Serves: BR-7.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

GENESIS = "genesis:"


def canonical(row: dict[str, Any]) -> str:
    """The row without its own chain fields, in a fixed serialization."""
    body = {k: v for k, v in row.items() if k not in ("hash", "prev_hash")}
    return json.dumps(body, separators=(",", ":"), sort_keys=True)


def row_hash(prev_hash: str, row: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + "\n" + canonical(row)).encode("utf-8")).hexdigest()


def link(row: dict[str, Any], prev_hash: str) -> dict[str, Any]:
    """Return the row with its chain fields set."""
    linked = {**row, "prev_hash": prev_hash}
    linked["hash"] = row_hash(prev_hash, linked)
    return linked


def verify(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Walk rows in order. Returns {ok, rows, segments, broken_at, reason}."""
    expected: str | None = None
    n = segments = 0
    for i, row in enumerate(rows):
        n += 1
        prev, h = row.get("prev_hash"), row.get("hash")
        if not prev or not h:
            return {"ok": False, "rows": n, "segments": segments, "broken_at": i, "reason": "row has no chain fields"}
        if prev.startswith(GENESIS):
            segments += 1
        elif prev != expected:
            return {"ok": False, "rows": n, "segments": segments, "broken_at": i, "reason": "prev_hash does not match the previous row"}
        if row_hash(prev, row) != h:
            return {"ok": False, "rows": n, "segments": segments, "broken_at": i, "reason": "row content does not match its hash"}
        expected = h
    return {"ok": True, "rows": n, "segments": segments, "broken_at": None, "reason": None}
