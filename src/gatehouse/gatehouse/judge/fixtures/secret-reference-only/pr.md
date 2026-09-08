# Wire the analyst's key from Secret Manager and the shell

## What

The analyst reads its signing key from Secret Manager; on Compose the same key comes
from the shell environment. No value is written anywhere; every line is a reference.

## Why

References, not values, are how secrets reach services here (ADR-001).

Serves: BR-7
