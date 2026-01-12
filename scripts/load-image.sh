#!/usr/bin/env bash
# Load a Docker image into the kind cluster
set -euo pipefail

CLUSTER_NAME="mellea"

if [ $# -eq 0 ]; then
    echo "Usage: $0 <image-name> [<image-name>...]"
    echo ""
    echo "Examples:"
    echo "  $0 mellea-backend:latest"
    echo "  $0 mellea-frontend:latest mellea-backend:latest"
    exit 1
fi

# Check cluster exists
if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "Error: Cluster '$CLUSTER_NAME' does not exist."
    echo "Run './scripts/cluster-up.sh' first."
    exit 1
fi

for IMAGE in "$@"; do
    echo "==> Loading image '$IMAGE' into cluster '$CLUSTER_NAME'..."
    kind load docker-image "$IMAGE" --name "$CLUSTER_NAME"
    echo "    Done."
done

echo ""
echo "==> All images loaded successfully."
