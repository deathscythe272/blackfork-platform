"""The Report Writer: a draft packet for one system, every sentence carrying its citation.

    python -m provenance.agent.writer sys-windrow-prod 3.3.1 3.1.2

For each control it runs the assessor (the mapper's statement and the analyst's
verdict), then assembles the packet. The writer does not write prose of its own: the
statements are the mapper's, the verdicts are the analyst's, and the writer's job is
structure and the citation rule. A statement that cites rows that do not exist, or
that cites none of the evidence held, is withheld and counted, so the packet carries
its own measure of what it could not stand behind. Signing and export are the packet store's business (ADR-007).

Serves: BR-2, BR-7, C3.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import sys
from typing import Any

from provenance.agent.assess import _gateway_call, main as assess_main
from provenance.packets import store

ROW_ID = re.compile(r"\bev-[0-9A-Za-z][0-9A-Za-z-]*")  # any ev- token; checked against the real rows
CONTROL_ID = re.compile(r"\b(?:\d{1,2}\.\d{1,2}\.\d{1,2}|0\d\.\d{2}\.\d{2}|SR-0\d\.\d{2}\.\d{2})\b")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
MAX_CONTROLS = int(os.environ.get("WRITER_MAX_CONTROLS", "6"))


NO_EVIDENCE = re.compile(r"\bno evidence\b", re.I)


def statement_check(text: str, real_rows: set[str]) -> dict[str, Any]:
    """Apply the citation rule to one statement as a whole. The mapper cites its rows on
    a trailing "Cited:" line or inline; either counts. Returns statement, rows_cited,
    invented, and withheld (a reason, or None). A statement is withheld when it cites
    a row that does not exist, or when evidence exists and it cites none of it. A
    statement that says no evidence is held, for a control with none, stands as it is.
    The first packet runs tried a per-sentence rule; it threw away honest statements
    that cite at the end and, loosened, dressed a model's reasoning up as cited."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    body = "\n".join(l for l in lines if not l.lower().startswith("cited:")).strip()
    ids = ROW_ID.findall(text)
    rows_cited = sorted({i for i in ids if i in real_rows})
    invented = sorted({i for i in ids if i not in real_rows})
    withheld = None
    if invented:
        withheld = f"cites rows that do not exist: {', '.join(invented)}"
    elif real_rows and not rows_cited:
        withheld = "cites none of the evidence held for this control"
    elif not real_rows and not NO_EVIDENCE.search(body) and not CONTROL_ID.search(body):
        withheld = "neither cites the control nor says no evidence is held"
    return {"statement": body, "rows_cited": rows_cited, "invented": invented, "withheld": withheld}


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [f"# Draft packet: {packet['system_id']}", "",
             f"Generated {packet['generated_at']} by the Report Writer from {len(packet['controls'])} control(s). "
             f"Status: {packet.get('status', 'draft')}. Every statement below cites the evidence rows it rests on; "
             f"{packet['withheld_statements']} statement(s) withheld, {packet.get('invented_citations', 0)} of them for citing rows that do not exist.", ""]
    for c in packet["controls"]:
        v = c.get("verdict")
        if not v:
            lines += [f"## {c['control_id']}", "", f"Mapping failed: {c.get('mapping_failed', 'unknown')}. No statement, no verdict; rerun before signing.", ""]
            continue
        lines += [f"## {c['control_id']} {c.get('title', '')}".rstrip(), "",
                  f"Verdict: {v['severity']} ({v['score']}/100). " + " ".join(v.get("reasons", [])[:2]), ""]
        if c.get("withheld"):
            lines += [f"Statement withheld: {c['withheld']}.", ""]
        else:
            lines += [c["statement"], ""]
        lines += [f"Rows cited: {', '.join(c['rows_cited']) or 'none'}", ""]
    lines += ["---", store.signed_footer(packet["signature"]) if packet.get("signature") else store.UNSIGNED_FOOTER]
    return "\n".join(lines) + "\n"


async def main(system_id: str, control_ids: list[str] | None = None, token: str | None = None) -> dict[str, Any]:
    token = token or os.environ["GATEWAY_TOKEN"]
    if not control_ids:
        listed = await _gateway_call("list_controls", {"system_id": system_id}, token)
        control_ids = [c["control_id"] for c in (listed or [])]
    control_ids = control_ids[:MAX_CONTROLS]
    controls, withheld_total, invented_total, failed = [], 0, 0, 0
    for cid in control_ids:
        result = await assess_main(system_id, cid, token=token)
        if result.get("mapping_failed"):
            failed += 1
            controls.append({"control_id": cid, "mapping_failed": result["mapping_failed"], "sentences": [], "dropped": [],
                             "invented": [], "rows_cited": [], "verdict": None})
            continue
        real_rows = set(result.get("finding_rows") or [])
        check = statement_check(result.get("answer", "").split("\n\nVerdict:")[0], real_rows)
        withheld_total += bool(check["withheld"])
        invented_total += bool(check["invented"])
        controls.append({
            "control_id": cid, "statement": "" if check["withheld"] else check["statement"], "withheld": check["withheld"],
            "invented": check["invented"], "rows_cited": [] if check["withheld"] else check["rows_cited"],
            "verdict": {k: result["verdict"].get(k) for k in ("severity", "score", "reasons", "cited_rows")},
            "input_blocked": result.get("input_blocked"), "output_blocked": result.get("output_blocked"),
        })
    packet = {"system_id": system_id, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "controls": controls, "withheld_statements": withheld_total, "invented_citations": invented_total,
              "failed_controls": failed, "writer": "report-writer"}
    stored = store.save_draft(packet, render_markdown(packet))
    rows = sorted({r for c in controls for r in c["rows_cited"]})
    answer = (f"Draft packet {stored['packet_id']} for {system_id}: {len(controls)} control(s), "
              f"{sum(1 for c in controls if c.get('statement'))} statement(s) kept, {withheld_total} withheld "
              f"({invented_total} for citing rows that do not exist). "
              f"Rows cited: {', '.join(rows) or 'none'}. Verdicts: "
              + "; ".join(f"{c['control_id']} {c['verdict']['severity'] if c.get('verdict') else 'mapping failed'}" for c in controls)
              + f". {failed} control(s) failed to map. Unsigned.")
    return {"answer": answer, "packet_id": stored["packet_id"], "packet": stored, "input_blocked": False,
            "output_blocked": False, "error": None, "withheld_statements": withheld_total, "invented_citations": invented_total,
            "failed_controls": failed}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    out = asyncio.run(main(sys.argv[1], sys.argv[2:] or None))
    print("\n=== RESULT ===")
    print(json.dumps({k: v for k, v in out.items() if k != "packet"}, indent=2))
