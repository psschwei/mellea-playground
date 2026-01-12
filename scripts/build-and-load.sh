#!/usr/bin/env bash
# Build Docker images and load them into kind
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CLUSTER_NAME="mellea"

cd "$PROJECT_ROOT"

# Parse arguments
BUILD_BACKEND=false
BUILD_FRONTEND=false
TAG="latest"

usage() {
    echo "Usage: $0 [--backend] [--frontend] [--all] [--tag <tag>]"
    echo ""
    echo "Options:"
    echo "  --backend   Build and load the backend image"
    echo "  --frontend  Build and load the frontend image"
    echo "  --all       Build and load all images"
    echo "  --tag       Tag for the images (default: latest)"
    exit 1
}

if [ $# -eq 0 ]; then
    usage
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        --backend)
            BUILD_BACKEND=true
            shift
            ;;
        --frontend)
            BUILD_FRONTEND=true
            shift
            ;;
        --all)
            BUILD_BACKEND=true
            BUILD_FRONTEND=true
            shift
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done

# Check cluster exists
if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "Error: Cluster '$CLUSTER_NAME' does not exist."
    echo "Run './scripts/cluster-up.sh' first."
    exit 1
fi

if $BUILD_BACKEND; then
    if [ -f "backend/Dockerfile" ]; then
        echo "==> Building backend image..."
        docker build -t "mellea-backend:${TAG}" backend/
        echo "==> Loading backend image into cluster..."
        kind load docker-image "mellea-backend:${TAG}" --name "$CLUSTER_NAME"
    else
        echo "Warning: backend/Dockerfile not found, skipping backend build"
    fi
fi

if $BUILD_FRONTEND; then
    if [ -f "frontend/Dockerfile" ]; then
        echo "==> Building frontend image..."
        docker build -t "mellea-frontend:${TAG}" frontend/
        echo "==> Loading frontend image into cluster..."
        kind load docker-image "mellea-frontend:${TAG}" --name "$CLUSTER_NAME"
    else
        echo "Warning: frontend/Dockerfile not found, skipping frontend build"
    fi
fi

echo ""
echo "==> Build complete!"
