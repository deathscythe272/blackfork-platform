# Delivery plane: the things CI needs before it can run Terraform for anything else.
# Terraform state, keyless identity for GitHub Actions, two deployer service accounts
# with different reach, and the image registry. Nothing here costs money while idle
# beyond a few kilobytes of state and whatever images are pushed.
# Serves: BR-5, BR-7, C4.

locals {
  labels = merge(var.labels, { plane = "delivery" })
  # A token from GitHub carries the repository it came from and the git ref the job
  # runs on. The pool trusts only this repository; the apply identity trusts only main.
  repo_principal = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
  main_principal = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_ref/${var.github_repository}:refs/heads/main"
}

# Terraform state for every environment root. Versioned so a bad apply can be walked
# back; public access prevented at the bucket, not by policy that could drift.
resource "google_storage_bucket" "tfstate" {
  name                        = "${var.project_id}-tfstate"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.labels

  versioning {
    enabled = true
  }
}

# Keyless identity: GitHub signs a token per job; Google verifies it and hands back
# short-lived credentials. No JSON key exists anywhere.
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  description               = "Trusts OIDC tokens from one GitHub repository."
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"           = "assertion.sub"
    "attribute.repository"     = "assertion.repository"
    "attribute.repository_ref" = "assertion.repository + ':' + assertion.ref"
  }

  # A token from any other repository is rejected before any identity is considered.
  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Two deployers with different reach. Pull requests plan with the first; only a job on
# main can become the second.
resource "google_service_account" "plan" {
  account_id   = "deployer-plan"
  display_name = "Terraform plan, pull requests"
  description  = "Reads the project and the state; cannot change anything."
}

resource "google_service_account" "apply" {
  account_id   = "deployer-apply"
  display_name = "Terraform apply, main only"
  description  = "Applies environment roots after merge to main."
}

resource "google_project_iam_member" "plan_viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.plan.email}"
}

# Plan needs to write the state lock, so it gets object access on the state bucket only.
resource "google_storage_bucket_iam_member" "plan_state" {
  bucket = google_storage_bucket.tfstate.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.plan.email}"
}

resource "google_project_iam_member" "apply" {
  for_each = toset(var.apply_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.apply.email}"
}

resource "google_storage_bucket_iam_member" "apply_state" {
  bucket = google_storage_bucket.tfstate.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.apply.email}"
}

# Which GitHub tokens may become which deployer.
resource "google_service_account_iam_member" "plan_wif" {
  service_account_id = google_service_account.plan.name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.repo_principal
}

resource "google_service_account_iam_member" "apply_wif" {
  service_account_id = google_service_account.apply.name
  role               = "roles/iam.workloadIdentityUser"
  member             = local.main_principal
}

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "blackfork"
  description   = "Container images for every plane."
  format        = "DOCKER"
  labels        = local.labels
}
