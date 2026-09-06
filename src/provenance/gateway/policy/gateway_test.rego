package blackfork.gateway_test

import rego.v1

import data.blackfork.gateway

test_collector_may_read_its_system if {
	gateway.allow with input as {
		"identity": "evidence-collector",
		"tool": "get_evidence",
		"args": {"system_id": "sys-windrow-prod", "control_id": "3.3.1"},
	}
}

test_collector_denied_other_system if {
	not gateway.allow with input as {
		"identity": "evidence-collector",
		"tool": "get_evidence",
		"args": {"system_id": "sys-windrow-dev", "control_id": "3.3.1"},
	}
}

test_reason_names_the_system_boundary if {
	gateway.reason == "system_id not granted to identity" with input as {
		"identity": "evidence-collector",
		"tool": "list_controls",
		"args": {"system_id": "sys-windrow-dev"},
	}
}

test_unknown_identity_denied if {
	not gateway.allow with input as {
		"identity": "report-writer",
		"tool": "get_evidence",
		"args": {"system_id": "sys-windrow-prod", "control_id": "3.3.1"},
	}
}

test_unknown_tool_denied if {
	not gateway.allow with input as {
		"identity": "evidence-collector",
		"tool": "run_sql",
		"args": {"system_id": "sys-windrow-prod", "sql": "select 1"},
	}
}

test_missing_system_id_denied if {
	not gateway.allow with input as {
		"identity": "evidence-collector",
		"tool": "list_controls",
		"args": {},
	}
}

test_decision_carries_version_and_reason if {
	d := gateway.decision with input as {
		"identity": "nobody",
		"tool": "get_evidence",
		"args": {"system_id": "sys-windrow-prod"},
	}
	d.version == gateway.version
	d.allow == false
	d.reason == "unknown identity"
}
