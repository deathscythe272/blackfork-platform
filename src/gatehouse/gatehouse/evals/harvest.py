"""Harvest the judge's live record from the repository's merged pull requests.

    python -m gatehouse.evals.harvest                 # reads GitHub through the gh CLI
    python -m gatehouse.evals.harvest --render-only   # rewrite the doc block from results/live.json

For every merged pull request that carries a judge comment, read the rubric version,
each item's verdict, and the finding table. ADR-005 says how they count:

  fixed       a finding the author made go away: accepted, a true positive
  dismissed   a finding a maintainer dismissed with a reason: a false positive
  open        an unresolved finding on a merged pull request: counts for nothing,
              and is listed so it does not hide
  pass / fail a judged instance; not_applicable (gated off by the parser) is not

Counts are given per rubric version, and totalled for the versions in which the
item's wording and the judge's prompt have not changed since, because ADR-005 resets
an item on any such change. Output: results/live.json and the marked block in
docs/analysis/judge-precision.md. Serves: BR-9.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

import yaml

from gatehouse.judge import gather

HERE = pathlib.Path(__file__).resolve().parent
RUBRIC = yaml.safe_load((HERE.parent / "judge" / "rubric.yml").read_text(encoding="utf-8"))
RESULTS = HERE / "results" / "live.json"
DOC = gather.REPO_ROOT / "docs" / "analysis" / "judge-precision.md"
REPO = "deathscythe272/blackfork-platform"
MARKER = "<!-- gatehouse-judge -->"

# The rubric version from which each item's current wording, and the judge's prompt,
# have been stable. ADR-005: a wording or prompt change resets the count.
COUNTS_FROM = {"R1": "1.2", "R5": "1.5"}  # R5's wording changed in v1.5; ADR-005 restarts its count, on the record


def _gh(path: str) -> list | dict:
    out = subprocess.run(["gh", "api", "--paginate", path], capture_output=True, text=True, check=True).stdout
    # --paginate concatenates arrays; join them
    chunks = re.split(r"\]\s*\[", out.strip())
    if len(chunks) == 1:
        return json.loads(out)
    return json.loads("[" + "],[".join(c.strip("[]") for c in chunks) + "]")


def parse_comment(body: str) -> dict:
    """Rubric version, item verdicts, and finding rows from one judge comment."""
    version = re.search(r"rubric v([\d.]+)", body)
    items = {m.group(1): m.group(2).strip("*") for m in
             re.finditer(r"^\| (R\d) [^|]*\| (pass|\*\*fail\*\*|n/a) \|", body, re.M)}
    findings = []
    for m in re.finditer(r"^\| `([A-Z]\d-[0-9a-f]{6})` \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|", body, re.M):
        fid, status, sev, where, why = (g.strip() for g in m.groups())
        state = "dismissed" if status.startswith("dismissed") else ("fixed" if status == "fixed" else "open")
        reason = status.split(":", 1)[1].strip() if state == "dismissed" and ":" in status else None
        # The finding text itself is not kept: it is quoted from the judge and can carry
        # the very identifiers R5 exists to keep out of the repo. The id points at it.
        findings.append({"id": fid, "item": fid.split("-")[0], "status": state, "reason": reason,
                         "where": where.replace("`", "")})
    return {"rubric_version": version.group(1) if version else "?", "items": items, "findings": findings}


def harvest() -> dict:
    prs = _gh(f"repos/{REPO}/pulls?state=closed&per_page=100")
    rows = []
    for pr in sorted(prs, key=lambda p: p["number"]):
        if not pr.get("merged_at"):
            continue
        comments = _gh(f"repos/{REPO}/issues/{pr['number']}/comments?per_page=100")
        judge = next((c["body"] for c in comments if MARKER in (c.get("body") or "")), None)
        if not judge:
            continue
        parsed = parse_comment(judge)
        rows.append({"pr": pr["number"], "merged_at": pr["merged_at"][:10], "title": pr["title"][:80], **parsed})
    return {"harvested_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "pull_requests": rows}


def _vkey(v: str) -> tuple:
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def summarize(report: dict) -> dict:
    per = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    open_findings = []
    for pr in report["pull_requests"]:
        v = pr["rubric_version"]
        for item, verdict in pr["items"].items():
            if verdict in ("pass", "fail"):
                per[item][v]["judged"] += 1
                per[item][v][verdict] += 1
        for f in pr["findings"]:
            per[f["item"]][v][f["status"]] += 1
            if f["status"] == "open":
                open_findings.append({"pr": pr["pr"], **f})
    summary = {}
    for item, byv in per.items():
        since = COUNTS_FROM.get(item)
        counted = collections.Counter()
        for v, c in byv.items():
            if since and _vkey(v) >= _vkey(since):
                counted.update(c)
        tp, fp = counted["fixed"], counted["dismissed"]
        summary[item] = {
            "by_version": {v: dict(c) for v, c in sorted(byv.items(), key=lambda kv: _vkey(kv[0]))},
            "counts_from": since,
            "judged": counted["judged"], "accepted": tp, "dismissed": fp,
            "live_precision": tp / (tp + fp) if tp + fp else None,
            "instances_needed": max(0, 20 - counted["judged"]) if since else None,
        }
    return {"items": summary, "open_findings": open_findings}


def _fmt(x):
    return "n/a" if x is None else f"{x:.2f}"


def render(report: dict) -> str:
    s = report["summary"]
    titles = {i["id"]: i["title"] for i in RUBRIC["items"]}
    lines = [f"Harvested {report['harvested_at']} from {len(report['pull_requests'])} merged pull requests with a judge comment.", "",
             "| Item | Counted since | Judged | Accepted (fixed) | Dismissed | Live precision | To 20 instances |",
             "|---|---|---|---|---|---|---|"]
    for item in sorted(s["items"]):
        d = s["items"][item]
        since = f"v{d['counts_from']}" if d["counts_from"] else "retired from the judge"
        need = "n/a" if d["instances_needed"] is None else str(d["instances_needed"])
        lines.append(f"| {item} {titles.get(item, '')} | {since} | {d['judged']} | {d['accepted']} | {d['dismissed']} | {_fmt(d['live_precision'])} | {need} |")
    lines += ["", "Per rubric version (judged / fixed / dismissed / open):", ""]
    for item in sorted(s["items"]):
        parts = [f"v{v}: {c.get('judged', 0)}/{c.get('fixed', 0)}/{c.get('dismissed', 0)}/{c.get('open', 0)}"
                 for v, c in s["items"][item]["by_version"].items()]
        lines.append(f"- {item}: " + "; ".join(parts))
    if s["open_findings"]:
        lines += ["", "Unresolved findings on merged pull requests (count for nothing, listed so they do not hide):", ""]
        # Id and location only. Finding text is quoted from the judge and can carry the
        # very identifiers R5 exists to keep out of the repo; the first harvest did.
        for f in s["open_findings"]:
            lines.append(f"- PR {f['pr']}, `{f['id']}` at `{f['where']}`")
    return "\n".join(lines)


def _rewrite_doc(report: dict) -> None:
    text = DOC.read_text(encoding="utf-8")
    start, end = "<!-- live:start -->", "<!-- live:end -->"
    a, b = text.index(start) + len(start), text.index(end)
    DOC.write_text(text[:a] + "\n" + render(report) + "\n" + text[b:], encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--render-only", action="store_true")
    args = ap.parse_args()
    if args.render_only:
        report = json.loads(RESULTS.read_text(encoding="utf-8"))
    else:
        report = harvest()
        report["summary"] = summarize(report)
        RESULTS.parent.mkdir(exist_ok=True)
        RESULTS.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _rewrite_doc(report)
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
