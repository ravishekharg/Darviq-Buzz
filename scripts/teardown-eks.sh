#!/usr/bin/env bash
# Remove everything deploy-eks.sh + Terraform/aws created, so nothing keeps
# billing. Order matters: delete the namespace FIRST so Kubernetes releases the
# load balancer and EBS volumes it created; `terraform destroy` doesn't know
# about those, and the VPC can't be deleted while the load balancer exists.
#
#   ./scripts/teardown-eks.sh
set -euo pipefail

REGION="${REGION:-ap-south-1}"
CLUSTER="${CLUSTER:-buzz}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"

if [ "${FORCE:-}" != "yes" ]; then
  echo "This deletes the Buzz namespace (all data), the EKS cluster, its VPC and the ECR repositories in account $ACCOUNT ($REGION)."
  read -r -p "Type the cluster name to confirm: " ans
  [ "$ans" = "$CLUSTER" ] || { echo "aborted"; exit 1; }
fi

if aws eks update-kubeconfig --name "$CLUSTER" --region "$REGION" >/dev/null 2>&1; then
  kubectl delete namespace darviq-buzz --ignore-not-found --timeout=600s
  # Give AWS a moment to finish deleting the load balancer before the VPC goes.
  sleep 60
fi

cd "$ROOT/Terraform/aws"
terraform destroy -auto-approve -var "region=$REGION" -var "cluster_name=$CLUSTER"

echo "Done. Check nothing is left billing:"
echo "  aws elb describe-load-balancers --region $REGION"
echo "  aws ec2 describe-volumes --region $REGION --filters Name=tag-key,Values=kubernetes.io/created-for/pvc/name"
