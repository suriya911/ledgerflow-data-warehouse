#!/usr/bin/env bash
# ecr_push.sh — Build the Airflow Docker image and push to AWS ECR.
#
# Run this manually for the first push, or when you need to force-push
# outside of CI (e.g., hotfix on a broken ECS task).
# CI (GitHub Actions) calls the same steps automatically on merge to main.
#
# Usage:
#   chmod +x aws/ecr_push.sh
#   ./aws/ecr_push.sh
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker running
#   - IAM user has ECR push permissions (aws/iam_policy.json)

set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────────────
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="ledgerflow-airflow"
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
IMAGE_URI="${REGISTRY}/${ECR_REPO}"
# Tag with git SHA for traceability; also tag as 'latest' for ECS
GIT_SHA=$(git rev-parse --short HEAD)

echo "=== LedgerFlow ECR Push ==="
echo "Account : $ACCOUNT_ID"
echo "Region  : $REGION"
echo "Registry: $REGISTRY"
echo "Image   : ${IMAGE_URI}:${GIT_SHA}"
echo ""

# ── Step 1: Create ECR repository if it doesn't exist ──────────────────────
echo "--- Step 1: Ensure ECR repository exists ---"
aws ecr describe-repositories \
  --repository-names "$ECR_REPO" \
  --region "$REGION" \
  > /dev/null 2>&1 || \
aws ecr create-repository \
  --repository-name "$ECR_REPO" \
  --region "$REGION" \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256
echo "Repository: $IMAGE_URI"

# ── Step 2: Authenticate Docker to ECR ─────────────────────────────────────
echo ""
echo "--- Step 2: Docker login to ECR ---"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

# ── Step 3: Build the Docker image ─────────────────────────────────────────
echo ""
echo "--- Step 3: Build Docker image ---"
# Run from repo root so COPY commands in Dockerfile resolve correctly
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

docker build \
  --file "$REPO_ROOT/airflow/Dockerfile" \
  --tag "${IMAGE_URI}:${GIT_SHA}" \
  --tag "${IMAGE_URI}:latest" \
  "$REPO_ROOT"

# ── Step 4: Push to ECR ─────────────────────────────────────────────────────
echo ""
echo "--- Step 4: Push to ECR ---"
docker push "${IMAGE_URI}:${GIT_SHA}"
docker push "${IMAGE_URI}:latest"

echo ""
echo "=== Push complete ==="
echo "SHA tag : ${IMAGE_URI}:${GIT_SHA}"
echo "Latest  : ${IMAGE_URI}:latest"
echo ""
echo "Next step: update ECS service to use the new image:"
echo "  aws ecs update-service \\"
echo "    --cluster ledgerflow-cluster \\"
echo "    --service ledgerflow-airflow \\"
echo "    --force-new-deployment"
