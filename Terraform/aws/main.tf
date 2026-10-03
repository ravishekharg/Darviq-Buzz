data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  services = [
    "user-service", "social-graph-service", "post-service", "engagement-service",
    "story-service", "messaging-service", "feed-service", "notification-service",
    "media-service", "gateway", "web-bff",
  ]
}

# --- Network ---------------------------------------------------------------
# Nodes live in private subnets; the public subnets hold the NAT gateway and
# the load balancer Kubernetes creates for web-bff. One NAT gateway (not one
# per AZ) keeps a demo deployment cheap.
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.cluster_name}-vpc"
  cidr = var.vpc_cidr
  azs  = local.azs

  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i)]
  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 10)]

  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true

  # Tags the in-tree AWS cloud provider uses to place load balancers.
  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}

# --- EKS ---------------------------------------------------------------------
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Public API endpoint so deploy-eks.sh can run from a laptop; access is
  # still controlled by IAM. The identity running Terraform becomes admin.
  cluster_endpoint_public_access           = true
  enable_cluster_creator_admin_permissions = true

  cluster_addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni = {
      # k8s/network-policies.yaml relies on NetworkPolicy being enforced;
      # the VPC CNI only does that when this is switched on.
      configuration_values = jsonencode({ enableNetworkPolicy = "true" })
    }
    # PersistentVolumeClaims (Postgres, Cassandra, media uploads) need the
    # EBS CSI driver on current EKS versions.
    aws-ebs-csi-driver = {
      service_account_role_arn = module.ebs_csi_irsa.iam_role_arn
    }
  }

  eks_managed_node_groups = {
    default = {
      instance_types = [var.node_instance_type]
      min_size       = 1
      max_size       = var.node_count + 1
      desired_size   = var.node_count
    }
  }
}

# IAM role for the EBS CSI driver's service account (IRSA), so the driver can
# create and attach volumes without giving the nodes that permission.
module "ebs_csi_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name             = "${var.cluster_name}-ebs-csi"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }
}

# --- Image registry ----------------------------------------------------------
resource "aws_ecr_repository" "service" {
  for_each = toset(local.services)

  name                 = "buzz/${each.value}"
  image_tag_mutability = "IMMUTABLE"
  # Lets `terraform destroy` remove repositories that still hold images.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Keep the registry from growing forever: only the 10 newest images per service.
resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the 10 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
