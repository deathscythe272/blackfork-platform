variable "project_id" {
  description = "GCP project id, created by hand once with billing linked. Never committed."
  type        = string
}

variable "region" {
  type    = string
  default = "us-east4"
}

variable "billing_account" {
  description = "Billing account id for the budget alert (XXXXXX-XXXXXX-XXXXXX). Empty disables the alert. Never committed."
  type        = string
  default     = ""
}

variable "budget_amount_usd" {
  description = "Monthly budget that triggers alerts at 50, 90, and 100 percent."
  type        = number
  default     = 5
}

variable "github_repository" {
  description = "owner/name of the repository whose Actions jobs may deploy."
  type        = string
}
