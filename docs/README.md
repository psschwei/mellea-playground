# Mellea Playground Documentation

Documentation for the Mellea Playground program execution platform.

## Guides

| Document | Description |
|----------|-------------|
| [Quickstart](./quickstart.md) | Get started in minutes |
| [Program Execution](./program-execution.md) | Detailed guide to running programs |
| [API Reference](./api-reference.md) | REST API documentation |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Mellea Playground                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │   Program    │   │ Environment  │   │     Run      │    │
│  │   Assets     │──▶│   Builder    │──▶│   Executor   │    │
│  └──────────────┘   └──────────────┘   └──────────────┘    │
│         │                  │                  │             │
│         ▼                  ▼                  ▼             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │  Workspace   │   │    Docker    │   │  Kubernetes  │    │
│  │   Storage    │   │   Registry   │   │    Jobs      │    │
│  └──────────────┘   └──────────────┘   └──────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Key Components

### Asset Catalog
Stores program metadata, dependencies, and workspace files. Supports programs, models, and compositions.

### Environment Builder
Builds Docker images using a two-layer caching strategy:
- **Dependency layer**: Cached based on requirements hash
- **Program layer**: Rebuilt on code changes

### Environment Service
Manages environment lifecycle with strict state machine:
`CREATING → READY → STARTING → RUNNING → STOPPING → STOPPED`

### Run Executor
Orchestrates program execution:
1. Creates Kubernetes Jobs
2. Monitors execution status
3. Handles completion/failure

## Quick Links

- **API Docs**: `http://localhost:8000/docs` (when running)
- **Design Specs**: [/spec/](../spec/) directory
- **Source Code**: [/backend/src/mellea_api/](../backend/src/mellea_api/)

## Development

```bash
# Install dependencies
cd backend
pip install -e ".[dev]"

# Run tests
pytest

# Start server
uvicorn mellea_api.main:app --reload
```
