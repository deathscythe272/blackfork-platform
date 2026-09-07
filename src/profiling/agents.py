"""Profile the platform's own agents: every model call's tokens and latency, per task.

    python -m profiling.agents --agent-runs 3 --judge-runs 1 --long-horizon 20

Runs, with the logging proxy in front of the model endpoint:
  agent          the Evidence Collector over its eval cases, in its container
  judge          the Gatehouse judge over its fixtures, in process
  long-horizon   the golden question repeated N times to look for drift

The proxy attributes nothing; this script records the wall-clock window of every task
and assigns each logged call to the task whose window contains it, which is exact
because tasks run one at a time. Outputs:
  src/profiling/results/agents-latest.json
  docs/analysis/charts/agents-*.png
  docs/analysis/agent-workload-profile.md   the marked results block

Serves: BR-9 (W1).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import pathlib
import statistics
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
SRC = REPO / "src"
CALLS = REPO / "profiling" / "calls.jsonl"
RESULTS = HERE / "results" / "agents-latest.json"
CHARTS = REPO / "docs" / "analysis" / "charts"
DOC = REPO / "docs" / "analysis" / "agent-workload-profile.md"
PROXY_HOST = "http://localhost:8765/v1"
PROXY_FROM_CONTAINER = "http://host.docker.internal:8765/v1"

SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, BLUE_LIGHT = "#2a78d6", "#eb6834", "#1baf7a", "#9ec5f4"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _calls_between(start: str, end: str) -> list[dict]:
    if not CALLS.exists():
        return []
    out = []
    for line in CALLS.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if start <= d["ts"] <= end:
            out.append(d)
    return out


def _task(name: str, caller: str, fn) -> dict:
    start = _now()
    t0 = time.perf_counter()
    ok, note = True, ""
    try:
        note = fn() or ""
    except Exception as e:  # a failed task is data
        ok, note = False, f"{e.__class__.__name__}: {e}"[:200]
    wall = round(time.perf_counter() - t0, 2)
    time.sleep(0.3)
    calls = _calls_between(start, _now())
    return {"task": name, "caller": caller, "ok": ok, "note": str(note)[:200], "wall_s": wall,
            "calls": len(calls),
            "prompt_tokens": [c.get("prompt_tokens") for c in calls],
            "completion_tokens": [c.get("completion_tokens") for c in calls],
            "latency_ms": [c.get("latency_ms") for c in calls],
            "statuses": [c.get("status") for c in calls]}


# ---- runners ------------------------------------------------------------------------

def run_agent_case(question: str) -> str:
    cmd = ["docker", "compose", "run", "--rm", "-T", "-e", f"NIM_BASE_URL={PROXY_FROM_CONTAINER}", "agent",
           "python", "-m", "provenance.agent.run", question]
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if "=== RESULT ===" not in p.stdout:
        raise RuntimeError("agent produced no result: " + (p.stderr[-300:] or p.stdout[-300:]))
    r = json.loads(p.stdout.split("=== RESULT ===", 1)[1])
    return f"input_blocked={r.get('input_blocked')} output_blocked={r.get('output_blocked')} err={bool(r.get('error'))}"


def run_judge_fixture(fixture: pathlib.Path) -> str:
    from gatehouse.judge import gather
    from gatehouse.judge.cli import run_judge

    bundle = gather.from_fixture(fixture)
    v = asyncio.run(run_judge(bundle))
    return f"parse_ok={v.get('parse_ok')} findings={len(v.get('findings', []))}"


# ---- aggregation ---------------------------------------------------------------------

def _pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


def summarize(tasks: list[dict]) -> dict:
    out = {}
    for caller in sorted({t["caller"] for t in tasks}):
        ts = [t for t in tasks if t["caller"] == caller]
        calls = [c for t in ts for c in zip(t["prompt_tokens"], t["completion_tokens"], t["latency_ms"])]
        per_task_prompt = [sum(x for x in t["prompt_tokens"] if x) for t in ts]
        per_task_completion = [sum(x for x in t["completion_tokens"] if x) for t in ts]
        out[caller] = {
            "tasks": len(ts), "tasks_ok": sum(1 for t in ts if t["ok"]),
            "calls_per_task": {"p50": _pct([t["calls"] for t in ts], .5), "max": max((t["calls"] for t in ts), default=0)},
            "prompt_tokens_per_call": {"p50": _pct([c[0] for c in calls], .5), "p95": _pct([c[0] for c in calls], .95), "max": max((c[0] or 0 for c in calls), default=0)},
            "completion_tokens_per_call": {"p50": _pct([c[1] for c in calls], .5), "p95": _pct([c[1] for c in calls], .95)},
            "prompt_tokens_per_task": {"p50": _pct(per_task_prompt, .5), "p95": _pct(per_task_prompt, .95), "max": max(per_task_prompt, default=0)},
            "completion_tokens_per_task": {"p50": _pct(per_task_completion, .5), "p95": _pct(per_task_completion, .95)},
            "latency_ms_per_call": {"p50": _pct([c[2] for c in calls], .5), "p95": _pct([c[2] for c in calls], .95)},
            "wall_s_per_task": {"p50": _pct([t["wall_s"] for t in ts], .5), "p95": _pct([t["wall_s"] for t in ts], .95)},
            "non_200": sum(1 for t in ts for s in t["statuses"] if s != 200),
        }
    return out


def charts(tasks: list[dict], summary: dict) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CHARTS.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
                         "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURFACE,
                         "axes.facecolor": SURFACE, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 1,
                         "axes.axisbelow": True, "font.size": 10})
    written = []

    # 1. Prompt size per model call within each agent task (context growth across ReAct steps).
    agent_tasks = [t for t in tasks if t["caller"] == "agent" and t["calls"] > 1]
    if agent_tasks:
        fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
        for t in agent_tasks:
            ys = [x for x in t["prompt_tokens"] if x]
            ax.plot(range(1, len(ys) + 1), ys, color=BLUE_LIGHT, linewidth=1.5, alpha=0.9)
        longest = max(agent_tasks, key=lambda t: t["calls"])
        ys = [x for x in longest["prompt_tokens"] if x]
        ax.plot(range(1, len(ys) + 1), ys, color=BLUE, linewidth=2)
        ax.annotate(f"{ys[-1]:,}", (len(ys), ys[-1]), textcoords="offset points", xytext=(6, -3), color=INK2, fontsize=9)
        ax.set_xlabel("model call within the task"); ax.set_ylabel("prompt tokens")
        ax.set_title("Evidence Collector: prompt size grows with each step of a task", loc="left", color=INK, fontsize=11)
        ax.set_ylim(bottom=0); ax.grid(axis="x", visible=False)
        fig.tight_layout(); p = CHARTS / "agents-context-per-step.png"; fig.savefig(p); plt.close(fig); written.append(p.name)

    # 2. Latency per call, p50 and p95, per caller (magnitude by category, one hue, two shades).
    callers = [c for c in ("agent", "judge", "long-horizon") if c in summary]
    if callers:
        fig, ax = plt.subplots(figsize=(7, 3.2), dpi=150)
        p50 = [summary[c]["latency_ms_per_call"]["p50"] or 0 for c in callers]
        p95 = [summary[c]["latency_ms_per_call"]["p95"] or 0 for c in callers]
        ys = range(len(callers)); h = 0.32
        ax.barh([y + h / 2 for y in ys], p95, height=h, color=BLUE_LIGHT, label="p95")
        ax.barh([y - h / 2 for y in ys], p50, height=h, color=BLUE, label="p50")
        for y, a, b in zip(ys, p50, p95):
            ax.text(a + max(p95) * 0.01, y - h / 2, f"{a:,.0f}", va="center", color=INK2, fontsize=9)
            ax.text(b + max(p95) * 0.01, y + h / 2, f"{b:,.0f}", va="center", color=INK2, fontsize=9)
        ax.set_yticks(list(ys)); ax.set_yticklabels(callers); ax.set_xlabel("latency per model call, ms")
        ax.legend(frameon=False, loc="lower right"); ax.grid(axis="y", visible=False)
        ax.set_title("Model-call latency by caller", loc="left", color=INK, fontsize=11)
        fig.tight_layout(); p = CHARTS / "agents-latency-by-caller.png"; fig.savefig(p); plt.close(fig); written.append(p.name)

    # 3. Long horizon: the same question repeated; per-task prompt tokens and wall time, two panels, one axis each.
    lh = [t for t in tasks if t["caller"] == "long-horizon"]
    if lh:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 4.6), dpi=150, sharex=True)
        xs = range(1, len(lh) + 1)
        ax1.plot(xs, [sum(x for x in t["prompt_tokens"] if x) for t in lh], color=BLUE, linewidth=2, marker="o", ms=5, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax1.set_ylabel("prompt tokens per run"); ax1.set_ylim(bottom=0); ax1.grid(axis="x", visible=False)
        ax1.set_title("Long horizon: the golden question, run after run", loc="left", color=INK, fontsize=11)
        ax2.plot(xs, [t["wall_s"] for t in lh], color=ORANGE, linewidth=2, marker="o", ms=5, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax2.set_ylabel("wall time per run, s"); ax2.set_xlabel("run"); ax2.set_ylim(bottom=0); ax2.grid(axis="x", visible=False)
        ax2.set_xticks([x for x in xs if x == 1 or x % 5 == 0])
        fig.tight_layout(); p = CHARTS / "agents-long-horizon.png"; fig.savefig(p); plt.close(fig); written.append(p.name)
    return written


def render_doc(report: dict, chart_files: list[str]) -> None:
    if not DOC.exists():
        return
    s = report["summary"]
    lines = [f"Measured {report['run_at']} through the logging proxy; model `{report['model']}`; endpoint reasoning off.", "",
             "| Caller | Tasks (ok) | Calls per task, median / max | Prompt tokens per call, median / p95 | Prompt tokens per task, median / max | Completion tokens per task, median | Latency per call, median / p95 | Wall time per task, median |",
             "|---|---|---|---|---|---|---|---|"]
    for c, d in s.items():
        lines.append(f"| {c} | {d['tasks']} ({d['tasks_ok']}) | {d['calls_per_task']['p50']} / {d['calls_per_task']['max']} | "
                     f"{(d['prompt_tokens_per_call']['p50'] or 0):,.0f} / {(d['prompt_tokens_per_call']['p95'] or 0):,.0f} | "
                     f"{(d['prompt_tokens_per_task']['p50'] or 0):,.0f} / {d['prompt_tokens_per_task']['max']:,} | "
                     f"{(d['completion_tokens_per_task']['p50'] or 0):,.0f} | "
                     f"{(d['latency_ms_per_call']['p50'] or 0):,.0f} ms / {(d['latency_ms_per_call']['p95'] or 0):,.0f} ms | "
                     f"{(d['wall_s_per_task']['p50'] or 0):.1f} s |")
    lines += [""] + [f"![{f}](charts/{f})" for f in chart_files]
    text = DOC.read_text(encoding="utf-8")
    a = text.index("<!-- results:start -->") + len("<!-- results:start -->"); b = text.index("<!-- results:end -->")
    DOC.write_text(text[:a] + "\n" + "\n".join(lines) + "\n" + text[b:], encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agent-runs", type=int, default=3)
    ap.add_argument("--judge-runs", type=int, default=1)
    ap.add_argument("--long-horizon", type=int, default=20)
    ap.add_argument("--skip-agent", action="store_true")
    ap.add_argument("--skip-judge", action="store_true")
    ap.add_argument("--render-only", action="store_true", help="redraw charts and the doc block from results/agents-latest.json")
    args = ap.parse_args()
    import yaml

    if args.render_only:
        report = json.loads(RESULTS.read_text(encoding="utf-8"))
        report["charts"] = charts(report["tasks"], report["summary"])
        RESULTS.write_text(json.dumps(report, indent=2), encoding="utf-8")
        render_doc(report, report["charts"])
        print("re-rendered", report["charts"])
        return 0

    os.environ["NIM_BASE_URL"] = PROXY_HOST  # the in-process judge
    sys.path.insert(0, str(SRC))
    tasks: list[dict] = []

    if not args.skip_agent:
        cases = yaml.safe_load((SRC / "provenance" / "evals" / "cases.yaml").read_text(encoding="utf-8"))["cases"]
        for r in range(args.agent_runs):
            for c in cases:
                print(f"agent run {r + 1}/{args.agent_runs} {c['id']} ...", end=" ", flush=True)
                t = _task(f"{c['id']}#{r + 1}", "agent", lambda q=c["question"]: run_agent_case(q))
                tasks.append(t); print(t["calls"], "calls", "ok" if t["ok"] else "FAILED")
        golden = next(c for c in cases if c["kind"] == "golden")
        for i in range(args.long_horizon):
            print(f"long-horizon {i + 1}/{args.long_horizon} ...", end=" ", flush=True)
            t = _task(f"golden#{i + 1}", "long-horizon", lambda q=golden["question"]: run_agent_case(q))
            tasks.append(t); print(t["calls"], "calls", f"{t['wall_s']}s")

    if not args.skip_judge:
        fixtures = sorted(p for p in (SRC / "gatehouse" / "gatehouse" / "judge" / "fixtures").iterdir() if p.is_dir())
        for r in range(args.judge_runs):
            for f in fixtures:
                print(f"judge run {r + 1}/{args.judge_runs} {f.name} ...", end=" ", flush=True)
                t = _task(f"{f.name}#{r + 1}", "judge", lambda fx=f: run_judge_fixture(fx))
                tasks.append(t); print(t["calls"], "calls", "ok" if t["ok"] else "FAILED")

    summary = summarize(tasks)
    report = {"run_at": _now(), "model": "nvidia/nemotron-3.5-lightning-30b-a3b", "proxy": PROXY_HOST,
              "summary": summary, "tasks": tasks}
    written = charts(tasks, summary)
    report["charts"] = written
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2), encoding="utf-8")
    render_doc(report, written)
    print(json.dumps(summary, indent=1))
    print("charts:", written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
