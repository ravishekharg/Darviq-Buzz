locals {
  apis = [
    "container.googleapis.com",
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.apis)

  service = each.value
  # Leave the APIs enabled on destroy: other things in the project may use
  # them, and re-disabling is slow and can fail on dependent services.
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "buzz" {
  location      = var.region
  repository_id = "buzz"
  format        = "DOCKER"
  description   = "Darviq-Buzz service images"

  depends_on = [google_project_service.apis]
}

# Autopilot: Google manages the nodes and bills per pod resource request, so
# there's no node pool to size and nothing running (or billing) beyond the
# pods themselves. It also enforces NetworkPolicy (Dataplane V2), which the
# k8s/network-policies.yaml manifests rely on.
resource "google_container_cluster" "buzz" {
  name     = var.cluster_name
  location = var.region

  enable_autopilot = true

  # This is a practice deployment meant to be torn down with
  # `terraform destroy`; deletion protection would just block that.
  deletion_protection = false

  release_channel {
    channel = "REGULAR"
  }

  # Let GKE pick pod/service ranges (required to be set explicitly for
  # VPC-native clusters, which Autopilot always is).
  ip_allocation_policy {}

  depends_on = [google_project_service.apis]
}
