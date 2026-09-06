"""Build the V1-slice gold-view stand-in: one DuckDB file with an `evidence` table.

The real platform serves Gold views out of Iceberg (roadmap phase 7). For the slice
a dozen fixture rows across two systems are enough to exercise the door: every row
carries `system_id`, which is what the gateway's policy constrains on.

Serves: BR-2 (chain of custody shape), BR-7/BR-8 (system_id is the policy boundary).
"""

from __future__ import annotations

import argparse
import pathlib

import duckdb

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "evidence.csv"


def build(csv_path: pathlib.Path, db_path: pathlib.Path) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE evidence AS
        SELECT * FROM read_csv(?, header = true, columns = {
            'row_id': 'VARCHAR', 'system_id': 'VARCHAR', 'control_id': 'VARCHAR',
            'control_name': 'VARCHAR', 'framework': 'VARCHAR', 'source': 'VARCHAR',
            'observed_at': 'TIMESTAMP', 'summary': 'VARCHAR', 'evidence_ref': 'VARCHAR'
        })
        """,
        [str(csv_path)],
    )
    n = con.execute("SELECT count(*) FROM evidence").fetchone()[0]
    con.close()
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=pathlib.Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=pathlib.Path, default=HERE.parents[2] / "data" / "evidence.duckdb")
    args = ap.parse_args()
    n = build(args.csv, args.out)
    print(f"built {args.out} with {n} evidence rows")


if __name__ == "__main__":
    main()
