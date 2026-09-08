"""Gatehouse Lane 1 rules: exact checks, standard library only, importable by the
CI scripts beside this file and by the judge's scorer.

Two rule families live here because the first precision pass showed the judge never
catches them while a script always does (docs/analysis/judge-precision.md):

  diagram_rules(text)   the mechanical half of the docs standard's diagram rules
  citation(body)        the pull-request body cites an existing requirement

Serves: BR-4, BR-9. ADR-005: a judgment check that turns out to be a rule moves lanes.
"""

from __future__ import annotations

import re

REQUIREMENT_IDS = {f"BR-{i}" for i in range(1, 10)} | {f"C{i}" for i in range(1, 6)}
DIAGRAM_EXEMPT = ("docs/02-architecture/end-state.md",)
MAX_NODES = 7

_FENCE = re.compile(r"```mermaid\n(.*?)```", re.S)
_NODE = re.compile(r'(?<![\w])([A-Za-z_][\w]*)\s*(\[|\(|\{|\[\[|\(\(|>)\s*"?([^\]\)\}"\n]*)"?', re.M)
_EDGE_TOKENS = re.compile(r"-->|-.->|==>|--|-\.|:::|\|")


def diagrams(text: str) -> list[dict]:
    """Every mermaid fence in a markdown text, with the facts the rules need."""
    out = []
    for fence in _FENCE.findall(text):
        first = fence.strip().splitlines()[0].strip() if fence.strip() else ""
        kind = "sequence" if first.startswith("sequenceDiagram") else "flowchart" if first.startswith("flowchart") else "other"
        direction = first.split()[1] if kind == "flowchart" and len(first.split()) > 1 else None
        nodes: dict[str, str] = {}
        if kind == "flowchart":
            for line in fence.splitlines()[1:]:
                if line.strip().startswith(("classDef", "class ", "subgraph", "end", "%%", "direction", "style", "linkStyle")):
                    continue
                for m in re.finditer(r'\b([A-Z][A-Z0-9_]*)\s*\["([^"]*)"\]', line):
                    nodes.setdefault(m.group(1), m.group(2))
                for m in re.finditer(r'\b([A-Z][A-Z0-9_]*)\s*\[([^\]"]+)\]', line):
                    nodes.setdefault(m.group(1), m.group(2))
        without_gloss = [n for n, label in nodes.items() if "<br>" not in label and "<i>" not in label]
        out.append({"kind": kind, "direction": direction, "node_count": len(nodes),
                    "nodes": list(nodes), "nodes_without_gloss": without_gloss})
    return out


def diagram_rules(text: str, path: str = "") -> list[str]:
    """Failures of the mechanical diagram rules for one template page. Empty = pass."""
    if any(path.replace("\\", "/").endswith(p) for p in DIAGRAM_EXEMPT):
        return []
    if "You are here:" not in text:
        return []
    ds = diagrams(text)
    fails = []
    prose = re.sub(r"```.*?```", "", text, flags=re.S)  # headings inside code samples do not count
    if re.search(r"^## The picture", prose, re.M) and not ds:
        fails.append("no mermaid diagram under '## The picture'")
    for i, d in enumerate(ds, 1):
        if d["kind"] == "flowchart" and d["direction"] != "LR":
            fails.append(f"diagram {i}: direction is {d['direction'] or 'unset'}, must be LR")
        if d["kind"] == "other":
            fails.append(f"diagram {i}: not a flowchart or sequence diagram")
        if d["node_count"] > MAX_NODES:
            fails.append(f"diagram {i}: {d['node_count']} nodes, max {MAX_NODES}")
        if d["nodes_without_gloss"]:
            fails.append(f"diagram {i}: nodes without a gloss: {', '.join(d['nodes_without_gloss'])}")
    return fails


def walkthrough_entries(text: str) -> int:
    m = re.search(r"^## How it works\n(.*?)(?=^## )", text, re.S | re.M)
    if not m:
        return 0
    return len(re.findall(r"^\s*\d+\.\s", m.group(1), re.M))


def walkthrough_rule(text: str, path: str = "") -> list[str]:
    """For a template page with exactly one flowchart, the numbered walkthrough must
    have one entry per box. Multi-part pages legitimately fold boxes into steps and
    stay with the judge (R2). Empty = pass."""
    if any(path.replace("\\", "/").endswith(p) for p in DIAGRAM_EXEMPT):
        return []
    if "You are here:" not in text:
        return []
    flows = [d for d in diagrams(text) if d["kind"] == "flowchart"]
    if len(flows) != 1:
        return []
    n, w = flows[0]["node_count"], walkthrough_entries(text)
    if n and w != n:
        return [f"walkthrough has {w} numbered entries for a {n}-box diagram (one entry per box)"]
    return []


THREAT_MODEL = "docs/02-architecture/agent-threat-model.md"
TOOL_DECORATOR = re.compile(r"^\s*@mcp\.tool\b")  # the decorator itself, not prose that names it
_TEST_DATA = re.compile(r"(^|/)(fixtures|tests|test|testdata|evals)/|\.patch$|\.diff$")
_PLACEHOLDER = re.compile(r"\.\.\.|\$\{|<[^>]+>|your[-_ ]?key|example|placeholder|paste", re.I)


def is_test_data(path: str) -> bool:
    return bool(_TEST_DATA.search(path))


_URL = re.compile(r"https?://[^\s\"')]+")
_ENV_VAR = re.compile(r"\b[A-Z][A-Z0-9_]*_(?:URL|ENDPOINT|HOST|KEY|TOKEN|SECRET|PASSWORD)\b")
_COMPOSE_SERVICE = re.compile(r"^  ([a-z0-9][a-z0-9_-]*):\s*$")
_OUTBOUND = re.compile(r"\b(?:httpx|requests|aiohttp|urllib)\.(?:post|get|put|request|urlopen)\(")


def boundary_signals(path: str, line: str) -> list[tuple[str, str]]:
    """(kind, token) for each trust-boundary signal on one added line. The token is the
    URL, variable name, service name, call, or decorator that carries the signal, so a
    line that only moves or reformats an existing token can be told from a new one."""
    out = []
    if not _PLACEHOLDER.search(line):
        out += [("url", m.group(0)) for m in _URL.finditer(line)]
    out += [("credential-or-endpoint env var", m.group(0)) for m in _ENV_VAR.finditer(line)]
    if path.endswith(("docker-compose.yml", "compose.yml", "compose.yaml")):
        m = _COMPOSE_SERVICE.match(line)
        if m:
            out.append(("compose service", m.group(1)))
    out += [("outbound call", m.group(0)) for m in _OUTBOUND.finditer(line)]
    if TOOL_DECORATOR.match(line):
        out.append(("tool", "@mcp.tool"))
    return out


def boundary_kinds(path: str, line: str) -> list[str]:
    """What kind of trust-boundary change one added line represents, if any."""
    kinds = []
    for kind, _ in boundary_signals(path, line):
        if kind not in kinds:
            kinds.append(kind)
    return kinds


def tool_rule(paths: list[str], added: list[tuple[str, int, str]]) -> list[str]:
    """R6, lane 1: a new agent tool ships with a policy grant and an eval case in the same change."""
    tools = [(p, n) for p, n, t in added if TOOL_DECORATOR.match(t) and not is_test_data(p)]
    if not tools:
        return []
    fails = []
    if not any(p.endswith(".rego") for p in paths):
        fails.append("new tool(s) at " + ", ".join(f"{p}:{n}" for p, n in tools) + " with no Rego policy change in this pull request")
    if not any(("/evals/" in p or p.endswith("cases.yaml")) and not p.endswith((".patch", ".diff")) for p in paths):
        fails.append("new tool(s) at " + ", ".join(f"{p}:{n}" for p, n in tools) + " with no eval case change in this pull request")
    return fails


def boundary_rule(paths: list[str], added: list[tuple[str, int, str]],
                  removed: list[tuple[str, str]] | None = None) -> list[str]:
    """R9, lane 1: a trust-boundary change comes with a threat-model change in the same pull request.

    `removed` is (path, text) for the removed lines of the same diff. A signal whose token
    (the URL, variable name, service name, call, or decorator) also appears in a removed
    line of the same file is a move or a reformat, not a new boundary, and is ignored.
    """
    gone_by_file: dict[str, str] = {}
    for p, t in removed or []:
        gone_by_file[p] = gone_by_file.get(p, "") + "\n" + t
    hits = []
    for p, n, t in added:
        if is_test_data(p):
            continue
        kinds = []
        for kind, token in boundary_signals(p, t):
            if kind == "tool" and TOOL_DECORATOR.search(gone_by_file.get(p, "")):
                continue  # a decorator that was also removed from this file: moved, not added
            if kind != "tool" and token in gone_by_file.get(p, ""):
                continue  # the same URL, variable, service, or call was removed: moved, not added
            if kind not in kinds:
                kinds.append(kind)
        if p.endswith(".md"):
            continue  # a docs page describes boundaries; only code and config introduce them
        if kinds:
            hits.append((p, n, kinds))
    if not hits:
        return []
    if THREAT_MODEL in paths:
        return []
    where = "; ".join(f"{p}:{n} ({', '.join(k)})" for p, n, k in hits[:6])
    return [f"trust-boundary change with no change to {THREAT_MODEL} in this pull request: {where}"]


def removed_lines_from_patch(path: str, patch: str) -> list[tuple[str, str]]:
    """(path, text) for every removed line in a unified diff of one file."""
    return [(path, line[1:]) for line in patch.splitlines()
            if line.startswith("-") and not line.startswith("---")]


def added_lines_from_patch(path: str, patch: str) -> list[tuple[str, int, str]]:
    """(path, new line number, text) for every added line in a unified diff of one file."""
    out = []
    new_ln = 0
    for line in patch.splitlines():
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            new_ln = int(m.group(1)) - 1 if m else 0
            continue
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            new_ln += 1
            out.append((path, new_ln, line[1:]))
        elif not line.startswith("-"):
            new_ln += 1
    return out


def citation(body: str) -> tuple[bool, str]:
    """Does a pull-request body cite an existing requirement or constraint?"""
    m = re.search(r"Serves:\s*((?:BR-\d+|C\d+)(?:\s*,\s*(?:BR-\d+|C\d+))*)", body or "")
    if not m:
        return False, "no 'Serves: BR-n' (or C-n) line in the pull-request body"
    ids = [i.strip() for i in m.group(1).split(",")]
    unknown = sorted(i for i in ids if i not in REQUIREMENT_IDS)
    if unknown:
        return False, f"cites unknown ids: {', '.join(unknown)}"
    return True, "cites " + ", ".join(ids)
