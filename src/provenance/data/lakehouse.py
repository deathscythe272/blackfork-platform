"""The lakehouse: Iceberg tables in three layers, written through a small catalog and
readable without one.

  bronze   evidence exactly as received
  silver   bronze with personal data redacted (redact.py); nothing downstream sees
           what silver does not carry
  gold     the narrow, typed view the evidence server serves, partitioned by system

Two settings decide where the tables live: LAKEHOUSE_WAREHOUSE (a file:// folder on a
laptop, gs://<bucket>/warehouse in the cloud) and LAKEHOUSE_CATALOG (a SQLite file the
pipeline uses to find tables by name). A reader needs neither: every table publishes a
pointer to its current metadata file, and a StaticTable loads from that. The same code
runs in both places; only the two settings change. ADR-002. Serves: BR-2, BR-5, C4.
"""

from __future__ import annotations

import os
import pathlib

import fsspec
import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.exceptions import NoSuchNamespaceError, NoSuchTableError
from pyiceberg.table import StaticTable, Table

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
IO_PROPS = {"py-io-impl": "pyiceberg.io.fsspec.FsspecFileIO"}  # one file layer for file:// and gs://
POINTER = "_current_metadata"


def warehouse() -> str:
    return os.environ.get("LAKEHOUSE_WAREHOUSE") or (REPO_ROOT / "data" / "warehouse").as_uri()


def catalog_uri() -> str:
    return os.environ.get("LAKEHOUSE_CATALOG") or f"sqlite:///{(REPO_ROOT / 'data' / 'catalog.db').as_posix()}"


def catalog() -> SqlCatalog:
    if catalog_uri().startswith("sqlite:///"):
        pathlib.Path(catalog_uri()[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
    return SqlCatalog("blackfork", uri=catalog_uri(), warehouse=warehouse(), **IO_PROPS)


def pointer_url(layer: str, name: str) -> str:
    return f"{warehouse().rstrip('/')}/{layer}/{name}/{POINTER}"


def write_table(layer: str, name: str, data: pa.Table, partition_by: str | None = None) -> Table:
    """Replace the table's contents with `data` (idempotent runs, not appends), then
    publish the pointer. Creates the namespace, the table, and the partition on first use."""
    cat = catalog()
    try:
        cat.create_namespace(layer)
    except Exception:  # namespace exists; pyiceberg's error type differs by backend
        pass
    ident = f"{layer}.{name}"
    try:
        table = cat.load_table(ident)
    except (NoSuchTableError, NoSuchNamespaceError):
        table = cat.create_table(ident, schema=data.schema, properties=IO_PROPS)
        if partition_by:
            with table.update_spec() as spec:
                spec.add_identity(partition_by)
    table.overwrite(data)
    with fsspec.open(pointer_url(layer, name), "w") as f:
        f.write(table.metadata_location)
    return table


def read_pointer(layer: str, name: str) -> str | None:
    try:
        with fsspec.open(pointer_url(layer, name), "r") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def load_static(layer: str, name: str) -> StaticTable:
    """The table as a reader sees it: from the pointer, no catalog, any file layer."""
    location = read_pointer(layer, name)
    if not location:
        raise FileNotFoundError(f"no pointer at {pointer_url(layer, name)}; run the pipeline first")
    return StaticTable.from_metadata(location, properties=IO_PROPS)


def read_arrow(layer: str, name: str) -> pa.Table:
    return load_static(layer, name).scan().to_arrow()
