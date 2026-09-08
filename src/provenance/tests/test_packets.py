"""Sign-off without a model: the citation rule, the packet store's signature and export
rules, the role claim, and the service routes with a fake writer.

Serves: BR-2, BR-7, C3. Tests: T1-HS-01 (no agent token can sign), T1-HS-02 (an
unsigned or altered packet cannot leave).
"""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from provenance.agent.writer import render_markdown, statement_check
from provenance.agent_service.server import build_app
from provenance.gateway.tokens import claims, mint
from provenance.packets import store

KEY = "k" * 40


def test_tokens_carry_a_role_and_old_tokens_read_as_agents(monkeypatch):
    monkeypatch.setenv("GATEWAY_SIGNING_KEY", KEY)
    assert claims(mint("control-mapper"))["role"] == "agent"
    assert claims(mint("jeff", role="person"))["role"] == "person"
    with pytest.raises(ValueError):
        mint("x", role="admin")


def test_statement_rule_keeps_whole_statements_and_withholds_the_unsupported():
    real = {"ev-0003", "ev-0004"}
    ok = statement_check("Logging is on and reviewed yearly. Alerts are forwarded within seconds.\nCited: 3.3.1; ev-0003, ev-0004", real)
    assert ok["withheld"] is None and ok["rows_cited"] == ["ev-0003", "ev-0004"] and "Cited:" not in ok["statement"]
    inline = statement_check("Logging is on per ev-0003.", real)
    assert inline["withheld"] is None and inline["rows_cited"] == ["ev-0003"]
    invented = statement_check("Per the Event Logging Policy (ev-20240115-001) and ev-0003.", real)
    assert invented["withheld"].startswith("cites rows that do not exist") and invented["invented"] == ["ev-20240115-001"]
    uncited = statement_check("Everything is fine and reviewed annually.", real)
    assert uncited["withheld"] == "cites none of the evidence held for this control"
    none = statement_check("No evidence is held for control 3.1.2 on system sys-windrow-prod.", set())
    assert none["withheld"] is None and none["rows_cited"] == []
    prose = statement_check("I have read the requirement and will now draft.", set())
    assert prose["withheld"] is not None


@pytest.fixture
def packets(tmp_path, monkeypatch):
    monkeypatch.setenv("PACKETS_URL", (tmp_path / "packets").as_uri())
    monkeypatch.setenv("GATEWAY_SIGNING_KEY", KEY)
    packet = {"system_id": "sys-windrow-prod", "generated_at": "2026-09-08T00:00:00+00:00", "writer": "report-writer",
              "withheld_statements": 0, "invented_citations": 0, "failed_controls": 0,
              "controls": [{"control_id": "3.3.1", "statement": "Logging is on per ev-0004.", "withheld": None, "invented": [],
                            "rows_cited": ["ev-0004"], "verdict": {"severity": "low", "score": 0, "reasons": ["fine"], "cited_rows": ["ev-0004"]}}]}
    return store.save_draft(packet, render_markdown(packet))


def test_store_signs_only_for_a_person_and_exports_only_when_signed_and_unchanged(packets):
    pid = packets["packet_id"]
    assert packets["status"] == "draft"
    with pytest.raises(PermissionError):
        store.export(pid)  # T1-HS-02: unsigned
    with pytest.raises(PermissionError):
        store.sign(pid, "control-mapper", "agent")  # T1-HS-01
    signed = store.sign(pid, "jeff", "person")
    assert signed["status"] == "signed" and signed["signature"]["signer"] == "jeff"
    packet, md = store.export(pid)
    assert packet["signature"]["packet_hash"] == store.packet_hash(packet) and "Signed by jeff" in md
    # altered after signing: the hash no longer matches, export refuses again
    tampered = dict(packet); tampered["controls"] = []
    store._write(store._path(pid, "packet.json"), json.dumps(tampered))
    with pytest.raises(PermissionError):
        store.export(pid)


def test_service_routes_enforce_the_person_rule(packets, tmp_path):
    async def fake_runner(agent, job_input, token):
        return {"answer": f"{agent} ran", "packet_id": packets["packet_id"], "withheld_statements": 0,
                "input_blocked": False, "output_blocked": False, "error": None}

    env = {"AGENT_JOB_QUOTA": "10", "AGENT_JOB_WINDOW_SECONDS": "3600", "AGENT_JOBS_LOG": str(tmp_path / "jobs.jsonl")}
    client = TestClient(build_app(fake_runner, env))
    pid = packets["packet_id"]
    agent_token = mint("control-mapper", role="agent")
    person_token = mint("jeff", role="person")
    r = client.post("/jobs", json={"agent": "report-writer", "input": {"system_id": "sys-windrow-prod"}}, headers={"X-Caller-Token": mint("eval-runner", role="caller")})
    assert r.status_code == 200 and r.json()["packet_id"] == pid
    assert client.get(f"/packets/{pid}", headers={"X-Caller-Token": agent_token}).json()["status"] == "draft"
    assert client.get(f"/packets/{pid}/export", headers={"X-Caller-Token": person_token}).status_code == 409
    assert client.post(f"/packets/{pid}/sign", headers={"X-Caller-Token": agent_token}).status_code == 403  # T1-HS-01
    assert client.post(f"/packets/{pid}/sign").status_code == 401
    signed = client.post(f"/packets/{pid}/sign", headers={"X-Caller-Token": person_token})
    assert signed.status_code == 200 and signed.json()["signature"]["signer"] == "jeff"
    exported = client.get(f"/packets/{pid}/export", headers={"X-Caller-Token": person_token})
    assert exported.status_code == 200 and "Signed by jeff" in exported.text
    records = [json.loads(l) for l in (tmp_path / "jobs.jsonl").read_text().splitlines() if l.strip()]
    assert [r.get("status") for r in records if r.get("action") == "sign"] == ["refused: only a person may sign", "signed"]
