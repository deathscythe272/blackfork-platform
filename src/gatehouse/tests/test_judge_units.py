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
    assert v == {"R3": False, "R7": True, "R8": True}
    v = lane1_verdicts(gather.from_fixture(FIXTURES / "no-citation"))
    assert v == {"R3": True, "R7": False, "R8": False}
    v = lane1_verdicts(gather.from_fixture(FIXTURES / "clean-docs-gloss"))
    assert v == {"R3": False, "R7": False, "R8": False}


def test_judge_scores_only_lane2_items():
    rubric = yaml.safe_load(RUBRIC)
    ids = [i["id"] for i in prompt.judged_items(rubric)]
    assert "R3" not in ids and "R7" not in ids and "R4" in ids
    v = prompt.parse_verdict('{"rubric_version":"1.1","items":[{"id":"R7","verdict":"fail"}],"findings":[{"item":"R7","severity":"high","file":"x","line":1,"why":"w","fix":"f"}]}', RUBRIC)
    assert all(i["id"] != "R7" for i in v["items"]) and v["findings"] == []


def test_parser_gates_close_items_with_no_signal():
    b = gather.from_fixture(FIXTURES / "clean-docs-gloss")
    assert set(prompt.gated_off(b["signals"])) == {"R4", "R5", "R6"}
    raw = '{"rubric_version":"1.2","items":[{"id":"R4","verdict":"fail","note":"pile-on"}],"findings":[{"item":"R4","severity":"high","file":"docs/x.md","line":1,"why":"w","fix":"f"}]}'
    v = prompt.parse_verdict(raw, RUBRIC, b["signals"])
    r4 = next(i for i in v["items"] if i["id"] == "R4")
    assert r4["verdict"] == "not_applicable" and v["findings"] == [] and "R4" in v["gated_off"]
    b2 = gather.from_fixture(FIXTURES / "new-tool-no-grant")
    assert "R4" not in prompt.gated_off(b2["signals"]) and "R6" not in prompt.gated_off(b2["signals"])
