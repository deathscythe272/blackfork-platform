"""A person's side of sign-off. Mints a token that names a person and signs a packet
through the agent service, then exports it.

    python -m provenance.packets.cli sign <packet_id> --as jeff
    python -m provenance.packets.cli export <packet_id> --as jeff

The signing key is the operator's to hold; an agent never runs this. Serves: C3, BR-7.
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

from provenance.gateway.tokens import mint


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["sign", "export", "show"])
    ap.add_argument("packet_id")
    ap.add_argument("--as", dest="person", required=True, help="the person signing, by name")
    args = ap.parse_args()
    url = os.environ.get("AGENT_SERVICE_URL", "http://localhost:8080").rstrip("/")
    headers = {"X-Caller-Token": mint(args.person, ttl_seconds=600, role="person")}
    if args.action == "sign":
        r = httpx.post(f"{url}/packets/{args.packet_id}/sign", headers=headers, timeout=60)
    elif args.action == "export":
        r = httpx.get(f"{url}/packets/{args.packet_id}/export", headers=headers, timeout=60)
    else:
        r = httpx.get(f"{url}/packets/{args.packet_id}", headers=headers, timeout=60)
    print(r.text if args.action == "export" else r.text[:2000])
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
