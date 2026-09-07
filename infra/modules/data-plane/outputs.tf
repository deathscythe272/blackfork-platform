output "lakehouse_bucket" {
  value = google_storage_bucket.lakehouse.name
}

output "platform_events_topic" {
  value = google_pubsub_topic.platform_events.id
}
