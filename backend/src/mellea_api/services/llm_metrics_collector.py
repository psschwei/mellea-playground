"""LLM Metrics Collector Service for tracking LLM API usage."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.common import ModelProvider
from mellea_api.models.llm_metrics import LLMMetricsAggregate, LLMUsageMetric

logger = logging.getLogger(__name__)


class LLMMetricsCollectorService:
    """Service for collecting and querying LLM usage metrics.

    Provides methods for recording LLM API calls and querying usage statistics.
    Metrics are persisted to a JSON store and can be filtered by various criteria.

    Example:
        ```python
        service = get_llm_metrics_collector_service()

        # Record a usage metric
        metric = service.record_usage(
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

        # Get metrics for a run
        metrics = service.get_metrics_for_run("run-123")

        # Get aggregated summary
        summary = service.get_aggregate(days=7)
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the LLMMetricsCollectorService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._metrics_store: JsonStore[LLMUsageMetric] | None = None

    @property
    def metrics_store(self) -> JsonStore[LLMUsageMetric]:
        """Get the metrics store, initializing if needed."""
        if self._metrics_store is None:
            file_path = self.settings.data_dir / "metadata" / "llm_metrics.json"
            self._metrics_store = JsonStore[LLMUsageMetric](
                file_path=file_path,
                collection_key="metrics",
                model_class=LLMUsageMetric,
            )
        return self._metrics_store

    # -------------------------------------------------------------------------
    # Recording Metrics
    # -------------------------------------------------------------------------

    def record_usage(
        self,
        run_id: str,
        program_id: str,
        user_id: str,
        provider: ModelProvider,
        model_name: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        success: bool = True,
        error_message: str | None = None,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> LLMUsageMetric:
        """Record an LLM API usage metric.

        Args:
            run_id: ID of the run that made the API call
            program_id: ID of the program being executed
            user_id: ID of the user who owns the run
            provider: LLM provider (openai, anthropic, etc.)
            model_name: Specific model used (gpt-4, claude-3-opus, etc.)
            input_tokens: Number of input/prompt tokens
            output_tokens: Number of output/completion tokens
            cost_usd: Estimated cost in USD
            latency_ms: API call latency in milliseconds
            success: Whether the API call succeeded
            error_message: Error message if the call failed
            metadata: Additional provider-specific metadata

        Returns:
            The created LLMUsageMetric
        """
        metric = LLMUsageMetric(
            run_id=run_id,
            program_id=program_id,
            user_id=user_id,
            provider=provider,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
            metadata=metadata,
        )

        created = self.metrics_store.create(metric)
        logger.debug(
            f"Recorded LLM usage: run={run_id} provider={provider.value} "
            f"model={model_name} tokens={created.total_tokens} cost=${cost_usd:.4f}"
        )
        return created

    # -------------------------------------------------------------------------
    # Querying Metrics
    # -------------------------------------------------------------------------

    def get_metric(self, metric_id: str) -> LLMUsageMetric | None:
        """Get a metric by ID.

        Args:
            metric_id: Metric's unique identifier

        Returns:
            LLMUsageMetric if found, None otherwise
        """
        return self.metrics_store.get_by_id(metric_id)

    def get_metrics_for_run(self, run_id: str) -> list[LLMUsageMetric]:
        """Get all metrics for a specific run.

        Args:
            run_id: Run's unique identifier

        Returns:
            List of metrics for the run, sorted by created_at
        """
        metrics = self.metrics_store.find(lambda m: m.run_id == run_id)
        return sorted(metrics, key=lambda m: m.created_at)

    def get_metrics_for_user(
        self,
        user_id: str,
        since: datetime | None = None,
        provider: ModelProvider | None = None,
    ) -> list[LLMUsageMetric]:
        """Get all metrics for a specific user.

        Args:
            user_id: User's unique identifier
            since: Only return metrics after this time
            provider: Filter by provider

        Returns:
            List of metrics for the user, sorted by created_at descending
        """

        def predicate(m: LLMUsageMetric) -> bool:
            if m.user_id != user_id:
                return False
            if since and m.created_at < since:
                return False
            return not (provider and m.provider != provider)

        metrics = self.metrics_store.find(predicate)
        return sorted(metrics, key=lambda m: m.created_at, reverse=True)

    def get_metrics_for_program(self, program_id: str) -> list[LLMUsageMetric]:
        """Get all metrics for a specific program.

        Args:
            program_id: Program's unique identifier

        Returns:
            List of metrics for the program, sorted by created_at descending
        """
        metrics = self.metrics_store.find(lambda m: m.program_id == program_id)
        return sorted(metrics, key=lambda m: m.created_at, reverse=True)

    def list_metrics(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        provider: ModelProvider | None = None,
        model_name: str | None = None,
        success_only: bool = False,
        limit: int | None = None,
    ) -> list[LLMUsageMetric]:
        """List metrics with filtering.

        Args:
            since: Only return metrics after this time
            until: Only return metrics before this time
            provider: Filter by provider
            model_name: Filter by model name
            success_only: Only return successful calls
            limit: Maximum number of results to return

        Returns:
            List of matching metrics, sorted by created_at descending
        """

        def predicate(m: LLMUsageMetric) -> bool:
            if since and m.created_at < since:
                return False
            if until and m.created_at > until:
                return False
            if provider and m.provider != provider:
                return False
            if model_name and m.model_name != model_name:
                return False
            return not (success_only and not m.success)

        metrics = self.metrics_store.find(predicate)
        metrics = sorted(metrics, key=lambda m: m.created_at, reverse=True)

        if limit:
            metrics = metrics[:limit]

        return metrics

    # -------------------------------------------------------------------------
    # Aggregation
    # -------------------------------------------------------------------------

    def get_aggregate(
        self,
        days: int = 30,
        user_id: str | None = None,
        program_id: str | None = None,
    ) -> LLMMetricsAggregate:
        """Get aggregated usage statistics.

        Args:
            days: Number of days to aggregate (default 30)
            user_id: Filter by user ID
            program_id: Filter by program ID

        Returns:
            LLMMetricsAggregate with summary statistics
        """
        now = datetime.utcnow()
        period_start = now - timedelta(days=days)

        def predicate(m: LLMUsageMetric) -> bool:
            if m.created_at < period_start:
                return False
            if user_id and m.user_id != user_id:
                return False
            return not (program_id and m.program_id != program_id)

        metrics = self.metrics_store.find(predicate)

        aggregate = LLMMetricsAggregate(
            period_start=period_start,
            period_end=now,
        )

        if not metrics:
            return aggregate

        total_latency = 0
        by_provider: dict[str, dict[str, int | float]] = {}
        by_model: dict[str, dict[str, int | float]] = {}

        for m in metrics:
            aggregate.total_calls += 1
            if m.success:
                aggregate.successful_calls += 1
            else:
                aggregate.failed_calls += 1

            aggregate.total_input_tokens += m.input_tokens
            aggregate.total_output_tokens += m.output_tokens
            aggregate.total_tokens += m.total_tokens
            aggregate.total_cost_usd += m.cost_usd
            total_latency += m.latency_ms

            # Aggregate by provider
            provider_key = m.provider.value
            if provider_key not in by_provider:
                by_provider[provider_key] = {
                    "calls": 0,
                    "tokens": 0,
                    "cost_usd": 0.0,
                }
            by_provider[provider_key]["calls"] = int(by_provider[provider_key]["calls"]) + 1
            by_provider[provider_key]["tokens"] = (
                int(by_provider[provider_key]["tokens"]) + m.total_tokens
            )
            by_provider[provider_key]["cost_usd"] = (
                float(by_provider[provider_key]["cost_usd"]) + m.cost_usd
            )

            # Aggregate by model
            model_key = f"{m.provider.value}:{m.model_name}"
            if model_key not in by_model:
                by_model[model_key] = {
                    "calls": 0,
                    "tokens": 0,
                    "cost_usd": 0.0,
                }
            by_model[model_key]["calls"] = int(by_model[model_key]["calls"]) + 1
            by_model[model_key]["tokens"] = int(by_model[model_key]["tokens"]) + m.total_tokens
            by_model[model_key]["cost_usd"] = (
                float(by_model[model_key]["cost_usd"]) + m.cost_usd
            )

        aggregate.avg_latency_ms = total_latency / aggregate.total_calls
        aggregate.by_provider = by_provider
        aggregate.by_model = by_model

        return aggregate

    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------

    def delete_metrics_for_run(self, run_id: str) -> int:
        """Delete all metrics for a specific run.

        Args:
            run_id: Run's unique identifier

        Returns:
            Number of metrics deleted
        """
        metrics = self.get_metrics_for_run(run_id)
        deleted = 0
        for m in metrics:
            if self.metrics_store.delete(m.id):
                deleted += 1

        if deleted > 0:
            logger.info(f"Deleted {deleted} metrics for run {run_id}")

        return deleted

    def delete_old_metrics(self, retention_days: int) -> int:
        """Delete metrics older than retention period.

        Args:
            retention_days: Delete metrics older than this many days

        Returns:
            Number of metrics deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        old_metrics = self.metrics_store.find(lambda m: m.created_at < cutoff)

        deleted = 0
        for m in old_metrics:
            if self.metrics_store.delete(m.id):
                deleted += 1

        if deleted > 0:
            logger.info(f"Deleted {deleted} metrics older than {retention_days} days")

        return deleted


# Global service instance
_llm_metrics_collector_service: LLMMetricsCollectorService | None = None


def get_llm_metrics_collector_service() -> LLMMetricsCollectorService:
    """Get the global LLMMetricsCollectorService instance."""
    global _llm_metrics_collector_service
    if _llm_metrics_collector_service is None:
        _llm_metrics_collector_service = LLMMetricsCollectorService()
    return _llm_metrics_collector_service
