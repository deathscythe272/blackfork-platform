"""The gateway's cloud paths, tested without a cloud: the audit sinks, the upstream
identity header, and the eval runner's audit sources. Fakes stand in for the Pub/Sub
and token clients; the file paths use a temp directory.

Serves: BR-7, BR-8. Tests: T1-GW-03 (audit before forward, both sinks), T1-EV-01
(gateway identity to the evidence server, cloud form).
"""

from __future__ import annotations

import base64
import json
import time

import pytest

from provenance.evals.audit_source import FileSource, PubSubSource, source_from_env
from provenance.gateway.audit import AuditWriteError, FileSink, PubSubSink, sink_from_env
from provenance.gateway.upstream import UpstreamIdentity, identity_from_env

ROW = {"id": "abc", "ts": "2026-09-08T00:00:00.000+00:00", "tool": "get_evidence", "decision": "deny", "args": {"system_id": "sys-x"}}


class _Future:
    def __init__(self, exc=None):
        self.exc = exc

    def result(self, timeout=None):
        if self.exc:
            raise self.exc
        return "msg-1"


class _Publisher:
    def __init__(self, exc=None):
        self.exc = exc
        self.published = []

    def publish(self, topic, data, **attrs):
        self.published.append((topic, data, attrs))
        return _Future(self.exc)


def test_file_sink_appends_one_sorted_json_line_per_row(tmp_path):
    sink = FileSink(tmp_path / "nested" / "audit.jsonl")
    sink.write(ROW)
    sink.write({**ROW, "id": "def"})
    lines = (tmp_path / "nested" / "audit.jsonl").read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["id"] == "abc"
    assert lines[0] == json.dumps(ROW, separators=(",", ":"), sort_keys=True)


def test_pubsub_sink_publishes_and_waits_for_the_broker():
    pub = _Publisher()
    PubSubSink("projects/p/topics/t", client=pub).write(ROW)
    topic, data, attrs = pub.published[0]
    assert topic == "projects/p/topics/t" and json.loads(data)["id"] == "abc"
    assert attrs == {"kind": "gateway-audit", "decision": "deny", "tool": "get_evidence"}


def test_pubsub_sink_fails_closed_when_the_broker_does_not_acknowledge():
    pub = _Publisher(exc=TimeoutError("no ack"))
    with pytest.raises(AuditWriteError):
        PubSubSink("projects/p/topics/t", client=pub).write(ROW)


def test_sink_from_env_selects_and_refuses_half_configuration(tmp_path):
    assert sink_from_env({"AUDIT_LOG": str(tmp_path / "a.jsonl")}).name == "file"
    with pytest.raises(ValueError):
        sink_from_env({"AUDIT_SINK": "pubsub"})
    with pytest.raises(ValueError):
        sink_from_env({"AUDIT_SINK": "carrier-pigeon"})


def _jwt(exp: float) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"h.{payload}.s"


def test_upstream_identity_is_absent_on_the_laptop_and_cached_in_the_cloud():
    assert UpstreamIdentity(None).headers() == {}
    assert identity_from_env({}).headers() == {}
    calls = []

    def fetch(aud):
        calls.append(aud)
        return _jwt(time.time() + 3600)

    ident = UpstreamIdentity("https://evidence.example", fetcher=fetch)
    h1, h2 = ident.headers(), ident.headers()
    assert h1["Authorization"].startswith("Bearer h.") and h1 == h2
    assert calls == ["https://evidence.example"]  # one fetch, then the cache


def test_upstream_identity_refreshes_before_expiry():
    tokens = iter([_jwt(time.time() + 30), _jwt(time.time() + 3600)])
    ident = UpstreamIdentity("aud", fetcher=lambda a: next(tokens), refresh_margin=60)
    first = ident.headers()["Authorization"]
    second = ident.headers()["Authorization"]
    assert first != second  # the first token was inside the refresh margin


def test_file_source_returns_only_rows_after_the_mark(tmp_path):
    path = tmp_path / "audit.jsonl"
    FileSink(path).write(ROW)
    src = FileSource(path)
    mark = src.mark()
    FileSink(path).write({**ROW, "id": "def"})
    rows = src.rows_since(mark)
    assert [r["id"] for r in rows] == ["def"]


class _Msg:
    def __init__(self, ack_id, row):
        self.ack_id = ack_id

        class M:
            data = json.dumps(row).encode()

        self.message = M()


class _Subscriber:
    """Serves queued batches once each, then empties; records acknowledgements."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.acked = []

    def pull(self, request, timeout=None):
        class R:
            received_messages = self.batches.pop(0) if self.batches else []

        return R()

    def acknowledge(self, request):
        self.acked += request["ack_ids"]


def test_pubsub_source_drains_on_mark_then_collects_and_dedupes():
    stale = _Msg("s1", {**ROW, "id": "stale"})
    fresh = _Msg("f1", {**ROW, "id": "fresh", "ts": "2026-09-08T00:00:02.000+00:00"})
    dup = _Msg("f2", {**ROW, "id": "fresh", "ts": "2026-09-08T00:00:02.000+00:00"})
    other = _Msg("f3", {**ROW, "id": "other", "ts": "2026-09-08T00:00:01.000+00:00"})
    sub = _Subscriber([[stale], [], [fresh, dup], [other]])
    src = PubSubSource("projects/p/subscriptions/s", client=sub, quiet_seconds=0.2, max_wait=5)
    mark = src.mark()  # drains the stale batch and stops at the empty pull
    rows = src.rows_since(mark)
    assert [r["id"] for r in rows] == ["other", "fresh"]  # deduped, time-ordered
    assert sub.acked == ["s1", "f1", "f2", "f3"]


def test_source_from_env_refuses_half_configuration():
    with pytest.raises(ValueError):
        source_from_env({"AUDIT_SOURCE": "pubsub"})
