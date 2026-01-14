"""Kaniko build service for in-cluster container image builds."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from mellea_api.core.config import Settings, get_settings
from mellea_api.models.assets import ProgramAsset
from mellea_api.models.build import BuildJob, BuildJobStatus, BuildResult

if TYPE_CHECKING:
    from kubernetes.client import BatchV1Api, CoreV1Api, V1Job

logger = logging.getLogger(__name__)

# Namespace for build jobs
BUILDS_NAMESPACE = "mellea-builds"

# Job configuration defaults
DEFAULT_TTL_SECONDS = 3600  # 1 hour after completion
DEFAULT_BACKOFF_LIMIT = 1  # Allow one retry for transient failures

# Docker config secret name (for registry auth)
DOCKER_CONFIG_SECRET = "kaniko-docker-config"


class KanikoBuildService:
    """Service for building container images using Kaniko in Kubernetes.

    Kaniko builds container images inside a Kubernetes cluster without
    requiring a Docker daemon, making it suitable for in-cluster builds.

    Example:
        ```python
        service = get_kaniko_build_service()
        result = await service.create_build_job(
            program=program,
            dockerfile_content="FROM python:3.12-slim...",
            context_files={"main.py": "print('hello')"},
            image_tag="registry.io/mellea-prog:abc123",
        )
        status = service.get_build_status(result.build_job_name)
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the Kaniko build service with lazy-loaded clients."""
        self.settings = settings or get_settings()
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

    def _generate_job_name(self, program_id: str) -> str:
        """Generate a unique job name from program ID."""
        short_id = program_id[:8].lower()
        return f"mellea-build-{short_id}"

    def _generate_configmap_name(self, program_id: str) -> str:
        """Generate a ConfigMap name for build context."""
        short_id = program_id[:8].lower()
        return f"build-context-{short_id}"

    def _create_build_context_configmap(
        self,
        configmap_name: str,
        program_id: str,
        dockerfile_content: str,
        context_files: dict[str, str],
    ) -> None:
        """Create a ConfigMap containing the build context.

        Args:
            configmap_name: Name for the ConfigMap
            program_id: Program ID for labeling
            dockerfile_content: Dockerfile content
            context_files: Dictionary of filename -> content
        """
        # Combine Dockerfile and context files
        data = {"Dockerfile": dockerfile_content}
        data.update(context_files)

        configmap = client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            metadata=client.V1ObjectMeta(
                name=configmap_name,
                namespace=BUILDS_NAMESPACE,
                labels={
                    "app.kubernetes.io/part-of": "mellea",
                    "mellea.io/program-id": program_id,
                    "mellea.io/resource-type": "build-context",
                },
            ),
            data=data,
        )

        try:
            self.core_api.create_namespaced_config_map(
                namespace=BUILDS_NAMESPACE,
                body=configmap,
            )
            logger.info("Created build context ConfigMap: %s", configmap_name)
        except ApiException as e:
            if e.status == 409:
                # ConfigMap exists, replace it
                self.core_api.replace_namespaced_config_map(
                    name=configmap_name,
                    namespace=BUILDS_NAMESPACE,
                    body=configmap,
                )
                logger.info("Replaced existing build context ConfigMap: %s", configmap_name)
            else:
                raise RuntimeError(f"Failed to create ConfigMap: {e.reason}") from e

    def _build_kaniko_job_spec(
        self,
        job_name: str,
        program_id: str,
        image_tag: str,
        configmap_name: str,
    ) -> V1Job:
        """Build the Kubernetes Job specification for a Kaniko build.

        Args:
            job_name: Name for the job
            program_id: Program ID for labeling
            image_tag: Full image tag including registry (e.g., registry.io/mellea-prog:abc)
            configmap_name: Name of the ConfigMap containing build context

        Returns:
            V1Job specification ready for creation
        """
        # Build Kaniko arguments
        kaniko_args = [
            "--dockerfile=/workspace/Dockerfile",
            "--context=dir:///workspace",
            f"--destination={image_tag}",
            "--cache=true",
            "--snapshot-mode=redo",
            "--use-new-run",  # Better layer caching
        ]

        # Add cache repo if registry is configured
        if self.settings.registry_url:
            cache_repo = f"{self.settings.registry_url}/mellea-cache"
            kaniko_args.append(f"--cache-repo={cache_repo}")

        # Volume mounts for Kaniko container
        volume_mounts = [
            # Build context from ConfigMap
            client.V1VolumeMount(
                name="build-context",
                mount_path="/workspace",
            ),
            # Docker config for registry auth
            client.V1VolumeMount(
                name="docker-config",
                mount_path="/kaniko/.docker",
                read_only=True,
            ),
        ]

        # Volumes
        volumes = [
            # ConfigMap with Dockerfile and source files
            client.V1Volume(
                name="build-context",
                config_map=client.V1ConfigMapVolumeSource(
                    name=configmap_name,
                ),
            ),
            # Docker config secret for registry auth
            client.V1Volume(
                name="docker-config",
                secret=client.V1SecretVolumeSource(
                    secret_name=DOCKER_CONFIG_SECRET,
                    optional=True,  # Allow builds without registry auth (for local registries)
                    default_mode=0o400,
                ),
            ),
        ]

        # Kaniko container
        container = client.V1Container(
            name="kaniko",
            image=self.settings.kaniko_image,
            args=kaniko_args,
            resources=client.V1ResourceRequirements(
                requests={
                    "cpu": "500m",
                    "memory": "512Mi",
                },
                limits={
                    "cpu": self.settings.build_cpu_limit,
                    "memory": self.settings.build_memory_limit,
                },
            ),
            volume_mounts=volume_mounts,
        )

        # Pod spec
        pod_spec = client.V1PodSpec(
            restart_policy="Never",
            containers=[container],
            volumes=volumes,
        )

        # Job spec
        job_spec = client.V1JobSpec(
            ttl_seconds_after_finished=DEFAULT_TTL_SECONDS,
            active_deadline_seconds=self.settings.build_timeout_seconds,
            backoff_limit=DEFAULT_BACKOFF_LIMIT,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app.kubernetes.io/part-of": "mellea",
                        "mellea.io/program-id": program_id,
                        "mellea.io/job-type": "build",
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
                namespace=BUILDS_NAMESPACE,
                labels={
                    "app.kubernetes.io/part-of": "mellea",
                    "mellea.io/program-id": program_id,
                    "mellea.io/job-type": "build",
                },
                annotations={
                    "mellea.io/image-tag": image_tag,
                    "mellea.io/configmap": configmap_name,
                },
            ),
            spec=job_spec,
        )

    def create_build_job(
        self,
        program: ProgramAsset,
        dockerfile_content: str,
        context_files: dict[str, str],
        image_tag: str,
    ) -> BuildResult:
        """Create a Kaniko build job.

        Args:
            program: The program asset to build
            dockerfile_content: Dockerfile content
            context_files: Dictionary of filename -> content for build context
            image_tag: Full destination image tag (e.g., registry.io/mellea-prog:abc123)

        Returns:
            BuildResult with job info (success=True indicates job created, not completed)
        """
        job_name = self._generate_job_name(program.id)
        configmap_name = self._generate_configmap_name(program.id)

        try:
            # Delete any existing job/configmap for this program
            self._cleanup_existing_build(job_name, configmap_name)

            # Create build context ConfigMap
            self._create_build_context_configmap(
                configmap_name=configmap_name,
                program_id=program.id,
                dockerfile_content=dockerfile_content,
                context_files=context_files,
            )

            # Build job spec
            job = self._build_kaniko_job_spec(
                job_name=job_name,
                program_id=program.id,
                image_tag=image_tag,
                configmap_name=configmap_name,
            )

            # Create the job
            self.batch_api.create_namespaced_job(namespace=BUILDS_NAMESPACE, body=job)
            logger.info("Created Kaniko build job %s for program %s", job_name, program.id)

            return BuildResult(
                program_id=program.id,
                success=True,
                image_tag=image_tag,
                cache_hit=False,
                total_duration_seconds=0.0,
                build_job_name=job_name,
            )

        except ApiException as e:
            logger.error("Failed to create build job: %s", e)
            return BuildResult(
                program_id=program.id,
                success=False,
                error_message=f"Failed to create build job: {e.reason}",
                total_duration_seconds=0.0,
            )

    def _cleanup_existing_build(self, job_name: str, configmap_name: str) -> None:
        """Clean up any existing build resources for this program."""
        # Delete existing job if present
        try:
            self.batch_api.delete_namespaced_job(
                name=job_name,
                namespace=BUILDS_NAMESPACE,
                body=client.V1DeleteOptions(propagation_policy="Background"),
            )
            logger.debug("Deleted existing build job: %s", job_name)
        except ApiException as e:
            if e.status != 404:
                logger.warning("Failed to delete existing job %s: %s", job_name, e.reason)

        # Delete existing ConfigMap if present
        try:
            self.core_api.delete_namespaced_config_map(
                name=configmap_name,
                namespace=BUILDS_NAMESPACE,
            )
            logger.debug("Deleted existing ConfigMap: %s", configmap_name)
        except ApiException as e:
            if e.status != 404:
                logger.warning("Failed to delete existing ConfigMap %s: %s", configmap_name, e.reason)

    def get_build_status(self, job_name: str) -> BuildJob:
        """Get the current status of a build job.

        Args:
            job_name: Name of the build job

        Returns:
            BuildJob with current status

        Raises:
            RuntimeError: If job cannot be found or queried
        """
        try:
            job = self.batch_api.read_namespaced_job(name=job_name, namespace=BUILDS_NAMESPACE)
        except ApiException as e:
            if e.status == 404:
                raise RuntimeError(f"Build job {job_name} not found") from e
            raise RuntimeError(f"Failed to get build status: {e.reason}") from e

        # Determine status
        status = self._determine_job_status(job)

        # Get error message if failed
        error_message = None
        if status == BuildJobStatus.FAILED:
            error_message = self._get_failure_reason(job_name)

        # Get image tag from annotation
        image_tag = job.metadata.annotations.get("mellea.io/image-tag", "") if job.metadata.annotations else ""
        program_id = job.metadata.labels.get("mellea.io/program-id", "") if job.metadata.labels else ""

        return BuildJob(
            job_name=job_name,
            program_id=program_id,
            image_tag=image_tag,
            status=status,
            started_at=job.status.start_time if job.status else None,
            completed_at=job.status.completion_time if job.status else None,
            error_message=error_message,
        )

    def _determine_job_status(self, job: V1Job) -> BuildJobStatus:
        """Determine the BuildJobStatus from a V1Job object."""
        if not job.status:
            return BuildJobStatus.PENDING

        # Check for completion conditions
        if job.status.conditions:
            for condition in job.status.conditions:
                if condition.type == "Complete" and condition.status == "True":
                    return BuildJobStatus.SUCCEEDED
                if condition.type == "Failed" and condition.status == "True":
                    return BuildJobStatus.FAILED

        # Check active/succeeded/failed counts
        if job.status.succeeded and job.status.succeeded > 0:
            return BuildJobStatus.SUCCEEDED
        if job.status.failed and job.status.failed > 0:
            return BuildJobStatus.FAILED
        if job.status.active and job.status.active > 0:
            return BuildJobStatus.RUNNING

        return BuildJobStatus.PENDING

    def _get_failure_reason(self, job_name: str) -> str | None:
        """Get the failure reason from pod logs or status."""
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=BUILDS_NAMESPACE,
                label_selector=f"job-name={job_name}",
            )
            if pods.items:
                pod = pods.items[0]
                if pod.status and pod.status.container_statuses:
                    container_status = pod.status.container_statuses[0]
                    if container_status.state and container_status.state.terminated:
                        reason = container_status.state.terminated.reason
                        message = container_status.state.terminated.message
                        if message:
                            return f"{reason}: {message}"
                        return reason
        except ApiException as e:
            logger.warning("Failed to get failure reason for %s: %s", job_name, e)
        return None

    def get_build_logs(self, job_name: str, tail_lines: int = 100) -> str:
        """Get logs from a build job.

        Args:
            job_name: Name of the build job
            tail_lines: Number of log lines to return (default: 100)

        Returns:
            Log output as string

        Raises:
            RuntimeError: If logs cannot be retrieved
        """
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=BUILDS_NAMESPACE,
                label_selector=f"job-name={job_name}",
            )
            if not pods.items:
                return "No pod found for build job"

            pod_name = pods.items[0].metadata.name
            logs = self.core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=BUILDS_NAMESPACE,
                container="kaniko",
                tail_lines=tail_lines,
            )
            return logs
        except ApiException as e:
            if e.status == 404:
                return "Pod not found or logs not available yet"
            raise RuntimeError(f"Failed to get build logs: {e.reason}") from e

    def delete_build_job(self, job_name: str) -> bool:
        """Delete a build job and its ConfigMap.

        Args:
            job_name: Name of the build job

        Returns:
            True if deleted, False if not found
        """
        configmap_name = job_name.replace("mellea-build-", "build-context-")
        deleted = False

        try:
            self.batch_api.delete_namespaced_job(
                name=job_name,
                namespace=BUILDS_NAMESPACE,
                body=client.V1DeleteOptions(propagation_policy="Background"),
            )
            logger.info("Deleted build job: %s", job_name)
            deleted = True
        except ApiException as e:
            if e.status != 404:
                logger.warning("Failed to delete job %s: %s", job_name, e.reason)

        try:
            self.core_api.delete_namespaced_config_map(
                name=configmap_name,
                namespace=BUILDS_NAMESPACE,
            )
            logger.info("Deleted ConfigMap: %s", configmap_name)
        except ApiException as e:
            if e.status != 404:
                logger.warning("Failed to delete ConfigMap %s: %s", configmap_name, e.reason)

        return deleted

    def wait_for_build(
        self,
        job_name: str,
        timeout_seconds: int = 600,
        poll_interval: int = 5,
    ) -> BuildJob:
        """Wait for a build job to complete.

        Args:
            job_name: Name of the build job
            timeout_seconds: Maximum time to wait
            poll_interval: Seconds between status checks

        Returns:
            Final BuildJob status

        Raises:
            TimeoutError: If build doesn't complete within timeout
        """
        import time

        start_time = time.time()
        while True:
            build = self.get_build_status(job_name)
            if build.status in (BuildJobStatus.SUCCEEDED, BuildJobStatus.FAILED):
                return build

            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                raise TimeoutError(f"Build job {job_name} did not complete within {timeout_seconds}s")

            time.sleep(poll_interval)


# Global singleton instance
_kaniko_build_service: KanikoBuildService | None = None


def get_kaniko_build_service() -> KanikoBuildService:
    """Get the global KanikoBuildService instance."""
    global _kaniko_build_service
    if _kaniko_build_service is None:
        _kaniko_build_service = KanikoBuildService()
    return _kaniko_build_service


def reset_kaniko_build_service() -> None:
    """Reset the global service instance (for testing)."""
    global _kaniko_build_service
    _kaniko_build_service = None
