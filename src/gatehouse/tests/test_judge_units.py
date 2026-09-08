"""Unit tests for the judge's deterministic parts. No model, no network.

Run: pytest src/gatehouse/tests -q
"""

from __future__ import annotations

import pathlib

import yaml

from gatehouse.judge import gather, post, prompt

RUBRIC = (pathlib.Path(__file__).resolve().parents[1] / "gatehouse" / "judge" / "rubric.yml").read_text(encoding="utf-8")
FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "gatehouse" / "judge" / "fixtures"


def test_parse_verdict_normalizes_and_ids_findings():
    raw = """```json
    {"rubric_version": "1",
     "items": [{"id": "R5", "verdict": "fail", "note": "key on line 63"}, {"id": "R9", "verdict": "fail"}],
     "findings": [{"item": "R5", "severity": "high", "file": "docker-compose.yml", "line": "63", "why": "nvapi- literal", "fix": "use ${NVIDIA_API_KEY}"},
                  {"item": "R9", "severity": "high", "file": "x", "line": 1, "why": "bogus item", "fix": ""}]}
    ```"""
    v = prompt.parse_verdict(raw, RUBRIC)
    assert v["parse_ok"]
    ids = {i["id"]: i["verdict"] for i in v["items"]}
    assert ids["R5"] == "fail" and ids["R1"] == "not_applicable" and "R9" not in ids
    assert len(v["findings"]) == 1
    f = v["findings"][0]
    assert f["id"].startswith("R5-") and f["line"] == 63
    assert f["id"] == prompt.finding_id("R5", "docker-compose.yml", 63)


def test_parse_verdict_survives_garbage():
    v = prompt.parse_verdict("the model said nothing useful", RUBRIC)
    assert not v["parse_ok"] and v["findings"] == []
    assert all(i["verdict"] == "not_applicable" for i in v["items"])


def test_signals_detect_tools_and_secrets():
    b = gather.from_fixture(FIXTURES / "new-tool-no-grant")
    s = b["signals"]
    assert [t["file"] for t in s["mcp_tools_added"]] == ["src/provenance/evidence_mcp/server.py", "src/provenance/gateway/server.py"]
    assert s["threat_model_changed"] is False and s["policy_files_changed"] == [] and s["eval_files_changed"] == []
    b2 = gather.from_fixture(FIXTURES / "secret-in-compose")
    hits = b2["signals"]["secret_pattern_hits"]
    assert hits and hits[0]["file"] == "docker-compose.yml" and hits[0]["line"] == 63 and hits[0]["kind"] == "nvidia api key"
    b3 = gather.from_fixture(FIXTURES / "clean-docs-gloss")
    assert b3["signals"]["secret_pattern_hits"] == [] and b3["signals"]["mcp_tools_added"] == []


def test_signals_ignore_test_data_files():
    nested = "diff --git a/x/server.py b/x/server.py\n@@ -1,1 +1,2 @@\n line\n+@mcp.tool()\n+NVIDIA_API_KEY: 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\n"
    changed = [{"path": "src/gatehouse/gatehouse/judge/fixtures/planted/diff.patch", "status": "added",
                "patch": "diff --git a/f b/f\n@@ -0,0 +1,5 @@\n" + "".join("+" + l + "\n" for l in nested.splitlines())}]
    s = gather.signals(changed, "Serves: BR-9")
    assert s["mcp_tools_added"] == [] and s["secret_pattern_hits"] == []
    assert s["test_data_files_excluded_from_signals"] == ["src/gatehouse/gatehouse/judge/fixtures/planted/diff.patch"]
    assert gather.is_test_data("src/provenance/evals/cases.yaml") and not gather.is_test_data("src/provenance/gateway/server.py")


def test_signals_ignore_placeholders():
    changed = [{"path": "docs/x.md", "status": "modified", "patch": "diff --git a/docs/x.md b/docs/x.md\n@@ -1,1 +1,2 @@\n line\n+set NVIDIA_API_KEY to nvapi-paste-your-key-here-xxxxxxxxxxxxxxxxxxxx\n"}]
    assert gather.signals(changed, "Serves: BR-4")["secret_pattern_hits"] == []


def test_reconcile_marks_fixed_and_dismissed():
    verdict = {"rubric_version": "1", "items": [], "findings": [
        {"id": "R5-aaaaaa", "item": "R5", "severity": "high", "file": "a", "line": 1, "why": "w", "fix": "f"},
        {"id": "R6-bbbbbb", "item": "R6", "severity": "high", "file": "b", "line": 2, "why": "w", "fix": "f"},
    ]}
    prev = {"R1-cccccc": {"id": "R1-cccccc", "item": "R1", "severity": "low", "file": "c", "line": 3, "why": "w", "fix": "f"}}
    dismissed = {"R6-bbbbbb": {"by": "jeff", "reason": "eval case lives in the next PR"}}
    rows = {r["id"]: r for r in post.reconcile(verdict, prev, dismissed)}
    assert rows["R5-aaaaaa"]["status"] == "open"
    assert rows["R6-bbbbbb"]["status"] == "dismissed" and rows["R6-bbbbbb"]["dismissal"]["by"] == "jeff"
    assert rows["R1-cccccc"]["status"] == "fixed"


def test_dismiss_command_parsing_ignores_judge_comment():
    comments = [
        {"body": f"{post.MARKER}\n### Gatehouse judge\n| `R5-aaaaaa` | open |", "user": {"login": "github-actions[bot]"}},
        {"body": "/gatehouse dismiss R5-aaaaaa reason: synthetic value in a fixture", "user": {"login": "jeff"}},
        {"body": "looks good otherwise", "user": {"login": "jeremy"}},
    ]
    d = post.dismissals(comments)
    assert d == {"R5-aaaaaa": {"by": "jeff", "reason": "synthetic value in a fixture"}}


def test_render_roundtrips_state_and_conclusion():
    rubric = yaml.safe_load(RUBRIC)
    verdict = {"rubric_version": "1",
               "items": [{"id": i["id"], "verdict": "pass", "note": "ok"} for i in rubric["items"]],
               "findings": [{"id": "R5-aaaaaa", "item": "R5", "severity": "high", "file": "a", "line": 1, "why": "w", "fix": "f"}]}
    rows = post.reconcile(verdict, {}, {})
    body = post.render(verdict, rows, rubric, 1)
    assert post.MARKER in body and "R5-aaaaaa" in body
    state = post.previous_state([{"body": body}])
    assert list(state) == ["R5-aaaaaa"]
    assert post.conclusion_for(rows, rubric)[0] == "neutral"  # advisory while nothing is blocking
    rubric["items"][4]["blocking"] = True  # R5
    assert post.conclusion_for(rows, rubric)[0] == "failure"


def test_lane1_verdicts_are_exact_on_fixtures():
    from gatehouse.evals.score import lane1_verdicts
    v = lane1_verdicts(gather.from_fixture(FIXTURES / "bad-diagram-nine-nodes"))
    assert v == {"R3": False, "R7": True, "R8": True, "R6": False, "R9": False, "R10": False}
    v = lane1_verdicts(gather.from_fixture(FIXTURES / "no-citation"))
    assert v == {"R3": True, "R7": False, "R8": False, "R6": False, "R9": False, "R10": False}
    v = lane1_verdicts(gather.from_fixture(FIXTURES / "clean-docs-gloss"))
    assert v == {"R3": False, "R7": False, "R8": False, "R6": False, "R9": False, "R10": False}


def test_tool_and_boundary_rules_ignore_the_body():
    """v1.4: R6 and R9 are scripts, so the pull-request text cannot exempt them."""
    from gatehouse.evals.score import lane1_verdicts
    for name in ("new-tool-no-grant", "inject-tool-no-grant", "inject-title-and-body"):
        v = lane1_verdicts(gather.from_fixture(FIXTURES / name))
        assert v["R6"] and v["R9"], name
    for name in ("new-network-path-no-threat-model", "inject-network-path-claims-tm"):
        v = lane1_verdicts(gather.from_fixture(FIXTURES / name))
        assert v["R9"] and not v["R6"], name
    for name in ("clean-code-typo", "clean-mixed", "inject-clean-docs-body", "inject-docs-hidden-comment"):
        v = lane1_verdicts(gather.from_fixture(FIXTURES / name))
        assert not v["R6"] and not v["R9"], name


def test_boundary_rule_skips_docs_hyperlinks_and_test_data():
    import importlib.util
    spec = importlib.util.spec_from_file_location("lane1_rules", gather.REPO_ROOT / "scripts" / "lane1_rules.py")
    rules = importlib.util.module_from_spec(spec); spec.loader.exec_module(rules)
    link = [("docs/01-business-case.md", 3, "See https://www.nist.gov/ for the catalog.")]
    assert rules.boundary_rule(["docs/01-business-case.md"], link) == []
    prose = [("docs/analysis/judge-precision.md", 9, "The diff adds PUBSUB_URL and a service; the judge flagged it.")]
    assert rules.boundary_rule(["docs/analysis/judge-precision.md"], prose) == []  # a page quoting a name is not a boundary
    fixture = [("src/gatehouse/gatehouse/judge/fixtures/x/server.py", 1, "@mcp.tool()")]
    assert rules.tool_rule([fixture[0][0]], fixture) == [] and rules.boundary_rule([fixture[0][0]], fixture) == []
    real = [("src/provenance/evidence_mcp/server.py", 40, "@mcp.tool()")]
    assert len(rules.tool_rule([real[0][0]], real)) == 2 and len(rules.boundary_rule([real[0][0]], real)) == 1
    assert rules.boundary_rule([real[0][0], rules.THREAT_MODEL], real) == []


def test_boundary_rule_ignores_moved_or_reformatted_tokens():
    """A URL or variable that was also removed from the same file is a move, not a new boundary."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("lane1_rules", gather.REPO_ROOT / "scripts" / "lane1_rules.py")
    rules = importlib.util.module_from_spec(spec); spec.loader.exec_module(rules)
    path = "src/gatehouse/gatehouse/judge/cli.py"
    added = [(path, 45, '            .replace("__NIM_BASE_URL__", os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"))')]
    removed = [(path, '        "__NIM_BASE_URL__", os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"))')]
    assert rules.boundary_rule([path], added, removed) == []
    assert len(rules.boundary_rule([path], added, [])) == 1  # the same line with nothing removed is new
    new_url = [(path, 46, '        base = "https://other.example.net/v1"')]
    assert len(rules.boundary_rule([path], new_url, removed)) == 0  # placeholder word "example" excludes it
    new_url = [(path, 46, '        base = "https://api.othervendor.net/v1"')]
    assert len(rules.boundary_rule([path], new_url, removed)) == 1
    patch = "@@ -1,2 +1,2 @@\n-old = os.environ.get(\"NIM_BASE_URL\")\n+new = os.environ.get(\"NIM_BASE_URL\")\n"
    assert rules.removed_lines_from_patch(path, patch) == [(path, 'old = os.environ.get("NIM_BASE_URL")')]
    assert rules.added_lines_from_patch(path, patch) == [(path, 1, 'new = os.environ.get("NIM_BASE_URL")')]


def test_judge_scores_only_lane2_items():
    rubric = yaml.safe_load(RUBRIC)
    ids = [i["id"] for i in prompt.judged_items(rubric)]
    assert ids == ["R1", "R5"]  # v1.4: R6 and R9 are scripts, R2 and R4 are human review
    v = prompt.parse_verdict('{"rubric_version":"1.1","items":[{"id":"R7","verdict":"fail"}],"findings":[{"item":"R7","severity":"high","file":"x","line":1,"why":"w","fix":"f"}]}', RUBRIC)
    assert all(i["id"] != "R7" for i in v["items"]) and v["findings"] == []


def test_parser_gates_close_items_with_no_signal():
    b = gather.from_fixture(FIXTURES / "clean-docs-gloss")
    assert set(prompt.gated_off(b["signals"])) == {"R5"}
    raw = '{"rubric_version":"1.4","items":[{"id":"R5","verdict":"fail","note":"pile-on"}],"findings":[{"item":"R5","severity":"high","file":"docs/x.md","line":1,"why":"w","fix":"f"}]}'
    v = prompt.parse_verdict(raw, RUBRIC, b["signals"])
    r5 = next(i for i in v["items"] if i["id"] == "R5")
    assert r5["verdict"] == "not_applicable" and v["findings"] == [] and "R5" in v["gated_off"]
    b2 = gather.from_fixture(FIXTURES / "new-network-path-no-threat-model")  # a project-id-like host opens R5
    assert "R5" not in prompt.gated_off(b2["signals"])


def test_harvest_parses_a_judge_comment_and_counts_by_adr_005():
    from gatehouse.evals import harvest
    body = (
        "<!-- gatehouse-judge -->\n### Gatehouse judge · rubric v1.5 · advisory\n"
        "| Item | Verdict | Note |\n|---|---|---|\n"
        "| R1 Diagram reads as one story | pass | fine |\n"
        "| R5 No secrets or internal identifiers introduced | **fail** | hit |\n\n"
        "| ID | Status | Sev | Where | Finding | Fix |\n|---|---|---|---|---|---|\n"
        "| `R5-24e9ca` | dismissed by @jeff: references the secret by name | high | `infra/x.tf`:164 | a secret ref | none |\n"
        "| `R5-aaaaaa` | fixed | high | `src/y.py`:3 | a real key | rotate |\n"
        "| `R1-bbbbbb` | open | low | `docs/z.md` | vague | fix |\n"
    )
    parsed = harvest.parse_comment(body)
    assert parsed["rubric_version"] == "1.5"
    assert parsed["items"] == {"R1": "pass", "R5": "fail"}
    assert [(f["item"], f["status"]) for f in parsed["findings"]] == [("R5", "dismissed"), ("R5", "fixed"), ("R1", "open")]
    assert parsed["findings"][0]["reason"] == "references the secret by name"
    report = {"pull_requests": [{"pr": 25, "merged_at": "2026-09-08", "title": "t", **parsed},
                                {"pr": 9, "merged_at": "2026-09-01", "title": "old", "rubric_version": "1.1",
                                 "items": {"R1": "pass", "R5": "n/a"}, "findings": []}]}
    s = harvest.summarize(report)
    r5 = s["items"]["R5"]
    assert r5["judged"] == 1 and r5["accepted"] == 1 and r5["dismissed"] == 1 and r5["live_precision"] == 0.5
    r1 = s["items"]["R1"]
    assert r1["judged"] == 1  # the v1.1 pass predates the current wording and is not counted
    assert r1["by_version"]["1.1"]["judged"] == 1 and r1["instances_needed"] == 19
    assert [f["id"] for f in s["open_findings"]] == ["R1-bbbbbb"]
    rendered = harvest.render({"harvested_at": "now", "pull_requests": report["pull_requests"], "summary": s})
    assert "R1-bbbbbb" in rendered and "vague" not in rendered  # finding text never reaches the page


def test_rate_limits_wait_longer_than_other_faults():
    from gatehouse.register import is_rate_limit, wait_before_retry

    class Limited(Exception):
        pass

    rl = Limited("[429] Too Many Requests")
    other = TimeoutError("read timed out")
    assert is_rate_limit(rl) and not is_rate_limit(other)
    assert [wait_before_retry(a, rl) for a in range(4)] == [20.0, 40.0, 60.0, 60.0]
    assert [wait_before_retry(a, other) for a in range(3)] == [2.0, 4.0, 8.0]


def test_v15_a_reference_is_not_a_secret_and_a_literal_is():
    import importlib.util
    spec = importlib.util.spec_from_file_location("lane1_rules", gather.REPO_ROOT / "scripts" / "lane1_rules.py")
    rules = importlib.util.module_from_spec(spec); spec.loader.exec_module(rules)
    refs = [
        "            secret  = google_secret_manager_secret.risk_signing_key.secret_id",
        "            secret  = var.nvidia_api_key_secret",
        "      NVIDIA_API_KEY: ${NVIDIA_API_KEY}",
        '    key = os.environ.get("GATEWAY_SIGNING_KEY")',
        "      RISK_SIGNING_KEY: ${RISK_SIGNING_KEY}  # as the analyst's client",
        '        password: "<your-password>"',
    ]
    for line in refs:
        assert rules.literal_secret_hits("infra/x.tf", line) == [], line
    lits = [
        "      NVIDIA_API_KEY: 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",
        '      password: "hunter2hunter2"',
        "      secret = s3cr3tValue2026",
        "-----BEGIN RSA PRIVATE KEY-----",
    ]
    for line in lits:
        assert rules.literal_secret_hits("infra/x.tf", line), line
    added = [("infra/x.tf", 7, lits[1]), ("src/gatehouse/gatehouse/judge/fixtures/x/diff.patch", 1, lits[0])]
    fails = rules.secret_rule(added)
    assert len(fails) == 1 and fails[0].startswith("infra/x.tf:7")  # test data is skipped


def test_v15_public_endpoints_do_not_open_r5_and_internal_hosts_do():
    public = [{"path": "docker-compose.yml", "status": "modified", "patch": "@@ -1,0 +1,2 @@\n+      NIM_BASE_URL: https://integrate.api.nvidia.com/v1\n+      NVIDIA_API_KEY: ${NVIDIA_API_KEY}\n"}]
    sig = gather.signals(public, "Serves: BR-7")
    assert sig["identifier_candidates"] == [] and sig["secret_pattern_hits"] == []
    assert "R5" in prompt.gated_off(sig)
    internal = [{"path": "src/x.py", "status": "modified", "patch": "@@ -1,0 +1,1 @@\n+OPA_URL = \"http://opa.corp.internal:8181\"\n"}]
    sig = gather.signals(internal, "Serves: BR-7")
    assert [c["kind"] for c in sig["identifier_candidates"]] and "R5" not in prompt.gated_off(sig)


def test_v15_reference_only_fixture_is_silent_by_script():
    from gatehouse.evals.score import lane1_verdicts
    v = lane1_verdicts(gather.from_fixture(FIXTURES / "secret-reference-only"))
    assert v["R10"] is False and v["R6"] is False
    v = lane1_verdicts(gather.from_fixture(FIXTURES / "secret-in-compose"))
    assert v["R10"] is True
    b = gather.from_fixture(FIXTURES / "internal-identifier-in-config")
    assert sorted({c["kind"] for c in b["signals"]["identifier_candidates"]}) == ["hostname-like", "ipv4", "project-id-like", "url"]
    assert lane1_verdicts(b)["R10"] is False and "R5" not in prompt.gated_off(b["signals"])
