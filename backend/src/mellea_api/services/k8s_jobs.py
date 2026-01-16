"""Kubernetes Job service for managing program execution jobs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from mellea_api.models.environment import ResourceLimits
from mellea_api.models.k8s import JobInfo, JobStatus

if TYPE_CHECKING:
    from kubernetes.client import BatchV1Api, CoreV1Api, V1Job

logger = logging.getLogger(__name__)

# Namespace constants
RUNS_NAMESPACE = "mellea-runs"
BUILDS_NAMESPACE = "mellea-builds"
CREDENTIALS_NAMESPACE = "mellea-credentials"

# Secret mount configuration
SECRETS_MOUNT_PATH = "/var/run/secrets/mellea"

# Job configuration defaults
DEFAULT_TTL_SECONDS = 3600  # 1 hour after completion
DEFAULT_BACKOFF_LIMIT = 0  # No retries
DEFAULT_USER_ID = 1000
DEFAULT_GROUP_ID = 1000
RUN_SERVICE_ACCOUNT = "mellea-run"
DEFAULT_TERMINATION_GRACE_PERIOD = 30  # Seconds to wait for graceful shutdown


class K8sJobService:
    """Manages Kubernetes Jobs for program runs.

    This service creates and manages Kubernetes Jobs for executing user programs
    in isolated containers with resource limits and security constraints.

    Example:
        ```python
        service = K8sJobService()
        job_name = service.create_run_job(
            environment_id="env-123",
            image_tag="mellea-prog:abc123",
            resource_limits=ResourceLimits(cpu_cores=2.0, memory_mb=1024),
            entrypoint="main.py",
        )
        status = service.get_job_status(job_name, RUNS_NAMESPACE)
        ```
    """

    def __init__(self) -> None:
        """Initialize the K8s job service with lazy-loaded clients."""
        self._batch_api: BatchV1Api | None = None
        self._core_api: CoreV1Api | None = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Initialize Kubernetes clients if not already done."""
        if self._initialized:
            return

        try:
            # Try in-cluster config first (when running in K8s)
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            # Fall back to kubeconfig (for local development)
            try:
                config.load_kube_config()
                logger.info("Loaded kubeconfig Kubernetes configuration")
            except config.ConfigException as e:
                logger.warning("Failed to load Kubernetes configuration: %s", e)
                raise RuntimeError("No Kubernetes configuration available") from e

        self._batch_api = client.BatchV1Api()
        self._core_api = client.CoreV1Api()
        self._initialized = True

    @property
    def batch_api(self) -> BatchV1Api:
        """Get the BatchV1 API client."""
        self._ensure_initialized()
        assert self._batch_api is not None
        return self._batch_api

    @property
    def core_api(self) -> CoreV1Api:
        """Get the CoreV1 API client."""
        self._ensure_initialized()
        assert self._core_api is not None
        return self._core_api

    def _generate_job_name(self, prefix: str, environment_id: str) -> str:
        """Generate a unique job name from environment ID."""
        # Use first 8 chars of environment ID for uniqueness
        short_id = environment_id[:8].lower()
        return f"{prefix}-{short_id}"

    def _build_run_job_spec(
        self,
        job_name: str,
        environment_id: str,
        image_tag: str,
        resource_limits: ResourceLimits,
        entrypoint: str,
        secret_names: list[str] | None = None,
    ) -> V1Job:
        """Build the Kubernetes Job specification for a program run.

        Args:
            job_name: Name for the job
            environment_id: ID of the environment being run
            image_tag: Docker image tag to run
            resource_limits: CPU, memory, and timeout constraints
            entrypoint: Python file to execute
            secret_names: List of K8s Secret names to inject as volumes

        Returns:
            V1Job specification ready for creation
        """
        # Resource requests (half of limits) and limits
        cpu_request = str(resource_limits.cpu_cores * 0.5)
        cpu_limit = str(resource_limits.cpu_cores)
        memory_request = f"{resource_limits.memory_mb // 2}Mi"
        memory_limit = f"{resource_limits.memory_mb}Mi"

        # Base volume mounts
        volume_mounts = [
            client.V1VolumeMount(name="tmp", mount_path="/tmp"),
            client.V1VolumeMount(name="output", mount_path="/output"),
        ]

        # Base volumes
        volumes = [
            client.V1Volume(name="tmp", empty_dir=client.V1EmptyDirVolumeSource()),
            client.V1Volume(name="output", empty_dir=client.V1EmptyDirVolumeSource()),
        ]

        # Add secret volume if credentials are provided
        if secret_names:
            # Add volume mount for secrets
            volume_mounts.append(
                client.V1VolumeMount(
                    name="mellea-secrets",
                    mount_path=SECRETS_MOUNT_PATH,
                    read_only=True,
                )
            )

            # Build projected volume sources from secrets
            # Each secret is mounted in a subdirectory named after the secret
            secret_sources = [
                client.V1VolumeProjection(
                    secret=client.V1SecretProjection(
                        name=secret_name,
                        items=None,  # Mount all keys from the secret
                    )
                )
                for secret_name in secret_names
            ]

            # Add projected volume combining all secrets
            volumes.append(
                client.V1Volume(
                    name="mellea-secrets",
                    projected=client.V1ProjectedVolumeSource(
                        sources=secret_sources,
                        default_mode=0o400,  # Read-only for owner
                    ),
                )
            )

            logger.debug(
                "Adding %d secrets to job %s: %s",
                len(secret_names),
                job_name,
                secret_names,
            )

        # Container spec with security context
        container = client.V1Container(
            name="program",
            image=image_tag,
            command=["python", entrypoint],
            resources=client.V1ResourceRequirements(
                requests={"cpu": cpu_request, "memory": memory_request},
                limits={"cpu": cpu_limit, "memory": memory_limit},
            ),
            security_context=client.V1SecurityContext(
                allow_privilege_escalation=False,
                capabilities=client.V1Capabilities(drop=["ALL"]),
                read_only_root_filesystem=True,
            ),
            volume_mounts=volume_mounts,
        )

        # Pod spec with security context
        # Use service account if secrets are being injected (for cross-namespace access)
        service_account = RUN_SERVICE_ACCOUNT if secret_names else None
        pod_spec = client.V1PodSpec(
            restart_policy="Never",
            service_account_name=service_account,
            termination_grace_period_seconds=DEFAULT_TERMINATION_GRACE_PERIOD,
            security_context=client.V1PodSecurityContext(
                run_as_non_root=True,
                run_as_user=DEFAULT_USER_ID,
                fs_group=DEFAULT_GROUP_ID,
                seccomp_profile=client.V1SeccompProfile(
                    type="RuntimeDefault",
                ),
            ),
            containers=[container],
            volumes=volumes,
        )

        # Job spec
        job_spec = client.V1JobSpec(
            ttl_seconds_after_finished=DEFAULT_TTL_SECONDS,
            active_deadline_seconds=resource_limits.timeout_seconds,
            backoff_limit=DEFAULT_BACKOFF_LIMIT,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app.kubernetes.io/part-of": "mellea",
                        "mellea.io/environment-id": environment_id,
                        "mellea.io/job-type": "run",
                    }
                ),
                spec=pod_spec,
            ),
        )

        # Full job
        return client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=job_name,
                namespace=RUNS_NAMESPACE,
                labels={
                    "app.kubernetes.io/part-of": "mellea",
                    "mellea.io/environment-id": environment_id,
                    "mellea.io/job-type": "run",
                },
            ),
            spec=job_spec,
        )

    def create_run_job(
        self,
        environment_id: str,
        image_tag: str,
        resource_limits: ResourceLimits | None = None,
        entrypoint: str = "main.py",
        secret_names: list[str] | None = None,
    ) -> str:
        """Create a Kubernetes Job to run a program.

        Args:
            environment_id: ID of the environment to run
            image_tag: Docker image tag for the program
            resource_limits: Optional resource constraints (uses defaults if None)
            entrypoint: Python file to execute (default: main.py)
            secret_names: List of K8s Secret names to inject into the container

        Returns:
            Name of the created job

        Raises:
            RuntimeError: If job creation fails
        """
        if resource_limits is None:
            resource_limits = ResourceLimits()

        job_name = self._generate_job_name("mellea-run", environment_id)
        job = self._build_run_job_spec(
            job_name=job_name,
            environment_id=environment_id,
            image_tag=image_tag,
            resource_limits=resource_limits,
            entrypoint=entrypoint,
            secret_names=secret_names,
        )

        try:
            self.batch_api.create_namespaced_job(namespace=RUNS_NAMESPACE, body=job)
            logger.info("Created run job %s for environment %s", job_name, environment_id)
            return job_name
        except ApiException as e:
            logger.error("Failed to create run job: %s", e)
            raise RuntimeError(f"Failed to create run job: {e.reason}") from e

    def get_job_status(self, job_name: str, namespace: str = RUNS_NAMESPACE) -> JobInfo:
        """Get the current status of a Kubernetes Job.

        Args:
            job_name: Name of the job
            namespace: Kubernetes namespace (default: mellea-runs)

        Returns:
            JobInfo with current status and metadata

        Raises:
            RuntimeError: If job cannot be found or queried
        """
        try:
            job = self.batch_api.read_namespaced_job(name=job_name, namespace=namespace)
        except ApiException as e:
            if e.status == 404:
                raise RuntimeError(f"Job {job_name} not found in namespace {namespace}") from e
            raise RuntimeError(f"Failed to get job status: {e.reason}") from e

        # Determine status from job conditions
        status = self._determine_job_status(job)

        # Get pod info if available
        pod_name = None
        exit_code = None
        error_message = None

        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"job-name={job_name}",
            )
            if pods.items:
                pod = pods.items[0]
                pod_name = pod.metadata.name
                # Get exit code from container status
                if pod.status and pod.status.container_statuses:
                    container_status = pod.status.container_statuses[0]
                    if container_status.state and container_status.state.terminated:
                        exit_code = container_status.state.terminated.exit_code
                        if exit_code != 0:
                            error_message = container_status.state.terminated.reason
        except ApiException as e:
            logger.warning("Failed to get pod info for job %s: %s", job_name, e)

        return JobInfo(
            name=job_name,
            namespace=namespace,
            status=status,
            startTime=job.status.start_time if job.status else None,
            completionTime=job.status.completion_time if job.status else None,
            podName=pod_name,
            exitCode=exit_code,
            errorMessage=error_message,
        )

    def get_pod_logs(
        self,
        job_name: str,
        namespace: str = RUNS_NAMESPACE,
        tail_lines: int | None = None,
    ) -> str | None:
        """Get logs from the pod associated with a job.

        Args:
            job_name: Name of the job
            namespace: Kubernetes namespace (default: mellea-runs)
            tail_lines: Number of lines to return from the end (None = all logs)

        Returns:
            Pod logs as a string, or None if pod not found or logs unavailable
        """
        try:
            # Find the pod for this job
            pods = self.core_api.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"job-name={job_name}",
            )
            if not pods.items:
                logger.debug("No pods found for job %s", job_name)
                return None

            pod = pods.items[0]
            pod_name = pod.metadata.name

            # Check if the pod has started running (has container status)
            if not pod.status or not pod.status.container_statuses:
                logger.debug("Pod %s has no container status yet", pod_name)
                return None

            # Get logs from the pod
            logs = self.core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container="program",
                tail_lines=tail_lines,
            )
            return logs

        except ApiException as e:
            if e.status == 404:
                logger.debug("Pod not found for job %s", job_name)
            else:
                logger.warning("Failed to get logs for job %s: %s", job_name, e)
            return None

    def _determine_job_status(self, job: V1Job) -> JobStatus:
        """Determine the JobStatus from a V1Job object."""
        if not job.status:
            return JobStatus.PENDING

        # Check for completion conditions
        if job.status.conditions:
            for condition in job.status.conditions:
                if condition.type == "Complete" and condition.status == "True":
                    return JobStatus.SUCCEEDED
                if condition.type == "Failed" and condition.status == "True":
                    return JobStatus.FAILED

        # Check active/succeeded/failed counts
        if job.status.succeeded and job.status.succeeded > 0:
            return JobStatus.SUCCEEDED
        if job.status.failed and job.status.failed > 0:
            return JobStatus.FAILED
        if job.status.active and job.status.active > 0:
            return JobStatus.RUNNING

        return JobStatus.PENDING

    def delete_job(
        self,
        job_name: str,
        namespace: str = RUNS_NAMESPACE,
        propagation_policy: str = "Background",
        grace_period_seconds: int | None = None,
    ) -> None:
        """Delete a Kubernetes Job and its pods.

        Args:
            job_name: Name of the job to delete
            namespace: Kubernetes namespace
            propagation_policy: How to delete dependent pods
                - "Background": Delete job, pods cleaned up async
                - "Foreground": Wait for pods to be deleted
                - "Orphan": Delete job, leave pods
            grace_period_seconds: Time to wait for graceful termination.
                If None, uses pod's terminationGracePeriodSeconds.
                If 0, forces immediate termination (SIGKILL).

        Raises:
            RuntimeError: If deletion fails
        """
        try:
            delete_options = client.V1DeleteOptions(
                propagation_policy=propagation_policy,
                grace_period_seconds=grace_period_seconds,
            )
            self.batch_api.delete_namespaced_job(
                name=job_name,
                namespace=namespace,
                body=delete_options,
            )
            logger.info(
                "Deleted job %s from namespace %s (grace_period=%s)",
                job_name,
                namespace,
                grace_period_seconds,
            )
        except ApiException as e:
            if e.status == 404:
                logger.warning("Job %s not found, already deleted?", job_name)
                return
            raise RuntimeError(f"Failed to delete job: {e.reason}") from e

    def cancel_job(
        self,
        job_name: str,
        namespace: str = RUNS_NAMESPACE,
        force: bool = False,
    ) -> None:
        """Cancel a running Kubernetes Job with graceful shutdown.

        This method sends SIGTERM to allow the process to clean up,
        waits for the termination grace period, then sends SIGKILL.

        Args:
            job_name: Name of the job to cancel
            namespace: Kubernetes namespace
            force: If True, immediately terminates without grace period (SIGKILL).
                   If False, allows graceful shutdown with SIGTERM first.

        Raises:
            RuntimeError: If cancellation fails
        """
        if force:
            # Immediate termination - skip grace period
            logger.info("Force cancelling job %s (immediate termination)", job_name)
            self.delete_job(
                job_name,
                namespace=namespace,
                propagation_policy="Foreground",
                grace_period_seconds=0,
            )
        else:
            # Graceful shutdown - let K8s use the pod's terminationGracePeriodSeconds
            logger.info("Gracefully cancelling job %s", job_name)
            self.delete_job(
                job_name,
                namespace=namespace,
                propagation_policy="Foreground",
                grace_period_seconds=None,  # Use pod's configured grace period
            )

    def list_jobs(
        self,
        namespace: str = RUNS_NAMESPACE,
        environment_id: str | None = None,
    ) -> list[JobInfo]:
        """List jobs in a namespace, optionally filtered by environment.

        Args:
            namespace: Kubernetes namespace to list from
            environment_id: Optional environment ID to filter by

        Returns:
            List of JobInfo for matching jobs
        """
        label_selector = "app.kubernetes.io/part-of=mellea"
        if environment_id:
            label_selector += f",mellea.io/environment-id={environment_id}"

        try:
            jobs = self.batch_api.list_namespaced_job(
                namespace=namespace,
                label_selector=label_selector,
            )
        except ApiException as e:
            raise RuntimeError(f"Failed to list jobs: {e.reason}") from e

        return [
            JobInfo(
                name=job.metadata.name,
                namespace=namespace,
                status=self._determine_job_status(job),
                startTime=job.status.start_time if job.status else None,
                completionTime=job.status.completion_time if job.status else None,
            )
            for job in jobs.items
        ]


# Global singleton instance
_k8s_job_service: K8sJobService | None = None


def get_k8s_job_service() -> K8sJobService:
    """Get the global K8sJobService instance."""
    global _k8s_job_service
    if _k8s_job_service is None:
        _k8s_job_service = K8sJobService()
    return _k8s_job_service
