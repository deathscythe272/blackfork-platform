"""Build the evidence bundle the judge scores, from GitHub or from a local fixture.

A fixture directory holds:
  pr.md        first line is the title, the rest is the body
  diff.patch   unified diff of the change
  files/       post-change content of changed files (same relative paths)
  expected.json (optional) which rubric items a planted flaw should fail

Serves: BR-3, BR-9.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
from typing import Any

import httpx

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
MAX_FILE_CHARS = 12_000
MAX_PATCH_CHARS = 12_000


def _diagram_rules() -> str:
    p = REPO_ROOT / "docs" / "DOCS-STANDARD.md"
    if not p.exists():
        return ""
    t = p.read_text(encoding="utf-8")
    m = re.search(r"## Diagram rules\n(.*?)\n## ", t, re.S)
    return m.group(1).strip() if m else ""


def _threat_boundaries() -> str:
    p = REPO_ROOT / "docs" / "02-architecture" / "agent-threat-model.md"
    if not p.exists():
        return ""
    t = p.read_text(encoding="utf-8")
    m = re.search(r"## How it works\n(.*?)\n## ", t, re.S)
    return m.group(1).strip() if m else ""


def _context() -> dict[str, str]:
    return {"diagram_rules": _diagram_rules(), "threat_model_boundaries": _threat_boundaries()}


SECRET_PATTERNS = [
    ("nvidia api key", re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("password assignment", re.compile(r"(?i)\b(password|passwd|secret)\s*[:=]\s*['\"]?[^\s'\"$]{8,}")),
]
PLACEHOLDER = re.compile(r"\.\.\.|\$\{|<[^>]+>|your[-_ ]?key|example|placeholder|paste", re.I)
# Test data by design: planted flaws live here on purpose and must never count as findings.
TOOL_DECORATOR = re.compile(r"^\s*@mcp\.tool\b")  # the decorator itself, not prose that names it
TEST_DATA = re.compile(r"(^|/)(fixtures|tests|test|testdata|evals)/|\.patch$|\.diff$")


def is_test_data(path: str) -> bool:
    return bool(TEST_DATA.search(path))


def signals(changed: list[dict[str, Any]], body: str) -> dict[str, Any]:
    """Facts a parser can establish about the change. Computed, not judged.

    The judge receives these as evidence so the probabilistic part reasons over
    exact facts instead of re-deriving them from a long diff.
    """
    paths = [f["path"] for f in changed]
    test_data_files = [p for p in paths if is_test_data(p)]
    added_lines: list[tuple[str, int, str]] = []
    for f in changed:
        if is_test_data(f["path"]):
            continue  # planted flaws in fixtures are the test, not the finding
        new_ln = 0
        for line in (f.get("patch") or "").splitlines():
            if line.startswith("@@"):
                m = re.search(r"\+(\d+)", line)
                new_ln = int(m.group(1)) - 1 if m else 0
                continue
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                new_ln += 1
                added_lines.append((f["path"], new_ln, line[1:]))
            elif not line.startswith("-"):
                new_ln += 1
    tools_added = [{"file": p, "line": n, "text": t.strip()} for p, n, t in added_lines if TOOL_DECORATOR.match(t)]
    boundary = []
    for p, n, t in added_lines:
        kinds = []
        if re.search(r"https?://", t) and not PLACEHOLDER.search(t):
            kinds.append("url")
        if re.search(r"\b[A-Z][A-Z0-9_]*_(URL|ENDPOINT|HOST|KEY|TOKEN|SECRET|PASSWORD)\b", t):
            kinds.append("credential-or-endpoint env var")
        if p.endswith(("docker-compose.yml", "compose.yml", "compose.yaml")) and re.match(r"^  [a-z0-9][a-z0-9_-]*:\s*$", t):
            kinds.append("compose service")
        if re.search(r"\b(httpx|requests|aiohttp|urllib)\.(post|get|put|request|urlopen)\(", t):
            kinds.append("outbound call")
        if TOOL_DECORATOR.match(t):
            kinds.append("tool")
        if kinds:
            boundary.append({"file": p, "line": n, "kinds": kinds, "excerpt": t.strip()[:80]})
    identifiers = []
    for p, n, t in added_lines:
        if PLACEHOLDER.search(t):
            continue
        for label, rx in (("url", re.compile(r"https?://[^\s\"']+")),
                          ("ipv4", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")),
                          ("project-id-like", re.compile(r"\b[a-z][a-z0-9]+-(?:dev|prod|demo|staging|test)\b")),
                          ("hostname-like", re.compile(r"\b[a-z0-9-]+\.(?:internal|local|corp|lan)\b"))):
            if rx.search(t):
                identifiers.append({"file": p, "line": n, "kind": label, "excerpt": t.strip()[:80]})
    secrets = []
    for p, n, t in added_lines:
        if PLACEHOLDER.search(t):
            continue
        for label, rx in SECRET_PATTERNS:
            if rx.search(t):
                secrets.append({"file": p, "line": n, "kind": label, "excerpt": t.strip()[:80]})
    docs_changed = [p for p in paths if p.startswith("docs/") and p.endswith(".md")]
    template_docs = [p for p in docs_changed if re.search(r"^\*\*You are here:\*\*", (REPO_ROOT / p).read_text(encoding="utf-8"), re.M)] \
        if all((REPO_ROOT / p).exists() for p in docs_changed) else docs_changed
    return {
        "changed_paths": paths,
        "test_data_files_excluded_from_signals": test_data_files,
        "docs_pages_changed": docs_changed,
        "template_docs_changed": template_docs,
        "threat_model_changed": "docs/02-architecture/agent-threat-model.md" in paths,
        "policy_files_changed": [p for p in paths if p.endswith(".rego")],
        "eval_files_changed": [p for p in paths if "/evals/" in p or p.endswith("cases.yaml")],
        "agent_or_tool_code_changed": [p for p in paths if p.endswith(".py") and ("mcp" in p or "gateway" in p or "agent" in p)],
        "mcp_tools_added": tools_added,
        "boundary_signals": boundary,
        "identifier_candidates": identifiers,
        "secret_pattern_hits": secrets,
        "body_cites_requirement": bool(re.search(r"Serves:\s*(BR-\d|C\d)", body)),
        "body_requirement_ids": re.findall(r"\b(BR-\d|C\d)\b", body),
    }


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + f"\n... [truncated {len(s) - n} chars]"


def _wants_full(path: str) -> bool:
    return path.endswith(".md") and path.startswith("docs/") and not is_test_data(path)


def _redact_test_data(changed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Test-data files stay in the changed list but their contents never reach the model."""
    out = []
    for f in changed:
        if is_test_data(f["path"]):
            out.append({**f, "patch": "(test data by design: contents withheld from the judge)"})
        else:
            out.append(f)
    return out


def _diagram_facts(full: dict[str, str]) -> list[dict[str, Any]]:
    """Node lists and walkthrough counts for changed template pages (for R2)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("lane1_rules", REPO_ROOT / "scripts" / "lane1_rules.py")
    rules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules)
    facts = []
    for path, text in full.items():
        if "You are here:" not in text:
            continue
        facts.append({"path": path,
                      "diagrams": [{"direction": d["direction"], "node_count": d["node_count"], "nodes": d["nodes"]}
                                   for d in rules.diagrams(text)],
                      "walkthrough_entries": rules.walkthrough_entries(text),
                      "lane1_failures": rules.diagram_rules(text, path)})
    return facts


# ---- local fixture -----------------------------------------------------------------

def from_fixture(fixture_dir: pathlib.Path) -> dict[str, Any]:
    pr_md = (fixture_dir / "pr.md").read_text(encoding="utf-8").splitlines()
    title, body = (pr_md[0].lstrip("# ").strip() if pr_md else ""), "\n".join(pr_md[1:]).strip()
    patch = (fixture_dir / "diff.patch").read_text(encoding="utf-8") if (fixture_dir / "diff.patch").exists() else ""
    changed = _split_patch(patch)
    full: dict[str, str] = {}
    files_dir = fixture_dir / "files"
    for f in changed:
        p = files_dir / f["path"]
        if _wants_full(f["path"]) and p.exists():
            full[f["path"]] = _clip(p.read_text(encoding="utf-8"), MAX_FILE_CHARS)
    sig = signals(changed, body)
    sig["diagram_facts"] = _diagram_facts(full)
    return {"pr": {"number": None, "title": title, "body": body, "source": f"fixture:{fixture_dir.name}"},
            "changed_files": _redact_test_data(changed), "raw_changed_files": changed,
            "full_files": full, "context": _context(), "signals": sig}


def _split_patch(patch: str) -> list[dict[str, Any]]:
    out = []
    for chunk in re.split(r"(?m)^(?=diff --git )", patch):
        if not chunk.strip():
            continue
        m = re.match(r"diff --git a/(\S+) b/(\S+)", chunk)
        if not m:
            continue
        status = "added" if "new file mode" in chunk else "removed" if "deleted file mode" in chunk else "modified"
        out.append({"path": m.group(2), "status": status, "patch": _clip(chunk, MAX_PATCH_CHARS)})
    return out


# ---- GitHub pull request ------------------------------------------------------------

def from_github(repo: str, number: int, token: str, checkout: pathlib.Path | None = None) -> dict[str, Any]:
    api = "https://api.github.com"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    with httpx.Client(headers=headers, timeout=30) as c:
        pr = c.get(f"{api}/repos/{repo}/pulls/{number}").raise_for_status().json()
        files = []
        page = 1
        while True:
            r = c.get(f"{api}/repos/{repo}/pulls/{number}/files", params={"per_page": 100, "page": page}).raise_for_status().json()
            files.extend(r)
            if len(r) < 100:
                break
            page += 1
    changed = [{"path": f["filename"], "status": f.get("status", "modified"), "patch": _clip(f.get("patch") or "", MAX_PATCH_CHARS)}
               for f in files]
    full: dict[str, str] = {}
    root = checkout or REPO_ROOT
    for f in changed:
        p = root / f["path"]
        if _wants_full(f["path"]) and p.exists():
            full[f["path"]] = _clip(p.read_text(encoding="utf-8"), MAX_FILE_CHARS)
    return {"pr": {"number": number, "title": pr.get("title", ""), "body": pr.get("body") or "", "source": f"github:{repo}#{number}",
                   "head_sha": pr.get("head", {}).get("sha")},
            "changed_files": _redact_test_data(changed), "raw_changed_files": changed, "full_files": full,
            "context": _context(),
            "signals": {**signals(changed, pr.get("body") or ""), "diagram_facts": _diagram_facts(full)}}


def from_env() -> dict[str, Any]:
    """Inside GitHub Actions: repo, PR number, and token come from the environment."""
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    number = int(os.environ.get("PR_NUMBER") or _pr_from_event())
    return from_github(repo, number, token, checkout=pathlib.Path(os.environ.get("GITHUB_WORKSPACE", str(REPO_ROOT))))


def _pr_from_event() -> int:
    event = json.loads(pathlib.Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    if "pull_request" in event:
        return int(event["pull_request"]["number"])
    if "issue" in event and event["issue"].get("pull_request"):
        return int(event["issue"]["number"])
    raise SystemExit("no pull request in event payload")
