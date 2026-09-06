# Gateway policy for the V1 slice.
#
# Input shape (built by the gateway on every tool call):
#   { "identity": "<agent id from the verified token>",
#     "tool":     "<MCP tool name>",
#     "args":     { ... tool arguments ... } }
#
# Default deny. An identity may call a tool only if the tool is in its grant AND the
# system_id it asks about is in its grant. There is no rule that allows a call without
# a system_id, so a tool that forgets to require one is unreachable by construction.
#
# Serves: BR-7 (every call decided by versioned policy), BR-8 (elevation of privilege,
# tool-based exfiltration; tests T1-GW-06).

package blackfork.gateway

import rego.v1

version := "2026-09-06.1"

default allow := false

# Grants: which identity may use which tools on which systems.
grants := {
	"evidence-collector": {
		"tools": {"list_controls", "get_evidence", "get_evidence_row"},
		"systems": {"sys-windrow-prod"},
	},
}

allow if {
	grant := grants[input.identity]
	grant.tools[input.tool]
	grant.systems[input.args.system_id]
}

reason := "allowed" if allow

reason := "unknown identity" if {
	not allow
	not grants[input.identity]
}

reason := "tool not granted to identity" if {
	not allow
	grant := grants[input.identity]
	not grant.tools[input.tool]
}

reason := "system_id not granted to identity" if {
	not allow
	grant := grants[input.identity]
	grant.tools[input.tool]
	not grant.systems[input.args.system_id]
}

decision := {"allow": allow, "reason": reason, "version": version}
