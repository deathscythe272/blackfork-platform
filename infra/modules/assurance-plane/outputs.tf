output "audit_subscription" {
  description = "Full name the eval runner reads audit rows from (AUDIT_SUBSCRIPTION)."
  value       = google_pubsub_subscription.platform_events.id
}

output "assurance_service_account" {
  value = google_service_account.assurance.email
}

output "results_bucket" {
  description = "Where the re-scoring harness appends one record per run (ASSURANCE_STORE=gs://<bucket>)."
  value       = google_storage_bucket.results.name
}
