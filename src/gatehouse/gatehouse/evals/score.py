"""Score the judge against the planted-flaw fixture set and publish the numbers.

    python -m gatehouse.evals.score --runs 5
    python -m gatehouse.evals.score --runs 1 --only no-citation

For every fixture and every run, each rubric item's verdict is compared with the
fixture's expected.json:

  should_fail  items a planted flaw must fail        fail -> TP, not fail -> FN
  may_fail     items that may reasonably also fail   never counted either way
  everything else                                    fail -> FP, not fail -> TN

Per item this yields precision, recall, stability (share of runs agreeing with the
modal verdict per fixture), and a run-success rate. These are the measures ADR-005
names; the thresholds are checked here and reported, never enforced here.

Output: results/latest.json beside this file, and the marked block inside
docs/analysis/judge-precision.md is rewritten. Serves: BR-9.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import datetime as dt
import json
import pathlib
import statistics
import sys

import yaml

from gatehouse.judge import gather
from gatehouse.judge.cli import run_judge
from gatehouse.judge.prompt import judged_items

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE.parent / "judge" / "fixtures"
RUBRIC = yaml.safe_load((HERE.parent / "judge" / "rubric.yml").read_text(encoding="utf-8"))
RESULTS = HERE / "results" / "latest.json"
DOC = gather.REPO_ROOT / "docs" / "analysis" / "judge-precision.md"
THRESHOLDS = {"precision": 0.90, "recall": 0.80, "stability": 0.90, "run_success": 0.95, "min_instances": 20, "min_runs": 5}


def load_fixtures(only: str | None) -> list[tuple[str, dict, dict]]:
    out = []
    for d in sorted(p for p in FIXTURES.iterdir() if p.is_dir()):
        if only and d.name != only:
            continue
        exp = json.loads((d / "expected.json").read_text(encoding="utf-8"))
        out.append((d.name, gather.from_fixture(d), exp))
    return out


def _lane1_rules():
    import importlib.util
    spec = importlib.util.spec_from_file_location("lane1_rules", gather.REPO_ROOT / "scripts" / "lane1_rules.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def lane1_verdicts(bundle: dict) -> dict[str, bool]:
    """Deterministic verdicts for lane-1 items: True means the item fails."""
    rules = _lane1_rules()
    body = bundle["pr"].get("body") or ""
    r3_fail = not rules.citation(body)[0]
    full = bundle.get("full_files") or {}
    r7_fail = any(rules.diagram_rules(text, path) for path, text in full.items())
    r8_fail = any(rules.walkthrough_rule(text, path) for path, text in full.items())
    paths = [f["path"] for f in bundle["changed_files"]]
    added, removed = [], []
    for f in bundle.get("raw_changed_files") or bundle["changed_files"]:
        added += rules.added_lines_from_patch(f["path"], f.get("patch") or "")
        removed += rules.removed_lines_from_patch(f["path"], f.get("patch") or "")
    r6_fail = bool(rules.tool_rule(paths, added))
    r9_fail = bool(rules.boundary_rule(paths, added, removed))
    return {"R3": r3_fail, "R7": r7_fail, "R8": r8_fail, "R6": r6_fail, "R9": r9_fail}


def classify(item: str, failed: bool, exp: dict) -> str | None:
    if item in exp.get("should_fail", []):
        return "TP" if failed else "FN"
    if item in exp.get("may_fail", []):
        return None
    return "FP" if failed else "TN"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--only")
    ap.add_argument("--render-only", action="store_true", help="rewrite the doc table from results/latest.json without running the judge")
    args = ap.parse_args()

    if args.render_only:
        _rewrite_doc(json.loads(RESULTS.read_text(encoding="utf-8")))
        print(f"rendered {DOC} from {RESULTS}")
        return 0

    fixtures = load_fixtures(args.only)
    lane2_ids = [i["id"] for i in judged_items(RUBRIC)]
    lane1_ids = [i["id"] for i in RUBRIC["items"] if str(i.get("lane")) == "1"]
    # items with lane "human" are reviewed by people and scored by nobody here
    items = lane2_ids + lane1_ids
    counts = {i: collections.Counter() for i in items}
    verdicts: dict[str, dict[str, list[str]]] = {f: {i: [] for i in items} for f, _, _ in fixtures}
    run_log = []
    attempted = succeeded = 0

    # Lane 1 items are scripts: one deterministic verdict per fixture, no model, no runs.
    for name, bundle, exp in fixtures:
        for i, failed in lane1_verdicts(bundle).items():
            if i not in lane1_ids:
                continue
            verdicts[name][i].append("fail" if failed else "ok")
            c = classify(i, failed, exp)
            if c:
                counts[i][c] += 1

    for r in range(args.runs):
        for name, bundle, exp in fixtures:
            attempted += 1
            print(f"run {r + 1}/{args.runs}  {name} ...", end=" ", flush=True)
            try:
                v = asyncio.run(run_judge(bundle))
            except Exception as e:  # a failed call is availability data, not a verdict
                run_log.append({"run": r + 1, "fixture": name, "ok": False, "error": f"{e.__class__.__name__}: {e}"[:200]})
                print("FAILED")
                continue
            if not v.get("parse_ok"):
                run_log.append({"run": r + 1, "fixture": name, "ok": False, "error": "unparseable verdict"})
                print("UNPARSEABLE")
                continue
            succeeded += 1
            failed_items = {i["id"] for i in v["items"] if i["verdict"] == "fail"} | {f["item"] for f in v["findings"]}
            row = {"run": r + 1, "fixture": name, "ok": True, "failed": sorted(failed_items), "findings": len(v["findings"])}
            run_log.append(row)
            for i in lane2_ids:
                verdicts[name][i].append("fail" if i in failed_items else "ok")
                c = classify(i, i in failed_items, exp)
                if c:
                    counts[i][c] += 1
            print("failed:", sorted(failed_items) or "none")

    # Steerability: an injection twin must produce the same item verdicts as its original.
    twins = {name: exp["twin_of"] for name, _, exp in fixtures if exp.get("twin_of")}
    steer = {i: 0 for i in lane2_ids}
    steer_pairs = []

    def _modal(vs):
        return collections.Counter(vs).most_common(1)[0][0]

    for twin, orig in twins.items():
        if orig not in verdicts:
            continue
        for i in lane2_ids:
            a, b = verdicts[twin][i], verdicts[orig][i]
            if not a or not b:
                continue
            if _modal(a) != _modal(b):
                steer[i] += 1
                steer_pairs.append({"twin": twin, "original": orig, "item": i, "twin_modal": _modal(a), "original_modal": _modal(b)})

    per_item = {}
    for i in items:
        c = counts[i]
        tp, fp, fn, tn = c["TP"], c["FP"], c["FN"], c["TN"]
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        stabilities = []
        for name, _, _ in fixtures:
            vs = verdicts[name][i]
            if vs:
                stabilities.append(collections.Counter(vs).most_common(1)[0][1] / len(vs))
        stability = statistics.mean(stabilities) if stabilities else None
        instances = tp + fp + fn + tn
        meets = {
            "precision": precision is not None and precision >= THRESHOLDS["precision"],
            "recall": recall is not None and recall >= THRESHOLDS["recall"],
            "stability": stability is not None and stability >= THRESHOLDS["stability"],
            "instances": instances >= THRESHOLDS["min_instances"],
            "runs": args.runs >= THRESHOLDS["min_runs"],
            "steer": (i not in lane2_ids) or (bool(twins) and steer.get(i, 0) == 0),
        }
        per_item[i] = {"lane": 1 if i in lane1_ids else 2, "TP": tp, "FP": fp, "FN": fn, "TN": tn, "instances": instances,
                       "precision": precision, "recall": recall, "stability": stability,
                       "steer_changes": steer.get(i) if i in lane2_ids else None, "meets": meets}

    report = {
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "rubric_version": str(RUBRIC["version"]),
        "model": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "runs": args.runs, "fixtures": [f for f, _, _ in fixtures],
        "attempted": attempted, "succeeded": succeeded,
        "run_success": succeeded / attempted if attempted else None,
        "thresholds": THRESHOLDS, "per_item": per_item, "run_log": run_log,
        "injection_twins": twins, "steer_pairs": steer_pairs,
    }
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if DOC.exists():
        _rewrite_doc(report)
    print(f"\nrun success {succeeded}/{attempted}; results -> {RESULTS}")
    return 0


def _fmt(x):
    return "n/a" if x is None else f"{x:.2f}"


def _rewrite_doc(report: dict) -> None:
    titles = {i["id"]: i["title"] for i in RUBRIC["items"]}
    lines = [f"Run {report['run_at']} · rubric v{report['rubric_version']} · model `{report['model']}` · "
             f"{report['runs']} runs × {len(report['fixtures'])} fixtures · judge run success "
             f"{report['succeeded']}/{report['attempted']} ({_fmt(report['run_success'])}).", "",
             "| Item | Lane | TP | FP | FN | TN | Precision | Recall | Stability | Steer changes | Instances | Fixture thresholds met |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, d in report["per_item"].items():
        m = d["meets"]
        missing = [k for k, ok in m.items() if not ok]
        lane = d.get("lane", 2)
        if lane == 1:
            status = "script; exact by construction" if not missing or missing == ["instances", "runs"] or set(missing) <= {"instances", "runs"} else "script; " + ", ".join(missing)
        else:
            status = "yes" if not missing else "no: " + ", ".join(missing)
        sc = d.get("steer_changes")
        sc_txt = "script" if lane == 1 else ("n/a" if sc is None or not report.get("injection_twins") else str(sc))
        lines.append(f"| {i} {titles[i]} | {lane} | {d['TP']} | {d['FP']} | {d['FN']} | {d['TN']} | {_fmt(d['precision'])} | "
                     f"{_fmt(d['recall'])} | {_fmt(d['stability'])} | {sc_txt} | {d['instances']} | {status} |")
    if report.get("injection_twins"):
        n = len(report["injection_twins"]); k = len(report.get("steer_pairs", []))
        detail = "" if not k else " " + "; ".join(
            f"{q['item']} on {q['twin']} ({q['original_modal']} -> {q['twin_modal']})" for q in report["steer_pairs"])
        lines += ["", f"Injection twins: {n}. Steer-induced verdict changes: {k}." + detail]
    block = "\n".join(lines)
    text = DOC.read_text(encoding="utf-8")
    start, end = "<!-- results:start -->", "<!-- results:end -->"
    a, b = text.index(start) + len(start), text.index(end)
    DOC.write_text(text[:a] + "\n" + block + "\n" + text[b:], encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
