variable "project_id" {
  description = "GCP project ID to deploy into (billing must already be enabled on it)."
  type        = string
}

variable "region" {
  description = "Region for the Autopilot cluster and the Artifact Registry repo."
  type        = string
  default     = "us-central1"
}

variable "cluster_name" {
  description = "Name of the GKE Autopilot cluster."
  type        = string
  default     = "buzz"
}
