# Data plane: where evidence lands and where events travel. The lakehouse bucket is
# the Iceberg warehouse path (ADR-002, phase 7); the topic carries platform events,
# including CI results that Provenance ingests as evidence. Both are free while empty.
# Serves: BR-1, BR-2, BR-5, C4.

locals {
  labels = merge(var.labels, { plane = "data" })
}

resource "google_storage_bucket" "lakehouse" {
  name                        = "${var.project_id}-lakehouse-${var.env}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.env == "dev"
  labels                      = local.labels
}

resource "google_pubsub_topic" "platform_events" {
  name   = "platform-events-${var.env}"
  labels = local.labels
}
