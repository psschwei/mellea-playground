#!/usr/bin/env bash
# Create and configure the Mellea kind cluster
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CLUSTER_NAME="mellea"

cd "$PROJECT_ROOT"

echo "==> Creating kind cluster '$CLUSTER_NAME'..."

# Check if cluster already exists
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "Cluster '$CLUSTER_NAME' already exists. Use 'cluster-down.sh' to delete it first."
    exit 1
fi

# Create data directories for PersistentVolumes
echo "==> Creating data directories..."
mkdir -p data/{assets,workspaces,artifacts,redis}

# Create the cluster
kind create cluster --config k8s/overlays/kind/kind-config.yaml

# Wait for cluster to be ready
echo "==> Waiting for cluster to be ready..."
kubectl wait --for=condition=Ready nodes --all --timeout=120s

# Configure containerd to use insecure local registry (containerd 2.x)
echo "==> Configuring local registry..."
docker exec "${CLUSTER_NAME}-control-plane" bash -c '
mkdir -p /etc/containerd/certs.d/kind-registry:5000
cat > /etc/containerd/certs.d/kind-registry:5000/hosts.toml <<EOF
server = "http://kind-registry:5000"

[host."http://kind-registry:5000"]
  capabilities = ["pull", "resolve", "push"]
  skip_verify = true
EOF
systemctl restart containerd
'
# Wait for containerd to restart
sleep 3

# Apply namespaces
echo "==> Creating namespaces..."
kubectl apply -f k8s/base/namespaces/namespaces.yaml

# Apply resource quotas and limit ranges
echo "==> Applying resource quotas..."
kubectl apply -f k8s/base/namespaces/resource-quotas.yaml

# Apply network policies
echo "==> Applying network policies..."
kubectl apply -f k8s/overlays/kind/network-policies.yaml

# Apply storage configuration
echo "==> Configuring storage..."
kubectl apply -f k8s/overlays/kind/storage/storage-class.yaml
kubectl apply -f k8s/overlays/kind/storage/persistent-volumes.yaml
kubectl apply -f k8s/overlays/kind/storage/persistent-volume-claims.yaml

echo ""
echo "==> Cluster '$CLUSTER_NAME' is ready!"
echo ""
echo "Cluster info:"
echo "  - API Server: kubectl cluster-info"
echo "  - Backend port: localhost:8080 (NodePort 30080)"
echo "  - Frontend port: localhost:3000 (NodePort 30000)"
echo "  - Redis port: localhost:6379 (NodePort 30379)"
echo ""
echo "Namespaces:"
kubectl get namespaces -l app.kubernetes.io/part-of=mellea
echo ""
echo "Next steps:"
echo "  1. Build your Docker images"
echo "  2. Load them with: ./scripts/load-image.sh <image-name>"
echo "  3. Deploy your services"
