# chore(slice): clearer denial message and one doc sentence

## What

The gateway's policy-denial error now names the tool as well as the reason. The slice page gains one sentence noting idle cost is zero.

## Why — requirement served

Serves: BR-7, C4.

## Docs & design

- [x] Architecture diagram / threat model updated, **or** N/A because: message text and one doc sentence; no boundary, tool, or path changes
- [x] Docs updated where behavior changed

## Checks

- [x] `scripts/check_docs_standard.py` passes locally
