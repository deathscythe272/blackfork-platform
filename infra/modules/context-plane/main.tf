# Context plane: the identities for the gateway and the evidence server, and the one
# secret the platform holds. The secret is created empty; its value is added from the
# operator's shell and never passes through Terraform or the repo. Cloud Run services
# for these identities arrive in phase 6 step 3.
# Serves: BR-7, BR-8, C4.

locals {
  labels = merge(var.labels, { plane = "context" })
}

resource "google_service_account" "gateway" {
  account_id   = "gateway-${var.env}"
  display_name = "Auth gateway (${var.env})"
  description  = "Identity of the MCP auth gateway: token check, policy decision, audit write."
}

resource "google_service_account" "evidence_mcp" {
  account_id   = "evidence-mcp-${var.env}"
  display_name = "Evidence MCP server (${var.env})"
  description  = "Identity of the evidence server: fixed queries over the lakehouse, read only."
}

resource "google_secret_manager_secret" "nvidia_api_key" {
  secret_id = "nvidia-api-key-${var.env}"
  labels    = local.labels

  replication {
    auto {}
  }
}

resource "google_storage_bucket_iam_member" "evidence_mcp_reads_lakehouse" {
  bucket = var.lakehouse_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.evidence_mcp.email}"
}
