## 4. Environment Provisioning

This section covers how program containers are built, managed, and secured for execution.

### 4.1 Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Import    │     │    Build    │     │    Store    │     │     Run     │
│   Program   │ →   │    Image    │ →   │   Registry  │ →   │  Container  │
│             │     │             │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
     ↓                    ↓                   ↓                    ↓
  Workspace         Dockerfile +         Image tag           Pod with
  files             dependencies         cached              limits
```

### 4.2 Container Build Pipeline

#### 4.2.1 Build Trigger Points

| Trigger | Description |
|---------|-------------|
| **On Import** | Build queued when program is created/imported |
| **On File Change** | Rebuild when source files are modified |
| **On Dependency Change** | Rebuild when requirements change |
| **Manual** | User triggers rebuild from UI |
| **On Run (if needed)** | Build on-demand if no image exists |

#### 4.2.2 Build Service

```python
class ImageBuildService:
    """Manages container image builds for programs."""

    def __init__(
        self,
        registry_url: str,
        build_namespace: str = "mellea-builds"
    ):
        self.registry_url = registry_url
        self.build_namespace = build_namespace
        self.k8s_client = kubernetes.client.BatchV1Api()

    async def queue_build(self, program: ProgramAsset) -> BuildJob:
        """Queue a container image build for a program."""

        # Check if rebuild is needed
        if await self._image_is_current(program):
            return BuildJob(status="skipped", reason="Image up to date")

        # Create build job
        job = BuildJob(
            id=f"build-{program.id}-{int(time.time())}",
            program_id=program.id,
            status="queued",
            created_at=datetime.utcnow()
        )

        # Update program status
        program.imageBuildStatus = "pending"
        await catalog.update_program(program)

        # Submit Kubernetes Job
        await self._create_build_job(job, program)

        return job

    async def _create_build_job(
        self,
        job: BuildJob,
        program: ProgramAsset
    ) -> None:
        """Create Kubernetes Job for image build."""

        image_tag = self._generate_image_tag(program)

        k8s_job = kubernetes.client.V1Job(
            metadata=kubernetes.client.V1ObjectMeta(
                name=job.id,
                namespace=self.build_namespace,
                labels={
                    "app": "mellea-build",
                    "program-id": program.id
                }
            ),
            spec=kubernetes.client.V1JobSpec(
                ttl_seconds_after_finished=3600,  # Cleanup after 1 hour
                backoff_limit=2,
                template=kubernetes.client.V1PodTemplateSpec(
                    spec=kubernetes.client.V1PodSpec(
                        restart_policy="Never",
                        service_account_name="mellea-builder",
                        containers=[
                            kubernetes.client.V1Container(
                                name="builder",
                                image="mellea/builder:latest",
                                args=[
                                    "--workspace", f"/workspaces/{program.id}",
                                    "--output", f"{self.registry_url}/{image_tag}",
                                    "--python-version", program.dependencies.pythonVersion or "3.11"
                                ],
                                resources=kubernetes.client.V1ResourceRequirements(
                                    requests={"cpu": "500m", "memory": "1Gi"},
                                    limits={"cpu": "2", "memory": "4Gi"}
                                ),
                                volume_mounts=[
                                    kubernetes.client.V1VolumeMount(
                                        name="workspaces",
                                        mount_path="/workspaces",
                                        read_only=True
                                    ),
                                    kubernetes.client.V1VolumeMount(
                                        name="cache",
                                        mount_path="/cache"
                                    )
                                ]
                            )
                        ],
                        volumes=[
                            kubernetes.client.V1Volume(
                                name="workspaces",
                                persistent_volume_claim=kubernetes.client.V1PersistentVolumeClaimVolumeSource(
                                    claim_name="mellea-workspaces"
                                )
                            ),
                            kubernetes.client.V1Volume(
                                name="cache",
                                persistent_volume_claim=kubernetes.client.V1PersistentVolumeClaimVolumeSource(
                                    claim_name="mellea-build-cache"
                                )
                            )
                        ]
                    )
                )
            )
        )

        self.k8s_client.create_namespaced_job(
            namespace=self.build_namespace,
            body=k8s_job
        )

    def _generate_image_tag(self, program: ProgramAsset) -> str:
        """Generate unique image tag for program version."""
        # Include content hash for cache invalidation
        content_hash = self._compute_workspace_hash(program.id)[:8]
        return f"programs/{program.id}:{program.version}-{content_hash}"
```

#### 4.2.3 Dockerfile Generation

```python
class DockerfileGenerator:
    """Generate Dockerfiles for mellea programs."""

    BASE_IMAGE = "python:3.11-slim-bookworm"

    SYSTEM_PACKAGES = [
        "git",
        "curl",
        "ca-certificates"
    ]

    def generate(self, program: ProgramAsset) -> str:
        """Generate Dockerfile content for program."""

        deps = program.dependencies
        python_version = deps.pythonVersion or "3.11"

        dockerfile = f"""
# Auto-generated Dockerfile for mellea program: {program.name}
# Generated at: {datetime.utcnow().isoformat()}

FROM python:{python_version}-slim-bookworm

# System setup
RUN apt-get update && apt-get install -y --no-install-recommends \\
    {' '.join(self.SYSTEM_PACKAGES)} \\
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 mellea
WORKDIR /app

# Install dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install mellea CLI
RUN pip install --no-cache-dir mellea-cli>=0.5.0

# Copy program code
COPY --chown=mellea:mellea . .

# Switch to non-root user
USER mellea

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV MELLEA_PROGRAM_ID={program.id}

# Default entrypoint
ENTRYPOINT ["python", "{program.entrypoint}"]
"""
        return dockerfile.strip()

    def generate_requirements(self, program: ProgramAsset) -> str:
        """Generate requirements.txt from program dependencies."""
        lines = []

        for pkg in program.dependencies.packages:
            if pkg.version:
                lines.append(f"{pkg.name}{pkg.version}")
            else:
                lines.append(pkg.name)

            if pkg.extras:
                # Handle extras like package[extra1,extra2]
                extras_str = ",".join(pkg.extras)
                lines[-1] = f"{pkg.name}[{extras_str}]{pkg.version or ''}"

        return "\n".join(sorted(lines))
```

#### 4.2.4 Build Status Tracking

```typescript
interface BuildJob {
  id: string
  programId: string
  status: BuildStatus
  createdAt: datetime
  startedAt?: datetime
  completedAt?: datetime

  // Results
  imageTag?: string
  imageSizeBytes?: number
  buildDurationSeconds?: number

  // Errors
  errorMessage?: string
  errorPhase?: "checkout" | "install" | "build" | "push"
  logs?: string
}

type BuildStatus =
  | "queued"
  | "building"
  | "succeeded"
  | "failed"
  | "cancelled"

// Build status API
GET /api/v1/programs/{id}/build/status
{
  "currentBuild": {
    "id": "build-prog-123-1705750000",
    "status": "building",
    "phase": "install",
    "progress": 65,
    "startedAt": "2024-01-20T10:00:00Z"
  },
  "lastSuccessfulBuild": {
    "id": "build-prog-123-1705700000",
    "imageTag": "programs/prog-123:1.0.0-abc123",
    "completedAt": "2024-01-19T14:30:00Z",
    "imageSizeBytes": 524288000
  }
}
```

### 4.3 Base Images & Layers

#### 4.3.1 Image Layer Strategy

```
┌─────────────────────────────────────┐
│         Program Code Layer          │  ← Changes frequently
├─────────────────────────────────────┤
│      Program Dependencies Layer     │  ← Changes on requirements update
├─────────────────────────────────────┤
│       Mellea Runtime Layer          │  ← Changes on mellea update
├─────────────────────────────────────┤
│        System Tools Layer           │  ← Rarely changes
├─────────────────────────────────────┤
│        Python Base Image            │  ← Updated monthly
└─────────────────────────────────────┘
```

#### 4.3.2 Pre-built Base Images

Maintain pre-built base images with common dependencies:

```yaml
# Base images maintained by platform
base-images:
  - name: mellea/base:python3.11
    description: Minimal Python 3.11 with mellea CLI
    size: ~150MB

  - name: mellea/base:python3.11-data
    description: Python 3.11 + common data science packages
    includes: [numpy, pandas, scipy, scikit-learn]
    size: ~800MB

  - name: mellea/base:python3.11-nlp
    description: Python 3.11 + NLP packages
    includes: [transformers, tokenizers, sentencepiece]
    size: ~1.2GB
```

### 4.4 Dependency Cache

#### 4.4.1 Cache Strategy

```python
class DependencyCache:
    """Cache pip packages to speed up builds."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.index_file = cache_dir / "index.json"

    def get_cache_key(self, requirements: List[PackageRef]) -> str:
        """Generate cache key from requirements."""
        # Sort for deterministic hashing
        sorted_reqs = sorted(
            f"{p.name}{p.version or ''}" for p in requirements
        )
        content = "\n".join(sorted_reqs)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def get_cached_layer(self, cache_key: str) -> Optional[Path]:
        """Get cached dependency layer if exists."""
        layer_path = self.cache_dir / cache_key / "layer.tar"
        if layer_path.exists():
            # Update access time for LRU
            layer_path.touch()
            return layer_path
        return None

    async def store_layer(self, cache_key: str, layer_tar: Path) -> None:
        """Store dependency layer in cache."""
        dest_dir = self.cache_dir / cache_key
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(layer_tar, dest_dir / "layer.tar")

        # Update index
        await self._update_index(cache_key)

    async def cleanup(self, max_size_gb: float = 50.0) -> None:
        """Remove old cache entries to stay under size limit."""
        entries = []
        for entry_dir in self.cache_dir.iterdir():
            if entry_dir.is_dir():
                layer = entry_dir / "layer.tar"
                if layer.exists():
                    entries.append({
                        "path": entry_dir,
                        "size": layer.stat().st_size,
                        "atime": layer.stat().st_atime
                    })

        # Sort by access time (oldest first)
        entries.sort(key=lambda e: e["atime"])

        total_size = sum(e["size"] for e in entries)
        max_bytes = max_size_gb * 1024 * 1024 * 1024

        # Remove oldest until under limit
        while total_size > max_bytes and entries:
            oldest = entries.pop(0)
            shutil.rmtree(oldest["path"])
            total_size -= oldest["size"]
```

#### 4.4.2 Cache Invalidation

| Event | Cache Action |
|-------|--------------|
| Requirements file changed | Generate new cache key → miss → rebuild |
| Python version changed | Different base image → rebuild |
| Mellea CLI updated | Invalidate mellea layer → partial rebuild |
| Security patch | Invalidate affected packages → selective rebuild |

### 4.5 Environment Lifecycle

#### 4.5.1 Lifecycle States

```typescript
type EnvironmentState =
  | "not_built"     // No image exists
  | "building"      // Build in progress
  | "ready"         // Image available, not running
  | "starting"      // Pod being created
  | "running"       // Pod active
  | "idle"          // Running but no activity
  | "stopping"      // Pod being terminated
  | "failed"        // Build or start failed

// State transitions
const transitions = {
  not_built: ["building"],
  building: ["ready", "failed"],
  ready: ["starting", "building"],
  starting: ["running", "failed"],
  running: ["idle", "stopping", "failed"],
  idle: ["running", "stopping"],
  stopping: ["ready"],
  failed: ["building", "starting"]
}
```

#### 4.5.2 Environment API

```typescript
// Start environment (creates pod if needed)
POST /api/v1/programs/{id}/environment/start
{
  "idleTimeoutMinutes": 30,      // Auto-stop after idle (default: 30)
  "resourceOverrides": {         // Optional overrides
    "cpuLimit": "2",
    "memoryLimit": "4Gi"
  }
}

// Response
{
  "environmentId": "env-prog-123-xyz",
  "state": "starting",
  "estimatedReadySeconds": 15
}

// Get environment status
GET /api/v1/programs/{id}/environment
{
  "environmentId": "env-prog-123-xyz",
  "state": "running",
  "podName": "mellea-run-prog-123-xyz",
  "startedAt": "2024-01-20T10:00:00Z",
  "lastActivityAt": "2024-01-20T10:15:00Z",
  "idleTimeoutAt": "2024-01-20T10:45:00Z",
  "resources": {
    "cpuUsage": "250m",
    "cpuLimit": "1",
    "memoryUsage": "512Mi",
    "memoryLimit": "2Gi"
  }
}

// Stop environment
POST /api/v1/programs/{id}/environment/stop
{
  "force": false   // true = immediate kill, false = graceful
}

// Execute command in running environment
POST /api/v1/programs/{id}/environment/exec
{
  "command": ["python", "main.py", "--input", "test.txt"],
  "env": {
    "CUSTOM_VAR": "value"
  },
  "timeout": 300
}
```

#### 4.5.3 Idle Timeout Management

```python
class IdleTimeoutManager:
    """Monitor environments and stop idle ones."""

    def __init__(self, default_timeout_minutes: int = 30):
        self.default_timeout = timedelta(minutes=default_timeout_minutes)

    async def check_and_stop_idle(self) -> List[str]:
        """Check all running environments and stop idle ones."""
        stopped = []

        environments = await self._get_running_environments()

        for env in environments:
            idle_duration = datetime.utcnow() - env.last_activity_at
            timeout = env.idle_timeout or self.default_timeout

            if idle_duration > timeout:
                await self._stop_environment(env.id)
                stopped.append(env.id)

                # Notify user
                await notifications.send(
                    user_id=env.owner_id,
                    type="environment_stopped",
                    message=f"Environment for '{env.program_name}' stopped due to inactivity"
                )

        return stopped

    async def record_activity(self, environment_id: str) -> None:
        """Record activity to reset idle timer."""
        env = await self._get_environment(environment_id)
        env.last_activity_at = datetime.utcnow()
        await self._update_environment(env)
```

### 4.6 Resource Controls

#### 4.6.1 Resource Profiles

```typescript
// Predefined resource profiles
const resourceProfiles = {
  small: {
    cpuRequest: "100m",
    cpuLimit: "500m",
    memoryRequest: "256Mi",
    memoryLimit: "512Mi",
    ephemeralStorage: "1Gi",
    timeoutSeconds: 300
  },
  medium: {
    cpuRequest: "250m",
    cpuLimit: "1",
    memoryRequest: "512Mi",
    memoryLimit: "2Gi",
    ephemeralStorage: "5Gi",
    timeoutSeconds: 1800
  },
  large: {
    cpuRequest: "500m",
    cpuLimit: "2",
    memoryRequest: "1Gi",
    memoryLimit: "4Gi",
    ephemeralStorage: "10Gi",
    timeoutSeconds: 3600
  }
}

// Custom profile (for advanced users)
interface CustomResourceProfile {
  cpuRequest: string      // e.g., "250m"
  cpuLimit: string        // e.g., "1"
  memoryRequest: string   // e.g., "512Mi"
  memoryLimit: string     // e.g., "2Gi"
  ephemeralStorage: string
  timeoutSeconds: number
  pidsLimit: number       // Default: 100
}
```

#### 4.6.2 Concurrency Limits

```python
class ConcurrencyLimiter:
    """Enforce per-user and system-wide concurrency limits."""

    def __init__(
        self,
        max_per_user: int = 3,
        max_system: int = 100
    ):
        self.max_per_user = max_per_user
        self.max_system = max_system

    async def can_start(self, user_id: str) -> Tuple[bool, str]:
        """Check if user can start a new environment."""

        # Check user limit
        user_count = await self._count_user_environments(user_id)
        if user_count >= self.max_per_user:
            return False, f"User limit ({self.max_per_user}) reached"

        # Check system limit
        system_count = await self._count_all_environments()
        if system_count >= self.max_system:
            return False, "System capacity reached, please try again later"

        return True, ""

    async def wait_for_slot(
        self,
        user_id: str,
        timeout: float = 60.0
    ) -> bool:
        """Wait for a slot to become available."""
        deadline = time.time() + timeout

        while time.time() < deadline:
            can_start, _ = await self.can_start(user_id)
            if can_start:
                return True
            await asyncio.sleep(2.0)

        return False
```

### 4.7 Credential Management

#### 4.7.1 Credential Storage

```typescript
// Credentials stored as Kubernetes secrets
interface CredentialSecret {
  name: string              // Secret name: "mellea-cred-{id}"
  namespace: string         // "mellea-credentials"

  // Metadata (stored in annotations)
  credentialId: string
  ownerId: string
  provider: string          // "openai", "anthropic", etc.
  createdAt: datetime
  lastUsedAt?: datetime

  // Secret data (encrypted at rest)
  data: {
    apiKey: string          // Base64 encoded
    // Additional provider-specific fields
  }
}
```

#### 4.7.2 Credential Injection

```python
class CredentialInjector:
    """Inject credentials into program pods."""

    # Environment variable mapping by provider
    ENV_MAPPING = {
        "openai": {
            "apiKey": "OPENAI_API_KEY"
        },
        "anthropic": {
            "apiKey": "ANTHROPIC_API_KEY"
        },
        "azure": {
            "apiKey": "AZURE_OPENAI_API_KEY",
            "endpoint": "AZURE_OPENAI_ENDPOINT"
        }
    }

    def get_env_from_secrets(
        self,
        credential_refs: List[str]
    ) -> List[kubernetes.client.V1EnvFromSource]:
        """Generate envFrom entries for pod spec."""
        env_from = []

        for cred_ref in credential_refs:
            secret_name = f"mellea-cred-{cred_ref}"
            env_from.append(
                kubernetes.client.V1EnvFromSource(
                    secret_ref=kubernetes.client.V1SecretEnvSource(
                        name=secret_name
                    )
                )
            )

        return env_from

    def get_env_vars(
        self,
        model: ModelAsset
    ) -> List[kubernetes.client.V1EnvVar]:
        """Generate explicit env vars for model configuration."""
        env_vars = []

        # Add provider-specific env vars
        mapping = self.ENV_MAPPING.get(model.provider, {})

        if model.credentialsRef:
            for secret_key, env_name in mapping.items():
                env_vars.append(
                    kubernetes.client.V1EnvVar(
                        name=env_name,
                        value_from=kubernetes.client.V1EnvVarSource(
                            secret_key_ref=kubernetes.client.V1SecretKeySelector(
                                name=f"mellea-cred-{model.credentialsRef}",
                                key=secret_key
                            )
                        )
                    )
                )

        # Add model configuration env vars
        env_vars.extend([
            kubernetes.client.V1EnvVar(
                name="MELLEA_MODEL_PROVIDER",
                value=model.provider
            ),
            kubernetes.client.V1EnvVar(
                name="MELLEA_MODEL_ID",
                value=model.modelId
            )
        ])

        if model.endpoint:
            env_vars.append(
                kubernetes.client.V1EnvVar(
                    name="MELLEA_MODEL_ENDPOINT",
                    value=model.endpoint.baseUrl
                )
            )

        return env_vars
```

### 4.8 Container Security & Isolation

#### 4.8.1 Pod Security Context

```yaml
# Security context applied to all program pods
apiVersion: v1
kind: Pod
metadata:
  name: mellea-run-{program-id}-{run-id}
  namespace: mellea-runs
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault

  containers:
    - name: program
      image: {program-image}
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL

      volumeMounts:
        - name: output
          mountPath: /output
        - name: tmp
          mountPath: /tmp

      resources:
        requests:
          cpu: {cpu-request}
          memory: {memory-request}
        limits:
          cpu: {cpu-limit}
          memory: {memory-limit}
          ephemeral-storage: {storage-limit}

  volumes:
    - name: output
      emptyDir:
        sizeLimit: 500Mi
    - name: tmp
      emptyDir:
        sizeLimit: 100Mi
```

#### 4.8.2 Network Policy

```yaml
# Default network policy for program pods
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: mellea-program-policy
  namespace: mellea-runs
spec:
  podSelector:
    matchLabels:
      app: mellea-program

  policyTypes:
    - Ingress
    - Egress

  # No ingress allowed
  ingress: []

  # Restricted egress
  egress:
    # Allow DNS
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53

    # Allow LLM API endpoints
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
      ports:
        - protocol: TCP
          port: 443
      # Note: Further restricted by domain allowlist in egress proxy

---
# Egress proxy configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: egress-allowlist
  namespace: mellea-system
data:
  domains: |
    # OpenAI
    api.openai.com
    # Anthropic
    api.anthropic.com
    # Azure OpenAI (wildcard)
    *.openai.azure.com
    # Ollama (internal)
    ollama.mellea-system.svc.cluster.local
```

#### 4.8.3 Resource Limits Enforcement

```python
class ResourceEnforcer:
    """Enforce resource limits and handle violations."""

    async def monitor_pod(self, pod_name: str, limits: ResourceProfile) -> None:
        """Monitor pod and terminate if limits exceeded."""

        while True:
            metrics = await self._get_pod_metrics(pod_name)

            if not metrics:
                break  # Pod no longer exists

            # Check memory (OOM will be handled by kubelet, but we can warn)
            if metrics.memory_usage > limits.memory_limit * 0.9:
                await self._send_warning(
                    pod_name,
                    f"Memory usage at {metrics.memory_usage / limits.memory_limit * 100:.0f}%"
                )

            # Check execution time
            runtime = datetime.utcnow() - metrics.start_time
            if runtime.total_seconds() > limits.timeout_seconds:
                await self._terminate_pod(
                    pod_name,
                    reason="TIMEOUT",
                    message=f"Execution time limit ({limits.timeout_seconds}s) exceeded"
                )
                break

            await asyncio.sleep(5)

    async def _terminate_pod(
        self,
        pod_name: str,
        reason: str,
        message: str,
        grace_period: int = 30
    ) -> None:
        """Terminate pod with grace period."""

        # Send SIGTERM
        await self._signal_pod(pod_name, signal.SIGTERM)

        # Wait for graceful shutdown
        await asyncio.sleep(grace_period)

        # Force kill if still running
        if await self._pod_exists(pod_name):
            await self._delete_pod(pod_name, grace_period_seconds=0)

        # Record termination
        await self._record_termination(pod_name, reason, message)
```

#### 4.8.4 Seccomp Profile

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"],
  "syscalls": [
    {
      "names": [
        "read", "write", "open", "close", "stat", "fstat", "lstat",
        "poll", "lseek", "mmap", "mprotect", "munmap", "brk",
        "rt_sigaction", "rt_sigprocmask", "ioctl", "access",
        "pipe", "select", "sched_yield", "mremap", "msync",
        "mincore", "madvise", "dup", "dup2", "nanosleep",
        "getpid", "socket", "connect", "sendto", "recvfrom",
        "shutdown", "bind", "listen", "getsockname", "getpeername",
        "socketpair", "setsockopt", "getsockopt", "clone", "fork",
        "execve", "exit", "wait4", "kill", "uname", "fcntl",
        "flock", "fsync", "fdatasync", "truncate", "ftruncate",
        "getdents", "getcwd", "chdir", "rename", "mkdir", "rmdir",
        "unlink", "readlink", "chmod", "chown", "umask", "gettimeofday",
        "getrlimit", "getrusage", "sysinfo", "times", "getuid",
        "getgid", "geteuid", "getegid", "getgroups", "setgroups",
        "getpgid", "setpgid", "setsid", "getpgrp", "arch_prctl",
        "futex", "epoll_create", "epoll_ctl", "epoll_wait",
        "set_tid_address", "clock_gettime", "clock_getres",
        "exit_group", "tgkill", "openat", "newfstatat", "readlinkat",
        "getrandom", "memfd_create", "copy_file_range",
        "statx", "pread64", "pwrite64", "eventfd2", "pipe2"
      ],
      "action": "SCMP_ACT_ALLOW"
    },
    {
      "names": [
        "ptrace", "mount", "umount2", "reboot", "swapon", "swapoff",
        "init_module", "delete_module", "acct", "settimeofday",
        "sethostname", "setdomainname", "ioperm", "iopl"
      ],
      "action": "SCMP_ACT_ERRNO",
      "comment": "Dangerous syscalls - always blocked"
    }
  ]
}
```

### 4.9 Monitoring & Observability

#### 4.9.1 Metrics Collection

```typescript
interface PodMetrics {
  podName: string
  programId: string
  runId: string
  userId: string

  // Resource usage
  cpuUsageMillicores: number
  cpuLimitMillicores: number
  memoryUsageBytes: number
  memoryLimitBytes: number
  ephemeralStorageBytes: number

  // Network
  networkRxBytes: number
  networkTxBytes: number

  // Timing
  startTime: datetime
  currentTime: datetime
  runtimeSeconds: number

  // State
  phase: string           // "Pending", "Running", "Succeeded", "Failed"
  restartCount: number
}
```

#### 4.9.2 Abuse Detection

```python
class AbuseDetector:
    """Detect and respond to abusive workloads."""

    # Thresholds for abuse detection
    THRESHOLDS = {
        "max_network_tx_per_run_mb": 100,
        "max_cpu_spike_duration_seconds": 60,
        "max_restarts_per_hour": 10,
        "max_failed_runs_per_hour": 20
    }

    async def check_run(self, run: Run, metrics: PodMetrics) -> List[AbuseAlert]:
        alerts = []

        # Check network abuse (potential data exfiltration)
        if metrics.networkTxBytes > self.THRESHOLDS["max_network_tx_per_run_mb"] * 1024 * 1024:
            alerts.append(AbuseAlert(
                type="EXCESSIVE_NETWORK",
                severity="warning",
                message=f"High network egress: {metrics.networkTxBytes / 1024 / 1024:.0f}MB"
            ))

        # Check repeated failures (potential DoS)
        recent_failures = await self._count_failures(
            user_id=run.user_id,
            since=datetime.utcnow() - timedelta(hours=1)
        )
        if recent_failures > self.THRESHOLDS["max_failed_runs_per_hour"]:
            alerts.append(AbuseAlert(
                type="REPEATED_FAILURES",
                severity="critical",
                message=f"{recent_failures} failed runs in past hour"
            ))

            # Auto-throttle user
            await self._throttle_user(run.user_id, duration_minutes=30)

        return alerts

    async def _throttle_user(self, user_id: str, duration_minutes: int) -> None:
        """Temporarily reduce user's quota."""
        await quota_service.set_temporary_limit(
            user_id=user_id,
            max_concurrent_runs=1,
            max_runs_per_day=5,
            duration=timedelta(minutes=duration_minutes)
        )

        await notifications.send(
            user_id=user_id,
            type="quota_throttled",
            message=f"Your quota has been temporarily reduced due to unusual activity"
        )
```

### 4.10 LLM Connectivity

#### 4.10.1 Supported Providers

| Provider | Endpoint Pattern | Auth Method |
|----------|-----------------|-------------|
| OpenAI | `https://api.openai.com/v1` | Bearer token |
| Anthropic | `https://api.anthropic.com` | x-api-key header |
| Azure OpenAI | `https://{resource}.openai.azure.com` | api-key header |
| Ollama | `http://ollama.mellea-system:11434` | None (internal) |
| Custom | User-configured | Configurable |

#### 4.10.2 Connection Proxy

```python
class LLMProxy:
    """Proxy LLM requests for monitoring and rate limiting."""

    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.metrics_collector = MetricsCollector()

    async def proxy_request(
        self,
        request: LLMRequest,
        user_id: str,
        run_id: str
    ) -> LLMResponse:
        """Proxy an LLM API request."""

        # Rate limiting
        await self.rate_limiter.check(user_id)

        # Record request
        start_time = time.time()

        try:
            response = await self._forward_request(request)

            # Record metrics
            await self.metrics_collector.record(
                user_id=user_id,
                run_id=run_id,
                provider=request.provider,
                model=request.model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                latency_ms=(time.time() - start_time) * 1000,
                success=True
            )

            return response

        except Exception as e:
            await self.metrics_collector.record(
                user_id=user_id,
                run_id=run_id,
                provider=request.provider,
                model=request.model,
                latency_ms=(time.time() - start_time) * 1000,
                success=False,
                error=str(e)
            )
            raise
```

