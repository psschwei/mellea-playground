"""Tests for ModelPricing service."""

import pytest

from mellea_api.models.common import ModelProvider
from mellea_api.services.model_pricing import (
    ModelPrice,
    ModelPricing,
    get_model_pricing,
)


@pytest.fixture
def pricing():
    """Create a ModelPricing instance for tests."""
    return ModelPricing()


class TestGetPrice:
    """Tests for getting model pricing."""

    def test_get_price_openai_gpt4o(self, pricing: ModelPricing):
        """Test getting price for GPT-4o."""
        price = pricing.get_price(ModelProvider.OPENAI, "gpt-4o")
        assert price.input_per_1k == 0.0025
        assert price.output_per_1k == 0.01

    def test_get_price_openai_gpt4o_mini(self, pricing: ModelPricing):
        """Test getting price for GPT-4o-mini."""
        price = pricing.get_price(ModelProvider.OPENAI, "gpt-4o-mini")
        assert price.input_per_1k == 0.00015
        assert price.output_per_1k == 0.0006

    def test_get_price_anthropic_claude35_sonnet(self, pricing: ModelPricing):
        """Test getting price for Claude 3.5 Sonnet."""
        price = pricing.get_price(ModelProvider.ANTHROPIC, "claude-3-5-sonnet")
        assert price.input_per_1k == 0.003
        assert price.output_per_1k == 0.015

    def test_get_price_anthropic_claude3_haiku(self, pricing: ModelPricing):
        """Test getting price for Claude 3 Haiku."""
        price = pricing.get_price(ModelProvider.ANTHROPIC, "claude-3-haiku")
        assert price.input_per_1k == 0.00025
        assert price.output_per_1k == 0.00125

    def test_get_price_ollama_wildcard(self, pricing: ModelPricing):
        """Test that Ollama models are free (wildcard match)."""
        price = pricing.get_price(ModelProvider.OLLAMA, "llama3.2")
        assert price.input_per_1k == 0.0
        assert price.output_per_1k == 0.0

        price = pricing.get_price(ModelProvider.OLLAMA, "codellama")
        assert price.input_per_1k == 0.0
        assert price.output_per_1k == 0.0

    def test_get_price_custom_wildcard(self, pricing: ModelPricing):
        """Test that custom provider models default to free."""
        price = pricing.get_price(ModelProvider.CUSTOM, "my-custom-model")
        assert price.input_per_1k == 0.0
        assert price.output_per_1k == 0.0

    def test_get_price_unknown_model(self, pricing: ModelPricing):
        """Test that unknown models return zero cost."""
        price = pricing.get_price(ModelProvider.OPENAI, "unknown-model-xyz")
        assert price.input_per_1k == 0.0
        assert price.output_per_1k == 0.0


class TestCalculate:
    """Tests for cost calculation."""

    def test_calculate_basic(self, pricing: ModelPricing):
        """Test basic cost calculation."""
        # GPT-4o: $0.0025/1K input, $0.01/1K output
        cost = pricing.calculate(
            provider=ModelProvider.OPENAI,
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=1000,
        )
        # Expected: (1000/1000 * 0.0025) + (1000/1000 * 0.01) = 0.0125
        assert cost == 0.0125

    def test_calculate_gpt4o_mini(self, pricing: ModelPricing):
        """Test cost calculation for GPT-4o-mini."""
        # GPT-4o-mini: $0.00015/1K input, $0.0006/1K output
        cost = pricing.calculate(
            provider=ModelProvider.OPENAI,
            model="gpt-4o-mini",
            input_tokens=10000,
            output_tokens=5000,
        )
        # Expected: (10000/1000 * 0.00015) + (5000/1000 * 0.0006) = 0.0015 + 0.003 = 0.0045
        assert cost == 0.0045

    def test_calculate_claude_opus(self, pricing: ModelPricing):
        """Test cost calculation for Claude 3 Opus."""
        # Claude 3 Opus: $0.015/1K input, $0.075/1K output
        cost = pricing.calculate(
            provider=ModelProvider.ANTHROPIC,
            model="claude-3-opus",
            input_tokens=2000,
            output_tokens=500,
        )
        # Expected: (2000/1000 * 0.015) + (500/1000 * 0.075) = 0.03 + 0.0375 = 0.0675
        assert cost == 0.0675

    def test_calculate_ollama_free(self, pricing: ModelPricing):
        """Test that Ollama models are always free."""
        cost = pricing.calculate(
            provider=ModelProvider.OLLAMA,
            model="llama3.2:70b",
            input_tokens=100000,
            output_tokens=50000,
        )
        assert cost == 0.0

    def test_calculate_zero_tokens(self, pricing: ModelPricing):
        """Test calculation with zero tokens."""
        cost = pricing.calculate(
            provider=ModelProvider.OPENAI,
            model="gpt-4o",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost == 0.0

    def test_calculate_precision(self, pricing: ModelPricing):
        """Test that calculations maintain precision."""
        # Small token counts should still have precise results
        cost = pricing.calculate(
            provider=ModelProvider.OPENAI,
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
        )
        # Expected: (100/1000 * 0.0025) + (50/1000 * 0.01) = 0.00025 + 0.0005 = 0.00075
        assert cost == 0.00075


class TestCalculateBatch:
    """Tests for batch cost calculation."""

    def test_calculate_batch_single(self, pricing: ModelPricing):
        """Test batch calculation with single call."""
        calls = [(ModelProvider.OPENAI, "gpt-4o", 1000, 1000)]
        cost = pricing.calculate_batch(calls)
        assert cost == 0.0125

    def test_calculate_batch_multiple(self, pricing: ModelPricing):
        """Test batch calculation with multiple calls."""
        calls = [
            (ModelProvider.OPENAI, "gpt-4o", 1000, 500),
            (ModelProvider.ANTHROPIC, "claude-3-5-sonnet", 2000, 1000),
            (ModelProvider.OLLAMA, "llama3.2", 5000, 2000),
        ]
        cost = pricing.calculate_batch(calls)
        # gpt-4o: (1000/1000 * 0.0025) + (500/1000 * 0.01) = 0.0025 + 0.005 = 0.0075
        # claude-3-5-sonnet: (2000/1000 * 0.003) + (1000/1000 * 0.015) = 0.006 + 0.015 = 0.021
        # ollama: 0.0
        # Total: 0.0075 + 0.021 + 0.0 = 0.0285
        assert cost == 0.0285

    def test_calculate_batch_empty(self, pricing: ModelPricing):
        """Test batch calculation with empty list."""
        cost = pricing.calculate_batch([])
        assert cost == 0.0


class TestCustomPrices:
    """Tests for custom pricing overrides."""

    def test_custom_price_new_model(self):
        """Test adding custom price for new model."""
        custom = {
            "openai": {
                "gpt-5": ModelPrice(input_per_1k=0.05, output_per_1k=0.15),
            }
        }
        pricing = ModelPricing(custom_prices=custom)

        price = pricing.get_price(ModelProvider.OPENAI, "gpt-5")
        assert price.input_per_1k == 0.05
        assert price.output_per_1k == 0.15

    def test_custom_price_override(self):
        """Test overriding existing price."""
        custom = {
            "openai": {
                "gpt-4o": ModelPrice(input_per_1k=0.001, output_per_1k=0.002),
            }
        }
        pricing = ModelPricing(custom_prices=custom)

        price = pricing.get_price(ModelProvider.OPENAI, "gpt-4o")
        assert price.input_per_1k == 0.001
        assert price.output_per_1k == 0.002

    def test_custom_price_fallback_to_default(self):
        """Test that non-overridden prices still work."""
        custom = {
            "openai": {
                "gpt-5": ModelPrice(input_per_1k=0.05, output_per_1k=0.15),
            }
        }
        pricing = ModelPricing(custom_prices=custom)

        # gpt-4o should still use default pricing
        price = pricing.get_price(ModelProvider.OPENAI, "gpt-4o")
        assert price.input_per_1k == 0.0025
        assert price.output_per_1k == 0.01


class TestListModels:
    """Tests for listing available models."""

    def test_list_models_all(self, pricing: ModelPricing):
        """Test listing all models."""
        models = pricing.list_models()
        assert len(models) > 0
        assert "openai/gpt-4o" in models
        assert "anthropic/claude-3-5-sonnet" in models

    def test_list_models_by_provider(self, pricing: ModelPricing):
        """Test listing models by provider."""
        openai_models = pricing.list_models(provider=ModelProvider.OPENAI)
        assert all(m.startswith("openai/") for m in openai_models)
        assert "openai/gpt-4o" in openai_models
        assert "openai/gpt-4o-mini" in openai_models

        anthropic_models = pricing.list_models(provider=ModelProvider.ANTHROPIC)
        assert all(m.startswith("anthropic/") for m in anthropic_models)
        assert "anthropic/claude-3-5-sonnet" in anthropic_models

    def test_list_models_sorted(self, pricing: ModelPricing):
        """Test that models are sorted."""
        models = pricing.list_models()
        assert models == sorted(models)


class TestGlobalInstance:
    """Tests for global pricing instance."""

    def test_get_model_pricing(self):
        """Test getting global instance."""
        pricing1 = get_model_pricing()
        pricing2 = get_model_pricing()
        assert pricing1 is pricing2

    def test_global_instance_works(self):
        """Test that global instance calculates correctly."""
        pricing = get_model_pricing()
        cost = pricing.calculate(
            provider=ModelProvider.OPENAI,
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=1000,
        )
        assert cost == 0.0125


class TestModelPriceDataclass:
    """Tests for ModelPrice dataclass."""

    def test_model_price_frozen(self):
        """Test that ModelPrice is immutable."""
        from dataclasses import FrozenInstanceError

        price = ModelPrice(input_per_1k=0.01, output_per_1k=0.02)
        with pytest.raises(FrozenInstanceError):
            price.input_per_1k = 0.05

    def test_model_price_equality(self):
        """Test ModelPrice equality."""
        price1 = ModelPrice(input_per_1k=0.01, output_per_1k=0.02)
        price2 = ModelPrice(input_per_1k=0.01, output_per_1k=0.02)
        assert price1 == price2

    def test_model_price_hash(self):
        """Test that ModelPrice is hashable."""
        price = ModelPrice(input_per_1k=0.01, output_per_1k=0.02)
        # Should not raise
        hash(price)
        # Can be used in sets
        prices = {price}
        assert len(prices) == 1
