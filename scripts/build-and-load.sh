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
BUILD_BASE=false
TAG="latest"

usage() {
    echo "Usage: $0 [--backend] [--frontend] [--base] [--all] [--tag <tag>]"
    echo ""
    echo "Options:"
    echo "  --backend   Build and load the backend image"
    echo "  --frontend  Build and load the frontend image"
    echo "  --base      Build and load base Python images (3.11, 3.12)"
    echo "  --all       Build and load all images (includes base images)"
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
        --base)
            BUILD_BASE=true
            shift
            ;;
        --all)
            BUILD_BACKEND=true
            BUILD_FRONTEND=true
            BUILD_BASE=true
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

# Build base images first (other images may depend on them)
if $BUILD_BASE; then
    echo "==> Building base Python images..."

    # Build Python 3.11 base image
    if [ -f "base-images/python/Dockerfile.3.11" ]; then
        echo "    Building mellea-python:3.11..."
        docker build -t "mellea-python:3.11" -f base-images/python/Dockerfile.3.11 base-images/python/
        echo "    Loading mellea-python:3.11 into cluster..."
        kind load docker-image "mellea-python:3.11" --name "$CLUSTER_NAME"
    else
        echo "Warning: base-images/python/Dockerfile.3.11 not found, skipping"
    fi

    # Build Python 3.12 base image
    if [ -f "base-images/python/Dockerfile.3.12" ]; then
        echo "    Building mellea-python:3.12..."
        docker build -t "mellea-python:3.12" -f base-images/python/Dockerfile.3.12 base-images/python/
        echo "    Loading mellea-python:3.12 into cluster..."
        kind load docker-image "mellea-python:3.12" --name "$CLUSTER_NAME"
    else
        echo "Warning: base-images/python/Dockerfile.3.12 not found, skipping"
    fi
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
