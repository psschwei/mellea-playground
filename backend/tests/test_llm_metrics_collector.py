"""Tests for LLMMetricsCollectorService."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mellea_api.core.config import Settings
from mellea_api.models.common import ModelProvider
from mellea_api.services.llm_metrics_collector import LLMMetricsCollectorService


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def settings(temp_data_dir: Path):
    """Create test settings with temporary data directory."""
    settings = Settings(
        data_dir=temp_data_dir,
        llm_metrics_retention_days=90,
    )
    settings.ensure_data_dirs()
    return settings


@pytest.fixture
def metrics_service(settings: Settings):
    """Create an LLMMetricsCollectorService with test settings."""
    return LLMMetricsCollectorService(settings=settings)


class TestRecordUsage:
    """Tests for recording LLM usage metrics."""

    def test_record_usage_basic(self, metrics_service: LLMMetricsCollectorService):
        """Test recording a basic usage metric."""
        metric = metrics_service.record_usage(
            run_id="run-123",
            program_id="prog-456",
            user_id="user-789",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.01,
            latency_ms=500,
        )

        assert metric.id is not None
        assert metric.run_id == "run-123"
        assert metric.program_id == "prog-456"
        assert metric.user_id == "user-789"
        assert metric.provider == ModelProvider.OPENAI
        assert metric.model_name == "gpt-4"
        assert metric.input_tokens == 100
        assert metric.output_tokens == 200
        assert metric.total_tokens == 300
        assert metric.cost_usd == 0.01
        assert metric.latency_ms == 500
        assert metric.success is True
        assert metric.error_message is None

    def test_record_usage_with_error(self, metrics_service: LLMMetricsCollectorService):
        """Test recording a failed API call."""
        metric = metrics_service.record_usage(
            run_id="run-123",
            program_id="prog-456",
            user_id="user-789",
            provider=ModelProvider.ANTHROPIC,
            model_name="claude-3-opus",
            success=False,
            error_message="Rate limit exceeded",
        )

        assert metric.success is False
        assert metric.error_message == "Rate limit exceeded"
        assert metric.input_tokens == 0
        assert metric.output_tokens == 0

    def test_record_usage_with_metadata(self, metrics_service: LLMMetricsCollectorService):
        """Test recording usage with additional metadata."""
        metadata: dict[str, str | int | float | bool] = {"temperature": 0.7, "max_tokens": 1000}

        metric = metrics_service.record_usage(
            run_id="run-123",
            program_id="prog-456",
            user_id="user-789",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_tokens=50,
            output_tokens=100,
            metadata=metadata,
        )

        assert metric.metadata is not None
        assert metric.metadata["temperature"] == 0.7
        assert metric.metadata["max_tokens"] == 1000


class TestQueryMetrics:
    """Tests for querying metrics."""

    def test_get_metric_by_id(self, metrics_service: LLMMetricsCollectorService):
        """Test getting a metric by ID."""
        created = metrics_service.record_usage(
            run_id="run-123",
            program_id="prog-456",
            user_id="user-789",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )

        metric = metrics_service.get_metric(created.id)
        assert metric is not None
        assert metric.id == created.id

    def test_get_nonexistent_metric(self, metrics_service: LLMMetricsCollectorService):
        """Test getting a nonexistent metric."""
        metric = metrics_service.get_metric("nonexistent")
        assert metric is None

    def test_get_metrics_for_run(self, metrics_service: LLMMetricsCollectorService):
        """Test getting all metrics for a run."""
        # Create metrics for the same run
        for i in range(3):
            metrics_service.record_usage(
                run_id="run-123",
                program_id="prog-456",
                user_id="user-789",
                provider=ModelProvider.OPENAI,
                model_name="gpt-4",
                input_tokens=100 * (i + 1),
            )

        # Create metric for different run
        metrics_service.record_usage(
            run_id="run-other",
            program_id="prog-456",
            user_id="user-789",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )

        metrics = metrics_service.get_metrics_for_run("run-123")
        assert len(metrics) == 3
        assert all(m.run_id == "run-123" for m in metrics)

    def test_get_metrics_for_user(self, metrics_service: LLMMetricsCollectorService):
        """Test getting metrics for a user."""
        # Create metrics for user-123
        for _ in range(2):
            metrics_service.record_usage(
                run_id="run-1",
                program_id="prog-1",
                user_id="user-123",
                provider=ModelProvider.OPENAI,
                model_name="gpt-4",
            )

        # Create metric for different user
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-other",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )

        metrics = metrics_service.get_metrics_for_user("user-123")
        assert len(metrics) == 2
        assert all(m.user_id == "user-123" for m in metrics)

    def test_get_metrics_for_user_with_provider_filter(
        self, metrics_service: LLMMetricsCollectorService
    ):
        """Test filtering user metrics by provider."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-123",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-123",
            provider=ModelProvider.ANTHROPIC,
            model_name="claude-3",
        )

        metrics = metrics_service.get_metrics_for_user(
            "user-123", provider=ModelProvider.OPENAI
        )
        assert len(metrics) == 1
        assert metrics[0].provider == ModelProvider.OPENAI

    def test_get_metrics_for_program(self, metrics_service: LLMMetricsCollectorService):
        """Test getting metrics for a program."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-123",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-123",
            user_id="user-2",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )
        metrics_service.record_usage(
            run_id="run-3",
            program_id="prog-other",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )

        metrics = metrics_service.get_metrics_for_program("prog-123")
        assert len(metrics) == 2
        assert all(m.program_id == "prog-123" for m in metrics)

    def test_list_metrics_with_limit(self, metrics_service: LLMMetricsCollectorService):
        """Test listing metrics with a limit."""
        for i in range(10):
            metrics_service.record_usage(
                run_id=f"run-{i}",
                program_id="prog-1",
                user_id="user-1",
                provider=ModelProvider.OPENAI,
                model_name="gpt-4",
            )

        metrics = metrics_service.list_metrics(limit=5)
        assert len(metrics) == 5

    def test_list_metrics_filter_by_provider(
        self, metrics_service: LLMMetricsCollectorService
    ):
        """Test filtering metrics by provider."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.ANTHROPIC,
            model_name="claude-3",
        )

        metrics = metrics_service.list_metrics(provider=ModelProvider.ANTHROPIC)
        assert len(metrics) == 1
        assert metrics[0].provider == ModelProvider.ANTHROPIC

    def test_list_metrics_filter_by_model_name(
        self, metrics_service: LLMMetricsCollectorService
    ):
        """Test filtering metrics by model name."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-3.5-turbo",
        )

        metrics = metrics_service.list_metrics(model_name="gpt-4")
        assert len(metrics) == 1
        assert metrics[0].model_name == "gpt-4"

    def test_list_metrics_success_only(self, metrics_service: LLMMetricsCollectorService):
        """Test filtering to only successful calls."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            success=True,
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            success=False,
            error_message="Error",
        )

        metrics = metrics_service.list_metrics(success_only=True)
        assert len(metrics) == 1
        assert metrics[0].success is True


class TestAggregation:
    """Tests for metrics aggregation."""

    def test_get_aggregate_empty(self, metrics_service: LLMMetricsCollectorService):
        """Test aggregation with no metrics."""
        aggregate = metrics_service.get_aggregate(days=30)

        assert aggregate.total_calls == 0
        assert aggregate.successful_calls == 0
        assert aggregate.failed_calls == 0
        assert aggregate.total_tokens == 0
        assert aggregate.total_cost_usd == 0.0

    def test_get_aggregate_basic(self, metrics_service: LLMMetricsCollectorService):
        """Test basic aggregation."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.01,
            latency_ms=500,
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_tokens=50,
            output_tokens=100,
            cost_usd=0.005,
            latency_ms=300,
        )

        aggregate = metrics_service.get_aggregate(days=30)

        assert aggregate.total_calls == 2
        assert aggregate.successful_calls == 2
        assert aggregate.failed_calls == 0
        assert aggregate.total_input_tokens == 150
        assert aggregate.total_output_tokens == 300
        assert aggregate.total_tokens == 450
        assert aggregate.total_cost_usd == 0.015
        assert aggregate.avg_latency_ms == 400.0

    def test_get_aggregate_by_provider(self, metrics_service: LLMMetricsCollectorService):
        """Test aggregation includes by_provider breakdown."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_tokens=100,
            output_tokens=100,
            cost_usd=0.01,
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.ANTHROPIC,
            model_name="claude-3",
            input_tokens=50,
            output_tokens=50,
            cost_usd=0.005,
        )

        aggregate = metrics_service.get_aggregate(days=30)

        assert "openai" in aggregate.by_provider
        assert "anthropic" in aggregate.by_provider
        assert aggregate.by_provider["openai"]["calls"] == 1
        assert aggregate.by_provider["openai"]["tokens"] == 200
        assert aggregate.by_provider["anthropic"]["calls"] == 1
        assert aggregate.by_provider["anthropic"]["tokens"] == 100

    def test_get_aggregate_by_model(self, metrics_service: LLMMetricsCollectorService):
        """Test aggregation includes by_model breakdown."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_tokens=100,
            output_tokens=100,
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-3.5-turbo",
            input_tokens=50,
            output_tokens=50,
        )

        aggregate = metrics_service.get_aggregate(days=30)

        assert "openai:gpt-4" in aggregate.by_model
        assert "openai:gpt-3.5-turbo" in aggregate.by_model
        assert aggregate.by_model["openai:gpt-4"]["calls"] == 1
        assert aggregate.by_model["openai:gpt-3.5-turbo"]["calls"] == 1

    def test_get_aggregate_filter_by_user(
        self, metrics_service: LLMMetricsCollectorService
    ):
        """Test filtering aggregate by user."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_tokens=100,
            output_tokens=100,
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-2",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_tokens=50,
            output_tokens=50,
        )

        aggregate = metrics_service.get_aggregate(days=30, user_id="user-1")

        assert aggregate.total_calls == 1
        assert aggregate.total_tokens == 200

    def test_get_aggregate_filter_by_program(
        self, metrics_service: LLMMetricsCollectorService
    ):
        """Test filtering aggregate by program."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_tokens=100,
            output_tokens=100,
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-2",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_tokens=50,
            output_tokens=50,
        )

        aggregate = metrics_service.get_aggregate(days=30, program_id="prog-1")

        assert aggregate.total_calls == 1
        assert aggregate.total_tokens == 200

    def test_get_aggregate_with_failures(
        self, metrics_service: LLMMetricsCollectorService
    ):
        """Test aggregation counts failed calls."""
        metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            success=True,
        )
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            success=False,
            error_message="Error",
        )

        aggregate = metrics_service.get_aggregate(days=30)

        assert aggregate.total_calls == 2
        assert aggregate.successful_calls == 1
        assert aggregate.failed_calls == 1


class TestCleanup:
    """Tests for metrics cleanup."""

    def test_delete_metrics_for_run(self, metrics_service: LLMMetricsCollectorService):
        """Test deleting metrics for a run."""
        for _ in range(3):
            metrics_service.record_usage(
                run_id="run-123",
                program_id="prog-1",
                user_id="user-1",
                provider=ModelProvider.OPENAI,
                model_name="gpt-4",
            )

        metrics_service.record_usage(
            run_id="run-other",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )

        deleted = metrics_service.delete_metrics_for_run("run-123")
        assert deleted == 3

        # Verify metrics are deleted
        assert len(metrics_service.get_metrics_for_run("run-123")) == 0
        # Other run's metrics should remain
        assert len(metrics_service.get_metrics_for_run("run-other")) == 1

    def test_delete_old_metrics(self, metrics_service: LLMMetricsCollectorService):
        """Test deleting old metrics."""
        # Create a metric and manually set its created_at to be old
        metric = metrics_service.record_usage(
            run_id="run-1",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )

        # Manually update the metric to be old
        old_metric = metrics_service.get_metric(metric.id)
        assert old_metric is not None
        # Update via direct store access
        old_metric.created_at = datetime.utcnow() - timedelta(days=100)
        metrics_service.metrics_store.update(old_metric.id, old_metric)

        # Create a recent metric
        metrics_service.record_usage(
            run_id="run-2",
            program_id="prog-1",
            user_id="user-1",
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
        )

        deleted = metrics_service.delete_old_metrics(retention_days=90)
        assert deleted == 1

        # Recent metric should remain
        all_metrics = metrics_service.list_metrics()
        assert len(all_metrics) == 1
        assert all_metrics[0].run_id == "run-2"
