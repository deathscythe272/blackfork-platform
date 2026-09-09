# Assurance plane: the identity that re-scores the deployed platform and reads its
# events into evidence. Nothing here has idle cost: an empty bucket, a subscription,
# a service account and its bindings.
#
# The re-scoring harness (.github/workflows/assurance.yml) becomes this identity with
# a signed GitHub token, and only from main. What it may do is listed below, and it is
# exactly what one run needs: read the gateway's signing key to mint its caller and
# agent tokens, find the deployed services' addresses, read the audit rows the run
# produced, and append its record to the results bucket. It cannot delete a record, so
# a run cannot erase a run. Serves: BR-7, BR-8, BR-9, C4.

locals {
  labels = merge(var.labels, { plane = "assurance" })
  # The keyless identity pool is created by the bootstrap root; the harness binding
  # accepts only a token minted for this repository on main, like the apply deployer.
  main_principal = "principalSet://iam.googleapis.com/projects/${data.google_project.this.number}/locations/global/workloadIdentityPools/${var.workload_identity_pool_id}/attribute.repository_ref/${var.github_repository}:refs/heads/main"
}

data "google_project" "this" {
  project_id = var.project_id
}

resource "google_service_account" "assurance" {
  account_id   = "assurance-${var.env}"
  display_name = "Assurance reader (${var.env})"
  description  = "Re-scores the deployed agents; reads platform events and audit rows; writes evidence."
}

resource "google_pubsub_subscription" "platform_events" {
  name   = "platform-events-assurance-${var.env}"
  topic  = var.platform_events_topic
  labels = local.labels

  message_retention_duration = "86400s"
  retain_acked_messages      = false
}

resource "google_pubsub_subscription_iam_member" "assurance_reads_events" {
  subscription = google_pubsub_subscription.platform_events.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.assurance.email}"
}

# Where every re-scoring run leaves its record. Append only for the harness: it may
# create and read objects, never delete or overwrite one.
resource "google_storage_bucket" "results" {
  name                        = "${var.project_id}-assurance-${var.env}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  labels                      = local.labels
}

resource "google_storage_bucket_iam_member" "assurance_appends_results" {
  for_each = toset(["roles/storage.objectCreator", "roles/storage.objectViewer"])
  bucket   = google_storage_bucket.results.name
  role     = each.value
  member   = "serviceAccount:${google_service_account.assurance.email}"
}

# The harness mints tokens the gateway and the agent service trust, so it reads the
# signing key at run time; the key never lives in the repository or its settings.
resource "google_secret_manager_secret_iam_member" "assurance_reads_signing_key" {
  secret_id = var.gateway_signing_key_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.assurance.email}"
}

# Finding the deployed services' addresses: read the three it calls, nothing else.
resource "google_cloud_run_v2_service_iam_member" "assurance_reads_services" {
  for_each = var.services_under_test
  location = var.region
  name     = each.value
  role     = "roles/run.viewer"
  member   = "serviceAccount:${google_service_account.assurance.email}"
}

# Which GitHub tokens may become the assurance identity: this repository, main only.
resource "google_service_account_iam_member" "assurance_wif" {
  service_account_id = google_service_account.assurance.name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.main_principal
}
