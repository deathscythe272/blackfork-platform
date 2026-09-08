"""The Risk Analyst's verdict, the deterministic half.

A finding is one control on one system with the requirement text, the mapper's
statement, and the evidence rows. The score comes from facts about the evidence, never
from the text of the statement or the requirement: how many rows, how many distinct
sources, how old the newest is, whether the statement cites rows that exist. Text is
an input to the explanation only, so an instruction planted in a statement cannot move
the number (T1-A2A-03). The explanation is written afterwards, by a model or by a
template, and either way it explains a score it did not choose.

Serves: BR-3, BR-8.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

ROW_ID = re.compile(r"\bev-\d{4}\b")
STALE_DAYS = 90


@dataclass
class Verdict:
    severity: str          # high | medium | low
    score: int             # 0 (nothing wrong) to 100 (nothing right)
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    cited_rows: list[str] = field(default_factory=list)
    uncited_rows: list[str] = field(default_factory=list)
    unknown_citations: list[str] = field(default_factory=list)


def _parse_ts(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00").replace(" ", "T")
        parsed = dt.datetime.fromisoformat(s)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def score(finding: dict[str, Any], now: dt.datetime | None = None) -> Verdict:
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = [r for r in (finding.get("evidence") or []) if isinstance(r, dict) and r.get("row_id")]
    statement = str(finding.get("statement") or "")
    reasons, missing = [], []
    points = 0

    row_ids = {str(r["row_id"]) for r in rows}
    cited = sorted(set(ROW_ID.findall(statement)))
    unknown = sorted(c for c in cited if c not in row_ids)
    uncited = sorted(row_ids - set(cited))

    if not rows:
        points += 70
        reasons.append("no evidence rows are held for this control")
        missing.append("at least one evidence row from a system of record")
    else:
        sources = {str(r.get("source") or "unknown") for r in rows}
        if len(sources) == 1:
            points += 20  # a single source is a real weakness: medium on its own
            reasons.append(f"all {len(rows)} row(s) come from one source ({next(iter(sources))}); a second source would corroborate")
            missing.append("evidence from a second, independent source")
        else:
            reasons.append(f"{len(rows)} rows from {len(sources)} sources corroborate each other")
        newest = max((t for t in (_parse_ts(r.get("observed_at")) for r in rows) if t), default=None)
        if newest is None:
            points += 15
            reasons.append("no evidence row carries a usable observation time")
            missing.append("observation timestamps on the evidence")
        else:
            age = (now - newest).days
            if age > STALE_DAYS:
                points += 25
                reasons.append(f"the newest evidence is {age} days old, past the {STALE_DAYS}-day freshness line")
                missing.append("a recent observation")
            else:
                reasons.append(f"the newest evidence is {age} day(s) old")
    if not statement.strip():
        points += 10
        reasons.append("no implementation statement was drafted")
        missing.append("an implementation statement that cites its rows")
    else:
        if unknown:
            points += 20
            reasons.append(f"the statement cites row(s) that are not in the evidence: {', '.join(unknown)}")
        if rows and not cited:
            points += 10
            reasons.append("the statement cites no evidence rows")
        elif uncited:
            reasons.append(f"evidence not used by the statement: {', '.join(uncited)}")

    points = max(0, min(100, points))
    severity = "high" if points >= 50 else ("medium" if points >= 20 else "low")
    return Verdict(severity, points, reasons, missing, cited, uncited, unknown)
