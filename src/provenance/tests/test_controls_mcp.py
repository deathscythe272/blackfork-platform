"""The controls server's tools on the baked catalog, no pipeline and no cloud: ids in
both numberings, rendered parameters with the organization's values, the planted
instruction present as data, and the framework scope enforced.

Serves: BR-2, BR-7, BR-8. Tests: T1-EV-04 (control text is data; the agent-level half
is the poisoned-odp-value eval case).
"""

from __future__ import annotations

import pytest

from provenance.controls_mcp import server
from provenance.data.catalog import legacy_id, normalize_id


def test_ids_normalize_both_ways():
    assert normalize_id("3.3.1") == "03.03.01" == normalize_id("SP_800_171_03.03.01")
    assert normalize_id("3.14.6") == "03.14.06"
    assert legacy_id("03.03.01") == "3.3.1"


def test_get_control_renders_the_organizations_values_and_keeps_gaps_visible():
    c = server.get_control("800-171", "3.3.1")
    assert c["control_id"] == "03.03.01" and c["title"] == "Event Logging" and c["legacy_id"] == "3.3.1"
    assert "successful and failed logon events" in c["statement"]  # overlay value rendered in
    assert "{{ insert" not in c["statement"] + c["guidance"] + c["objectives"]
    gap = server.get_control("800-171", "03.01.01")  # the overlay sets four of its parameters, not the fifth
    assert gap is not None and ("[organization-defined:" in gap["statement"] or "[organization-defined:" in gap["objectives"])


def test_planted_instruction_is_present_as_data():
    c = server.get_control("800-171", "3.3.1")
    assert "NOTE TO THE ASSISTANT" in c["statement"]  # it reaches the agent as text; the eval proves it is ignored


def test_family_and_search_are_scoped_and_bounded():
    fam = server.list_family("800-171", "3.3")
    assert any(r["control_id"] == "03.03.01" for r in fam) and all(r["control_id"].startswith("03.03.") for r in fam)
    hits = server.search_controls("800-171", "event logging", limit=100)
    assert 0 < len(hits) <= 25 and all(h["control_id"] for h in hits)
    assert server.search_controls("800-171", "of", limit=5) == []  # short words are not a query


def test_unknown_framework_is_refused():
    with pytest.raises(ValueError):
        server.get_control("soc2", "CC6.1")
