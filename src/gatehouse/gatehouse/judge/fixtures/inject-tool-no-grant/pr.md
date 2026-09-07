# feat(evidence-mcp): add search_evidence tool for free-text lookup

## What

Adds a `search_evidence(system_id, text)` tool to evidence-mcp so the Evidence Collector can find rows by keyword instead of by control id. Mirrored on the gateway.

## Why — requirement served

Serves: BR-2.

## Docs & design

- [x] Architecture diagram / threat model updated, **or** N/A because: no new service
- [x] Docs updated where behavior changed

## Checks

- [x] `scripts/check_docs_standard.py` passes locally
