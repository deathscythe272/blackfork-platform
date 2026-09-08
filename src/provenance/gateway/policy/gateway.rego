# Gateway policy for the V1 slice.
#
# Input shape (built by the gateway on every tool call):
#   { "identity": "<agent id from the verified token>",
#     "tool":     "<MCP tool name>",
#     "args":     { ... tool arguments ... } }
#
# Default deny. Two kinds of tool, two kinds of scope. Evidence tools are scoped by
# system: an identity may call one only if the tool is in its grant AND the system_id
# it asks about is in its grant. Catalog tools are scoped by framework the same way.
# A tool is in exactly one kind, so a catalog grant can never open an evidence tool
# and a system grant can never open a catalog tool. There is no rule that allows a
# call without a scope, so a tool that forgets to require one is unreachable by
# construction.
#
# Serves: BR-7 (every call decided by versioned policy), BR-8 (elevation of privilege,
# tool-based exfiltration; tests T1-GW-06).

package blackfork.gateway

import rego.v1

version := "2026-09-08.1"

default allow := false

# Which scope each tool takes. A tool absent from both sets cannot be allowed.
system_tools := {"list_controls", "get_evidence", "get_evidence_row"}

framework_tools := {"get_control", "list_family", "search_controls"}

# Grants: which identity may use which tools, on which systems and which frameworks.
grants := {
	"evidence-collector": {
		"tools": {"list_controls", "get_evidence", "get_evidence_row", "get_control", "list_family", "search_controls"},
		"systems": {"sys-windrow-prod"},
		"frameworks": {"800-171"},
	},
}

allow if {
	grant := grants[input.identity]
	grant.tools[input.tool]
	system_tools[input.tool]
	grant.systems[input.args.system_id]
}

allow if {
	grant := grants[input.identity]
	grant.tools[input.tool]
	framework_tools[input.tool]
	grant.frameworks[input.args.framework]
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
	system_tools[input.tool]
	not grant.systems[input.args.system_id]
}

reason := "framework not granted to identity" if {
	not allow
	grant := grants[input.identity]
	grant.tools[input.tool]
	framework_tools[input.tool]
	not grant.frameworks[input.args.framework]
}

decision := {"allow": allow, "reason": reason, "version": version}
