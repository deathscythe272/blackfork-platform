"""Where the gateway's audit rows go. One row per call, written before the call is
forwarded, and a failed write fails the call (ADR-001).

Two sinks, chosen by AUDIT_SINK:

  file    (default)  append-only JSONL at AUDIT_LOG, flushed and fsynced per row.
                     The laptop slice and the Compose stack use this.
  pubsub             publish each row to the platform-events topic named by
                     AUDIT_TOPIC, and wait for the broker's acknowledgement. The
                     deployed slice uses this; the assurance plane's subscription
                     reads it. Nothing on the instance's disk is trusted.

Both sinks are synchronous on purpose: the row is durable before the data moves.

Serves: BR-7, BR-8.
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
from typing import Any, Protocol


class AuditWriteError(Exception):
    """The row could not be made durable. The caller fails closed."""


class AuditSink(Protocol):
    name: str

    def write(self, row: dict[str, Any]) -> None: ...


def _encode(row: dict[str, Any]) -> str:
    return json.dumps(row, separators=(",", ":"), sort_keys=True)


class FileSink:
    name = "file"

    def __init__(self, path: pathlib.Path):
        self.path = path
        self._lock = threading.Lock()

    def write(self, row: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self.path.open("a", encoding="utf-8") as f:
                f.write(_encode(row) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            raise AuditWriteError(e.__class__.__name__) from e


class PubSubSink:
    name = "pubsub"

    def __init__(self, topic: str, client: Any | None = None, timeout: float = 10.0):
        """`topic` is the full name, projects/<id>/topics/<name>. `client` is a
        PublisherClient or anything with publish(topic, data, **attrs) -> future."""
        self.topic = topic
        self.timeout = timeout
        if client is None:
            from google.cloud import pubsub_v1  # imported here so the file sink needs no cloud library

            client = pubsub_v1.PublisherClient()
        self._client = client

    def write(self, row: dict[str, Any]) -> None:
        attrs = {"kind": "gateway-audit", "decision": str(row.get("decision")), "tool": str(row.get("tool"))}
        try:
            future = self._client.publish(self.topic, _encode(row).encode("utf-8"), **attrs)
            future.result(timeout=self.timeout)  # the broker has it, or we do not proceed
        except Exception as e:  # any failure here is a failed audit, whatever the client raised
            raise AuditWriteError(e.__class__.__name__) from e


def sink_from_env(env: dict[str, str] | None = None) -> AuditSink:
    env = os.environ if env is None else env
    kind = env.get("AUDIT_SINK", "file").lower()
    if kind == "file":
        return FileSink(pathlib.Path(env.get("AUDIT_LOG", "audit/audit.jsonl")))
    if kind == "pubsub":
        topic = env.get("AUDIT_TOPIC")
        if not topic:
            raise ValueError("AUDIT_SINK=pubsub needs AUDIT_TOPIC (projects/<id>/topics/<name>)")
        return PubSubSink(topic)
    raise ValueError(f"unknown AUDIT_SINK {kind!r}; use file or pubsub")
