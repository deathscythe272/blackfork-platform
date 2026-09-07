variable "project_id" {
  description = "GCP project id. From dev.tfvars locally or TF_VAR_project_id in CI; never committed."
  type        = string
}

variable "region" {
  type    = string
  default = "us-east4"
}

variable "env" {
  type    = string
  default = "dev"
}
