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

# The gateway's token-signing key. Created empty; the value is added from an
# operator's shell (`gcloud secrets versions add`) and never passes through code.
resource "google_secret_manager_secret" "gateway_signing_key" {
  secret_id = "gateway-signing-key-${var.env}"
  labels    = local.labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "gateway_reads_signing_key" {
  secret_id = google_secret_manager_secret.gateway_signing_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.gateway.email}"
}

# Audit rows leave the gateway as events; only the gateway may publish them.
resource "google_pubsub_topic_iam_member" "gateway_publishes_audit" {
  topic  = var.platform_events_topic
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.gateway.email}"
}

# The evidence server: fixed queries over baked-in fixture data. Reachable on the
# network, but Cloud Run admits only callers presenting a signed identity token for
# this service, and the only identity granted that right is the gateway's (ADR-001).
resource "google_cloud_run_v2_service" "evidence_mcp" {
  name                = "evidence-mcp-${var.env}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels
  deletion_protection = false

  template {
    service_account = google_service_account.evidence_mcp.email
    labels          = local.labels

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image   = "${var.image_registry}/services:${var.image_tag}"
      command = ["python", "-m", "provenance.evidence_mcp.server"]

      ports {
        container_port = 8001
      }

      env {
        name  = "EVIDENCE_DB"
        value = "/data/evidence.duckdb" # fallback until the pipeline has run
      }
      env {
        name  = "LAKEHOUSE_WAREHOUSE"
        value = "gs://${var.lakehouse_bucket}/warehouse" # gold from the data plane, bucket read only
      }
      env {
        name  = "EVIDENCE_MCP_PORT"
        value = "8001"
      }

      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true
        startup_cpu_boost = true
      }
    }
  }
}

# The controls server: fixed queries over the control catalogs. Same door as the
# evidence server: only the gateway's identity may invoke it.
resource "google_cloud_run_v2_service" "controls_mcp" {
  name                = "controls-mcp-${var.env}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels
  deletion_protection = false

  template {
    service_account = google_service_account.evidence_mcp.email
    labels          = local.labels

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image   = "${var.image_registry}/services:${var.image_tag}"
      command = ["python", "-m", "provenance.controls_mcp.server"]

      ports {
        container_port = 8002
      }

      env {
        name  = "LAKEHOUSE_WAREHOUSE"
        value = "gs://${var.lakehouse_bucket}/warehouse" # gold controls from the data plane; the baked catalog otherwise
      }
      env {
        name  = "CONTROLS_MCP_PORT"
        value = "8002"
      }

      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true
        startup_cpu_boost = true
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "controls_mcp_invoker_gateway" {
  name     = google_cloud_run_v2_service.controls_mcp.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.gateway.email}"
}

resource "google_cloud_run_v2_service_iam_member" "evidence_mcp_invoker_gateway" {
  name     = google_cloud_run_v2_service.evidence_mcp.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.gateway.email}"
}

# The gateway: the only door to evidence. Open on the network because it enforces its
# own signed tokens; the policy engine runs beside it as a sidecar on localhost.
resource "google_cloud_run_v2_service" "gateway" {
  name                = "gateway-${var.env}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels
  deletion_protection = false

  template {
    service_account = google_service_account.gateway.email
    labels          = local.labels

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      name       = "gateway"
      image      = "${var.image_registry}/services:${var.image_tag}"
      command    = ["python", "-m", "provenance.gateway.server"]
      depends_on = ["opa"]

      ports {
        container_port = 8000
      }

      env {
        name  = "GATEWAY_PORT"
        value = "8000"
      }
      env {
        name  = "OPA_URL"
        value = "http://127.0.0.1:8181"
      }
      env {
        name  = "EVIDENCE_MCP_URL"
        value = "${google_cloud_run_v2_service.evidence_mcp.uri}/mcp"
      }
      env {
        name  = "EVIDENCE_MCP_AUDIENCE"
        value = google_cloud_run_v2_service.evidence_mcp.uri
      }
      env {
        name  = "CONTROLS_MCP_URL"
        value = "${google_cloud_run_v2_service.controls_mcp.uri}/mcp"
      }
      env {
        name  = "CONTROLS_MCP_AUDIENCE"
        value = google_cloud_run_v2_service.controls_mcp.uri
      }
      env {
        name  = "AUDIT_SINK"
        value = "pubsub"
      }
      env {
        name  = "AUDIT_TOPIC"
        value = var.platform_events_topic
      }
      env {
        name = "GATEWAY_SIGNING_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gateway_signing_key.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        tcp_socket {
          port = 8000
        }
        initial_delay_seconds = 2
        period_seconds        = 2
        failure_threshold     = 30
      }

      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true
        startup_cpu_boost = true
      }
    }

    containers {
      name  = "opa"
      image = "${var.image_registry}/opa:${var.image_tag}"

      startup_probe {
        tcp_socket {
          port = 8181
        }
        initial_delay_seconds = 1
        period_seconds        = 1
        failure_threshold     = 30
      }

      resources {
        limits   = { cpu = "1", memory = "256Mi" }
        cpu_idle = true
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.gateway_reads_signing_key,
    google_pubsub_topic_iam_member.gateway_publishes_audit,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "gateway_public" {
  name     = google_cloud_run_v2_service.gateway.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_storage_bucket_iam_member" "evidence_mcp_reads_lakehouse" {
  bucket = var.lakehouse_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.evidence_mcp.email}"
}
