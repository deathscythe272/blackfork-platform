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

variable "image_registry" {
  type = string
}

variable "image_tag" {
  type = string
}

variable "gateway_url" {
  description = "The gateway's address; the agent's only data door."
  type        = string
}

variable "gateway_signing_key_secret" {
  description = "Secret id of the gateway signing key: the service verifies callers and mints per-job agent tokens with it."
  type        = string
}

variable "lakehouse_bucket" {
  description = "Bucket that holds draft packets and signatures under packets/."
  type        = string
}

variable "nvidia_api_key_secret" {
  description = "Secret id the agent may read for model access."
  type        = string
}
