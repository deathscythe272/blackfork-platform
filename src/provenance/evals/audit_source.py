"""Where the eval runner reads the gateway's audit rows from.

The audit rows are the containment assertion: a hostile request that reaches the door
must show as a denied row and no allowed row may name another system. The runner
needs the rows written during one case, wherever the gateway put them.

  file     (default)  the JSONL file at AUDIT_LOG; the mark is a line offset.
  pubsub              the assurance plane's subscription named by AUDIT_SUBSCRIPTION;
                      the mark drains whatever is pending, and rows_since pulls until
                      the subscription has been quiet for a moment. Delivery is
                      at-least-once, so rows are de-duplicated by id.

Serves: BR-8, BR-9.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Protocol


class AuditSource(Protocol):
    def mark(self) -> Any: ...

    def rows_since(self, mark: Any) -> list[dict]: ...


class FileSource:
    def __init__(self, path: pathlib.Path):
        self.path = path

    def _lines(self) -> list[str]:
        return self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []

    def mark(self) -> int:
        return len(self._lines())

    def rows_since(self, mark: int) -> list[dict]:
        return [json.loads(line) for line in self._lines()[mark:] if line.strip()]


class PubSubSource:
    def __init__(self, subscription: str, client: Any | None = None, quiet_seconds: float = 3.0, max_wait: float = 60.0):
        """`subscription` is projects/<id>/subscriptions/<name>. `client` is a
        SubscriberClient or anything with pull(...) and acknowledge(...)."""
        self.subscription = subscription
        self.quiet_seconds = quiet_seconds
        self.max_wait = max_wait
        if client is None:
            from google.cloud import pubsub_v1

            client = pubsub_v1.SubscriberClient()
        self._client = client

    def _pull_once(self, timeout: float) -> list[dict]:
        try:
            resp = self._client.pull(request={"subscription": self.subscription, "max_messages": 100}, timeout=timeout)
        except Exception as e:  # DeadlineExceeded and friends mean "nothing right now"
            if e.__class__.__name__ not in ("DeadlineExceeded", "RetryError"):
                raise
            return []
        msgs = list(resp.received_messages)
        if not msgs:
            return []
        self._client.acknowledge(request={"subscription": self.subscription, "ack_ids": [m.ack_id for m in msgs]})
        rows = []
        for m in msgs:
            try:
                rows.append(json.loads(m.message.data.decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                continue  # not an audit row; someone else's event on the shared topic
        return rows

    def mark(self) -> None:
        """Drain whatever is pending so the next rows_since sees only this case's rows.
        A pull can come back empty while messages remain, so the drain stops only after
        the subscription has been quiet for quiet_seconds, not at the first empty pull.
        The first cloud run learned this: rows from an earlier check leaked into case one."""
        deadline = time.time() + self.max_wait
        last_seen = time.time()
        while time.time() < deadline and time.time() - last_seen < self.quiet_seconds:
            if self._pull_once(timeout=2.0):
                last_seen = time.time()
        return None

    def rows_since(self, mark: Any) -> list[dict]:
        seen: dict[str, dict] = {}
        deadline = time.time() + self.max_wait
        last_new = time.time()
        while time.time() < deadline and time.time() - last_new < self.quiet_seconds:
            for row in self._pull_once(timeout=2.0):
                key = str(row.get("id", len(seen)))
                if key not in seen:
                    seen[key] = row
                    last_new = time.time()
        return sorted(seen.values(), key=lambda r: str(r.get("ts", "")))


def source_from_env(env: dict[str, str] | None = None) -> AuditSource:
    env = os.environ if env is None else env
    kind = env.get("AUDIT_SOURCE", "file").lower()
    if kind == "file":
        return FileSource(pathlib.Path(env.get("AUDIT_LOG", "audit/audit.jsonl")))
    if kind == "pubsub":
        sub = env.get("AUDIT_SUBSCRIPTION")
        if not sub:
            raise ValueError("AUDIT_SOURCE=pubsub needs AUDIT_SUBSCRIPTION (projects/<id>/subscriptions/<name>)")
        return PubSubSource(sub)
    raise ValueError(f"unknown AUDIT_SOURCE {kind!r}; use file or pubsub")
