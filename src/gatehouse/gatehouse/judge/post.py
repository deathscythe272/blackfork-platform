"""Post the verdict to the pull request and keep the fixed-or-dismissed loop honest.

One comment per pull request, updated in place. Each finding has a stable id and one
of three states:
  open       reported by the latest run and not dismissed
  fixed      reported by an earlier run, absent from the latest run
  dismissed  a human replied `/gatehouse dismiss <id> reason: ...`; counted as a
             false positive for that rubric item in the published precision table

A check run named "gatehouse/judge" carries the count. While every rubric item is
advisory its conclusion is neutral; an item marked blocking in the rubric turns open
findings into a failure.

Serves: BR-3, BR-9.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
import yaml

MARKER = "<!-- gatehouse-judge -->"
STATE_MARKER = "<!-- gatehouse-state:"
DISMISS_RE = re.compile(r"/gatehouse\s+dismiss\s+([A-Z]\d-[0-9a-f]{6})\s*(?:reason:\s*(.+))?", re.I | re.S)


class GitHub:
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.c = httpx.Client(base_url="https://api.github.com",
                              headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                       "X-GitHub-Api-Version": "2022-11-28"}, timeout=30)

    def comments(self, number: int) -> list[dict]:
        out, page = [], 1
        while True:
            r = self.c.get(f"/repos/{self.repo}/issues/{number}/comments", params={"per_page": 100, "page": page}).raise_for_status().json()
            out.extend(r)
            if len(r) < 100:
                return out
            page += 1

    def upsert_comment(self, number: int, body: str) -> None:
        for cm in self.comments(number):
            if MARKER in (cm.get("body") or ""):
                self.c.patch(f"/repos/{self.repo}/issues/comments/{cm['id']}", json={"body": body}).raise_for_status()
                return
        self.c.post(f"/repos/{self.repo}/issues/{number}/comments", json={"body": body}).raise_for_status()

    def check_run(self, head_sha: str, conclusion: str, title: str, summary: str) -> None:
        self.c.post(f"/repos/{self.repo}/check-runs", json={
            "name": "gatehouse/judge", "head_sha": head_sha, "status": "completed",
            "conclusion": conclusion, "output": {"title": title, "summary": summary},
        }).raise_for_status()


def previous_state(comments: list[dict]) -> dict[str, dict]:
    """Findings recorded in the last judge comment, keyed by id."""
    for cm in comments:
        body = cm.get("body") or ""
        if MARKER in body and STATE_MARKER in body:
            raw = body.split(STATE_MARKER, 1)[1].split("-->", 1)[0]
            try:
                return {f["id"]: f for f in json.loads(raw)}
            except json.JSONDecodeError:
                return {}
    return {}


def dismissals(comments: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for cm in comments:
        body = cm.get("body") or ""
        if MARKER in body:
            continue
        for m in DISMISS_RE.finditer(body):
            out[m.group(1)] = {"by": (cm.get("user") or {}).get("login", "?"),
                               "reason": (m.group(2) or "").strip()[:300] or "(no reason given)"}
    return out


def reconcile(verdict: dict, prev: dict[str, dict], dismissed: dict[str, dict]) -> list[dict]:
    """Merge the latest findings with history into rows carrying a status."""
    rows: dict[str, dict] = {}
    for f in verdict["findings"]:
        rows[f["id"]] = {**f, "status": "dismissed" if f["id"] in dismissed else "open",
                         "dismissal": dismissed.get(f["id"])}
    for fid, f in prev.items():
        if fid not in rows:
            status = "dismissed" if fid in dismissed else "fixed"
            rows[fid] = {**f, "status": status, "dismissal": dismissed.get(fid)}
    order = {"open": 0, "dismissed": 1, "fixed": 2}
    return sorted(rows.values(), key=lambda r: (order[r["status"]], r.get("severity", "z"), r["id"]))


def render(verdict: dict, rows: list[dict], rubric: dict, n_files: int) -> str:
    v = verdict["rubric_version"]
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("open", "fixed", "dismissed")}
    blocking = {i["id"] for i in rubric["items"] if i.get("blocking")}
    judged = [i for i in rubric["items"] if int(i.get("lane", 2)) == 2]
    lines = [MARKER, f"### Gatehouse judge · rubric v{v} · advisory",
             f"Checked {len(judged)} judgment items on {n_files} changed file(s); "
             f"{len(rubric['items']) - len(judged)} exact-rule items run as scripts. "
             f"**{counts['open']} open**, {counts['fixed']} fixed, {counts['dismissed']} dismissed.", ""]
    lines.append("| Item | Verdict | Note |")
    lines.append("|---|---|---|")
    titles = {i["id"]: i["title"] for i in rubric["items"]}
    for it in verdict["items"]:
        mark = {"pass": "pass", "fail": "**fail**", "not_applicable": "n/a"}[it["verdict"]]
        lines.append(f"| {it['id']} {titles.get(it['id'], '')} | {mark} | {it['note']} |")
    if rows:
        lines += ["", "| ID | Status | Sev | Where | Finding | Fix |", "|---|---|---|---|---|---|"]
        for r in rows:
            where = f"`{r['file']}`" + (f":{r['line']}" if r.get("line") else "")
            status = r["status"]
            if status == "dismissed" and r.get("dismissal"):
                status = f"dismissed by @{r['dismissal']['by']}: {r['dismissal']['reason']}"
            b = " (blocking)" if r["item"] in blocking else ""
            lines.append(f"| `{r['id']}` | {status} | {r['severity']}{b} | {where} | {r['why']} | {r['fix']} |")
    lines += ["", "_A finding closes when a later run no longer reports it (fixed) or when a maintainer replies "
              "`/gatehouse dismiss <ID> reason: ...` (dismissed). Dismissals count as false positives for that "
              "rubric item in the published precision table. Every item is advisory until its measured precision "
              "clears the ADR-005 threshold._"]
    state = [{k: r[k] for k in ("id", "item", "severity", "file", "line", "why", "fix")} for r in rows if r["status"] != "fixed"]
    lines.append(f"{STATE_MARKER}{json.dumps(state, separators=(',', ':'))}-->")
    return "\n".join(lines)


def conclusion_for(rows: list[dict], rubric: dict) -> tuple[str, str]:
    blocking = {i["id"] for i in rubric["items"] if i.get("blocking")}
    open_rows = [r for r in rows if r["status"] == "open"]
    open_blocking = [r for r in open_rows if r["item"] in blocking]
    if open_blocking:
        return "failure", f"{len(open_blocking)} open finding(s) on blocking rubric items"
    if open_rows:
        return "neutral", f"{len(open_rows)} open advisory finding(s)"
    return "success", "no open findings"


def publish(gh: GitHub, number: int, head_sha: str | None, verdict: dict, rubric_text: str, n_files: int) -> dict[str, Any]:
    rubric = yaml.safe_load(rubric_text)
    comments = gh.comments(number)
    rows = reconcile(verdict, previous_state(comments), dismissals(comments))
    gh.upsert_comment(number, render(verdict, rows, rubric, n_files))
    concl, summary = conclusion_for(rows, rubric)
    if head_sha:
        try:
            gh.check_run(head_sha, concl, f"Gatehouse judge · rubric v{verdict['rubric_version']}", summary)
        except httpx.HTTPStatusError as e:  # checks:write may be unavailable on forks; the comment still stands
            summary += f" (check run not created: HTTP {e.response.status_code})"
    return {"conclusion": concl, "summary": summary, "rows": rows}
