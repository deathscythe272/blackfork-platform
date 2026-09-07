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
