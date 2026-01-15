"""Tests for KanikoBuildService."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from kubernetes.client import (
    V1ContainerState,
    V1ContainerStateTerminated,
    V1ContainerStatus,
    V1Job,
    V1JobCondition,
    V1JobStatus,
    V1ObjectMeta,
    V1Pod,
    V1PodList,
    V1PodStatus,
)
from kubernetes.client.exceptions import ApiException

from mellea_api.core.config import Settings
from mellea_api.models.assets import DependencySpec, PackageRef, ProgramAsset
from mellea_api.models.build import BuildJobStatus
from mellea_api.services.kaniko_builder import (
    BUILDS_NAMESPACE,
    KanikoBuildService,
    reset_kaniko_build_service,
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
def settings():
    """Create test settings."""
    return Settings(
        build_backend="kaniko",
        build_namespace="mellea-builds",
        kaniko_image="gcr.io/kaniko-project/executor:v1.23.0",
        build_timeout_seconds=1800,
        build_cpu_limit="2",
        build_memory_limit="2Gi",
        registry_url="localhost:5001",
    )


@pytest.fixture
def kaniko_service(mock_batch_api, mock_core_api, settings):
    """Create a KanikoBuildService with mocked clients."""
    service = KanikoBuildService(settings=settings)
    service._batch_api = mock_batch_api
    service._core_api = mock_core_api
    service._initialized = True
    return service


@pytest.fixture
def sample_program():
    """Create a sample program asset for testing."""
    return ProgramAsset(
        id="test-prog-1234",
        name="Test Program",
        type="program",
        owner="test-user",
        entrypoint="main.py",
        projectRoot="workspaces/test-prog-1234",
        dependencies=DependencySpec(
            source="manual",
            packages=[
                PackageRef(name="requests", version="2.31.0", extras=[]),
                PackageRef(name="pydantic", version="2.5.0", extras=["email"]),
            ],
            pythonVersion="3.12",
        ),
    )


@pytest.fixture(autouse=True)
def reset_service():
    """Reset the global service instance after each test."""
    yield
    reset_kaniko_build_service()


class TestJobNameGeneration:
    """Tests for job and configmap name generation."""

    def test_generate_job_name(self, kaniko_service: KanikoBuildService):
        """Test that job names use the correct format."""
        name = kaniko_service._generate_job_name("abc12345-6789-def0")
        assert name == "mellea-build-abc12345"

    def test_generate_configmap_name(self, kaniko_service: KanikoBuildService):
        """Test that configmap names use the correct format."""
        name = kaniko_service._generate_configmap_name("abc12345-6789-def0")
        assert name == "build-context-abc12345"


class TestBuildContextConfigMap:
    """Tests for build context ConfigMap creation."""

    def test_create_configmap_success(
        self, kaniko_service: KanikoBuildService, mock_core_api
    ):
        """Test successful ConfigMap creation."""
        kaniko_service._create_build_context_configmap(
            configmap_name="build-context-test1234",
            program_id="test1234-5678",
            dockerfile_content="FROM python:3.12-slim",
            context_files={"main.py": "print('hello')"},
        )

        mock_core_api.create_namespaced_config_map.assert_called_once()
        call_args = mock_core_api.create_namespaced_config_map.call_args
        assert call_args.kwargs["namespace"] == BUILDS_NAMESPACE

        configmap = call_args.kwargs["body"]
        assert configmap.metadata.name == "build-context-test1234"
        assert "Dockerfile" in configmap.data
        assert "main.py" in configmap.data

    def test_create_configmap_replaces_existing(
        self, kaniko_service: KanikoBuildService, mock_core_api
    ):
        """Test that existing ConfigMap is replaced on conflict."""
        # Simulate conflict on create
        mock_core_api.create_namespaced_config_map.side_effect = ApiException(status=409)

        kaniko_service._create_build_context_configmap(
            configmap_name="build-context-test1234",
            program_id="test1234-5678",
            dockerfile_content="FROM python:3.12-slim",
            context_files={},
        )

        mock_core_api.replace_namespaced_config_map.assert_called_once()


class TestKanikoJobSpec:
    """Tests for Kaniko job specification building."""

    def test_build_kaniko_job_spec_basic(
        self, kaniko_service: KanikoBuildService, settings
    ):
        """Test building a basic Kaniko job spec."""
        job = kaniko_service._build_kaniko_job_spec(
            job_name="mellea-build-test1234",
            program_id="test1234-5678",
            image_tag="localhost:5001/mellea-prog:test1234",
            configmap_name="build-context-test1234",
        )

        # Check job metadata
        assert job.metadata.name == "mellea-build-test1234"
        assert job.metadata.namespace == BUILDS_NAMESPACE
        assert job.metadata.labels["mellea.io/program-id"] == "test1234-5678"
        assert job.metadata.labels["mellea.io/job-type"] == "build"
        assert job.metadata.annotations["mellea.io/image-tag"] == "localhost:5001/mellea-prog:test1234"

        # Check job spec
        assert job.spec.active_deadline_seconds == settings.build_timeout_seconds

    def test_build_kaniko_job_spec_container(
        self, kaniko_service: KanikoBuildService, settings
    ):
        """Test that Kaniko container is correctly configured."""
        job = kaniko_service._build_kaniko_job_spec(
            job_name="test-job",
            program_id="prog-123",
            image_tag="registry/image:tag",
            configmap_name="context-map",
        )

        container = job.spec.template.spec.containers[0]

        # Check container image
        assert container.name == "kaniko"
        assert container.image == settings.kaniko_image

        # Check resource limits
        assert container.resources.limits["cpu"] == settings.build_cpu_limit
        assert container.resources.limits["memory"] == settings.build_memory_limit

        # Check Kaniko args
        assert "--dockerfile=/workspace/Dockerfile" in container.args
        assert "--context=dir:///workspace" in container.args
        assert "--destination=registry/image:tag" in container.args
        assert "--cache=false" in container.args

    def test_build_kaniko_job_spec_volumes(self, kaniko_service: KanikoBuildService):
        """Test that volumes are correctly configured."""
        job = kaniko_service._build_kaniko_job_spec(
            job_name="test-job",
            program_id="prog-123",
            image_tag="registry/image:tag",
            configmap_name="build-context-prog123",
        )

        volumes = job.spec.template.spec.volumes
        volume_names = [v.name for v in volumes]

        assert "build-context" in volume_names
        assert "docker-config" in volume_names

        # Check ConfigMap volume
        context_vol = next(v for v in volumes if v.name == "build-context")
        assert context_vol.config_map.name == "build-context-prog123"


class TestCreateBuildJob:
    """Tests for creating build jobs."""

    def test_create_build_job_success(
        self,
        kaniko_service: KanikoBuildService,
        mock_batch_api,
        mock_core_api,
        sample_program,
    ):
        """Test successful build job creation."""
        result = kaniko_service.create_build_job(
            program=sample_program,
            dockerfile_content="FROM python:3.12-slim",
            context_files={"main.py": "print('hello')"},
            image_tag="localhost:5001/mellea-prog:test-prog",
        )

        assert result.success is True
        assert result.program_id == sample_program.id
        assert result.build_job_name == "mellea-build-test-pro"
        assert result.image_tag == "localhost:5001/mellea-prog:test-prog"

        # Verify ConfigMap was created
        mock_core_api.create_namespaced_config_map.assert_called_once()

        # Verify Job was created
        mock_batch_api.create_namespaced_job.assert_called_once()

    def test_create_build_job_cleanup_existing(
        self,
        kaniko_service: KanikoBuildService,
        mock_batch_api,
        mock_core_api,
        sample_program,
    ):
        """Test that existing resources are cleaned up before creating new ones."""
        kaniko_service.create_build_job(
            program=sample_program,
            dockerfile_content="FROM python:3.12-slim",
            context_files={},
            image_tag="registry/image:tag",
        )

        # Verify cleanup was attempted
        mock_batch_api.delete_namespaced_job.assert_called_once()
        mock_core_api.delete_namespaced_config_map.assert_called_once()


class TestGetBuildStatus:
    """Tests for getting build status."""

    def test_get_build_status_pending(
        self, kaniko_service: KanikoBuildService, mock_batch_api
    ):
        """Test getting status of a pending build."""
        mock_job = V1Job(
            metadata=V1ObjectMeta(
                name="mellea-build-test1234",
                labels={"mellea.io/program-id": "test1234"},
                annotations={"mellea.io/image-tag": "registry/image:tag"},
            ),
            status=V1JobStatus(),
        )
        mock_batch_api.read_namespaced_job.return_value = mock_job

        build = kaniko_service.get_build_status("mellea-build-test1234")

        assert build.job_name == "mellea-build-test1234"
        assert build.status == BuildJobStatus.PENDING
        assert build.program_id == "test1234"

    def test_get_build_status_succeeded(
        self, kaniko_service: KanikoBuildService, mock_batch_api
    ):
        """Test getting status of a succeeded build."""
        mock_job = V1Job(
            metadata=V1ObjectMeta(
                name="mellea-build-test1234",
                labels={"mellea.io/program-id": "test1234"},
                annotations={"mellea.io/image-tag": "registry/image:tag"},
            ),
            status=V1JobStatus(
                succeeded=1,
                completion_time=datetime.now(UTC),
                conditions=[
                    V1JobCondition(type="Complete", status="True"),
                ],
            ),
        )
        mock_batch_api.read_namespaced_job.return_value = mock_job

        build = kaniko_service.get_build_status("mellea-build-test1234")

        assert build.status == BuildJobStatus.SUCCEEDED
        assert build.completed_at is not None

    def test_get_build_status_failed(
        self, kaniko_service: KanikoBuildService, mock_batch_api, mock_core_api
    ):
        """Test getting status of a failed build with error message."""
        mock_job = V1Job(
            metadata=V1ObjectMeta(
                name="mellea-build-test1234",
                labels={"mellea.io/program-id": "test1234"},
                annotations={"mellea.io/image-tag": "registry/image:tag"},
            ),
            status=V1JobStatus(
                failed=1,
                conditions=[
                    V1JobCondition(type="Failed", status="True"),
                ],
            ),
        )
        mock_batch_api.read_namespaced_job.return_value = mock_job

        # Mock pod with failure info
        mock_pod = V1Pod(
            metadata=V1ObjectMeta(name="build-pod"),
            status=V1PodStatus(
                container_statuses=[
                    V1ContainerStatus(
                        name="kaniko",
                        ready=False,
                        restart_count=0,
                        image="kaniko",
                        image_id="",
                        state=V1ContainerState(
                            terminated=V1ContainerStateTerminated(
                                exit_code=1,
                                reason="Error",
                                message="Build failed",
                            )
                        ),
                    )
                ]
            ),
        )
        mock_core_api.list_namespaced_pod.return_value = V1PodList(items=[mock_pod])

        build = kaniko_service.get_build_status("mellea-build-test1234")

        assert build.status == BuildJobStatus.FAILED
        assert build.error_message is not None
        assert "Error" in build.error_message

    def test_get_build_status_not_found(
        self, kaniko_service: KanikoBuildService, mock_batch_api
    ):
        """Test getting status of a non-existent build raises error."""
        mock_batch_api.read_namespaced_job.side_effect = ApiException(status=404)

        with pytest.raises(RuntimeError, match="not found"):
            kaniko_service.get_build_status("nonexistent-job")


class TestGetBuildLogs:
    """Tests for getting build logs."""

    def test_get_build_logs_success(
        self, kaniko_service: KanikoBuildService, mock_core_api
    ):
        """Test getting build logs successfully."""
        mock_pod = V1Pod(metadata=V1ObjectMeta(name="build-pod-xyz"))
        mock_core_api.list_namespaced_pod.return_value = V1PodList(items=[mock_pod])
        mock_core_api.read_namespaced_pod_log.return_value = "Building image...\nPushing to registry..."

        logs = kaniko_service.get_build_logs("mellea-build-test1234")

        assert "Building image" in logs
        mock_core_api.read_namespaced_pod_log.assert_called_once()

    def test_get_build_logs_no_pod(
        self, kaniko_service: KanikoBuildService, mock_core_api
    ):
        """Test getting logs when no pod exists yet."""
        mock_core_api.list_namespaced_pod.return_value = V1PodList(items=[])

        logs = kaniko_service.get_build_logs("mellea-build-test1234")

        assert "No pod found" in logs


class TestDeleteBuildJob:
    """Tests for deleting build jobs."""

    def test_delete_build_job_success(
        self, kaniko_service: KanikoBuildService, mock_batch_api, mock_core_api
    ):
        """Test successful build job deletion."""
        result = kaniko_service.delete_build_job("mellea-build-test1234")

        assert result is True
        mock_batch_api.delete_namespaced_job.assert_called_once()
        mock_core_api.delete_namespaced_config_map.assert_called_once()

    def test_delete_build_job_not_found(
        self, kaniko_service: KanikoBuildService, mock_batch_api, mock_core_api
    ):
        """Test deleting non-existent job returns False."""
        mock_batch_api.delete_namespaced_job.side_effect = ApiException(status=404)
        mock_core_api.delete_namespaced_config_map.side_effect = ApiException(status=404)

        result = kaniko_service.delete_build_job("nonexistent-job")

        assert result is False


class TestDetermineJobStatus:
    """Tests for job status determination."""

    def test_determine_status_no_status(self, kaniko_service: KanikoBuildService):
        """Test status is PENDING when job has no status."""
        job = V1Job(status=None)
        assert kaniko_service._determine_job_status(job) == BuildJobStatus.PENDING

    def test_determine_status_active(self, kaniko_service: KanikoBuildService):
        """Test status is RUNNING when job has active pods."""
        job = V1Job(status=V1JobStatus(active=1))
        assert kaniko_service._determine_job_status(job) == BuildJobStatus.RUNNING

    def test_determine_status_succeeded(self, kaniko_service: KanikoBuildService):
        """Test status is SUCCEEDED when job completed successfully."""
        job = V1Job(status=V1JobStatus(succeeded=1))
        assert kaniko_service._determine_job_status(job) == BuildJobStatus.SUCCEEDED

    def test_determine_status_failed(self, kaniko_service: KanikoBuildService):
        """Test status is FAILED when job failed."""
        job = V1Job(status=V1JobStatus(failed=1))
        assert kaniko_service._determine_job_status(job) == BuildJobStatus.FAILED
