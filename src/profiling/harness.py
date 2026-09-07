"""Profile the coding-agent harness that builds this repo, from its own session logs.

    python -m profiling.harness                 # default: this repo's session directory
    python -m profiling.harness --sessions DIR  # any Claude Code project directory

Reads every session file, computes aggregates only, writes:
  src/profiling/results/harness-latest.json   counts and statistics, no message text
  docs/analysis/charts/harness-*.png          three charts
  docs/analysis/coding-agent-harness-profile.md   the marked results block

What is measured, per assistant turn: prompt size (fresh input + cache read + cache
creation tokens, which is the whole context the model saw), output tokens, cache hit
share, tool calls by tool name, whether the turn carried visible reasoning, and the
gap since the previous record as a latency proxy. Per session: turns, human prompts,
tool results and errors, repeated reads of the same file, wall-clock span.

Nothing quoted. Tool arguments, file paths, prompts, and replies are never stored;
paths are hashed only to count re-reads. Serves: BR-9 (P7).
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
DEFAULT_SESSIONS = pathlib.Path.home() / ".claude" / "projects" / "c--Users-jeffr-Downloads-blackfork-platform"
RESULTS = HERE / "results" / "harness-latest.json"
CHARTS = REPO / "docs" / "analysis" / "charts"
DOC = REPO / "docs" / "analysis" / "coding-agent-harness-profile.md"

# Reference palette (docs: dataviz skill, light surface). One hue for magnitude.
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, BLUE_LIGHT, ORANGE = "#2a78d6", "#9ec5f4", "#eb6834"


def _ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_session(path: pathlib.Path) -> dict:
    turns: list[dict] = []
    tools = collections.Counter()
    tool_results = errors = human_prompts = 0
    reads = collections.Counter()
    prev_ts: dt.datetime | None = None
    first = last = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = _ts(d.get("timestamp"))
        if t:
            first = first or t
            last = t
        kind = d.get("type")
        if kind == "assistant":
            m = d.get("message") or {}
            u = m.get("usage") or {}
            content = m.get("content") or []
            names = [b.get("name") for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            tools.update(names)
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Read":
                    fp = (b.get("input") or {}).get("file_path")
                    if fp:
                        reads[hashlib.sha1(str(fp).encode()).hexdigest()[:10]] += 1
            fresh = int(u.get("input_tokens") or 0)
            cache_read = int(u.get("cache_read_input_tokens") or 0)
            cache_new = int(u.get("cache_creation_input_tokens") or 0)
            turns.append({
                "t": t.isoformat() if t else None,
                "prompt_tokens": fresh + cache_read + cache_new,
                "fresh_input": fresh, "cache_read": cache_read, "cache_creation": cache_new,
                "output_tokens": int(u.get("output_tokens") or 0),
                "tool_calls": len(names),
                "thinking": any(isinstance(b, dict) and b.get("type") == "thinking" for b in content),
                "gap_s": (t - prev_ts).total_seconds() if t and prev_ts else None,
            })
        elif kind == "user":
            c = (d.get("message") or {}).get("content")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        tool_results += 1
                        errors += bool(b.get("is_error"))
                if any(isinstance(b, dict) and b.get("type") == "text" for b in c) and not any(
                        isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                    human_prompts += 1
            elif isinstance(c, str) and c.strip():
                human_prompts += 1
        if t:
            prev_ts = t
    return {"file": path.name[:8], "turns": turns, "tools": dict(tools), "tool_results": tool_results,
            "tool_errors": errors, "human_prompts": human_prompts,
            "re_reads": sum(n - 1 for n in reads.values() if n > 1), "files_read": len(reads),
            "first": first.isoformat() if first else None, "last": last.isoformat() if last else None,
            "span_hours": round((last - first).total_seconds() / 3600, 2) if first and last else None}


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


def aggregate(sessions: list[dict]) -> dict:
    turns = [t for s in sessions for t in s["turns"]]
    tools = collections.Counter()
    for s in sessions:
        tools.update(s["tools"])
    out_tok = [t["output_tokens"] for t in turns]
    prompt = [t["prompt_tokens"] for t in turns]
    gaps = [t["gap_s"] for t in turns if t["gap_s"] is not None and 0 < t["gap_s"] < 600]
    cache_share = [t["cache_read"] / t["prompt_tokens"] for t in turns if t["prompt_tokens"]]
    total_tools = sum(tools.values())
    return {
        "sessions": len(sessions),
        "assistant_turns": len(turns),
        "human_prompts": sum(s["human_prompts"] for s in sessions),
        "wall_clock_hours": round(sum(s["span_hours"] or 0 for s in sessions), 1),
        "tool_calls": total_tools,
        "tool_mix": {k: {"calls": v, "share": round(v / total_tools, 3)} for k, v in tools.most_common()},
        "tool_results": sum(s["tool_results"] for s in sessions),
        "tool_errors": sum(s["tool_errors"] for s in sessions),
        "tool_error_rate": round(sum(s["tool_errors"] for s in sessions) / max(1, sum(s["tool_results"] for s in sessions)), 3),
        "files_read": sum(s["files_read"] for s in sessions),
        "re_reads": sum(s["re_reads"] for s in sessions),
        "turns_with_visible_reasoning": sum(1 for t in turns if t["thinking"]),
        "turns_with_tool_calls": sum(1 for t in turns if t["tool_calls"]),
        "prompt_tokens": {"p50": pct(prompt, .5), "p95": pct(prompt, .95), "max": max(prompt) if prompt else None,
                          "first_turn": prompt[0] if prompt else None, "last_turn": prompt[-1] if prompt else None},
        "output_tokens": {"p50": pct(out_tok, .5), "p95": pct(out_tok, .95), "max": max(out_tok) if out_tok else None,
                          "total": sum(out_tok)},
        "cache_read_share": {"p50": pct(cache_share, .5), "min": round(min(cache_share), 3) if cache_share else None},
        "turn_gap_seconds": {"p50": pct(gaps, .5), "p95": pct(gaps, .95), "note": "gap since the previous record; a latency proxy, not a measurement"},
        "total_prompt_tokens_billed_shape": {"fresh_input": sum(t["fresh_input"] for t in turns),
                                              "cache_read": sum(t["cache_read"] for t in turns),
                                              "cache_creation": sum(t["cache_creation"] for t in turns)},
    }


def charts(sessions: list[dict], agg: dict) -> list[str]:
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
    biggest = max(sessions, key=lambda s: len(s["turns"]))
    turns = biggest["turns"]

    # 1. Context size per turn across the longest session (trend over time, one series).
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=150)
    xs = list(range(1, len(turns) + 1)); ys = [t["prompt_tokens"] / 1000 for t in turns]
    ax.fill_between(xs, ys, color=BLUE_LIGHT, alpha=0.45, linewidth=0)
    ax.plot(xs, ys, color=BLUE, linewidth=2, solid_joinstyle="round", solid_capstyle="round")
    ax.plot([xs[-1]], [ys[-1]], "o", ms=8, color=BLUE, markeredgecolor=SURFACE, markeredgewidth=2)
    ax.annotate(f"{ys[-1]:.0f}k", (xs[-1], ys[-1]), textcoords="offset points", xytext=(6, -3), color=INK2, fontsize=9)
    ax.set_xlabel("assistant turn"); ax.set_ylabel("prompt size, thousand tokens")
    ax.set_title("Context the model saw, per turn, longest session", loc="left", color=INK, fontsize=11)
    ax.set_ylim(bottom=0); ax.grid(axis="x", visible=False)
    fig.tight_layout(); p = CHARTS / "harness-context-per-turn.png"; fig.savefig(p); plt.close(fig); written.append(p.name)

    # 2. Tool-call mix (magnitude by category: horizontal bars, one hue).
    mix = list(agg["tool_mix"].items())[:8]
    fig, ax = plt.subplots(figsize=(7, 3.4), dpi=150)
    names = [k for k, _ in mix][::-1]; vals = [v["calls"] for _, v in mix][::-1]
    bars = ax.barh(names, vals, color=BLUE, height=0.5)
    for b, v in zip(bars, vals):
        ax.text(b.get_width() + max(vals) * 0.01, b.get_y() + b.get_height() / 2, str(v), va="center", color=INK2, fontsize=9)
    ax.set_xlabel("tool calls"); ax.grid(axis="y", visible=False)
    ax.set_title(f"Tool calls by tool, all sessions ({agg['tool_calls']} total)", loc="left", color=INK, fontsize=11)
    fig.tight_layout(); p = CHARTS / "harness-tool-mix.png"; fig.savefig(p); plt.close(fig); written.append(p.name)

    # 3. Output tokens per turn, longest session (trend, one series; emphasis on the p95 line).
    fig, ax = plt.subplots(figsize=(9, 3.4), dpi=150)
    ys2 = [t["output_tokens"] for t in turns]
    ax.plot(xs, ys2, color=BLUE, linewidth=1.5)
    p95 = agg["output_tokens"]["p95"]
    ax.axhline(p95, color=ORANGE, linewidth=1.5)
    ax.text(xs[0], p95, f" p95 = {p95:.0f}", va="bottom", color=INK2, fontsize=9)
    ax.set_xlabel("assistant turn"); ax.set_ylabel("output tokens")
    ax.set_title("Output tokens per turn, longest session", loc="left", color=INK, fontsize=11)
    ax.set_ylim(bottom=0); ax.grid(axis="x", visible=False)
    fig.tight_layout(); p = CHARTS / "harness-output-per-turn.png"; fig.savefig(p); plt.close(fig); written.append(p.name)
    return written


def render_doc(agg: dict, chart_files: list[str], sessions: list[dict]) -> None:
    if not DOC.exists():
        return
    m = agg["tool_mix"]
    lines = [f"Measured {agg['run_at']} over {agg['sessions']} session file(s): {agg['assistant_turns']} assistant turns, "
             f"{agg['human_prompts']} human prompts, {agg['wall_clock_hours']} wall-clock hours.", "",
             "| Measure | Value |", "|---|---|",
             f"| Prompt size per turn, median / p95 / max | {agg['prompt_tokens']['p50']:,.0f} / {agg['prompt_tokens']['p95']:,.0f} / {agg['prompt_tokens']['max']:,} tokens |",
             f"| Prompt size, first turn → last turn of the longest session | {agg['prompt_tokens']['first_turn']:,} → {agg['prompt_tokens']['last_turn']:,} tokens |",
             f"| Output tokens per turn, median / p95 / max | {agg['output_tokens']['p50']:,.0f} / {agg['output_tokens']['p95']:,.0f} / {agg['output_tokens']['max']:,} |",
             f"| Output tokens, total | {agg['output_tokens']['total']:,} |",
             f"| Share of each prompt served from cache, median | {agg['cache_read_share']['p50']:.0%} |",
             f"| Tool calls | {agg['tool_calls']} across {len(m)} tools; {agg['turns_with_tool_calls']} of {agg['assistant_turns']} turns call a tool |",
             f"| Tool errors | {agg['tool_errors']} of {agg['tool_results']} results ({agg['tool_error_rate']:.1%}) |",
             f"| Files read, and repeat reads of the same file | {agg['files_read']} files; {agg['re_reads']} repeat reads |",
             f"| Turns with visible reasoning | {agg['turns_with_visible_reasoning']} of {agg['assistant_turns']} |",
             f"| Gap between records, median / p95 | {agg['turn_gap_seconds']['p50']} s / {agg['turn_gap_seconds']['p95']} s (a latency proxy) |",
             "", "| Tool | Calls | Share |", "|---|---|---|"]
    for k, v in m.items():
        lines.append(f"| {k} | {v['calls']} | {v['share']:.0%} |")
    lines += [""] + [f"![{f}](charts/{f})" for f in chart_files]
    block = "\n".join(lines)
    text = DOC.read_text(encoding="utf-8")
    a = text.index("<!-- results:start -->") + len("<!-- results:start -->"); b = text.index("<!-- results:end -->")
    DOC.write_text(text[:a] + "\n" + block + "\n" + text[b:], encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sessions", type=pathlib.Path, default=DEFAULT_SESSIONS)
    args = ap.parse_args()
    files = sorted(args.sessions.glob("*.jsonl"))
    if not files:
        sys.exit(f"no session files under {args.sessions}")
    sessions = [parse_session(f) for f in files]
    agg = aggregate(sessions)
    agg["run_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    agg["harness"] = "Claude Code (session logs under ~/.claude/projects)"
    agg["per_session"] = [{k: v for k, v in s.items() if k != "turns"} | {"turns": len(s["turns"])} for s in sessions]
    written = charts(sessions, agg)
    agg["charts"] = written
    RESULTS.parent.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(agg, indent=2), encoding="utf-8")
    render_doc(agg, written, sessions)
    print(json.dumps({k: agg[k] for k in ("assistant_turns", "human_prompts", "tool_calls", "tool_error_rate", "prompt_tokens", "output_tokens", "cache_read_share")}, indent=1))
    print("charts:", written, "->", CHARTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
