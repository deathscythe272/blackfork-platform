output "gateway_service_account" {
  value = google_service_account.gateway.email
}

output "evidence_mcp_service_account" {
  value = google_service_account.evidence_mcp.email
}

output "gateway_url" {
  description = "Where the agent and the eval runner point GATEWAY_URL (append /mcp)."
  value       = google_cloud_run_v2_service.gateway.uri
}

output "evidence_mcp_url" {
  value = google_cloud_run_v2_service.evidence_mcp.uri
}

output "controls_mcp_url" {
  value = google_cloud_run_v2_service.controls_mcp.uri
}

output "gateway_signing_key_secret" {
  value = google_secret_manager_secret.gateway_signing_key.secret_id
}

output "nvidia_api_key_secret" {
  value = google_secret_manager_secret.nvidia_api_key.id
}
