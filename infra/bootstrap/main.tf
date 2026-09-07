# Bootstrap: run once per project from an operator's machine, before CI can run
# anything. It creates the delivery plane (state bucket, keyless identity, deployers,
# registry). Its own state stays local and is ignored by git; it holds only ids.
#
#   cd infra/bootstrap
#   cp terraform.tfvars.example terraform.tfvars   # fill in the project id
#   terraform init && terraform apply
#
# Serves: BR-5, BR-7, C4.

provider "google" {
  project = var.project_id
  region  = var.region
}

# The cost claim, enforced: a small monthly budget with alerts at half, ninety percent,
# and full, sent to the billing account's default recipients (the owner). C4.
resource "google_billing_budget" "platform" {
  count           = var.billing_account == "" ? 0 : 1
  billing_account = var.billing_account
  display_name    = "blackfork platform, ${var.project_id}"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount_usd)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }
}

data "google_project" "this" {
  project_id = var.project_id
}

module "delivery" {
  source            = "../modules/delivery-plane"
  project_id        = var.project_id
  region            = var.region
  env               = "dev"
  github_repository = var.github_repository
  labels = {
    system    = "platform"
    env       = "dev"
    serves-br = "br5"
  }
}
