# Program Execution Guide

This guide explains how to run Python programs in isolated containers using the Mellea Playground execution system.

## Overview

The program execution system provides a complete pipeline for running user programs:

```
Program Asset → Environment Build → Image Registry → K8s Job → Run Tracking
```

### Key Components

| Component | Purpose |
|-----------|---------|
| **Asset Catalog** | Stores program metadata, dependencies, and workspace files |
| **EnvironmentBuilder** | Builds Docker images with intelligent layer caching |
| **EnvironmentService** | Manages environment lifecycle with state machine |
| **RunService** | Manages program execution lifecycle |
| **RunExecutor** | Orchestrates K8s job submission and status sync |

## Quick Start

### 1. Create a Program Asset

```bash
curl -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{
    "type": "program",
    "name": "Hello World",
    "description": "A simple test program",
    "entrypoint": "main.py",
    "dependencies": {
      "source": "requirements",
      "packages": [
        {"name": "requests", "version": ">=2.28.0"}
      ],
      "pythonVersion": "3.12"
    },
    "resourceProfile": {
      "cpuCores": 1,
      "memoryMb": 512,
      "timeoutSeconds": 300
    }
  }'
```

Response:
```json
{
  "asset": {
    "id": "prog-abc123",
    "name": "Hello World",
    "type": "program",
    ...
  }
}
```

### 2. Upload Program Code

Write your Python code to the program's workspace:

```python
# main.py
import requests

def main():
    response = requests.get("https://httpbin.org/json")
    print(f"Status: {response.status_code}")
    print(f"Data: {response.json()}")

if __name__ == "__main__":
    main()
```

### 3. Build the Environment

The environment builder creates a Docker image for your program using a two-layer strategy:

1. **Dependency Layer** (cached): Contains Python + installed packages
2. **Program Layer**: Contains your source code

```python
from mellea_api.services.environment_builder import get_environment_builder_service
from mellea_api.services.assets import get_asset_service

builder = get_environment_builder_service()
asset_service = get_asset_service()

program = asset_service.get_program("prog-abc123")
workspace = f"/data/workspaces/{program.id}"

result = builder.build_image(program, workspace)

if result.success:
    print(f"Image built: {result.image_tag}")
    print(f"Cache hit: {result.cache_hit}")
else:
    print(f"Build failed: {result.error_message}")
```

### 4. Create an Environment

```python
from mellea_api.services.environment import get_environment_service

env_service = get_environment_service()

env = env_service.create_environment(
    program_id="prog-abc123",
    image_tag=result.image_tag,
    resource_limits={
        "cpu_cores": 1,
        "memory_mb": 512,
        "timeout_seconds": 300
    }
)

# Mark ready after successful build
env = env_service.mark_ready(env.id)
```

### 5. Execute the Program

```python
from mellea_api.services.run import get_run_service
from mellea_api.services.run_executor import get_run_executor

run_service = get_run_service()
executor = get_run_executor()

# Create a run
run = run_service.create_run(
    environment_id=env.id,
    program_id="prog-abc123"
)

# Submit to Kubernetes
run = executor.submit_run(run.id, entrypoint="main.py")

# Monitor execution
import time
while run.status not in ["SUCCEEDED", "FAILED", "CANCELLED"]:
    time.sleep(2)
    run = executor.sync_run_status(run.id)
    print(f"Status: {run.status}")

print(f"Final status: {run.status}")
if run.exit_code is not None:
    print(f"Exit code: {run.exit_code}")
```

## Data Models

### ProgramAsset

```python
@dataclass
class ProgramAsset:
    id: str                    # Unique identifier
    name: str                  # Display name
    description: str           # Program description
    owner: str                 # Owner username
    type: str = "program"
    entrypoint: str            # Main Python file (e.g., "main.py")
    project_root: str          # Workspace path
    dependencies: DependencySpec
    exported_slots: List[str]  # @generative entry points
    resource_profile: ResourceProfile
    image_tag: Optional[str]   # Docker image reference
    image_build_status: str    # pending/building/ready/failed
```

### DependencySpec

```python
@dataclass
class DependencySpec:
    source: str                # "requirements" or "pyproject"
    packages: List[PackageRef]
    python_version: str        # "3.11" or "3.12"
```

### Environment

```python
@dataclass
class Environment:
    id: str
    program_id: str
    image_tag: str
    status: EnvironmentStatus  # CREATING → READY → RUNNING → etc.
    container_id: Optional[str]
    resource_limits: ResourceLimits
    created_at: datetime
    updated_at: datetime
```

### Run

```python
@dataclass
class Run:
    id: str
    environment_id: str
    program_id: str
    status: RunExecutionStatus  # QUEUED → STARTING → RUNNING → SUCCEEDED/FAILED
    job_name: Optional[str]     # K8s Job name
    exit_code: Optional[int]
    error_message: Optional[str]
    output_path: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
```

## State Machines

### Environment Lifecycle

```
┌─────────────┐
│  CREATING   │  Initial state after creation
└──────┬──────┘
       │
       ├─→ READY (build succeeded) ──→ STARTING → RUNNING → STOPPING → STOPPED
       │                                            ↓         (graceful)
       └─→ FAILED (build failed) ──────────────────────────────────────→ DELETING
```

Valid transitions:
- `CREATING` → `READY`, `FAILED`
- `READY` → `STARTING`, `DELETING`
- `STARTING` → `RUNNING`, `FAILED`
- `RUNNING` → `STOPPING`, `FAILED`
- `STOPPING` → `STOPPED`
- `STOPPED`, `FAILED` → `DELETING`

### Run Execution

```
┌─────────────┐
│   QUEUED    │  Initial state
└──────┬──────┘
       │
       ├─→ STARTING (job created) → RUNNING → SUCCEEDED (exit 0)
       │                              ↓
       │                           FAILED (exit != 0)
       │
       └─→ CANCELLED (user action)
```

Terminal states: `SUCCEEDED`, `FAILED`, `CANCELLED`

## Layer Caching

The build system uses a two-layer caching strategy to speed up builds:

### How It Works

1. **Cache Key Computation**: A SHA256 hash is computed from the normalized dependency specification (sorted packages, Python version)

2. **Dependency Layer**: If the cache key matches an existing image, that layer is reused. Otherwise, a new dependency image is built.

3. **Program Layer**: Always rebuilt on top of the dependency layer since source code changes frequently.

### Cache Benefits

| Scenario | Build Time |
|----------|------------|
| First build (no cache) | ~60-120s |
| Same dependencies (cache hit) | ~5-10s |
| Different dependencies (cache miss) | ~60-120s |

### Cache Management

```python
from mellea_api.services.environment_builder import get_environment_builder_service

builder = get_environment_builder_service()

# Check cache status
cache_key = builder.compute_cache_key(program.dependencies)
cached = builder.get_cached_layer(cache_key)

if cached:
    print(f"Cache hit: {cached.image_tag}")
else:
    print("Cache miss - will rebuild dependencies")

# Force rebuild (ignores cache)
result = builder.build_image(program, workspace, force_rebuild=True)

# Prune stale cache entries (>30 days unused)
builder.prune_stale_cache_entries(max_age_days=30)
```

## Kubernetes Integration

### Job Specification

Programs run as Kubernetes Jobs with the following configuration:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: mellea-run-{environment_id[:8]}
  namespace: mellea-runs
  labels:
    app.kubernetes.io/part-of: mellea
    mellea.io/environment-id: {env_id}
    mellea.io/job-type: run
spec:
  backoffLimit: 0
  activeDeadlineSeconds: {timeout_seconds}
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: Never
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
      containers:
        - name: program
          image: {image_tag}
          command: ["python", "{entrypoint}"]
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: [ALL]
          resources:
            requests:
              cpu: {cpu_cores / 2}
              memory: {memory_mb / 2}Mi
            limits:
              cpu: {cpu_cores}
              memory: {memory_mb}Mi
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            - name: output
              mountPath: /output
      volumes:
        - name: tmp
          emptyDir:
            medium: Memory
        - name: output
          emptyDir: {}
```

### Security Features

- **Non-root execution**: Programs run as UID 1000
- **Read-only root filesystem**: Only `/tmp` and `/output` are writable
- **Dropped capabilities**: All Linux capabilities are dropped
- **No privilege escalation**: Containers cannot gain additional privileges
- **Timeout enforcement**: Jobs are killed after `activeDeadlineSeconds`
- **Auto-cleanup**: Jobs are deleted 1 hour after completion

## Resource Profiles

### Default Profiles

| Profile | CPU | Memory | Timeout |
|---------|-----|--------|---------|
| Small | 0.5 cores | 512 MB | 5 min |
| Medium | 1 core | 1 GB | 30 min |
| Large | 2 cores | 4 GB | 60 min |

### Custom Resources

```python
resource_profile = ResourceProfile(
    cpu_cores=2,
    memory_mb=2048,
    timeout_seconds=1800
)
```

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `EnvironmentNotFoundError` | Invalid environment ID | Verify environment exists |
| `InvalidStateTransitionError` | Invalid status change | Check state machine diagram |
| `ImagePullBackOff` | Image doesn't exist | Rebuild environment |
| `OOMKilled` | Out of memory | Increase `memory_mb` |
| `DeadlineExceeded` | Timeout | Increase `timeout_seconds` |

### Error Classification

The system classifies errors as:

1. **User Code Errors**: Python exceptions, syntax errors, runtime errors
2. **Infrastructure Errors**: OOM, network issues, permission errors

## File Locations

| File | Purpose |
|------|---------|
| `backend/src/mellea_api/models/assets.py` | Asset data models |
| `backend/src/mellea_api/models/environment.py` | Environment model |
| `backend/src/mellea_api/models/run.py` | Run model with state machine |
| `backend/src/mellea_api/models/build.py` | Build context and cache models |
| `backend/src/mellea_api/services/assets.py` | Asset CRUD operations |
| `backend/src/mellea_api/services/environment_builder.py` | Docker image builder |
| `backend/src/mellea_api/services/environment.py` | Environment lifecycle |
| `backend/src/mellea_api/services/run.py` | Run lifecycle |
| `backend/src/mellea_api/services/k8s_jobs.py` | K8s Job operations |
| `backend/src/mellea_api/services/run_executor.py` | Run orchestration |

## Data Persistence

Data is stored in JSON files:

```
/data/
├── metadata/
│   ├── programs.json       # ProgramAsset store
│   ├── models.json         # ModelAsset store
│   ├── compositions.json   # CompositionAsset store
│   ├── environments.json   # Environment store
│   ├── runs.json           # Run store
│   └── layer_cache.json    # Build cache entries
└── workspaces/
    ├── {program_id_1}/
    │   └── main.py
    └── {program_id_2}/
        └── src/
            └── main.py
```
