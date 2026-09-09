"""Draft packets, signatures, and the export rule (ADR-007).

A packet is the Report Writer's draft for one system: a list of controls, each with
the mapper's statement, the analyst's verdict, and the rows cited. It is stored as it
was drafted, with a hash. Signing is a person's act: the signature record names the
signer, the time, and the hash of exactly what they signed. Export is refused unless a
signature exists and the hash still matches. No agent identity can sign; the service
that calls `sign` checks the caller's role first.

Where: PACKETS_URL, a folder (file://) on a laptop or a bucket path (gs://) in the
cloud, through the same file layer the lakehouse uses. Serves: BR-2, BR-7, C3.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import uuid
from typing import Any

import fsspec

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
UNSIGNED_FOOTER = "Unsigned draft. A person must sign before this packet can leave."


def signed_footer(signature: dict[str, Any]) -> str:
    return f"Signed by {signature['signer']} at {signature['at']} over hash {signature['packet_hash'][:16]}."


def packets_url() -> str:
    return (os.environ.get("PACKETS_URL") or (REPO_ROOT / "jobs" / "packets").as_uri()).rstrip("/")


def _path(packet_id: str, name: str) -> str:
    return f"{packets_url()}/{packet_id}/{name}"


def packet_hash(packet: dict[str, Any]) -> str:
    body = {k: v for k, v in packet.items() if k not in ("hash", "status", "signature")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _write(url: str, text: str) -> None:
    fs, _ = fsspec.core.url_to_fs(url)
    parent = url.rsplit("/", 1)[0]
    try:
        fs.makedirs(fs._strip_protocol(parent), exist_ok=True)
    except Exception:
        pass
    with fsspec.open(url, "w", encoding="utf-8") as f:
        f.write(text)


def _read(url: str) -> str | None:
    try:
        with fsspec.open(url, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def save_draft(packet: dict[str, Any], markdown: str) -> dict[str, Any]:
    packet_id = packet.get("packet_id") or str(uuid.uuid4())
    stored = {**packet, "packet_id": packet_id, "status": "draft"}
    stored["hash"] = packet_hash(stored)
    _write(_path(packet_id, "packet.json"), json.dumps(stored, indent=2, sort_keys=True))
    _write(_path(packet_id, "packet.md"), markdown)
    return stored


def load(packet_id: str) -> dict[str, Any] | None:
    text = _read(_path(packet_id, "packet.json"))
    return json.loads(text) if text else None


def load_markdown(packet_id: str) -> str | None:
    return _read(_path(packet_id, "packet.md"))


def sign(packet_id: str, signer: str, role: str) -> dict[str, Any]:
    """Record a person's signature over the packet as it is now. The caller has already
    verified the token; this checks the role again because it is the whole point."""
    if role != "person":
        raise PermissionError(f"only a person may sign; the caller's role is {role!r}")
    packet = load(packet_id)
    if packet is None:
        raise FileNotFoundError(packet_id)
    current = packet_hash(packet)
    signature = {"signer": signer, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "packet_hash": current}
    packet.update(status="signed", signature=signature)
    _write(_path(packet_id, "packet.json"), json.dumps(packet, indent=2, sort_keys=True))
    _write(_path(packet_id, "signature.json"), json.dumps(signature, indent=2, sort_keys=True))
    md = load_markdown(packet_id) or ""
    if UNSIGNED_FOOTER in md:  # the rendering says what the record says
        _write(_path(packet_id, "packet.md"), md.replace(UNSIGNED_FOOTER, signed_footer(signature)))
    return packet


def export(packet_id: str) -> tuple[dict[str, Any], str]:
    """The packet and its markdown, only when signed and unchanged since the signature."""
    packet = load(packet_id)
    if packet is None:
        raise FileNotFoundError(packet_id)
    sig = packet.get("signature")
    if packet.get("status") != "signed" or not sig:
        raise PermissionError("unsigned packets cannot leave; a person must sign first")
    if sig.get("packet_hash") != packet_hash(packet):
        raise PermissionError("the packet changed after it was signed; it needs a new signature")
    return packet, load_markdown(packet_id) or ""
