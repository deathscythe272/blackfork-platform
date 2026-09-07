# The dev environment: every plane except delivery, which bootstrap owns. CI plans
# this root on pull requests and applies it on main. Nothing declared here has idle
# cost: empty buckets, a topic, service accounts, an empty secret.
#
#   cd infra/envs/dev
#   cp backend.hcl.example backend.hcl && cp dev.tfvars.example dev.tfvars   # fill in
#   terraform init -backend-config=backend.hcl
#   terraform plan -var-file=dev.tfvars
#
# Serves: BR-5, C4.

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  labels = {
    system    = "platform"
    env       = var.env
    serves-br = "br5"
  }
}

module "data" {
  source     = "../../modules/data-plane"
  project_id = var.project_id
  region     = var.region
  env        = var.env
  labels     = local.labels
}

module "context" {
  source           = "../../modules/context-plane"
  project_id       = var.project_id
  region           = var.region
  env              = var.env
  labels           = local.labels
  lakehouse_bucket = module.data.lakehouse_bucket
}

module "agent" {
  source                = "../../modules/agent-plane"
  project_id            = var.project_id
  region                = var.region
  env                   = var.env
  labels                = local.labels
  nvidia_api_key_secret = module.context.nvidia_api_key_secret
}

module "assurance" {
  source                = "../../modules/assurance-plane"
  project_id            = var.project_id
  region                = var.region
  env                   = var.env
  labels                = local.labels
  platform_events_topic = module.data.platform_events_topic
}
