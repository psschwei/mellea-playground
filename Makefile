# Mellea Playground Makefile
.PHONY: help cluster-up cluster-down cluster-status build load redis-cli clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

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

# Development helpers
redis-cli: ## Open Redis CLI
	kubectl exec -it -n mellea-system deployment/redis -- redis-cli

logs-redis: ## Tail Redis logs
	kubectl logs -f -n mellea-system deployment/redis

# Cleanup
clean: ## Remove data directories (preserves cluster)
	rm -rf data/

clean-all: cluster-down clean ## Delete cluster and all data
