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

resource "google_secret_manager_secret_iam_member" "collector_reads_signing_key" {
  secret_id = var.gateway_signing_key_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.evidence_collector.email}"
}

# The agent service: agents as a service behind a signed-token door, a quota per
# caller, a record per job. Open on the network because it checks its own tokens; its
# only data door is the gateway. One instance holds the quota buckets.
resource "google_cloud_run_v2_service" "agents" {
  name                = "agents-${var.env}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels
  deletion_protection = false

  template {
    service_account = google_service_account.evidence_collector.email
    labels          = local.labels
    timeout         = "600s"

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image   = "${var.image_registry}/agent:${var.image_tag}"
      command = ["python", "-m", "provenance.agent_service.server"]

      ports {
        container_port = 8080
      }

      env {
        name  = "AGENT_SERVICE_PORT"
        value = "8080"
      }
      env {
        name  = "GATEWAY_URL"
        value = var.gateway_url
      }
      env {
        name  = "AGENT_JOB_QUOTA"
        value = "30" # jobs per caller per window (T1-IN-04)
      }
      env {
        name  = "AGENT_JOB_WINDOW_SECONDS"
        value = "3600"
      }
      env {
        name  = "AGENT_JOBS_LOG"
        value = "/tmp/jobs.jsonl" # per instance; the durable record is the gateway's audit trail
      }
      env {
        name  = "PACKETS_URL"
        value = "gs://${var.lakehouse_bucket}/packets" # drafts and signatures, beside the evidence they cite
      }
      env {
        name  = "RISK_ANALYST_URL"
        value = google_cloud_run_v2_service.risk_analyst.uri
      }
      env {
        name  = "RISK_ANALYST_AUDIENCE"
        value = google_cloud_run_v2_service.risk_analyst.uri
      }
      env {
        name = "RISK_SIGNING_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.risk_signing_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "GATEWAY_SIGNING_KEY"
        value_source {
          secret_key_ref {
            secret  = var.gateway_signing_key_secret
            version = "latest"
          }
        }
      }
      env {
        name = "NVIDIA_API_KEY"
        value_source {
          secret_key_ref {
            secret  = var.nvidia_api_key_secret
            version = "latest"
          }
        }
      }

      startup_probe {
        tcp_socket {
          port = 8080
        }
        initial_delay_seconds = 5
        period_seconds        = 3
        failure_threshold     = 40
      }

      resources {
        limits            = { cpu = "1", memory = "2Gi" }
        cpu_idle          = true
        startup_cpu_boost = true
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.collector_reads_model_key,
    google_secret_manager_secret_iam_member.collector_reads_signing_key,
    google_secret_manager_secret_iam_member.collector_reads_analyst_key,
  ]
}

# The Risk Analyst: its own identity, its own key, no grant at the evidence door and no
# bucket. Closed at the platform level to everyone but the agent service's identity,
# and closed again by its own token (ADR-004).
resource "google_service_account" "risk_analyst" {
  account_id   = "risk-analyst-${var.env}"
  display_name = "Risk Analyst (${var.env})"
  description  = "Scores findings it is handed; holds no data-plane or gateway access."
}

resource "google_secret_manager_secret" "risk_signing_key" {
  secret_id = "risk-signing-key-${var.env}"
  labels    = local.labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "analyst_reads_its_key" {
  secret_id = google_secret_manager_secret.risk_signing_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.risk_analyst.email}"
}

resource "google_secret_manager_secret_iam_member" "collector_reads_analyst_key" {
  secret_id = google_secret_manager_secret.risk_signing_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.evidence_collector.email}" # as the analyst's client
}

resource "google_secret_manager_secret_iam_member" "analyst_reads_model_key" {
  secret_id = var.nvidia_api_key_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.risk_analyst.email}" # to write the explanation
}

resource "google_cloud_run_v2_service" "risk_analyst" {
  name                = "risk-analyst-${var.env}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels
  deletion_protection = false

  template {
    service_account = google_service_account.risk_analyst.email
    labels          = local.labels
    timeout         = "300s"

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image   = "${var.image_registry}/agent:${var.image_tag}"
      command = ["python", "-m", "provenance.risk_analyst.server"]

      ports {
        container_port = 8090
      }

      env {
        name  = "RISK_ANALYST_PORT"
        value = "8090"
      }
      env {
        name  = "RISK_EXPLAIN"
        value = "model"
      }
      env {
        name = "RISK_SIGNING_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.risk_signing_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "NVIDIA_API_KEY"
        value_source {
          secret_key_ref {
            secret  = var.nvidia_api_key_secret
            version = "latest"
          }
        }
      }

      startup_probe {
        tcp_socket {
          port = 8090
        }
        initial_delay_seconds = 5
        period_seconds        = 3
        failure_threshold     = 40
      }

      resources {
        limits            = { cpu = "1", memory = "1Gi" }
        cpu_idle          = true
        startup_cpu_boost = true
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.analyst_reads_its_key,
    google_secret_manager_secret_iam_member.analyst_reads_model_key,
  ]
}

# Only the agent service's identity may invoke the analyst at the platform level.
resource "google_cloud_run_v2_service_iam_member" "risk_analyst_invoker_agents" {
  name     = google_cloud_run_v2_service.risk_analyst.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.evidence_collector.email}"
}

# The agent service writes packets and signatures under packets/ in the lakehouse bucket.
resource "google_storage_bucket_iam_member" "agents_write_packets" {
  bucket = var.lakehouse_bucket
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.evidence_collector.email}"
}

resource "google_cloud_run_v2_service_iam_member" "agents_public" {
  name     = google_cloud_run_v2_service.agents.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
