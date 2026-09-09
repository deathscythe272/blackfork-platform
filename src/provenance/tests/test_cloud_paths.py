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
    first = json.loads(lines[0])
    assert {k: v for k, v in first.items() if k not in ("hash", "prev_hash")} == ROW  # the row, plus its chain fields


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


def _stamp(offset_seconds: float) -> str:
    import datetime as dt

    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=offset_seconds)).isoformat(timespec="milliseconds")


def test_pubsub_source_drains_on_mark_then_collects_and_dedupes():
    stale = _Msg("s1", {**ROW, "id": "stale"})
    fresh = _Msg("f1", {**ROW, "id": "fresh", "ts": _stamp(2)})
    dup = _Msg("f2", {**ROW, "id": "fresh", "ts": _stamp(2)})
    other = _Msg("f3", {**ROW, "id": "other", "ts": _stamp(1)})
    sub = _Subscriber([[stale], [], [], [stale]])  # an empty pull does not mean empty
    src = PubSubSource("projects/p/subscriptions/s", client=sub, quiet_seconds=0.2, max_wait=5)
    mark = src.mark()  # drains through the empty pulls until quiet
    assert sub.batches == []
    sub.batches += [[fresh, dup], [other]]  # rows written during the case
    rows = src.rows_since(mark)
    assert [r["id"] for r in rows] == ["other", "fresh"]  # deduped, time-ordered
    assert sub.acked == ["s1", "s1", "f1", "f2", "f3"]


def test_pubsub_source_attributes_rows_by_their_own_timestamp_not_by_arrival():
    """The first nightly run: the door checks' denials, published minutes before the
    first case, arrived during it and were charged to it. The row's own timestamp
    decides; a row with no timestamp is kept."""
    late_denial = _Msg("d1", {**ROW, "id": "door-check-denial", "decision": "deny", "ts": _stamp(-120)})
    mine = _Msg("m1", {**ROW, "id": "mine", "ts": _stamp(1)})
    unstamped = _Msg("u1", {**{k: v for k, v in ROW.items() if k != "ts"}, "id": "unstamped"})
    sub = _Subscriber([])
    src = PubSubSource("projects/p/subscriptions/s", client=sub, quiet_seconds=0.2, max_wait=5)
    mark = src.mark()
    sub.batches += [[late_denial, mine, unstamped]]
    rows = src.rows_since(mark)
    assert [r["id"] for r in rows] == ["unstamped", "mine"]
    assert sub.acked == ["d1", "m1", "u1"], "the late row is acknowledged so it never comes back"


def test_source_from_env_refuses_half_configuration():
    with pytest.raises(ValueError):
        source_from_env({"AUDIT_SOURCE": "pubsub"})


def test_token_verification_tolerates_small_clock_skew(monkeypatch):
    """A token minted on a laptop a second ahead of the gateway's clock must verify;
    one minted well into the future must not."""
    import datetime as dt

    import jwt

    from provenance.gateway import tokens

    key = "k" * 40
    monkeypatch.setenv("GATEWAY_SIGNING_KEY", key)

    def minted(seconds_ahead: int) -> str:
        now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds_ahead)
        claims = {"iss": tokens.ISSUER, "aud": tokens.AUDIENCE, "sub": "evidence-collector",
                  "iat": int(now.timestamp()), "exp": int((now + dt.timedelta(hours=1)).timestamp())}
        return jwt.encode(claims, key, algorithm=tokens.ALGO)

    assert tokens.verify(minted(5)) == "evidence-collector"
    with pytest.raises(tokens.IdentityError):
        tokens.verify(minted(120))


def test_rate_limiter_is_per_identity_and_refills():
    from provenance.gateway.ratelimit import Limiter

    lim = Limiter(limit=3, window_s=30)
    t0 = 1000.0
    assert [lim.check("a", t0 + i * 0.01).allowed for i in range(4)] == [True, True, True, False]
    assert lim.check("b", t0).allowed  # another identity has its own bucket
    assert lim.check("a", t0 + 11).allowed  # one token refills every ten seconds at 3 per 30
    assert not lim.check("a", t0 + 11.01).allowed


def test_chain_links_rows_and_detects_alteration_and_removal():
    from provenance.gateway import chain

    rows, prev = [], "genesis:test:1"
    for i in range(4):
        r = chain.link({"id": f"r{i}", "decision": "allow"}, prev)
        rows.append(r)
        prev = r["hash"]
    assert chain.verify(rows)["ok"]
    altered = [dict(r) for r in rows]
    altered[2]["decision"] = "deny"
    v = chain.verify(altered)
    assert not v["ok"] and v["broken_at"] == 2 and "content" in v["reason"]
    removed = rows[:2] + rows[3:]
    v = chain.verify(removed)
    assert not v["ok"] and v["broken_at"] == 2 and "prev_hash" in v["reason"]
    segments = rows[:2] + [chain.link({"id": "s2"}, "genesis:test:2")]
    assert chain.verify(segments) == {"ok": True, "rows": 3, "segments": 2, "broken_at": None, "reason": None}


def test_file_sink_chains_and_resumes_across_restarts(tmp_path):
    from provenance.gateway import chain

    path = tmp_path / "audit.jsonl"
    FileSink(path).write(ROW)
    FileSink(path).write({**ROW, "id": "def"})  # a new process resumes from the file
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    assert rows[0]["prev_hash"].startswith("genesis:") and rows[1]["prev_hash"] == rows[0]["hash"]
    assert chain.verify(rows) == {"ok": True, "rows": 2, "segments": 1, "broken_at": None, "reason": None}


def test_pubsub_sink_chains_within_its_segment():
    from provenance.gateway import chain

    pub = _Publisher()
    sink = PubSubSink("projects/p/topics/t", client=pub)
    sink.write(ROW); sink.write({**ROW, "id": "def"})
    rows = [json.loads(data) for _, data, _ in pub.published]
    assert rows[1]["prev_hash"] == rows[0]["hash"] and chain.verify(rows)["ok"]
