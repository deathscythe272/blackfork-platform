variable "project_id" {
  description = "GCP project id, created by hand once with billing linked. Never committed."
  type        = string
}

variable "region" {
  type    = string
  default = "us-east4"
}

variable "github_repository" {
  description = "owner/name of the repository whose Actions jobs may deploy."
  type        = string
}
