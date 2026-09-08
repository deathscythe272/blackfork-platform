"""Run the evidence pipeline once, checks included, and exit non-zero if any check
fails. The same entry point serves the laptop, the tests, and a cloud run.

    python -m provenance.data.run                       # data/warehouse on this machine
    LAKEHOUSE_WAREHOUSE=gs://<bucket>/warehouse python -m provenance.data.run

Serves: BR-2, BR-7.
"""

from __future__ import annotations

import sys

from dagster import materialize

from provenance.data.assets import ASSETS, CHECKS
from provenance.data import lakehouse


def run() -> tuple[bool, dict[str, bool]]:
    result = materialize(ASSETS + CHECKS, raise_on_error=False)
    checks = {ev.check_name: ev.passed for ev in result.get_asset_check_evaluations()}
    return result.success and all(checks.values()), checks


def main() -> int:
    ok, checks = run()
    print(f"warehouse: {lakehouse.warehouse()}")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    print("pipeline:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
