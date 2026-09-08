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

variable "image_tag" {
  description = "Tag of the services and policy images to run. CI passes the commit it built; a plan reads the deployed tag from the state bucket."
  type        = string
}
