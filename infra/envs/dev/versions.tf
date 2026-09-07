terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0, < 8.0"
    }
  }
}

# Partial backend: the bucket name carries the project id, so it comes from
# backend.hcl (ignored by git; see backend.hcl.example) or -backend-config flags in CI.
terraform {
  backend "gcs" {}
}
