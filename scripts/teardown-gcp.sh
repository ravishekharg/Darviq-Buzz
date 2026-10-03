#!/usr/bin/env bash
# Remove everything deploy-gcp.sh + Terraform/gcp created, so nothing keeps
# billing. Order matters: delete the namespace FIRST so Kubernetes releases the
# load balancer and persistent disks it created; `terraform destroy` doesn't
# know about those and they would be orphaned (and keep billing) otherwise.
#
#   PROJECT_ID=my-project ./scripts/teardown-gcp.sh
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
CLUSTER="${CLUSTER:-buzz}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ "${FORCE:-}" != "yes" ]; then
  echo "This deletes the Buzz namespace (all data), the GKE cluster and the image registry in project $PROJECT_ID."
  read -r -p "Type the project ID to confirm: " ans
  [ "$ans" = "$PROJECT_ID" ] || { echo "aborted"; exit 1; }
fi

if gcloud container clusters get-credentials "$CLUSTER" --region "$REGION" --project "$PROJECT_ID" 2>/dev/null; then
  kubectl delete namespace darviq-buzz --ignore-not-found --timeout=600s
fi

cd "$ROOT/Terraform/gcp"
GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token)" \
  terraform destroy -auto-approve -var "project_id=$PROJECT_ID" -var "region=$REGION" -var "cluster_name=$CLUSTER"

echo "Done. Verify nothing is left billing: gcloud compute disks list --project $PROJECT_ID; gcloud compute forwarding-rules list --project $PROJECT_ID"
