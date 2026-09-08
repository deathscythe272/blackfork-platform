"""Control catalogs in OSCAL, the machine-readable format NIST publishes, turned into
rows an agent can ask about.

A catalog is a tree: families, controls, and inside each control the statement, the
guidance, and the assessment objectives, with organization-defined parameters
(ODPs) left as placeholders such as `{{ insert: param, A.03.03.01.ODP.01 }}`. Rendering
fills those from the organization's overlay (odp/<org>.yml); a parameter the overlay
does not set renders as `[organization-defined: <label>]` so the gap is visible rather
than silent. Overlay values are organization-authored text, which makes them the
catalog's injection surface; one planted value proves the agent treats them as data.

Control ids are accepted in both numberings: revision 3's `03.03.01` and the older
`3.3.1` the evidence rows still carry. Serves: BR-2, BR-7, BR-8.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

import yaml

HERE = pathlib.Path(__file__).resolve().parent
CATALOGS = HERE.parent / "fixtures" / "catalogs"
FRAMEWORKS = {
    "800-171": {"file": CATALOGS / "NIST_SP800-171_rev3_catalog-min.json", "revision": "3",
                "title": "NIST SP 800-171 rev. 3, Protecting Controlled Unclassified Information"},
}
OVERLAYS = HERE / "odp"
_PLACEHOLDER = re.compile(r"\{\{\s*insert:\s*param,\s*([A-Za-z0-9._-]+)\s*\}\}")


def normalize_id(control_id: str) -> str:
    """`3.3.1` and `03.03.01` and `SP_800_171_03.03.01` all name the same control."""
    cid = control_id.strip().split("SP_800_171_")[-1]
    parts = cid.split(".")
    if all(p.isdigit() for p in parts) and len(parts) in (2, 3):
        return ".".join(p.zfill(2) for p in parts)
    return cid


def legacy_id(control_id: str) -> str:
    """The pre-revision-3 numbering, `3.3.1`, which the evidence rows use."""
    return ".".join(str(int(p)) for p in normalize_id(control_id).split("."))


def load_overlay(org: str = "blackfork") -> dict[str, str]:
    path = OVERLAYS / f"{org}.yml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in (data.get("parameters") or {}).items()}


def _render(prose: str | None, params: dict[str, dict[str, Any]], overlay: dict[str, str], fill: bool = True) -> str:
    if not prose:
        return ""
    if not fill:
        return prose.strip()  # bronze: exactly as published, placeholders and all

    def _fill(m: re.Match) -> str:
        pid = m.group(1)
        if pid in overlay:
            return overlay[pid]
        label = (params.get(pid) or {}).get("label") or pid
        return f"[organization-defined: {label}]"

    return _PLACEHOLDER.sub(_fill, prose).strip()


def _items(parts: list[dict[str, Any]], params: dict, overlay: dict, depth: int = 0, fill: bool = True) -> list[str]:
    out = []
    for p in parts:
        if p.get("name") not in ("item", "statement"):
            continue
        label = next((pp["value"] for pp in p.get("props", []) if pp.get("name") == "label"), "")
        text = _render(p.get("prose"), params, overlay, fill)
        if text:
            out.append(("  " * depth) + (f"{label} " if label else "") + text)
        out += _items(p.get("parts", []), params, overlay, depth + 1, fill)
    return out


def rows(framework: str = "800-171", overlay: dict[str, str] | None = None, rendered: bool = True) -> list[dict[str, Any]]:
    """One row per control. `rendered=False` keeps placeholders, for bronze."""
    spec = FRAMEWORKS[framework]
    catalog = json.loads(spec["file"].read_text(encoding="utf-8"))["catalog"]
    overlay = ({} if not rendered else (overlay if overlay is not None else load_overlay()))
    out = []
    for group in catalog.get("groups", []):
        family_id = normalize_id(group["id"].split("SP_800_171_")[-1])
        for c in group.get("controls", []):
            params = {p["id"]: p for p in c.get("params", [])}
            props = {p.get("name"): p.get("value") for p in c.get("props", [])}
            statement = next((p for p in c.get("parts", []) if p.get("name") == "statement"), None)
            objectives = [_render(p.get("prose"), params, overlay, rendered) for p in c.get("parts", []) if p.get("name") == "assessment-objective"]
            guidance = next((p.get("prose") for p in c.get("parts", []) if p.get("name") == "guidance"), None)
            cid = normalize_id(c["id"])
            out.append({
                "framework": framework, "revision": spec["revision"], "control_id": cid, "legacy_id": legacy_id(cid),
                "family_id": family_id, "family": group.get("title", ""), "title": c.get("title", ""),
                "status": props.get("status", "active"),
                "statement": "\n".join(_items([statement], params, overlay, fill=rendered)) if statement else "",
                "guidance": _render(guidance, params, overlay, rendered),
                "objectives": "\n".join(o for o in objectives if o),
                "parameters": json.dumps({pid: (p.get("label") or pid) for pid, p in params.items()}, sort_keys=True),
            })
    return out
