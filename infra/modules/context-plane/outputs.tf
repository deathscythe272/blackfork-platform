output "gateway_service_account" {
  value = google_service_account.gateway.email
}

output "evidence_mcp_service_account" {
  value = google_service_account.evidence_mcp.email
}

output "nvidia_api_key_secret" {
  value = google_secret_manager_secret.nvidia_api_key.id
}
