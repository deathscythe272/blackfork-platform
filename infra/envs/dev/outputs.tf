output "lakehouse_bucket" {
  value = module.data.lakehouse_bucket
}

output "platform_events_topic" {
  value = module.data.platform_events_topic
}

output "service_accounts" {
  value = {
    gateway            = module.context.gateway_service_account
    evidence_mcp       = module.context.evidence_mcp_service_account
    evidence_collector = module.agent.evidence_collector_service_account
    assurance          = module.assurance.assurance_service_account
  }
}

output "gateway_url" {
  value = module.context.gateway_url
}

output "evidence_mcp_url" {
  value = module.context.evidence_mcp_url
}

output "agent_service_url" {
  value = module.agent.agent_service_url
}

output "audit_subscription" {
  value = module.assurance.audit_subscription
}

output "nvidia_api_key_secret" {
  value = module.context.nvidia_api_key_secret
}
