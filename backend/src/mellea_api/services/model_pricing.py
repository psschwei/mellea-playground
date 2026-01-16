"""Model Pricing Service for LLM cost estimation.

Provides pricing information for various LLM models and calculates
estimated costs based on token usage.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from typing import ClassVar

from mellea_api.models.common import ModelProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPrice:
    """Pricing information for a model.

    Attributes:
        input_per_1k: Cost per 1,000 input tokens in USD
        output_per_1k: Cost per 1,000 output tokens in USD
    """

    input_per_1k: float
    output_per_1k: float


class ModelPricing:
    """Service for calculating LLM API costs based on token usage.

    Provides pricing data for common LLM models from various providers
    and calculates estimated costs based on input/output token counts.

    Supports wildcard patterns for model matching (e.g., "ollama/*" matches
    any Ollama model).

    Example:
        ```python
        pricing = ModelPricing()

        # Calculate cost for a specific call
        cost = pricing.calculate(
            provider=ModelProvider.OPENAI,
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500
        )

        # Get pricing info for a model
        price = pricing.get_price(ModelProvider.ANTHROPIC, "claude-3-5-sonnet")
        if price:
            print(f"Input: ${price.input_per_1k}/1K, Output: ${price.output_per_1k}/1K")
        ```
    """

    # Pricing data per 1,000 tokens (USD)
    # Last updated: January 2025
    PRICES: ClassVar[dict[str, dict[str, ModelPrice]]] = {
        ModelProvider.OPENAI.value: {
            # GPT-4o series
            "gpt-4o": ModelPrice(input_per_1k=0.0025, output_per_1k=0.01),
            "gpt-4o-2024-11-20": ModelPrice(input_per_1k=0.0025, output_per_1k=0.01),
            "gpt-4o-2024-08-06": ModelPrice(input_per_1k=0.0025, output_per_1k=0.01),
            "gpt-4o-mini": ModelPrice(input_per_1k=0.00015, output_per_1k=0.0006),
            "gpt-4o-mini-2024-07-18": ModelPrice(input_per_1k=0.00015, output_per_1k=0.0006),
            # GPT-4 Turbo
            "gpt-4-turbo": ModelPrice(input_per_1k=0.01, output_per_1k=0.03),
            "gpt-4-turbo-2024-04-09": ModelPrice(input_per_1k=0.01, output_per_1k=0.03),
            "gpt-4-turbo-preview": ModelPrice(input_per_1k=0.01, output_per_1k=0.03),
            # GPT-4
            "gpt-4": ModelPrice(input_per_1k=0.03, output_per_1k=0.06),
            "gpt-4-0613": ModelPrice(input_per_1k=0.03, output_per_1k=0.06),
            # GPT-3.5 Turbo
            "gpt-3.5-turbo": ModelPrice(input_per_1k=0.0005, output_per_1k=0.0015),
            "gpt-3.5-turbo-0125": ModelPrice(input_per_1k=0.0005, output_per_1k=0.0015),
            # o1 series (reasoning models)
            "o1": ModelPrice(input_per_1k=0.015, output_per_1k=0.06),
            "o1-preview": ModelPrice(input_per_1k=0.015, output_per_1k=0.06),
            "o1-mini": ModelPrice(input_per_1k=0.003, output_per_1k=0.012),
        },
        ModelProvider.ANTHROPIC.value: {
            # Claude 3.5 series
            "claude-3-5-sonnet": ModelPrice(input_per_1k=0.003, output_per_1k=0.015),
            "claude-3-5-sonnet-20241022": ModelPrice(input_per_1k=0.003, output_per_1k=0.015),
            "claude-3-5-sonnet-20240620": ModelPrice(input_per_1k=0.003, output_per_1k=0.015),
            "claude-3-5-haiku": ModelPrice(input_per_1k=0.001, output_per_1k=0.005),
            "claude-3-5-haiku-20241022": ModelPrice(input_per_1k=0.001, output_per_1k=0.005),
            # Claude 3 series
            "claude-3-opus": ModelPrice(input_per_1k=0.015, output_per_1k=0.075),
            "claude-3-opus-20240229": ModelPrice(input_per_1k=0.015, output_per_1k=0.075),
            "claude-3-sonnet": ModelPrice(input_per_1k=0.003, output_per_1k=0.015),
            "claude-3-sonnet-20240229": ModelPrice(input_per_1k=0.003, output_per_1k=0.015),
            "claude-3-haiku": ModelPrice(input_per_1k=0.00025, output_per_1k=0.00125),
            "claude-3-haiku-20240307": ModelPrice(input_per_1k=0.00025, output_per_1k=0.00125),
        },
        ModelProvider.AZURE.value: {
            # Azure OpenAI uses similar pricing to OpenAI
            "gpt-4o": ModelPrice(input_per_1k=0.0025, output_per_1k=0.01),
            "gpt-4o-mini": ModelPrice(input_per_1k=0.00015, output_per_1k=0.0006),
            "gpt-4-turbo": ModelPrice(input_per_1k=0.01, output_per_1k=0.03),
            "gpt-4": ModelPrice(input_per_1k=0.03, output_per_1k=0.06),
            "gpt-35-turbo": ModelPrice(input_per_1k=0.0005, output_per_1k=0.0015),
        },
        ModelProvider.OLLAMA.value: {
            # Local models are free
            "*": ModelPrice(input_per_1k=0.0, output_per_1k=0.0),
        },
        ModelProvider.CUSTOM.value: {
            # Default to zero for custom/unknown providers
            "*": ModelPrice(input_per_1k=0.0, output_per_1k=0.0),
        },
    }

    # Default pricing for unknown models
    DEFAULT_PRICE: ClassVar[ModelPrice] = ModelPrice(input_per_1k=0.0, output_per_1k=0.0)

    def __init__(self, custom_prices: dict[str, dict[str, ModelPrice]] | None = None):
        """Initialize ModelPricing.

        Args:
            custom_prices: Optional custom pricing overrides. Structure:
                {provider: {model_name: ModelPrice}}
        """
        self._custom_prices = custom_prices or {}

    def get_price(self, provider: ModelProvider, model: str) -> ModelPrice:
        """Get pricing for a specific model.

        Checks custom prices first, then falls back to default pricing data.
        Supports wildcard patterns (e.g., "*" matches any model).

        Args:
            provider: The LLM provider
            model: The model name

        Returns:
            ModelPrice with input/output costs per 1K tokens
        """
        # Check custom prices first
        if provider.value in self._custom_prices:
            price = self._match_model(self._custom_prices[provider.value], model)
            if price is not None:
                return price

        # Check default prices
        if provider.value in self.PRICES:
            price = self._match_model(self.PRICES[provider.value], model)
            if price is not None:
                return price

        logger.warning(f"No pricing found for {provider.value}/{model}, using zero cost")
        return self.DEFAULT_PRICE

    def _match_model(
        self, prices: dict[str, ModelPrice], model: str
    ) -> ModelPrice | None:
        """Match a model name against pricing patterns.

        Args:
            prices: Dict of model patterns to prices
            model: The model name to match

        Returns:
            ModelPrice if found, None otherwise
        """
        # Exact match first
        if model in prices:
            return prices[model]

        # Try wildcard patterns
        for pattern, price in prices.items():
            if "*" in pattern and fnmatch.fnmatch(model, pattern):
                return price

        return None

    def calculate(
        self,
        provider: ModelProvider,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Calculate the estimated cost for an LLM API call.

        Args:
            provider: The LLM provider
            model: The model name
            input_tokens: Number of input/prompt tokens
            output_tokens: Number of output/completion tokens

        Returns:
            Estimated cost in USD
        """
        price = self.get_price(provider, model)
        cost = (
            (input_tokens / 1000) * price.input_per_1k
            + (output_tokens / 1000) * price.output_per_1k
        )
        return round(cost, 6)  # Round to 6 decimal places for precision

    def calculate_batch(
        self,
        calls: list[tuple[ModelProvider, str, int, int]],
    ) -> float:
        """Calculate total cost for multiple LLM calls.

        Args:
            calls: List of (provider, model, input_tokens, output_tokens) tuples

        Returns:
            Total estimated cost in USD
        """
        return sum(
            self.calculate(provider, model, input_tokens, output_tokens)
            for provider, model, input_tokens, output_tokens in calls
        )

    def list_models(self, provider: ModelProvider | None = None) -> list[str]:
        """List all known models, optionally filtered by provider.

        Args:
            provider: Filter by provider (returns all if None)

        Returns:
            List of model identifiers in "provider/model" format
        """
        models = []
        providers = [provider] if provider else list(ModelProvider)

        for p in providers:
            if p.value in self.PRICES:
                for model_name in self.PRICES[p.value]:
                    if model_name != "*":  # Skip wildcards
                        models.append(f"{p.value}/{model_name}")

        return sorted(models)


# Global service instance
_model_pricing: ModelPricing | None = None


def get_model_pricing() -> ModelPricing:
    """Get the global ModelPricing instance."""
    global _model_pricing
    if _model_pricing is None:
        _model_pricing = ModelPricing()
    return _model_pricing
