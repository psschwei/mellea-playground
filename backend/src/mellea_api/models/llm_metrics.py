"""LLM usage metrics models for tracking API calls and costs."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from mellea_api.models.common import ModelProvider


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class LLMUsageMetric(BaseModel):
    """Individual LLM API call usage record.

    Tracks a single LLM API call with token counts, cost, and latency.

    Attributes:
        id: Unique identifier for this metric record
        run_id: ID of the run that made this API call
        program_id: ID of the program being executed
        user_id: ID of the user who owns the run
        provider: LLM provider (openai, anthropic, etc.)
        model_name: Specific model used (gpt-4, claude-3-opus, etc.)
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
        total_tokens: Total tokens (input + output)
        cost_usd: Estimated cost in USD
        latency_ms: API call latency in milliseconds
        success: Whether the API call succeeded
        error_message: Error message if the call failed
        metadata: Additional provider-specific metadata
        created_at: When the API call was made
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=generate_uuid)
    run_id: str = Field(validation_alias="runId", serialization_alias="runId")
    program_id: str = Field(validation_alias="programId", serialization_alias="programId")
    user_id: str = Field(validation_alias="userId", serialization_alias="userId")
    provider: ModelProvider
    model_name: str = Field(validation_alias="modelName", serialization_alias="modelName")
    input_tokens: int = Field(
        default=0, validation_alias="inputTokens", serialization_alias="inputTokens"
    )
    output_tokens: int = Field(
        default=0, validation_alias="outputTokens", serialization_alias="outputTokens"
    )
    total_tokens: int = Field(
        default=0, validation_alias="totalTokens", serialization_alias="totalTokens"
    )
    cost_usd: float = Field(
        default=0.0, validation_alias="costUsd", serialization_alias="costUsd"
    )
    latency_ms: int = Field(
        default=0, validation_alias="latencyMs", serialization_alias="latencyMs"
    )
    success: bool = True
    error_message: str | None = Field(
        default=None, validation_alias="errorMessage", serialization_alias="errorMessage"
    )
    metadata: dict[str, str | int | float | bool] | None = None
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        validation_alias="createdAt",
        serialization_alias="createdAt",
    )


@dataclass
class LLMMetricsAggregate:
    """Aggregated LLM usage statistics.

    Provides summary statistics for a collection of LLM usage metrics,
    useful for reporting and dashboards.

    Attributes:
        period_start: Start of the aggregation period
        period_end: End of the aggregation period
        total_calls: Total number of API calls
        successful_calls: Number of successful calls
        failed_calls: Number of failed calls
        total_input_tokens: Sum of all input tokens
        total_output_tokens: Sum of all output tokens
        total_tokens: Sum of all tokens
        total_cost_usd: Total cost in USD
        avg_latency_ms: Average latency in milliseconds
        by_provider: Breakdown by provider
        by_model: Breakdown by model
    """

    period_start: datetime
    period_end: datetime
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    by_provider: dict[str, dict[str, int | float]] = field(default_factory=dict)
    by_model: dict[str, dict[str, int | float]] = field(default_factory=dict)
