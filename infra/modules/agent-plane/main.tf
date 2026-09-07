# Agent plane: one identity per agent. The Evidence Collector may read the model key
# and nothing else; its only data path is the gateway (ADR-003). Cloud Run services
# arrive in phase 6 step 3.
# Serves: BR-3, BR-8, C4.

locals {
  labels = merge(var.labels, { plane = "agent" })
}

resource "google_service_account" "evidence_collector" {
  account_id   = "evidence-collector-${var.env}"
  display_name = "Evidence Collector agent (${var.env})"
  description  = "One job, one system, three tools, all through the gateway."
}

resource "google_secret_manager_secret_iam_member" "collector_reads_model_key" {
  secret_id = var.nvidia_api_key_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.evidence_collector.email}"
}
