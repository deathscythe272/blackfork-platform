# Assurance plane: the identity that reads platform events (CI results, gate
# decisions) into evidence, and its subscription. Dashboards and the audit table come
# with phase 7. Nothing here has idle cost.
# Serves: BR-7, BR-9, C4.

locals {
  labels = merge(var.labels, { plane = "assurance" })
}

resource "google_service_account" "assurance" {
  account_id   = "assurance-${var.env}"
  display_name = "Assurance reader (${var.env})"
  description  = "Reads platform events and audit rows; writes evidence."
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
