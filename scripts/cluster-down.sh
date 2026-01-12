#!/usr/bin/env bash
# Delete the Mellea kind cluster
set -euo pipefail

CLUSTER_NAME="mellea"

echo "==> Deleting kind cluster '$CLUSTER_NAME'..."

if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "Cluster '$CLUSTER_NAME' does not exist."
    exit 0
fi

kind delete cluster --name "$CLUSTER_NAME"

echo "==> Cluster '$CLUSTER_NAME' deleted."
echo ""
echo "Note: Data directories (./data/*) have been preserved."
echo "To remove them: rm -rf ./data"
