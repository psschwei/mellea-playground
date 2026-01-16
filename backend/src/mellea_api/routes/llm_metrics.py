"""LLM metrics routes for tracking and querying LLM API usage."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from mellea_api.core.deps import CurrentUser
from mellea_api.models.common import ModelProvider
from mellea_api.models.llm_metrics import LLMUsageMetric
from mellea_api.services.llm_metrics_collector import (
    LLMMetricsCollectorService,
    get_llm_metrics_collector_service,
)

LLMMetricsServiceDep = Annotated[
    LLMMetricsCollectorService, Depends(get_llm_metrics_collector_service)
]

router = APIRouter(prefix="/api/v1/llm-metrics", tags=["llm-metrics"])


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------


class RecordUsageRequest(BaseModel):
    """Request body for recording LLM usage."""

    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(alias="runId", description="ID of the run")
    program_id: str = Field(alias="programId", description="ID of the program")
    provider: ModelProvider = Field(description="LLM provider")
    model_name: str = Field(alias="modelName", description="Model name")
    input_tokens: int = Field(
        default=0, alias="inputTokens", description="Input token count"
    )
    output_tokens: int = Field(
        default=0, alias="outputTokens", description="Output token count"
    )
    cost_usd: float = Field(default=0.0, alias="costUsd", description="Cost in USD")
    latency_ms: int = Field(default=0, alias="latencyMs", description="Latency in ms")
    success: bool = Field(default=True, description="Whether the call succeeded")
    error_message: str | None = Field(
        default=None, alias="errorMessage", description="Error message if failed"
    )
    metadata: dict[str, str | int | float | bool] | None = Field(
        default=None, description="Additional metadata"
    )


class MetricResponse(BaseModel):
    """Response wrapper for a single metric."""

    metric: LLMUsageMetric


class MetricsListResponse(BaseModel):
    """Response for list metrics operation."""

    metrics: list[LLMUsageMetric]
    total: int


class AggregateResponse(BaseModel):
    """Response for aggregated metrics."""

    model_config = ConfigDict(populate_by_name=True)

    period_start: str = Field(serialization_alias="periodStart")
    period_end: str = Field(serialization_alias="periodEnd")
    total_calls: int = Field(serialization_alias="totalCalls")
    successful_calls: int = Field(serialization_alias="successfulCalls")
    failed_calls: int = Field(serialization_alias="failedCalls")
    total_input_tokens: int = Field(serialization_alias="totalInputTokens")
    total_output_tokens: int = Field(serialization_alias="totalOutputTokens")
    total_tokens: int = Field(serialization_alias="totalTokens")
    total_cost_usd: float = Field(serialization_alias="totalCostUsd")
    avg_latency_ms: float = Field(serialization_alias="avgLatencyMs")
    by_provider: dict[str, dict[str, int | float]] = Field(serialization_alias="byProvider")
    by_model: dict[str, dict[str, int | float]] = Field(serialization_alias="byModel")


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------


@router.post("", response_model=MetricResponse, status_code=status.HTTP_201_CREATED)
async def record_usage(
    request: RecordUsageRequest,
    current_user: CurrentUser,
    metrics_service: LLMMetricsServiceDep,
) -> MetricResponse:
    """Record an LLM API usage metric.

    Records a single LLM API call with token counts, cost, and latency.
    The user_id is automatically set from the authenticated user.
    """
    metric = metrics_service.record_usage(
        run_id=request.run_id,
        program_id=request.program_id,
        user_id=current_user.id,
        provider=request.provider,
        model_name=request.model_name,
        input_tokens=request.input_tokens,
        output_tokens=request.output_tokens,
        cost_usd=request.cost_usd,
        latency_ms=request.latency_ms,
        success=request.success,
        error_message=request.error_message,
        metadata=request.metadata,
    )

    return MetricResponse(metric=metric)


@router.get("", response_model=MetricsListResponse)
async def list_metrics(
    current_user: CurrentUser,
    metrics_service: LLMMetricsServiceDep,
    provider: ModelProvider | None = Query(None, description="Filter by provider"),
    model_name: str | None = Query(
        None, alias="modelName", description="Filter by model name"
    ),
    success_only: bool = Query(
        False, alias="successOnly", description="Only show successful calls"
    ),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
) -> MetricsListResponse:
    """List LLM usage metrics with filtering.

    Returns metrics for the authenticated user within the specified time period.
    Admins can see all metrics; regular users only see their own.
    """
    since = datetime.utcnow()
    since = since.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta

    since = since - timedelta(days=days)

    # Admins see all metrics, users see only their own
    if current_user.role.value == "admin":
        metrics = metrics_service.list_metrics(
            since=since,
            provider=provider,
            model_name=model_name,
            success_only=success_only,
            limit=limit,
        )
    else:
        metrics = metrics_service.get_metrics_for_user(
            user_id=current_user.id,
            since=since,
            provider=provider,
        )
        # Apply additional filters not supported by get_metrics_for_user
        if model_name:
            metrics = [m for m in metrics if m.model_name == model_name]
        if success_only:
            metrics = [m for m in metrics if m.success]
        metrics = metrics[:limit]

    return MetricsListResponse(metrics=metrics, total=len(metrics))


@router.get("/summary", response_model=AggregateResponse)
async def get_summary(
    current_user: CurrentUser,
    metrics_service: LLMMetricsServiceDep,
    days: int = Query(30, ge=1, le=365, description="Number of days to aggregate"),
    program_id: str | None = Query(
        None, alias="programId", description="Filter by program ID"
    ),
) -> AggregateResponse:
    """Get aggregated usage summary.

    Returns summary statistics for the authenticated user's LLM usage.
    Admins can see system-wide summary; regular users see only their own.
    """
    # Admins see all, users see only their own
    user_id = None if current_user.role.value == "admin" else current_user.id

    aggregate = metrics_service.get_aggregate(
        days=days,
        user_id=user_id,
        program_id=program_id,
    )

    return AggregateResponse(
        period_start=aggregate.period_start.isoformat(),
        period_end=aggregate.period_end.isoformat(),
        total_calls=aggregate.total_calls,
        successful_calls=aggregate.successful_calls,
        failed_calls=aggregate.failed_calls,
        total_input_tokens=aggregate.total_input_tokens,
        total_output_tokens=aggregate.total_output_tokens,
        total_tokens=aggregate.total_tokens,
        total_cost_usd=aggregate.total_cost_usd,
        avg_latency_ms=aggregate.avg_latency_ms,
        by_provider=aggregate.by_provider,
        by_model=aggregate.by_model,
    )


@router.get("/runs/{run_id}", response_model=MetricsListResponse)
async def get_metrics_for_run(
    run_id: str,
    current_user: CurrentUser,
    metrics_service: LLMMetricsServiceDep,
) -> MetricsListResponse:
    """Get all metrics for a specific run.

    Returns all LLM API calls made during a specific program run.
    Users can only access metrics for runs they own.
    """
    metrics = metrics_service.get_metrics_for_run(run_id)

    # Check access: users can only see their own metrics
    if (
        metrics
        and current_user.role.value != "admin"
        and not any(m.user_id == current_user.id for m in metrics)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view metrics for this run",
        )

    return MetricsListResponse(metrics=metrics, total=len(metrics))


@router.get("/programs/{program_id}", response_model=MetricsListResponse)
async def get_metrics_for_program(
    program_id: str,
    current_user: CurrentUser,
    metrics_service: LLMMetricsServiceDep,
    limit: int = Query(100, ge=1, le=1000, description="Maximum results to return"),
) -> MetricsListResponse:
    """Get metrics for a specific program.

    Returns LLM usage metrics for all runs of a specific program.
    Users can only access metrics for their own runs.
    """
    metrics = metrics_service.get_metrics_for_program(program_id)

    # Filter by user if not admin
    if current_user.role.value != "admin":
        metrics = [m for m in metrics if m.user_id == current_user.id]

    metrics = metrics[:limit]

    return MetricsListResponse(metrics=metrics, total=len(metrics))


@router.get("/{metric_id}", response_model=MetricResponse)
async def get_metric(
    metric_id: str,
    current_user: CurrentUser,
    metrics_service: LLMMetricsServiceDep,
) -> MetricResponse:
    """Get a specific metric by ID.

    Returns details of a single LLM usage metric.
    """
    metric = metrics_service.get_metric(metric_id)
    if metric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metric not found: {metric_id}",
        )

    # Check access: users can only see their own metrics
    if current_user.role.value != "admin" and metric.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this metric",
        )

    return MetricResponse(metric=metric)
