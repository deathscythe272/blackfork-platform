output "risk_analyst_url" {
  value = google_cloud_run_v2_service.risk_analyst.uri
}

output "risk_signing_key_secret" {
  value = google_secret_manager_secret.risk_signing_key.secret_id
}

output "agent_service_url" {
  value = google_cloud_run_v2_service.agents.uri
}

output "evidence_collector_service_account" {
  value = google_service_account.evidence_collector.email
}
