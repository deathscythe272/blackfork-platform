"""The agent service without a model: the door, the quota, the per-job agent token,
and the record. A fake runner stands in for the agents.

Serves: BR-3, BR-7, BR-8. Tests: T1-IN-04 (quota per caller).
"""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from provenance.agent_service.server import build_app
from provenance.gateway.tokens import mint, verify

KEY = "k" * 40


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("GATEWAY_SIGNING_KEY", KEY)
    seen: list[tuple[str, dict, str]] = []

    async def fake_runner(agent, job_input, token):
        seen.append((agent, job_input, token))
        return {"answer": f"{agent} ran", "input_blocked": False, "output_blocked": False, "error": None}

    env = {"AGENT_JOB_QUOTA": "2", "AGENT_JOB_WINDOW_SECONDS": "3600", "AGENT_JOBS_LOG": str(tmp_path / "jobs.jsonl")}
    client = TestClient(build_app(fake_runner, env))
    return client, seen, tmp_path / "jobs.jsonl"


def _records(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def test_no_or_bad_caller_token_is_refused_and_recorded(service):
    client, seen, log = service
    assert client.post("/jobs", json={"agent": "evidence-collector", "input": {"question": "q"}}).status_code == 401
    assert client.post("/jobs", json={"agent": "evidence-collector", "input": {"question": "q"}},
                       headers={"X-Caller-Token": "not.a.token"}).status_code == 401
    assert seen == [] and [r["status"] for r in _records(log)] == ["refused: no valid caller token"] * 2


def test_job_runs_with_a_token_for_the_agents_own_identity(service):
    client, seen, log = service
    r = client.post("/jobs", json={"agent": "control-mapper", "input": {"system_id": "sys-windrow-prod", "control_id": "3.3.1"}},
                    headers={"X-Caller-Token": mint("eval-runner")})
    assert r.status_code == 200 and r.json()["answer"] == "control-mapper ran" and r.json()["caller"] == "eval-runner"
    agent, job_input, token = seen[0]
    assert agent == "control-mapper" and verify(token) == "control-mapper"  # not the caller's token
    rec = _records(log)[0]
    assert rec["caller"] == "eval-runner" and rec["agent"] == "control-mapper" and rec["status"] == "ok" and "input_sha256" in rec
    assert "question" not in json.dumps(rec) and "3.3.1" not in json.dumps(rec)  # the record holds a hash, not the input


def test_quota_per_caller_refuses_the_third_job_and_not_another_caller(service):
    client, seen, log = service
    body = {"agent": "evidence-collector", "input": {"question": "q"}}
    codes = [client.post("/jobs", json=body, headers={"X-Caller-Token": mint("eval-runner")}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert client.post("/jobs", json=body, headers={"X-Caller-Token": mint("someone-else")}).status_code == 200
    assert [r["status"] for r in _records(log)] == ["ok", "ok", "refused: quota", "ok"]


def test_bad_agent_or_input_is_refused_before_any_run(service):
    client, seen, log = service
    h = {"X-Caller-Token": mint("eval-runner")}
    assert client.post("/jobs", json={"agent": "report-writer", "input": {"question": "q"}}, headers=h).status_code == 400
    assert client.post("/jobs", json={"agent": "control-mapper", "input": {"question": "q"}}, headers=h).status_code == 400
    assert seen == []
