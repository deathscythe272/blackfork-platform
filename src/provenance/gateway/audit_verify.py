"""Verify an audit trail's hash chain (T1-PL-02).

    python -m provenance.gateway.audit_verify audit/audit.jsonl
    python -m provenance.gateway.audit_verify rows.jsonl   # rows pulled from the topic, in order

Exit 0 when every row links to the one before it; exit 1 with the first break and
its reason otherwise. Serves: BR-7.
"""

from __future__ import annotations

import json
import pathlib
import sys

from provenance.gateway import chain


def main(argv: list[str]) -> int:
    path = pathlib.Path(argv[1] if len(argv) > 1 else "audit/audit.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    result = chain.verify(rows)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
