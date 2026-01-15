# Mellea Playground Makefile
.PHONY: help cluster-up cluster-down cluster-status build load deploy redis-cli clean \
        ci-check lint test setup-hooks spin-up-from-scratch

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# CI/Development
setup-hooks: ## Install git hooks for pre-push CI checks
	git config core.hooksPath .githooks
	@echo "Git hooks installed. Pre-push CI checks are now enabled."

ci-check: ## Run all CI checks locally (same as pre-push hook)
	./scripts/ci-check.sh

lint: ## Run linting (ruff + mypy for backend, eslint for frontend)
	@echo "=== Backend Lint ===" && ruff check backend/ && mypy backend/ --ignore-missing-imports
	@if [ -f frontend/package.json ]; then echo "=== Frontend Lint ===" && cd frontend && npm run lint; fi

test: ## Run all tests
	pytest backend/tests/ -v
	@if [ -f frontend/package.json ]; then cd frontend && npm test; fi

# Cluster management
cluster-up: ## Create and configure the kind cluster
	./scripts/cluster-up.sh

cluster-down: ## Delete the kind cluster
	./scripts/cluster-down.sh

cluster-status: ## Show cluster status
	./scripts/cluster-status.sh

# Build and load
build-backend: ## Build backend Docker image
	./scripts/build-and-load.sh --backend

build-frontend: ## Build frontend Docker image
	./scripts/build-and-load.sh --frontend

build-all: ## Build all Docker images
	./scripts/build-and-load.sh --all

load: ## Load a Docker image into kind (usage: make load IMAGE=myimage:tag)
	./scripts/load-image.sh $(IMAGE)

# Deployment
deploy: ## Deploy all resources to the cluster
	kubectl apply -k k8s/

# Development helpers
redis-cli: ## Open Redis CLI
	kubectl exec -it -n mellea-system deployment/redis -- redis-cli

logs-redis: ## Tail Redis logs
	kubectl logs -f -n mellea-system deployment/redis

# Cleanup
clean: ## Remove data directories (preserves cluster)
	rm -rf data/

clean-all: cluster-down clean ## Delete cluster and all data

# Full setup
spin-up-from-scratch: cluster-down cluster-up build-all deploy ## Delete existing cluster, create new one, build images, and deploy
