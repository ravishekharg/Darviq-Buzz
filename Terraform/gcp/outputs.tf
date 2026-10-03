output "cluster_name" {
  value = google_container_cluster.buzz.name
}

output "registry" {
  description = "Prefix to tag/push images with."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.buzz.repository_id}"
}

output "get_credentials_command" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.buzz.name} --region ${var.region} --project ${var.project_id}"
}
