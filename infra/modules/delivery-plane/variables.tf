variable "project_id" {
  description = "GCP project id. Never committed; comes from a tfvars file or TF_VAR_project_id."
  type        = string
}

variable "region" {
  description = "Region for regional resources."
  type        = string
  default     = "us-east4"
}

variable "env" {
  description = "Environment copy: dev or demo."
  type        = string
  validation {
    condition     = contains(["dev", "demo"], var.env)
    error_message = "env must be dev or demo (docs/10-foundation/13-taxonomy.md)."
  }
}

variable "labels" {
  description = "Labels every resource carries: plane, system, env, serves-br (docs/10-foundation/13-taxonomy.md)."
  type        = map(string)
  default     = {}
}

variable "github_repository" {
  description = "owner/name of the GitHub repository whose Actions jobs may deploy."
  type        = string
}

variable "apply_roles" {
  description = "Project roles the apply identity holds. Broad by necessity for a root that creates service accounts and bindings; narrowed as the planes settle."
  type        = list(string)
  default = [
    "roles/run.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/resourcemanager.projectIamAdmin",
    "roles/artifactregistry.admin",
    "roles/secretmanager.admin",
    "roles/pubsub.admin",
    "roles/storage.admin",
    "roles/serviceusage.serviceUsageConsumer",
  ]
}
