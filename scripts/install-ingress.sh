#!/usr/bin/env bash
# Install NGINX Ingress Controller for Kind
# Can be run standalone or called from cluster-up.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# NGINX Ingress Controller version for Kind
# See: https://github.com/kubernetes/ingress-nginx/releases
INGRESS_NGINX_VERSION="v1.14.3"

echo "==> Installing NGINX Ingress Controller ${INGRESS_NGINX_VERSION} for Kind..."

# Apply the official Kind-specific manifest
# Note: GitHub tag format is "controller-vX.Y.Z"
kubectl apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-${INGRESS_NGINX_VERSION}/deploy/static/provider/kind/deploy.yaml"

# Wait for the ingress controller to be ready
echo "==> Waiting for Ingress Controller to be ready..."
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

echo "==> NGINX Ingress Controller is ready!"
echo ""
echo "Ingress endpoints:"
echo "  - HTTP:  http://localhost"
echo "  - HTTPS: https://localhost (self-signed certificate)"
echo ""
echo "To create Ingress resources, use the 'kubernetes.io/ingress.class: nginx' annotation"
echo "or set 'spec.ingressClassName: nginx'"
