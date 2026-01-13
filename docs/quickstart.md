# Quickstart Guide

Get started running Python programs in Mellea Playground in minutes.

## Prerequisites

- Kubernetes cluster with `kubectl` configured
- Docker installed (for local builds)
- Python 3.11+

## Step 1: Start the API Server

```bash
cd backend
pip install -e ".[dev]"
uvicorn mellea_api.main:app --reload
```

The API will be available at `http://localhost:8000`.

## Step 2: Create Your First Program

### Using the API

```bash
# Create a program asset
curl -X POST http://localhost:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{
    "type": "program",
    "name": "Hello World",
    "entrypoint": "main.py",
    "dependencies": {
      "source": "requirements",
      "packages": [],
      "pythonVersion": "3.12"
    }
  }'
```

Save the returned `id` (e.g., `prog-abc123`).

### Using Python SDK

```python
from mellea_api.services.assets import get_asset_service
from mellea_api.models.assets import CreateProgramRequest, DependencySpec

asset_service = get_asset_service()

program = asset_service.create_program(CreateProgramRequest(
    name="Hello World",
    description="My first program",
    entrypoint="main.py",
    dependencies=DependencySpec(
        source="requirements",
        packages=[],
        python_version="3.12"
    )
))

print(f"Created program: {program.id}")
```

## Step 3: Add Program Code

Write your Python code to the workspace:

```python
# Using the SDK
asset_service.write_workspace_file(
    program.id,
    "main.py",
    '''
print("Hello from Mellea!")
print("This program runs in an isolated container.")
'''
)
```

Or manually:

```bash
# Get workspace path
WORKSPACE="/data/workspaces/${PROGRAM_ID}"

# Write your code
cat > ${WORKSPACE}/main.py << 'EOF'
print("Hello from Mellea!")
print("This program runs in an isolated container.")
EOF
```

## Step 4: Build the Container Image

```python
from mellea_api.services.environment_builder import get_environment_builder_service

builder = get_environment_builder_service()

# Build the image
result = builder.build_image(
    program=program,
    workspace_path=f"/data/workspaces/{program.id}"
)

if result.success:
    print(f"Built image: {result.image_tag}")
    print(f"Build time: {result.total_duration_seconds:.1f}s")
    print(f"Cache hit: {result.cache_hit}")
else:
    print(f"Build failed: {result.error_message}")
```

## Step 5: Create an Environment

```python
from mellea_api.services.environment import get_environment_service
from mellea_api.models.environment import ResourceLimits

env_service = get_environment_service()

# Create environment with the built image
env = env_service.create_environment(
    program_id=program.id,
    image_tag=result.image_tag,
    resource_limits=ResourceLimits(
        cpu_cores=1,
        memory_mb=512,
        timeout_seconds=300
    )
)

# Mark it ready
env = env_service.mark_ready(env.id)
print(f"Environment ready: {env.id}")
```

## Step 6: Run the Program

```python
from mellea_api.services.run import get_run_service
from mellea_api.services.run_executor import get_run_executor
import time

run_service = get_run_service()
executor = get_run_executor()

# Create a run
run = run_service.create_run(
    environment_id=env.id,
    program_id=program.id
)
print(f"Created run: {run.id}")

# Submit to Kubernetes
run = executor.submit_run(run.id, entrypoint="main.py")
print(f"Submitted run, job: {run.job_name}")

# Wait for completion
while run.status not in ["SUCCEEDED", "FAILED", "CANCELLED"]:
    time.sleep(2)
    run = executor.sync_run_status(run.id)
    print(f"  Status: {run.status}")

# Check result
print(f"\nFinal status: {run.status}")
if run.exit_code is not None:
    print(f"Exit code: {run.exit_code}")
if run.error_message:
    print(f"Error: {run.error_message}")
```

## Complete Example Script

Here's a complete script that runs through all steps:

```python
#!/usr/bin/env python3
"""Run a simple program in Mellea Playground."""

import time
from mellea_api.services.assets import get_asset_service
from mellea_api.services.environment import get_environment_service
from mellea_api.services.environment_builder import get_environment_builder_service
from mellea_api.services.run import get_run_service
from mellea_api.services.run_executor import get_run_executor
from mellea_api.models.assets import CreateProgramRequest, DependencySpec, PackageRef
from mellea_api.models.environment import ResourceLimits

def main():
    # Initialize services
    asset_service = get_asset_service()
    env_service = get_environment_service()
    builder = get_environment_builder_service()
    run_service = get_run_service()
    executor = get_run_executor()

    # 1. Create program
    print("Creating program...")
    program = asset_service.create_program(CreateProgramRequest(
        name="Data Fetcher",
        description="Fetches data from an API",
        entrypoint="main.py",
        dependencies=DependencySpec(
            source="requirements",
            packages=[
                PackageRef(name="requests", version=">=2.28.0"),
                PackageRef(name="rich")
            ],
            python_version="3.12"
        )
    ))
    print(f"  Created: {program.id}")

    # 2. Write program code
    print("Writing program code...")
    asset_service.write_workspace_file(
        program.id,
        "main.py",
        '''
import requests
from rich import print as rprint
from rich.panel import Panel

def main():
    rprint(Panel("Data Fetcher Starting", style="bold green"))

    response = requests.get("https://httpbin.org/json")
    data = response.json()

    rprint("[bold]Response received![/bold]")
    rprint(f"Status: {response.status_code}")
    rprint(f"Data keys: {list(data.keys())}")

    rprint(Panel("Complete!", style="bold blue"))

if __name__ == "__main__":
    main()
'''
    )

    # 3. Build image
    print("Building container image...")
    workspace = f"/data/workspaces/{program.id}"
    result = builder.build_image(program, workspace)

    if not result.success:
        print(f"  Build failed: {result.error_message}")
        return

    print(f"  Image: {result.image_tag}")
    print(f"  Cache hit: {result.cache_hit}")
    print(f"  Duration: {result.total_duration_seconds:.1f}s")

    # 4. Create environment
    print("Creating environment...")
    env = env_service.create_environment(
        program_id=program.id,
        image_tag=result.image_tag,
        resource_limits=ResourceLimits(
            cpu_cores=1,
            memory_mb=512,
            timeout_seconds=300
        )
    )
    env = env_service.mark_ready(env.id)
    print(f"  Environment: {env.id}")

    # 5. Execute program
    print("Executing program...")
    run = run_service.create_run(env.id, program.id)
    run = executor.submit_run(run.id, entrypoint="main.py")
    print(f"  Run: {run.id}")
    print(f"  Job: {run.job_name}")

    # 6. Wait for completion
    print("Waiting for completion...")
    while run.status not in ["SUCCEEDED", "FAILED", "CANCELLED"]:
        time.sleep(2)
        run = executor.sync_run_status(run.id)
        print(f"  Status: {run.status}")

    # 7. Report results
    print("\n" + "="*50)
    print(f"Final Status: {run.status}")
    if run.exit_code is not None:
        print(f"Exit Code: {run.exit_code}")
    if run.error_message:
        print(f"Error: {run.error_message}")
    print("="*50)

    # 8. Cleanup (optional)
    executor.cleanup_completed_job(run.id)
    print("\nJob cleaned up.")

if __name__ == "__main__":
    main()
```

## Next Steps

- **Add dependencies**: Specify packages in `dependencies.packages`
- **Increase resources**: Adjust `cpu_cores`, `memory_mb`, `timeout_seconds`
- **Use caching**: Dependency layers are cached automatically
- **Push to registry**: Set `push=True` in `build_image()` for registry storage

## Troubleshooting

### Build Fails

1. Check workspace has valid Python files
2. Verify dependencies are valid package names
3. Check Docker daemon is running

### Run Fails to Start

1. Verify Kubernetes cluster is accessible
2. Check image exists: `docker images | grep mellea`
3. Review K8s events: `kubectl -n mellea-runs get events`

### Run Times Out

1. Increase `timeout_seconds` in resource limits
2. Check program doesn't have infinite loops
3. Verify network access if program needs external APIs

### Out of Memory

1. Increase `memory_mb` in resource limits
2. Optimize program memory usage
3. Process data in smaller batches

## Getting Help

- Check API docs at `http://localhost:8000/docs`
- Review spec files in `/spec/` directory
- See detailed guide in [program-execution.md](./program-execution.md)
