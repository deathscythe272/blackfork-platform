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

variable "platform_events_topic" {
  description = "Data-plane topic to subscribe to."
  type        = string
}

variable "github_repository" {
  description = "owner/repo whose main-branch workflow may become the assurance identity."
  type        = string
}

variable "workload_identity_pool_id" {
  description = "Id of the keyless identity pool the bootstrap root created."
  type        = string
  default     = "github"
}

variable "gateway_signing_key_secret" {
  description = "Secret id of the gateway's signing key; the harness mints its tokens with it."
  type        = string
}

variable "services_under_test" {
  description = "Cloud Run service names the harness needs the addresses of, keyed by role."
  type        = map(string)
}
