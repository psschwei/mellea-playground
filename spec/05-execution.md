# 5. Execution & Observability

This section details the run model, execution lifecycle, log streaming, artifact capture, and monitoring capabilities for mellea programs.

## 5.1 Run Model & Schema

### 5.1.1 Run Interface
Each execution is represented as a Run resource:
```typescript
interface Run {
  id: string                    // UUID v4
  asset_id: string              // Program or composition being run
  asset_version: string         // Git commit or version tag
  owner_id: string              // User who initiated

  // Configuration
  config: RunConfig

  // Lifecycle
  status: RunStatus
  created_at: string            // ISO 8601
  started_at?: string
  finished_at?: string

  // Results
  exit_code?: number
  error_message?: string
  artifacts: ArtifactRef[]
  metrics: RunMetrics

  // Audit
  cancelled_by?: string         // User ID if cancelled
  retry_of?: string             // Parent run ID if retry
}

interface RunConfig {
  model: string                 // e.g., "openai/gpt-4o", "ollama/llama3"
  environment_id?: string       // Custom environment, or use asset default
  env_vars: Record<string, string>
  datasets: DatasetBinding[]    // Named dataset references
  timeout_seconds: number       // Max wall-clock time (default: 3600)
  artifact_quota_mb: number     // Max artifact storage (default: 200)
}

interface DatasetBinding {
  name: string                  // Variable name in program
  dataset_id: string            // Reference to data collection asset
  version?: string              // Specific version, or "latest"
}
```

### 5.1.2 Run Metrics
Metrics captured from mellea runtime instrumentation:
```typescript
interface RunMetrics {
  // Timing
  queue_duration_ms: number     // Time in Queued state
  startup_duration_ms: number   // Container initialization
  execution_duration_ms: number // Actual program runtime
  total_duration_ms: number     // End-to-end

  // LLM Usage
  llm_calls: number
  input_tokens: number
  output_tokens: number
  estimated_cost_usd: number    // Based on model pricing

  // Sampling
  samples_generated: number
  repair_attempts: number
  loop_iterations: number

  // Resources
  peak_memory_mb: number
  cpu_seconds: number
}
```

## 5.2 Run Status State Machine

```
                    ┌──────────────┐
                    │   Created    │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
              ┌─────│   Queued     │─────┐
              │     └──────┬───────┘     │
              │            │             │
              │            ▼             │
              │     ┌──────────────┐     │
              │     │ Pulling Image│     │
              │     └──────┬───────┘     │
              │            │             │
              │            ▼             │
              │     ┌──────────────┐     │
              │     │   Starting   │     │
              │     └──────┬───────┘     │
              │            │             │
              │            ▼             │
     Cancel   │     ┌──────────────┐     │  Timeout/
     Request  │     │   Running    │     │  Error
              │     └──────┬───────┘     │
              │            │             │
              │     ┌──────┼──────┐      │
              │     │      │      │      │
              ▼     ▼      ▼      ▼      ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │Cancelled │ │Succeeded │ │  Failed  │
        └──────────┘ └──────────┘ └──────────┘
```

Status enum:
```typescript
type RunStatus =
  | "created"       // Initial state
  | "queued"        // Waiting for executor
  | "pulling_image" // Downloading container image
  | "starting"      // Container initializing
  | "running"       // Program executing
  | "succeeded"     // Completed with exit code 0
  | "failed"        // Completed with error
  | "cancelled"     // User-initiated cancellation
```

## 5.3 Run Initiation

### 5.3.1 Run Service
```python
class RunService:
    def __init__(
        self,
        store: JsonStore,
        environment_service: EnvironmentService,
        executor: RunExecutor,
        log_service: LogService
    ):
        self.store = store
        self.environment_service = environment_service
        self.executor = executor
        self.log_service = log_service

    async def create_run(
        self,
        asset_id: str,
        config: RunConfig,
        user: User
    ) -> Run:
        """Create and queue a new run."""
        # Validate asset exists and user has execute permission
        asset = await self.store.get("assets", asset_id)
        if not asset:
            raise AssetNotFoundError(asset_id)

        if not self._can_execute(asset, user):
            raise PermissionDeniedError("execute", asset_id)

        # Resolve environment
        env_id = config.environment_id or asset.get("default_environment_id")
        environment = await self.environment_service.get_or_create(env_id)

        # Create run record
        run = Run(
            id=str(uuid.uuid4()),
            asset_id=asset_id,
            asset_version=asset.get("version", "latest"),
            owner_id=user.id,
            config=config,
            status="created",
            created_at=datetime.utcnow().isoformat(),
            artifacts=[],
            metrics=RunMetrics()
        )

        await self.store.create("runs", run.id, run.dict())

        # Queue for execution
        await self._enqueue_run(run, environment)

        return run

    async def _enqueue_run(self, run: Run, environment: Environment):
        """Submit run to executor queue."""
        await self.store.update("runs", run.id, {"status": "queued"})

        # Submit to async executor
        await self.executor.submit(
            run_id=run.id,
            environment=environment,
            config=run.config,
            callbacks={
                "on_status_change": self._handle_status_change,
                "on_log": self.log_service.append,
                "on_artifact": self._handle_artifact,
                "on_metrics": self._handle_metrics
            }
        )

    async def rerun(
        self,
        original_run_id: str,
        user: User,
        config_overrides: Optional[dict] = None
    ) -> Run:
        """Create a new run reusing previous configuration."""
        original = await self.store.get("runs", original_run_id)
        if not original:
            raise RunNotFoundError(original_run_id)

        # Merge config with overrides
        config = RunConfig(**original["config"])
        if config_overrides:
            config = config.copy(update=config_overrides)

        # Create new run linked to original
        new_run = await self.create_run(
            asset_id=original["asset_id"],
            config=config,
            user=user
        )

        # Link as retry
        await self.store.update("runs", new_run.id, {
            "retry_of": original_run_id
        })

        return new_run
```

### 5.3.2 Run Initiation API
```
POST /api/runs
Content-Type: application/json

{
  "asset_id": "prog_abc123",
  "config": {
    "model": "openai/gpt-4o",
    "env_vars": {
      "DEBUG": "true"
    },
    "datasets": [
      {"name": "training_data", "dataset_id": "ds_xyz789"}
    ],
    "timeout_seconds": 1800,
    "artifact_quota_mb": 100
  }
}

Response 201:
{
  "id": "run_def456",
  "status": "queued",
  "created_at": "2025-01-15T10:30:00Z",
  ...
}
```

## 5.4 Log Streaming

### 5.4.1 Log Frame Structure
```typescript
interface LogFrame {
  timestamp: string           // ISO 8601 with milliseconds
  stream: "stdout" | "stderr" | "system"
  level: "debug" | "info" | "warn" | "error"
  message: string
  metadata?: Record<string, any>  // Structured data (e.g., LLM call details)
}
```

### 5.4.2 Log Service with SSE
```python
class LogService:
    def __init__(self, redis: Redis):
        self.redis = redis
        self.retention_hours = 72

    async def append(self, run_id: str, frame: LogFrame):
        """Append log frame and publish to subscribers."""
        key = f"logs:{run_id}"

        # Store in Redis list
        await self.redis.rpush(key, frame.json())
        await self.redis.expire(key, self.retention_hours * 3600)

        # Publish to SSE channel
        channel = f"logs:{run_id}:stream"
        await self.redis.publish(channel, frame.json())

    async def stream(self, run_id: str) -> AsyncGenerator[LogFrame, None]:
        """Stream logs via Server-Sent Events."""
        key = f"logs:{run_id}"
        channel = f"logs:{run_id}:stream"

        # First, send existing logs
        existing = await self.redis.lrange(key, 0, -1)
        for log_json in existing:
            yield LogFrame.parse_raw(log_json)

        # Then subscribe to new logs
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield LogFrame.parse_raw(message["data"])
        finally:
            await pubsub.unsubscribe(channel)

    async def get_full_log(self, run_id: str) -> List[LogFrame]:
        """Retrieve complete log for download."""
        key = f"logs:{run_id}"
        logs = await self.redis.lrange(key, 0, -1)
        return [LogFrame.parse_raw(log) for log in logs]
```

### 5.4.3 SSE Endpoint
```python
@router.get("/runs/{run_id}/logs/stream")
async def stream_logs(
    run_id: str,
    log_service: LogService = Depends(),
    user: User = Depends(get_current_user)
):
    """Stream logs via Server-Sent Events."""
    # Verify access
    run = await get_run_with_access(run_id, user)

    async def event_generator():
        async for frame in log_service.stream(run_id):
            yield {
                "event": "log",
                "data": frame.json()
            }

        # Send completion event when run finishes
        yield {
            "event": "complete",
            "data": json.dumps({"status": run.status})
        }

    return EventSourceResponse(event_generator())
```

### 5.4.4 Log UI Component
```typescript
function LogViewer({ runId }: { runId: string }) {
  const [logs, setLogs] = useState<LogFrame[]>([])
  const [isStreaming, setIsStreaming] = useState(true)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const eventSource = new EventSource(`/api/runs/${runId}/logs/stream`)

    eventSource.addEventListener('log', (e) => {
      const frame = JSON.parse(e.data)
      setLogs(prev => [...prev, frame])
    })

    eventSource.addEventListener('complete', () => {
      setIsStreaming(false)
      eventSource.close()
    })

    return () => eventSource.close()
  }, [runId])

  // Auto-scroll to bottom
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs])

  return (
    <Box ref={containerRef} fontFamily="mono" fontSize="sm" overflowY="auto">
      {logs.map((log, i) => (
        <LogLine key={i} frame={log} />
      ))}
      {isStreaming && <Spinner size="sm" />}
    </Box>
  )
}

function LogLine({ frame }: { frame: LogFrame }) {
  const levelColors = {
    debug: "gray.500",
    info: "blue.500",
    warn: "orange.500",
    error: "red.500"
  }

  return (
    <HStack spacing={2} py={0.5}>
      <Text color="gray.400" fontSize="xs">
        {new Date(frame.timestamp).toLocaleTimeString()}
      </Text>
      <Badge colorScheme={levelColors[frame.level]} size="sm">
        {frame.level}
      </Badge>
      <Badge variant="outline" size="sm">
        {frame.stream}
      </Badge>
      <Text whiteSpace="pre-wrap">{frame.message}</Text>
    </HStack>
  )
}
```

## 5.5 Artifacts & Outputs

### 5.5.1 Artifact Structure
```typescript
interface ArtifactRef {
  id: string
  run_id: string
  name: string                  // Original filename
  path: string                  // Storage path
  content_type: string          // MIME type
  size_bytes: number
  created_at: string
  checksum: string              // SHA-256
  metadata?: Record<string, any>
}

interface StructuredOutput {
  artifact_id: string
  schema_version: string
  data: any                     // JSON-serializable result
}
```

### 5.5.2 Artifact Collector
```python
class ArtifactCollector:
    def __init__(
        self,
        storage: ObjectStorage,
        store: JsonStore,
        quota_mb: int = 200
    ):
        self.storage = storage
        self.store = store
        self.quota_mb = quota_mb

    async def collect(
        self,
        run_id: str,
        output_dir: Path
    ) -> List[ArtifactRef]:
        """Collect artifacts from run output directory."""
        artifacts = []
        total_size = 0

        for file_path in output_dir.rglob("*"):
            if file_path.is_file():
                size = file_path.stat().st_size
                total_size += size

                # Check quota
                if total_size > self.quota_mb * 1024 * 1024:
                    await self._log_quota_exceeded(run_id, total_size)
                    break

                # Upload to storage
                storage_path = f"runs/{run_id}/artifacts/{file_path.name}"
                await self.storage.upload(file_path, storage_path)

                # Create artifact record
                artifact = ArtifactRef(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    name=file_path.name,
                    path=storage_path,
                    content_type=self._detect_mime(file_path),
                    size_bytes=size,
                    created_at=datetime.utcnow().isoformat(),
                    checksum=self._compute_sha256(file_path)
                )
                artifacts.append(artifact)

        # Store artifact references
        await self.store.update("runs", run_id, {
            "artifacts": [a.dict() for a in artifacts]
        })

        return artifacts

    async def get_download_url(
        self,
        artifact_id: str,
        expires_in: int = 3600
    ) -> str:
        """Generate presigned download URL."""
        artifact = await self.store.get("artifacts", artifact_id)
        return await self.storage.presigned_url(
            artifact["path"],
            expires_in=expires_in
        )
```

### 5.5.3 Retention Policy
```python
class RetentionPolicy:
    def __init__(self, store: JsonStore, storage: ObjectStorage):
        self.store = store
        self.storage = storage

    async def apply_retention(
        self,
        org_id: str,
        retention_days: int = 14
    ):
        """Delete artifacts older than retention period."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        # Find expired runs
        expired_runs = await self.store.query(
            "runs",
            filters={
                "org_id": org_id,
                "finished_at": {"$lt": cutoff.isoformat()},
                "artifacts_purged": {"$ne": True}
            }
        )

        for run in expired_runs:
            # Delete from storage
            for artifact in run.get("artifacts", []):
                await self.storage.delete(artifact["path"])

            # Mark as purged (keep run record for history)
            await self.store.update("runs", run["id"], {
                "artifacts": [],
                "artifacts_purged": True,
                "artifacts_purged_at": datetime.utcnow().isoformat()
            })
```

## 5.6 Run Dashboard

### 5.6.1 Dashboard Views
```typescript
// Global runs dashboard
function RunsDashboard() {
  const [filters, setFilters] = useState<RunFilters>({})
  const { data: runs, isLoading } = useRuns(filters)

  return (
    <VStack spacing={4} align="stretch">
      <RunFiltersBar
        filters={filters}
        onChange={setFilters}
      />

      <RunsTable
        runs={runs}
        isLoading={isLoading}
        columns={["status", "asset", "owner", "started", "duration", "cost"]}
      />

      <RunsMetricsSummary runs={runs} />
    </VStack>
  )
}

interface RunFilters {
  status?: RunStatus[]
  owner_id?: string
  asset_id?: string
  tags?: string[]
  started_after?: string
  started_before?: string
  search?: string
}
```

### 5.6.2 Status Indicators
```typescript
function RunStatusBadge({ status }: { status: RunStatus }) {
  const config = {
    created: { color: "gray", icon: FiCircle },
    queued: { color: "yellow", icon: FiClock },
    pulling_image: { color: "blue", icon: FiDownload },
    starting: { color: "blue", icon: FiPlay },
    running: { color: "blue", icon: FiActivity, pulse: true },
    succeeded: { color: "green", icon: FiCheck },
    failed: { color: "red", icon: FiX },
    cancelled: { color: "orange", icon: FiSlash }
  }

  const { color, icon: Icon, pulse } = config[status]

  return (
    <Badge
      colorScheme={color}
      display="flex"
      alignItems="center"
      gap={1}
      className={pulse ? "pulse-animation" : ""}
    >
      <Icon size={12} />
      {status}
    </Badge>
  )
}
```

### 5.6.3 Run Detail Page
```typescript
function RunDetailPage({ runId }: { runId: string }) {
  const { data: run } = useRun(runId)

  return (
    <Box>
      <RunHeader run={run} />

      <Tabs>
        <TabList>
          <Tab>Logs</Tab>
          <Tab>Artifacts ({run?.artifacts.length})</Tab>
          <Tab>Metrics</Tab>
          <Tab>Configuration</Tab>
        </TabList>

        <TabPanels>
          <TabPanel>
            <LogViewer runId={runId} />
          </TabPanel>

          <TabPanel>
            <ArtifactList artifacts={run?.artifacts} />
          </TabPanel>

          <TabPanel>
            <RunMetricsDisplay metrics={run?.metrics} />
          </TabPanel>

          <TabPanel>
            <RunConfigDisplay config={run?.config} />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  )
}
```

## 5.7 Metrics & Cost Tracking

### 5.7.1 Metrics Collector
```python
class MetricsCollector:
    def __init__(self, store: JsonStore, pricing: ModelPricing):
        self.store = store
        self.pricing = pricing

    async def record_llm_call(
        self,
        run_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int
    ):
        """Record LLM call metrics."""
        cost = self.pricing.calculate(model, input_tokens, output_tokens)

        await self.store.increment("runs", run_id, {
            "metrics.llm_calls": 1,
            "metrics.input_tokens": input_tokens,
            "metrics.output_tokens": output_tokens,
            "metrics.estimated_cost_usd": cost
        })

    async def record_sampling(
        self,
        run_id: str,
        samples: int,
        repairs: int,
        iterations: int
    ):
        """Record mellea sampling metrics."""
        await self.store.increment("runs", run_id, {
            "metrics.samples_generated": samples,
            "metrics.repair_attempts": repairs,
            "metrics.loop_iterations": iterations
        })

    async def finalize(self, run_id: str, resource_usage: ResourceUsage):
        """Finalize metrics when run completes."""
        await self.store.update("runs", run_id, {
            "metrics.peak_memory_mb": resource_usage.peak_memory_mb,
            "metrics.cpu_seconds": resource_usage.cpu_seconds
        })


class ModelPricing:
    PRICES = {
        "openai/gpt-4o": {"input": 0.0025, "output": 0.01},
        "openai/gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "anthropic/claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
        "ollama/*": {"input": 0, "output": 0}  # Local models
    }

    def calculate(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        prices = self._get_prices(model)
        return (
            (input_tokens / 1000) * prices["input"] +
            (output_tokens / 1000) * prices["output"]
        )
```

### 5.7.2 Aggregated Metrics View
```typescript
function RunsMetricsSummary({ runs }: { runs: Run[] }) {
  const totals = useMemo(() => ({
    totalRuns: runs.length,
    successRate: runs.filter(r => r.status === "succeeded").length / runs.length,
    totalTokens: runs.reduce((sum, r) =>
      sum + (r.metrics?.input_tokens || 0) + (r.metrics?.output_tokens || 0), 0
    ),
    totalCost: runs.reduce((sum, r) =>
      sum + (r.metrics?.estimated_cost_usd || 0), 0
    ),
    avgDuration: runs.reduce((sum, r) =>
      sum + (r.metrics?.total_duration_ms || 0), 0
    ) / runs.length
  }), [runs])

  return (
    <SimpleGrid columns={5} spacing={4}>
      <StatCard label="Total Runs" value={totals.totalRuns} />
      <StatCard
        label="Success Rate"
        value={`${(totals.successRate * 100).toFixed(1)}%`}
        color={totals.successRate > 0.9 ? "green" : "orange"}
      />
      <StatCard
        label="Total Tokens"
        value={formatNumber(totals.totalTokens)}
      />
      <StatCard
        label="Total Cost"
        value={`$${totals.totalCost.toFixed(2)}`}
      />
      <StatCard
        label="Avg Duration"
        value={formatDuration(totals.avgDuration)}
      />
    </SimpleGrid>
  )
}
```

## 5.8 Error Classification & Handling

### 5.8.1 Error Classifier
```python
class ErrorClassifier:
    """Classify errors as user-code vs infrastructure."""

    USER_CODE_PATTERNS = [
        (r"File \".*\.py\", line \d+", "python_error"),
        (r"SyntaxError:", "syntax_error"),
        (r"TypeError:|ValueError:|KeyError:", "runtime_error"),
        (r"mellea\.ValidationError:", "validation_error"),
        (r"@generative.*failed", "generative_error")
    ]

    INFRA_PATTERNS = [
        (r"OOMKilled", "out_of_memory"),
        (r"ImagePullBackOff", "image_pull_failed"),
        (r"connection refused|timeout", "network_error"),
        (r"permission denied", "permission_error"),
        (r"disk quota exceeded", "storage_error")
    ]

    def classify(self, error_output: str) -> ErrorClassification:
        # Check user code patterns first
        for pattern, error_type in self.USER_CODE_PATTERNS:
            if re.search(pattern, error_output):
                return ErrorClassification(
                    category="user_code",
                    type=error_type,
                    stack_trace=self._extract_stack_trace(error_output),
                    suggestion=self._get_user_suggestion(error_type)
                )

        # Check infrastructure patterns
        for pattern, error_type in self.INFRA_PATTERNS:
            if re.search(pattern, error_output, re.IGNORECASE):
                return ErrorClassification(
                    category="infrastructure",
                    type=error_type,
                    suggestion=self._get_infra_suggestion(error_type)
                )

        return ErrorClassification(
            category="unknown",
            type="unclassified"
        )

    def _get_infra_suggestion(self, error_type: str) -> str:
        suggestions = {
            "out_of_memory": "Increase memory limit in environment settings or optimize your program's memory usage.",
            "image_pull_failed": "Check that the container image exists and you have pull permissions.",
            "network_error": "Verify network connectivity and that the target service is available.",
            "permission_error": "Check file permissions and credential configuration.",
            "storage_error": "Reduce artifact output size or increase storage quota."
        }
        return suggestions.get(error_type, "Check the system logs for more details.")
```

### 5.8.2 Error Display Component
```typescript
function RunErrorDisplay({ run }: { run: Run }) {
  const classification = run.error_classification

  if (!classification) return null

  return (
    <Alert
      status="error"
      variant={classification.category === "infrastructure" ? "solid" : "subtle"}
    >
      <AlertIcon />
      <Box flex="1">
        <AlertTitle>
          {classification.category === "user_code"
            ? "Program Error"
            : "Infrastructure Error"}
        </AlertTitle>
        <AlertDescription>
          {run.error_message}

          {classification.stack_trace && (
            <Code display="block" mt={2} p={2} whiteSpace="pre-wrap">
              {classification.stack_trace}
            </Code>
          )}

          {classification.suggestion && (
            <Text mt={2} fontStyle="italic">
              {classification.suggestion}
            </Text>
          )}
        </AlertDescription>
      </Box>
    </Alert>
  )
}
```

## 5.9 Run Controls

### 5.9.1 Cancel Operation
```python
class RunControls:
    def __init__(self, store: JsonStore, executor: RunExecutor):
        self.store = store
        self.executor = executor

    async def cancel(self, run_id: str, user: User) -> Run:
        """Cancel a running execution."""
        run = await self.store.get("runs", run_id)

        if run["status"] not in ["queued", "pulling_image", "starting", "running"]:
            raise InvalidOperationError(
                f"Cannot cancel run in status: {run['status']}"
            )

        # Verify permission (owner or admin)
        if run["owner_id"] != user.id and user.role != "admin":
            raise PermissionDeniedError("cancel", run_id)

        # Send cancellation signal
        await self.executor.cancel(
            run_id,
            grace_period_seconds=10  # SIGTERM, then SIGKILL after 10s
        )

        # Update status
        await self.store.update("runs", run_id, {
            "status": "cancelled",
            "cancelled_by": user.id,
            "finished_at": datetime.utcnow().isoformat()
        })

        return await self.store.get("runs", run_id)

    async def retry(
        self,
        run_id: str,
        user: User,
        config_overrides: Optional[dict] = None
    ) -> Run:
        """Retry a failed or cancelled run."""
        run = await self.store.get("runs", run_id)

        if run["status"] not in ["failed", "cancelled"]:
            raise InvalidOperationError(
                f"Can only retry failed or cancelled runs, not: {run['status']}"
            )

        # Create new run with same config
        return await self.run_service.rerun(
            run_id,
            user,
            config_overrides
        )

    async def bulk_cancel(
        self,
        run_ids: List[str],
        user: User
    ) -> Dict[str, str]:
        """Cancel multiple runs, return status per run."""
        results = {}
        for run_id in run_ids:
            try:
                await self.cancel(run_id, user)
                results[run_id] = "cancelled"
            except Exception as e:
                results[run_id] = f"error: {str(e)}"
        return results
```

### 5.9.2 Control UI
```typescript
function RunControls({ run, onUpdate }: RunControlsProps) {
  const cancelMutation = useCancelRun()
  const retryMutation = useRetryRun()

  const canCancel = ["queued", "pulling_image", "starting", "running"]
    .includes(run.status)
  const canRetry = ["failed", "cancelled"].includes(run.status)

  return (
    <HStack spacing={2}>
      {canCancel && (
        <Button
          leftIcon={<FiX />}
          colorScheme="red"
          variant="outline"
          onClick={() => cancelMutation.mutate(run.id)}
          isLoading={cancelMutation.isLoading}
        >
          Cancel
        </Button>
      )}

      {canRetry && (
        <Button
          leftIcon={<FiRefreshCw />}
          colorScheme="blue"
          onClick={() => retryMutation.mutate(run.id)}
          isLoading={retryMutation.isLoading}
        >
          Retry
        </Button>
      )}

      <Menu>
        <MenuButton as={IconButton} icon={<FiMoreVertical />} />
        <MenuList>
          <MenuItem icon={<FiCopy />}>Clone Configuration</MenuItem>
          <MenuItem icon={<FiDownload />}>Download Logs</MenuItem>
          {run.artifacts.length > 0 && (
            <MenuItem icon={<FiPackage />}>Download All Artifacts</MenuItem>
          )}
        </MenuList>
      </Menu>
    </HStack>
  )
}
```

## 5.10 Notifications

### 5.10.1 Notification Service
```python
class RunNotificationService:
    def __init__(
        self,
        store: JsonStore,
        email_service: EmailService,
        websocket_manager: WebSocketManager
    ):
        self.store = store
        self.email_service = email_service
        self.ws = websocket_manager

    async def on_run_complete(self, run: Run):
        """Send notifications when run completes."""
        user = await self.store.get("users", run.owner_id)
        prefs = user.get("notification_preferences", {})

        # In-app notification (always)
        await self._create_notification(
            user_id=run.owner_id,
            type="run_complete",
            title=f"Run {run.status}: {run.asset_id}",
            body=self._format_run_summary(run),
            link=f"/runs/{run.id}"
        )

        # WebSocket push for toast
        await self.ws.send_to_user(run.owner_id, {
            "type": "run_complete",
            "run_id": run.id,
            "status": run.status
        })

        # Email (if enabled and run was long or failed)
        if prefs.get("email_on_run_complete"):
            duration = run.metrics.get("total_duration_ms", 0)
            if duration > 60000 or run.status == "failed":  # > 1 min or failed
                await self.email_service.send(
                    to=user["email"],
                    template="run_complete",
                    context={"run": run}
                )

    async def on_shared_run_complete(self, run: Run, shared_with: List[str]):
        """Notify users when a shared run completes."""
        for user_id in shared_with:
            await self._create_notification(
                user_id=user_id,
                type="shared_run_complete",
                title=f"Shared run completed: {run.asset_id}",
                body=f"Run by {run.owner_id} has {run.status}",
                link=f"/runs/{run.id}"
            )
```

### 5.10.2 Notification Preferences UI
```typescript
function NotificationSettings() {
  const { data: prefs, mutate } = useNotificationPreferences()

  return (
    <VStack align="stretch" spacing={4}>
      <FormControl display="flex" alignItems="center">
        <FormLabel mb={0}>Email on run completion</FormLabel>
        <Switch
          isChecked={prefs?.email_on_run_complete}
          onChange={(e) => mutate({ email_on_run_complete: e.target.checked })}
        />
      </FormControl>

      <FormControl display="flex" alignItems="center">
        <FormLabel mb={0}>Email on shared run completion</FormLabel>
        <Switch
          isChecked={prefs?.email_on_shared_complete}
          onChange={(e) => mutate({ email_on_shared_complete: e.target.checked })}
        />
      </FormControl>

      <FormControl display="flex" alignItems="center">
        <FormLabel mb={0}>In-app toast notifications</FormLabel>
        <Switch
          isChecked={prefs?.toast_enabled}
          onChange={(e) => mutate({ toast_enabled: e.target.checked })}
        />
      </FormControl>
    </VStack>
  )
}
```

## 5.11 API Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/runs` | Create and queue new run |
| GET | `/api/runs` | List runs with filters |
| GET | `/api/runs/{id}` | Get run details |
| DELETE | `/api/runs/{id}` | Cancel active run |
| POST | `/api/runs/{id}/retry` | Retry failed/cancelled run |
| GET | `/api/runs/{id}/logs` | Get complete log |
| GET | `/api/runs/{id}/logs/stream` | Stream logs via SSE |
| GET | `/api/runs/{id}/artifacts` | List artifacts |
| GET | `/api/runs/{id}/artifacts/{artifact_id}` | Download artifact |
| GET | `/api/runs/{id}/metrics` | Get run metrics |
| POST | `/api/runs/bulk/cancel` | Cancel multiple runs |
| GET | `/api/assets/{id}/runs` | List runs for asset |
| GET | `/api/users/me/runs` | List current user's runs |
