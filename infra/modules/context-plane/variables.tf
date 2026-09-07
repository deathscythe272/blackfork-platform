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

variable "lakehouse_bucket" {
  description = "Data-plane bucket the evidence server may read."
  type        = string
}
