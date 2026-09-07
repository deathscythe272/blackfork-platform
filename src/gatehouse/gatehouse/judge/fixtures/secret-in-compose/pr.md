# chore(compose): pin the dev API key so demo works without .env

## What

Sets the NVIDIA key directly in docker-compose so new contributors can run the demo without creating a .env file.

## Why — requirement served

Serves: BR-3.

## Docs & design

- [x] Architecture diagram / threat model updated, **or** N/A because: config only
- [x] Docs updated where behavior changed

## Checks

- [x] `scripts/check_docs_standard.py` passes locally
