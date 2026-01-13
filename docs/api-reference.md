# API Reference

This document describes the REST API endpoints for program execution in Mellea Playground.

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

All endpoints require authentication via Bearer token:

```
Authorization: Bearer <token>
```

---

## Assets API

### Create Asset

Create a new program, model, or composition asset.

```http
POST /assets
Content-Type: application/json
```

**Request Body (Program)**

```json
{
  "type": "program",
  "name": "My Program",
  "description": "A Python program",
  "entrypoint": "main.py",
  "projectRoot": "workspaces/prog-xxx",
  "dependencies": {
    "source": "requirements",
    "packages": [
      {"name": "requests", "version": ">=2.28.0"},
      {"name": "numpy", "extras": ["dev"]}
    ],
    "pythonVersion": "3.12"
  },
  "resourceProfile": {
    "cpuCores": 1,
    "memoryMb": 512,
    "timeoutSeconds": 300
  }
}
```

**Response** `201 Created`

```json
{
  "asset": {
    "id": "prog-abc123",
    "type": "program",
    "name": "My Program",
    "description": "A Python program",
    "owner": "user@example.com",
    "entrypoint": "main.py",
    "projectRoot": "workspaces/prog-abc123",
    "dependencies": {
      "source": "requirements",
      "packages": [
        {"name": "requests", "version": ">=2.28.0"},
        {"name": "numpy", "extras": ["dev"]}
      ],
      "pythonVersion": "3.12"
    },
    "resourceProfile": {
      "cpuCores": 1,
      "memoryMb": 512,
      "timeoutSeconds": 300
    },
    "imageBuildStatus": "pending",
    "createdAt": "2026-01-13T10:00:00Z",
    "updatedAt": "2026-01-13T10:00:00Z"
  }
}
```

### Get Asset

Retrieve a specific asset by ID.

```http
GET /assets/{asset_id}
```

**Response** `200 OK`

```json
{
  "asset": {
    "id": "prog-abc123",
    "type": "program",
    ...
  }
}
```

**Error Response** `404 Not Found`

```json
{
  "detail": "Asset not found: prog-xxx"
}
```

### List Assets

List all assets with optional filtering.

```http
GET /assets?type=program&owner=user@example.com
```

**Query Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `type` | string | Filter by asset type: `program`, `model`, `composition` |
| `owner` | string | Filter by owner |
| `tags` | string[] | Filter by tags |

**Response** `200 OK`

```json
{
  "assets": [
    {"id": "prog-abc123", "type": "program", ...},
    {"id": "prog-def456", "type": "program", ...}
  ],
  "total": 2
}
```

### Update Asset

Update an existing asset.

```http
PATCH /assets/{asset_id}
Content-Type: application/json
```

**Request Body**

```json
{
  "name": "Updated Name",
  "description": "Updated description"
}
```

**Response** `200 OK`

### Delete Asset

Delete an asset.

```http
DELETE /assets/{asset_id}
```

**Response** `204 No Content`

---

## Environments API

### Create Environment

Create a new execution environment for a program.

```http
POST /environments
Content-Type: application/json
```

**Request Body**

```json
{
  "programId": "prog-abc123",
  "imageTag": "mellea-prog:abc123",
  "resourceLimits": {
    "cpuCores": 1,
    "memoryMb": 512,
    "timeoutSeconds": 300
  }
}
```

**Response** `201 Created`

```json
{
  "environment": {
    "id": "env-xyz789",
    "programId": "prog-abc123",
    "imageTag": "mellea-prog:abc123",
    "status": "CREATING",
    "resourceLimits": {
      "cpuCores": 1,
      "memoryMb": 512,
      "timeoutSeconds": 300
    },
    "createdAt": "2026-01-13T10:00:00Z",
    "updatedAt": "2026-01-13T10:00:00Z"
  }
}
```

### Get Environment

```http
GET /environments/{environment_id}
```

**Response** `200 OK`

```json
{
  "environment": {
    "id": "env-xyz789",
    "programId": "prog-abc123",
    "imageTag": "mellea-prog:abc123",
    "status": "READY",
    ...
  }
}
```

### Update Environment Status

Update the status of an environment.

```http
PATCH /environments/{environment_id}/status
Content-Type: application/json
```

**Request Body**

```json
{
  "status": "READY"
}
```

**Valid Status Transitions**

| From | To |
|------|----|
| CREATING | READY, FAILED |
| READY | STARTING, DELETING |
| STARTING | RUNNING, FAILED |
| RUNNING | STOPPING, FAILED |
| STOPPING | STOPPED |
| STOPPED, FAILED | DELETING |

**Error Response** `400 Bad Request`

```json
{
  "detail": "Invalid state transition: CREATING -> RUNNING"
}
```

### Delete Environment

```http
DELETE /environments/{environment_id}
```

**Response** `204 No Content`

---

## Runs API

### Create Run

Create a new program run.

```http
POST /runs
Content-Type: application/json
```

**Request Body**

```json
{
  "environmentId": "env-xyz789",
  "programId": "prog-abc123"
}
```

**Response** `201 Created`

```json
{
  "run": {
    "id": "run-uvw456",
    "environmentId": "env-xyz789",
    "programId": "prog-abc123",
    "status": "QUEUED",
    "createdAt": "2026-01-13T10:00:00Z"
  }
}
```

### Get Run

```http
GET /runs/{run_id}
```

**Response** `200 OK`

```json
{
  "run": {
    "id": "run-uvw456",
    "environmentId": "env-xyz789",
    "programId": "prog-abc123",
    "status": "SUCCEEDED",
    "jobName": "mellea-run-xyz789ab",
    "exitCode": 0,
    "createdAt": "2026-01-13T10:00:00Z",
    "startedAt": "2026-01-13T10:00:05Z",
    "completedAt": "2026-01-13T10:01:30Z"
  }
}
```

### List Runs

```http
GET /runs?environmentId=env-xyz789&status=SUCCEEDED
```

**Query Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `environmentId` | string | Filter by environment |
| `programId` | string | Filter by program |
| `status` | string | Filter by status: `QUEUED`, `STARTING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED` |

### Submit Run

Submit a queued run for execution.

```http
POST /runs/{run_id}/submit
Content-Type: application/json
```

**Request Body**

```json
{
  "entrypoint": "main.py"
}
```

**Response** `200 OK`

```json
{
  "run": {
    "id": "run-uvw456",
    "status": "STARTING",
    "jobName": "mellea-run-xyz789ab",
    ...
  }
}
```

### Sync Run Status

Synchronize run status with Kubernetes job status.

```http
POST /runs/{run_id}/sync
```

**Response** `200 OK`

```json
{
  "run": {
    "id": "run-uvw456",
    "status": "RUNNING",
    ...
  }
}
```

### Cancel Run

Cancel a running or queued run.

```http
POST /runs/{run_id}/cancel
```

**Response** `200 OK`

```json
{
  "run": {
    "id": "run-uvw456",
    "status": "CANCELLED",
    ...
  }
}
```

### Get Run Logs

```http
GET /runs/{run_id}/logs
```

**Response** `200 OK`

```json
{
  "logs": [
    {
      "timestamp": "2026-01-13T10:00:10Z",
      "stream": "stdout",
      "message": "Starting program..."
    },
    {
      "timestamp": "2026-01-13T10:00:15Z",
      "stream": "stdout",
      "message": "Processing complete"
    }
  ]
}
```

### Stream Run Logs (SSE)

Stream logs in real-time using Server-Sent Events.

```http
GET /runs/{run_id}/logs/stream
Accept: text/event-stream
```

**Response** (SSE stream)

```
event: log
data: {"timestamp": "2026-01-13T10:00:10Z", "stream": "stdout", "message": "Starting..."}

event: log
data: {"timestamp": "2026-01-13T10:00:15Z", "stream": "stdout", "message": "Done"}

event: complete
data: {"status": "SUCCEEDED"}
```

---

## Build API

### Build Image

Build a Docker image for a program.

```http
POST /builds
Content-Type: application/json
```

**Request Body**

```json
{
  "programId": "prog-abc123",
  "forceRebuild": false,
  "push": false
}
```

**Response** `202 Accepted`

```json
{
  "build": {
    "id": "build-xyz789",
    "programId": "prog-abc123",
    "status": "BUILDING",
    "cacheKey": "a1b2c3d4e5f6...",
    "startedAt": "2026-01-13T10:00:00Z"
  }
}
```

### Get Build Status

```http
GET /builds/{build_id}
```

**Response** `200 OK`

```json
{
  "build": {
    "id": "build-xyz789",
    "programId": "prog-abc123",
    "status": "COMPLETE",
    "cacheHit": true,
    "imageTag": "mellea-prog:abc123",
    "totalDurationSeconds": 8.5,
    "startedAt": "2026-01-13T10:00:00Z",
    "completedAt": "2026-01-13T10:00:08Z"
  }
}
```

### Build Status Values

| Status | Description |
|--------|-------------|
| `PREPARING` | Preparing build context |
| `CACHE_LOOKUP` | Checking dependency cache |
| `BUILDING_DEPS` | Building dependency layer |
| `BUILDING_PROGRAM` | Building program layer |
| `COMPLETE` | Build succeeded |
| `FAILED` | Build failed |

---

## Health API

### Health Check

```http
GET /health
```

**Response** `200 OK`

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-01-13T10:00:00Z"
}
```

### Readiness Check

```http
GET /health/ready
```

**Response** `200 OK`

```json
{
  "ready": true,
  "checks": {
    "database": "ok",
    "kubernetes": "ok",
    "registry": "ok"
  }
}
```

---

## Error Responses

All endpoints may return these error responses:

### 400 Bad Request

```json
{
  "detail": "Invalid request body",
  "errors": [
    {"field": "name", "message": "Field is required"}
  ]
}
```

### 401 Unauthorized

```json
{
  "detail": "Missing or invalid authentication token"
}
```

### 403 Forbidden

```json
{
  "detail": "Permission denied"
}
```

### 404 Not Found

```json
{
  "detail": "Resource not found: {id}"
}
```

### 500 Internal Server Error

```json
{
  "detail": "Internal server error",
  "requestId": "req-abc123"
}
```

---

## Rate Limiting

API requests are rate limited:

| Tier | Requests/minute |
|------|-----------------|
| Free | 60 |
| Pro | 300 |
| Enterprise | 1000 |

Rate limit headers are included in responses:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1673528400
```

When rate limited, you'll receive:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
```

```json
{
  "detail": "Rate limit exceeded. Retry after 30 seconds."
}
```
