# These five values become GitHub repository variables (not secrets: none is sensitive)
# so the plan and apply workflows can find the project.
output "state_bucket" {
  value = module.delivery.state_bucket
}

output "workload_identity_provider" {
  value = module.delivery.workload_identity_provider
}

output "plan_service_account" {
  value = module.delivery.plan_service_account
}

output "apply_service_account" {
  value = module.delivery.apply_service_account
}

output "image_registry" {
  value = module.delivery.image_registry
}
