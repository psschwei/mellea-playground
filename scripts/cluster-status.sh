#!/usr/bin/env bash
# Show status of the Mellea kind cluster
set -euo pipefail

CLUSTER_NAME="mellea"

# Check cluster exists
if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "Cluster '$CLUSTER_NAME' is not running."
    echo "Run './scripts/cluster-up.sh' to create it."
    exit 1
fi

echo "==> Cluster '$CLUSTER_NAME' Status"
echo ""

echo "--- Nodes ---"
kubectl get nodes -o wide
echo ""

echo "--- Namespaces ---"
kubectl get namespaces -l app.kubernetes.io/part-of=mellea
echo ""

echo "--- Pods (all Mellea namespaces) ---"
for ns in mellea-system mellea-builds mellea-runs mellea-credentials; do
    echo ""
    echo "Namespace: $ns"
    kubectl get pods -n "$ns" 2>/dev/null || echo "  (no pods)"
done
echo ""

echo "--- Services ---"
kubectl get services -n mellea-system
echo ""

echo "--- PersistentVolumes ---"
kubectl get pv -l app.kubernetes.io/part-of=mellea
echo ""

echo "--- PersistentVolumeClaims ---"
kubectl get pvc -n mellea-system
echo ""

echo "--- Resource Quotas ---"
for ns in mellea-builds mellea-runs; do
    echo ""
    echo "Namespace: $ns"
    kubectl get resourcequota -n "$ns" 2>/dev/null || echo "  (none)"
done
