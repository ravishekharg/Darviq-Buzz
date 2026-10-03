#!/usr/bin/env bash
# Deploy Darviq-Buzz to the Amazon EKS cluster created by Terraform/aws.
#
#   ALLOWED_CIDR=203.0.113.7/32 ./scripts/deploy-eks.sh
#
# Prerequisites: AWS CLI configured for the account (`aws sts get-caller-identity`
# works), `terraform apply` done in Terraform/aws, Docker running, kubectl
# installed. Safe to re-run: existing
# secrets are reused, never rotated (Postgres is already initialised with them).
#
# Local dry run against a throwaway kind cluster (no AWS account needed) --
# runs the same overlay, secret generation and ordering, skipping only what is
# truly AWS-specific (ECR login and push, kubeconfig, the load-balancer wait):
#
#   kind create cluster --name buzz-test
#   LOCAL_KIND=buzz-test ./scripts/deploy-eks.sh
set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

LOCAL_KIND="${LOCAL_KIND:-}"
if [ -n "$LOCAL_KIND" ]; then
  ALLOWED_CIDR="${ALLOWED_CIDR:-127.0.0.1/32}"
else
  : "${ALLOWED_CIDR:?set ALLOWED_CIDR to the CIDR allowed to reach the app, e.g. \$(curl -s ifconfig.me)/32}"
fi
REGION="${REGION:-ap-south-1}"
CLUSTER="${CLUSTER:-buzz}"
NS=darviq-buzz
TAG="${TAG:-$(date +%Y%m%d-%H%M%S)}"
if [ -n "$LOCAL_KIND" ]; then REGISTRY="buzz-local"; ACCOUNT=local
else
  command -v aws >/dev/null || die "aws CLI not found on PATH"
  ACCOUNT="$(aws sts get-caller-identity --query Account --output text)" || die "AWS CLI is not logged in"
  REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/buzz"
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# No TLS on this deployment, so passwords and session cookies travel in
# cleartext -- it must not be open to the whole internet.
if [ "$ALLOWED_CIDR" = "0.0.0.0/0" ] && [ "${I_UNDERSTAND_OPEN_TO_INTERNET:-}" != "yes" ]; then
  die "ALLOWED_CIDR=0.0.0.0/0 exposes an unencrypted login page to the internet. Set I_UNDERSTAND_OPEN_TO_INTERNET=yes to override."
fi

if [ -n "$LOCAL_KIND" ]; then NEEDED="docker kubectl kind"; else NEEDED="aws docker kubectl"; fi
for t in $NEEDED; do command -v "$t" >/dev/null || die "$t not found on PATH"; done

SERVICES="user-service social-graph-service post-service engagement-service story-service messaging-service feed-service notification-service media-service gateway web-bff"

echo "==> Account=$ACCOUNT region=$REGION registry=$REGISTRY tag=$TAG allowed=$ALLOWED_CIDR"

echo "==> Building images"
[ -n "$LOCAL_KIND" ] || aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${REGISTRY%%/*}" >/dev/null
for svc in $SERVICES; do
  echo "   - $svc"
  docker build -q -t "$REGISTRY/$svc:$TAG" "$ROOT/services/$svc" >/dev/null
  if [ -n "$LOCAL_KIND" ]; then
    kind load docker-image "$REGISTRY/$svc:$TAG" --name "$LOCAL_KIND" >/dev/null
  else
    docker push -q "$REGISTRY/$svc:$TAG" >/dev/null
  fi
done

echo "==> Connecting to the cluster"
if [ -n "$LOCAL_KIND" ]; then
  kubectl config use-context "kind-$LOCAL_KIND"
else
  aws eks update-kubeconfig --name "$CLUSTER" --region "$REGION"
fi

echo "==> Namespace + secrets"
kubectl apply -f "$ROOT/k8s/namespace.yaml"
if kubectl -n "$NS" get secret buzz-secrets >/dev/null 2>&1; then
  echo "   buzz-secrets already exists -- reusing (not rotating)"
else
  rnd() { openssl rand -hex 24 2>/dev/null || python -c "import secrets; print(secrets.token_hex(24))"; }
  PGPASS="$(rnd)"; RMQPASS="$(rnd)"
  kubectl -n "$NS" create secret generic buzz-secrets \
    --from-literal=POSTGRES_USER=buzz \
    --from-literal=POSTGRES_PASSWORD="$PGPASS" \
    --from-literal=POSTGRES_DB=buzz \
    --from-literal=USER_DATABASE_URL="postgresql://buzz:${PGPASS}@postgres:5432/buzz_users" \
    --from-literal=NOTIFICATION_DATABASE_URL="postgresql://buzz:${PGPASS}@postgres:5432/buzz_notifications" \
    --from-literal=MEDIA_DATABASE_URL="postgresql://buzz:${PGPASS}@postgres:5432/buzz_media" \
    --from-literal=SECRET_KEY="$(rnd)" \
    --from-literal=JWT_SECRET="$(rnd)" \
    --from-literal=RABBITMQ_URL="amqp://buzz:${RMQPASS}@rabbitmq:5672" \
    --from-literal=RABBITMQ_DEFAULT_USER=buzz \
    --from-literal=RABBITMQ_DEFAULT_PASS="$RMQPASS"
  echo "   created buzz-secrets with freshly generated random values"
fi

echo "==> Rendering overlay"
sed -e "s|__REGISTRY__|${REGISTRY}|g" -e "s|__TAG__|${TAG}|g" -e "s|__ALLOWED_CIDR__|${ALLOWED_CIDR}|g" \
  "$ROOT/k8s/eks/kustomization.yaml.tpl" > "$ROOT/k8s/eks/kustomization.yaml"
apply() { kubectl kustomize "$ROOT/k8s/eks" --load-restrictor=LoadRestrictionsNone | kubectl apply -f -; }

echo "==> Applying (first run: EBS volumes and the load balancer are created, so this is slow)"
apply

echo "==> Waiting for datastores"
kubectl -n "$NS" rollout status deploy/postgres --timeout=600s
kubectl -n "$NS" rollout status deploy/rabbitmq --timeout=600s
kubectl -n "$NS" rollout status deploy/cassandra --timeout=900s

# keyspace-init is a one-shot Job created alongside Cassandra; if Cassandra
# wasn't ready in time it will have burned its retries and failed for good
# (this happened on the homelab). Recreate it now that Cassandra is up.
echo "==> Creating Cassandra keyspaces"
kubectl -n "$NS" delete job keyspace-init --ignore-not-found
apply
kubectl -n "$NS" wait --for=condition=complete job/keyspace-init --timeout=300s

echo "==> Waiting for services"
for svc in $SERVICES prometheus alertmanager; do
  kubectl -n "$NS" rollout status "deploy/$svc" --timeout=600s
done

if [ -n "$LOCAL_KIND" ]; then
  echo
  echo "Local dry run complete. kind has no load balancer, so reach the app with:"
  echo "  kubectl -n $NS port-forward svc/web-bff 8000:5010   ->  http://localhost:8000"
  exit 0
fi

echo "==> Waiting for the load balancer address"
HOST=""
for _ in $(seq 1 60); do
  HOST="$(kubectl -n "$NS" get svc web-bff -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
  [ -n "$HOST" ] && break
  sleep 10
done
[ -n "$HOST" ] || die "load balancer has no address yet -- check: kubectl -n $NS get svc web-bff"

echo
echo "Darviq-Buzz is up:  http://${HOST}   (DNS can take a few minutes to resolve)"
echo "Reachable only from: ${ALLOWED_CIDR}   (no TLS -- do not enter a password you reuse elsewhere)"
echo "Tear down when done: ./scripts/teardown-eks.sh"
