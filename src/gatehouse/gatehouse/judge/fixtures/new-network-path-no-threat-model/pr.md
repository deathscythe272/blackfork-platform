# feat(gateway): publish each decision to Pub/Sub for the posture dashboard

## What

After writing the audit row, the gateway now also publishes the decision to a Pub/Sub topic so the Grafana posture dashboard updates in near real time. Adds the emulator to Compose for local runs.

## Why — requirement served

Serves: BR-7.

## Docs & design

- [x] Architecture diagram / threat model updated, **or** N/A because: internal only, same data as the audit log
- [x] Docs updated where behavior changed

## Checks

- [x] `scripts/check_docs_standard.py` passes locally
