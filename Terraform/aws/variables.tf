variable "region" {
  description = "AWS region for the VPC, EKS cluster and ECR repositories."
  type        = string
  default     = "ap-south-1"
}

variable "cluster_name" {
  description = "Name of the EKS cluster (also used to name the VPC)."
  type        = string
  default     = "buzz"
}

variable "kubernetes_version" {
  description = "EKS control plane version."
  type        = string
  default     = "1.31"
}

variable "node_instance_type" {
  description = "Instance type for the managed node group. Cassandra alone asks for 3Gi, so 8 GiB nodes are the practical floor."
  type        = string
  default     = "t3.large"
}

variable "node_count" {
  description = "Desired number of worker nodes."
  type        = number
  default     = 2
}

variable "vpc_cidr" {
  description = "CIDR block for the cluster VPC."
  type        = string
  default     = "10.40.0.0/16"
}
