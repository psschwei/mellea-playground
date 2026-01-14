"""Tests for K8sJobService."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from kubernetes.client import V1Job, V1JobCondition, V1JobStatus, V1ObjectMeta

from mellea_api.models.environment import ResourceLimits
from mellea_api.models.k8s import JobInfo, JobStatus
from mellea_api.services.k8s_jobs import (
    DEFAULT_BACKOFF_LIMIT,
    DEFAULT_TERMINATION_GRACE_PERIOD,
    DEFAULT_TTL_SECONDS,
    DEFAULT_USER_ID,
    RUNS_NAMESPACE,
    K8sJobService,
)


@pytest.fixture
def mock_batch_api():
    """Create a mock BatchV1Api."""
    return MagicMock()


@pytest.fixture
def mock_core_api():
    """Create a mock CoreV1Api."""
    return MagicMock()


@pytest.fixture
def k8s_service(mock_batch_api, mock_core_api):
    """Create a K8sJobService with mocked clients."""
    service = K8sJobService()
    service._batch_api = mock_batch_api
    service._core_api = mock_core_api
    service._initialized = True
    return service


class TestJobNameGeneration:
    """Tests for job name generation."""

    def test_generate_job_name_uses_prefix_and_short_id(self, k8s_service: K8sJobService):
        """Test that job names use the prefix and first 8 chars of ID."""
        name = k8s_service._generate_job_name("mellea-run", "abc12345-6789-def0")
        assert name == "mellea-run-abc12345"

    def test_generate_job_name_lowercase(self, k8s_service: K8sJobService):
        """Test that job names are lowercase."""
        name = k8s_service._generate_job_name("mellea-run", "ABC12345")
        assert name == "mellea-run-abc12345"


class TestBuildRunJobSpec:
    """Tests for run job specification building."""

    def test_build_run_job_spec_basic(self, k8s_service: K8sJobService):
        """Test building a basic run job spec."""
        limits = ResourceLimits(cpuCores=2.0, memoryMb=1024, timeoutSeconds=600)
        job = k8s_service._build_run_job_spec(
            job_name="mellea-run-abc12345",
            environment_id="abc12345-6789",
            image_tag="mellea-prog:test123",
            resource_limits=limits,
            entrypoint="main.py",
        )

        # Check job metadata
        assert job.metadata.name == "mellea-run-abc12345"
        assert job.metadata.namespace == RUNS_NAMESPACE
        assert job.metadata.labels["mellea.io/environment-id"] == "abc12345-6789"
        assert job.metadata.labels["mellea.io/job-type"] == "run"

        # Check job spec
        assert job.spec.ttl_seconds_after_finished == DEFAULT_TTL_SECONDS
        assert job.spec.active_deadline_seconds == 600
        assert job.spec.backoff_limit == DEFAULT_BACKOFF_LIMIT

    def test_build_run_job_spec_resource_limits(self, k8s_service: K8sJobService):
        """Test that resource limits are correctly applied."""
        limits = ResourceLimits(cpuCores=4.0, memoryMb=2048, timeoutSeconds=900)
        job = k8s_service._build_run_job_spec(
            job_name="test-job",
            environment_id="env-123",
            image_tag="test:latest",
            resource_limits=limits,
            entrypoint="run.py",
        )

        container = job.spec.template.spec.containers[0]

        # Check resource requests (half of limits)
        assert container.resources.requests["cpu"] == "2.0"
        assert container.resources.requests["memory"] == "1024Mi"

        # Check resource limits
        assert container.resources.limits["cpu"] == "4.0"
        assert container.resources.limits["memory"] == "2048Mi"

    def test_build_run_job_spec_security_context(self, k8s_service: K8sJobService):
        """Test that security context is correctly configured."""
        limits = ResourceLimits()
        job = k8s_service._build_run_job_spec(
            job_name="test-job",
            environment_id="env-123",
            image_tag="test:latest",
            resource_limits=limits,
            entrypoint="main.py",
        )

        # Pod security context
        pod_security = job.spec.template.spec.security_context
        assert pod_security.run_as_non_root is True
        assert pod_security.run_as_user == DEFAULT_USER_ID
        assert pod_security.fs_group == DEFAULT_USER_ID

        # Container security context
        container = job.spec.template.spec.containers[0]
        container_security = container.security_context
        assert container_security.allow_privilege_escalation is False
        assert "ALL" in container_security.capabilities.drop
        assert container_security.read_only_root_filesystem is True

    def test_build_run_job_spec_volumes(self, k8s_service: K8sJobService):
        """Test that volumes are correctly configured."""
        limits = ResourceLimits()
        job = k8s_service._build_run_job_spec(
            job_name="test-job",
            environment_id="env-123",
            image_tag="test:latest",
            resource_limits=limits,
            entrypoint="main.py",
        )

        # Check volumes
        volumes = job.spec.template.spec.volumes
        volume_names = [v.name for v in volumes]
        assert "tmp" in volume_names
        assert "output" in volume_names

        # Check volume mounts
        container = job.spec.template.spec.containers[0]
        mount_paths = {m.name: m.mount_path for m in container.volume_mounts}
        assert mount_paths["tmp"] == "/tmp"
        assert mount_paths["output"] == "/output"

    def test_build_run_job_spec_entrypoint(self, k8s_service: K8sJobService):
        """Test that entrypoint is correctly set."""
        limits = ResourceLimits()
        job = k8s_service._build_run_job_spec(
            job_name="test-job",
            environment_id="env-123",
            image_tag="test:latest",
            resource_limits=limits,
            entrypoint="scripts/run_analysis.py",
        )

        container = job.spec.template.spec.containers[0]
        assert container.command == ["python", "scripts/run_analysis.py"]

    def test_build_run_job_spec_termination_grace_period(self, k8s_service: K8sJobService):
        """Test that termination grace period is set for graceful shutdown."""
        limits = ResourceLimits()
        job = k8s_service._build_run_job_spec(
            job_name="test-job",
            environment_id="env-123",
            image_tag="test:latest",
            resource_limits=limits,
            entrypoint="main.py",
        )

        # Check that termination grace period is set on pod spec
        pod_spec = job.spec.template.spec
        assert pod_spec.termination_grace_period_seconds == DEFAULT_TERMINATION_GRACE_PERIOD


class TestCreateRunJob:
    """Tests for creating run jobs."""

    def test_create_run_job_success(self, k8s_service: K8sJobService, mock_batch_api):
        """Test successful job creation."""
        mock_batch_api.create_namespaced_job.return_value = MagicMock()

        job_name = k8s_service.create_run_job(
            environment_id="env-abc12345",
            image_tag="mellea-prog:test",
            resource_limits=ResourceLimits(),
            entrypoint="main.py",
        )

        assert job_name == "mellea-run-env-abc1"
        mock_batch_api.create_namespaced_job.assert_called_once()
        call_args = mock_batch_api.create_namespaced_job.call_args
        assert call_args.kwargs["namespace"] == RUNS_NAMESPACE

    def test_create_run_job_default_limits(self, k8s_service: K8sJobService, mock_batch_api):
        """Test job creation with default resource limits."""
        mock_batch_api.create_namespaced_job.return_value = MagicMock()

        k8s_service.create_run_job(
            environment_id="env-123",
            image_tag="test:latest",
        )

        # Verify the job was created with defaults
        call_args = mock_batch_api.create_namespaced_job.call_args
        job = call_args.kwargs["body"]
        assert job.spec.active_deadline_seconds == 300  # Default timeout


class TestDetermineJobStatus:
    """Tests for job status determination."""

    def test_determine_status_no_status(self, k8s_service: K8sJobService):
        """Test status determination when job has no status."""
        job = V1Job(status=None)
        assert k8s_service._determine_job_status(job) == JobStatus.PENDING

    def test_determine_status_succeeded_condition(self, k8s_service: K8sJobService):
        """Test status determination with Complete condition."""
        job = V1Job(
            status=V1JobStatus(
                conditions=[V1JobCondition(type="Complete", status="True")]
            )
        )
        assert k8s_service._determine_job_status(job) == JobStatus.SUCCEEDED

    def test_determine_status_failed_condition(self, k8s_service: K8sJobService):
        """Test status determination with Failed condition."""
        job = V1Job(
            status=V1JobStatus(
                conditions=[V1JobCondition(type="Failed", status="True")]
            )
        )
        assert k8s_service._determine_job_status(job) == JobStatus.FAILED

    def test_determine_status_active(self, k8s_service: K8sJobService):
        """Test status determination when job is active."""
        job = V1Job(status=V1JobStatus(active=1, succeeded=0, failed=0))
        assert k8s_service._determine_job_status(job) == JobStatus.RUNNING

    def test_determine_status_succeeded_count(self, k8s_service: K8sJobService):
        """Test status determination from succeeded count."""
        job = V1Job(status=V1JobStatus(active=0, succeeded=1, failed=0))
        assert k8s_service._determine_job_status(job) == JobStatus.SUCCEEDED

    def test_determine_status_failed_count(self, k8s_service: K8sJobService):
        """Test status determination from failed count."""
        job = V1Job(status=V1JobStatus(active=0, succeeded=0, failed=1))
        assert k8s_service._determine_job_status(job) == JobStatus.FAILED


class TestGetJobStatus:
    """Tests for getting job status."""

    def test_get_job_status_success(
        self, k8s_service: K8sJobService, mock_batch_api, mock_core_api
    ):
        """Test getting job status successfully."""
        start_time = datetime.now(UTC)
        mock_job = V1Job(
            metadata=V1ObjectMeta(name="test-job"),
            status=V1JobStatus(
                active=1,
                start_time=start_time,
            ),
        )
        mock_batch_api.read_namespaced_job.return_value = mock_job
        mock_core_api.list_namespaced_pod.return_value = MagicMock(items=[])

        result = k8s_service.get_job_status("test-job", RUNS_NAMESPACE)

        assert isinstance(result, JobInfo)
        assert result.name == "test-job"
        assert result.namespace == RUNS_NAMESPACE
        assert result.status == JobStatus.RUNNING
        assert result.start_time == start_time


class TestDeleteJob:
    """Tests for deleting jobs."""

    def test_delete_job_success(self, k8s_service: K8sJobService, mock_batch_api):
        """Test successful job deletion."""
        mock_batch_api.delete_namespaced_job.return_value = MagicMock()

        k8s_service.delete_job("test-job", RUNS_NAMESPACE)

        mock_batch_api.delete_namespaced_job.assert_called_once()
        call_args = mock_batch_api.delete_namespaced_job.call_args
        assert call_args.kwargs["name"] == "test-job"
        assert call_args.kwargs["namespace"] == RUNS_NAMESPACE

    def test_delete_job_with_grace_period(self, k8s_service: K8sJobService, mock_batch_api):
        """Test job deletion with custom grace period."""
        mock_batch_api.delete_namespaced_job.return_value = MagicMock()

        k8s_service.delete_job("test-job", RUNS_NAMESPACE, grace_period_seconds=60)

        call_args = mock_batch_api.delete_namespaced_job.call_args
        delete_options = call_args.kwargs["body"]
        assert delete_options.grace_period_seconds == 60

    def test_delete_job_immediate(self, k8s_service: K8sJobService, mock_batch_api):
        """Test immediate job deletion (grace_period_seconds=0)."""
        mock_batch_api.delete_namespaced_job.return_value = MagicMock()

        k8s_service.delete_job("test-job", RUNS_NAMESPACE, grace_period_seconds=0)

        call_args = mock_batch_api.delete_namespaced_job.call_args
        delete_options = call_args.kwargs["body"]
        assert delete_options.grace_period_seconds == 0


class TestCancelJob:
    """Tests for cancelling jobs with graceful shutdown."""

    def test_cancel_job_graceful(self, k8s_service: K8sJobService, mock_batch_api):
        """Test graceful job cancellation uses Foreground propagation and default grace period."""
        mock_batch_api.delete_namespaced_job.return_value = MagicMock()

        k8s_service.cancel_job("test-job", RUNS_NAMESPACE, force=False)

        mock_batch_api.delete_namespaced_job.assert_called_once()
        call_args = mock_batch_api.delete_namespaced_job.call_args
        delete_options = call_args.kwargs["body"]
        # Graceful uses Foreground propagation and pod's configured grace period
        assert delete_options.propagation_policy == "Foreground"
        assert delete_options.grace_period_seconds is None

    def test_cancel_job_force(self, k8s_service: K8sJobService, mock_batch_api):
        """Test forced job cancellation uses immediate termination."""
        mock_batch_api.delete_namespaced_job.return_value = MagicMock()

        k8s_service.cancel_job("test-job", RUNS_NAMESPACE, force=True)

        mock_batch_api.delete_namespaced_job.assert_called_once()
        call_args = mock_batch_api.delete_namespaced_job.call_args
        delete_options = call_args.kwargs["body"]
        # Force uses immediate termination (grace_period_seconds=0)
        assert delete_options.propagation_policy == "Foreground"
        assert delete_options.grace_period_seconds == 0

    def test_cancel_job_default_is_graceful(self, k8s_service: K8sJobService, mock_batch_api):
        """Test that cancel_job defaults to graceful cancellation."""
        mock_batch_api.delete_namespaced_job.return_value = MagicMock()

        k8s_service.cancel_job("test-job")

        call_args = mock_batch_api.delete_namespaced_job.call_args
        delete_options = call_args.kwargs["body"]
        # Default should be graceful (no immediate termination)
        assert delete_options.grace_period_seconds is None


class TestListJobs:
    """Tests for listing jobs."""

    def test_list_jobs_basic(self, k8s_service: K8sJobService, mock_batch_api):
        """Test listing jobs in a namespace."""
        mock_job = V1Job(
            metadata=V1ObjectMeta(name="test-job-1"),
            status=V1JobStatus(active=1),
        )
        mock_batch_api.list_namespaced_job.return_value = MagicMock(items=[mock_job])

        jobs = k8s_service.list_jobs(RUNS_NAMESPACE)

        assert len(jobs) == 1
        assert jobs[0].name == "test-job-1"
        assert jobs[0].status == JobStatus.RUNNING

    def test_list_jobs_with_environment_filter(
        self, k8s_service: K8sJobService, mock_batch_api
    ):
        """Test listing jobs filtered by environment ID."""
        mock_batch_api.list_namespaced_job.return_value = MagicMock(items=[])

        k8s_service.list_jobs(RUNS_NAMESPACE, environment_id="env-123")

        call_args = mock_batch_api.list_namespaced_job.call_args
        label_selector = call_args.kwargs["label_selector"]
        assert "mellea.io/environment-id=env-123" in label_selector


class TestJobInfoModel:
    """Tests for the JobInfo model."""

    def test_job_info_creation(self):
        """Test creating a JobInfo instance."""
        now = datetime.now(UTC)
        info = JobInfo(
            name="test-job",
            namespace="mellea-runs",
            status=JobStatus.RUNNING,
            startTime=now,
            podName="test-pod-abc",
        )

        assert info.name == "test-job"
        assert info.namespace == "mellea-runs"
        assert info.status == JobStatus.RUNNING
        assert info.start_time == now
        assert info.pod_name == "test-pod-abc"
        assert info.exit_code is None
        assert info.completion_time is None

    def test_job_status_enum_values(self):
        """Test JobStatus enum values."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.SUCCEEDED.value == "succeeded"
        assert JobStatus.FAILED.value == "failed"
