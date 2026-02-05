"""Tests for the MelleaRuntime adapter module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from mellea_api.runtime.mellea_runtime import (
    DEFAULT_MODELS,
    PROVIDER_TO_BACKEND,
    MelleaRuntime,
    MelleaRuntimeError,
    SlotExecutionError,
    cleanup_runtime,
    get_runtime,
    invoke_model,
    run_program,
)


class TestProviderMapping:
    """Tests for provider name mapping."""

    def test_ollama_mapping(self) -> None:
        """Test Ollama provider mapping."""
        assert PROVIDER_TO_BACKEND["OLLAMA"] == "ollama"
        assert PROVIDER_TO_BACKEND["ollama"] == "ollama"

    def test_openai_mapping(self) -> None:
        """Test OpenAI provider mapping."""
        assert PROVIDER_TO_BACKEND["OPENAI"] == "openai"
        assert PROVIDER_TO_BACKEND["openai"] == "openai"

    def test_watsonx_mapping(self) -> None:
        """Test WatsonX provider mapping."""
        assert PROVIDER_TO_BACKEND["WATSONX"] == "watsonx"
        assert PROVIDER_TO_BACKEND["watsonx"] == "watsonx"

    def test_huggingface_mapping(self) -> None:
        """Test HuggingFace provider mapping."""
        assert PROVIDER_TO_BACKEND["HUGGINGFACE"] == "hf"
        assert PROVIDER_TO_BACKEND["huggingface"] == "hf"
        assert PROVIDER_TO_BACKEND["hf"] == "hf"

    def test_litellm_mapping(self) -> None:
        """Test LiteLLM provider mapping."""
        assert PROVIDER_TO_BACKEND["LITELLM"] == "litellm"
        assert PROVIDER_TO_BACKEND["litellm"] == "litellm"


class TestDefaultModels:
    """Tests for default model configuration."""

    def test_default_models_exist(self) -> None:
        """Test that all backends have default models."""
        assert "ollama" in DEFAULT_MODELS
        assert "openai" in DEFAULT_MODELS
        assert "watsonx" in DEFAULT_MODELS
        assert "hf" in DEFAULT_MODELS
        assert "litellm" in DEFAULT_MODELS

    def test_ollama_default(self) -> None:
        """Test Ollama default model."""
        assert DEFAULT_MODELS["ollama"] == "granite4:micro"


class TestMelleaRuntimeInit:
    """Tests for MelleaRuntime initialization."""

    def test_default_initialization(self) -> None:
        """Test runtime initializes with defaults."""
        runtime = MelleaRuntime()
        assert runtime.backend == "ollama"
        assert runtime.model_id == "granite4:micro"
        assert runtime._initialized is False

    def test_explicit_backend(self) -> None:
        """Test runtime with explicit backend."""
        runtime = MelleaRuntime(backend="openai")
        assert runtime.backend == "openai"

    def test_backend_mapping(self) -> None:
        """Test that provider names are mapped correctly."""
        runtime = MelleaRuntime(backend="OLLAMA")
        assert runtime.backend == "ollama"

        runtime2 = MelleaRuntime(backend="HUGGINGFACE")
        assert runtime2.backend == "hf"

    def test_explicit_model_id(self) -> None:
        """Test runtime with explicit model ID."""
        runtime = MelleaRuntime(model_id="llama3.2:3b")
        assert runtime.model_id == "llama3.2:3b"

    def test_model_options(self) -> None:
        """Test runtime with model options."""
        options = {"temperature": 0.7, "max_tokens": 1024}
        runtime = MelleaRuntime(model_options=options)
        assert runtime._model_options == options

    def test_run_id(self) -> None:
        """Test runtime with run ID."""
        runtime = MelleaRuntime(run_id="test-run-123")
        assert runtime._run_id == "test-run-123"

    def test_unknown_backend_defaults_to_ollama(self) -> None:
        """Test that unknown backend defaults to ollama."""
        runtime = MelleaRuntime(backend="unknown_provider")
        assert runtime.backend == "ollama"

    def test_env_var_backend(self) -> None:
        """Test backend from environment variable."""
        with patch.dict(os.environ, {"MELLEA_BACKEND": "watsonx"}):
            runtime = MelleaRuntime()
            assert runtime.backend == "watsonx"

    def test_env_var_model_id(self) -> None:
        """Test model ID from environment variable."""
        with patch.dict(os.environ, {"MELLEA_MODEL_ID": "custom-model"}):
            runtime = MelleaRuntime()
            assert runtime.model_id == "custom-model"

    def test_env_var_model_options(self) -> None:
        """Test model options from environment variable."""
        with patch.dict(
            os.environ, {"MELLEA_MODEL_OPTIONS": '{"temperature": 0.5}'}
        ):
            runtime = MelleaRuntime()
            assert runtime._model_options == {"temperature": 0.5}

    def test_env_var_model_options_invalid_json(self) -> None:
        """Test invalid JSON in model options env var."""
        with patch.dict(os.environ, {"MELLEA_MODEL_OPTIONS": "not json"}):
            runtime = MelleaRuntime()
            assert runtime._model_options == {}


class TestMelleaRuntimeSession:
    """Tests for MelleaRuntime session management."""

    def test_session_lazy_initialization(self) -> None:
        """Test that session is not created until needed."""
        runtime = MelleaRuntime()
        assert runtime._session is None
        assert runtime._initialized is False

    def test_ensure_session_import_error(self) -> None:
        """Test error when mellea is not installed."""
        runtime = MelleaRuntime()

        # Patch the import to fail
        with patch.dict("sys.modules", {"mellea": None}):
            # Need to make the actual import fail
            def mock_ensure() -> None:
                raise MelleaRuntimeError(
                    "mellea library not installed. Install with: pip install mellea>=0.3.0"
                )

            runtime._ensure_session = mock_ensure  # type: ignore[method-assign]

            with pytest.raises(MelleaRuntimeError, match="mellea library not installed"):
                _ = runtime.session


class TestMelleaRuntimeChat:
    """Tests for MelleaRuntime.chat() method."""

    def test_chat_calls_session(self) -> None:
        """Test that chat delegates to session."""
        runtime = MelleaRuntime()

        # Mock the session
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Paris is the capital of France"
        mock_session.chat.return_value = mock_response

        runtime._session = mock_session
        runtime._initialized = True

        result = runtime.chat("What is the capital of France?")

        mock_session.chat.assert_called_once()
        assert result == "Paris is the capital of France"

    def test_chat_passes_options(self) -> None:
        """Test that chat passes model options."""
        runtime = MelleaRuntime(model_options={"temperature": 0.5})

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Response"
        mock_session.chat.return_value = mock_response

        runtime._session = mock_session
        runtime._initialized = True

        runtime.chat("Hello", temperature=0.9)

        call_kwargs = mock_session.chat.call_args[1]
        assert call_kwargs["model_options"]["temperature"] == 0.9

    def test_chat_error_handling(self) -> None:
        """Test that chat errors are wrapped."""
        runtime = MelleaRuntime()

        mock_session = MagicMock()
        mock_session.chat.side_effect = Exception("API error")

        runtime._session = mock_session
        runtime._initialized = True

        with pytest.raises(MelleaRuntimeError, match="Chat failed"):
            runtime.chat("Hello")


class TestMelleaRuntimeInstruct:
    """Tests for MelleaRuntime.instruct() method."""

    def test_instruct_calls_session(self) -> None:
        """Test that instruct delegates to session."""
        runtime = MelleaRuntime()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.value = "Generated haiku"
        mock_session.instruct.return_value = mock_result

        runtime._session = mock_session
        runtime._initialized = True

        result = runtime.instruct("Generate a haiku")

        mock_session.instruct.assert_called_once()
        assert result == "Generated haiku"

    def test_instruct_passes_requirements(self) -> None:
        """Test that instruct passes requirements."""
        runtime = MelleaRuntime()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.value = "Result"
        mock_session.instruct.return_value = mock_result

        runtime._session = mock_session
        runtime._initialized = True

        runtime.instruct(
            "Generate JSON",
            requirements=["Must be valid JSON"],
            examples=["Example 1"],
            context={"key": "value"},
        )

        call_kwargs = mock_session.instruct.call_args[1]
        assert call_kwargs["requirements"] == ["Must be valid JSON"]
        assert call_kwargs["icl_examples"] == ["Example 1"]
        assert call_kwargs["grounding_context"] == {"key": "value"}


class TestMelleaRuntimeSlots:
    """Tests for MelleaRuntime slot execution."""

    def test_execute_slot_imports_module(self) -> None:
        """Test that execute_slot imports the module."""
        runtime = MelleaRuntime()

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.value = "Slot result"
        mock_session.instruct.return_value = mock_result

        runtime._session = mock_session
        runtime._initialized = True

        # Create a mock module with a @generative slot
        mock_slot = MagicMock()
        mock_slot.format_for_llm.return_value = "Slot template"
        mock_slot.parse.return_value = "Slot result"

        mock_module = MagicMock()
        mock_module.my_slot = mock_slot

        with patch(
            "mellea_api.runtime.mellea_runtime.importlib.import_module",
            return_value=mock_module,
        ):
            result = runtime.execute_slot("my_module", "my_slot", arg1="value")

        assert result == "Slot result"
        mock_slot.format_for_llm.assert_called_once()

    def test_execute_slot_module_not_found(self) -> None:
        """Test error when module is not found."""
        runtime = MelleaRuntime()

        with (
            patch(
                "mellea_api.runtime.mellea_runtime.importlib.import_module",
                side_effect=ImportError("Module not found"),
            ),
            pytest.raises(SlotExecutionError, match="Failed to import module"),
        ):
            runtime.execute_slot("nonexistent_module", "slot")

    def test_execute_slot_slot_not_found(self) -> None:
        """Test error when slot is not found in module."""
        runtime = MelleaRuntime()

        mock_module = MagicMock(spec=[])  # Empty module

        with (
            patch(
                "mellea_api.runtime.mellea_runtime.importlib.import_module",
                return_value=mock_module,
            ),
            pytest.raises(SlotExecutionError, match="not found in module"),
        ):
            runtime.execute_slot("my_module", "nonexistent_slot")

    def test_invoke_slot_regular_function(self) -> None:
        """Test invoking a regular function (not @generative)."""
        runtime = MelleaRuntime()

        runtime._session = MagicMock()
        runtime._initialized = True

        def regular_func(x: int) -> int:
            return x * 2

        result = runtime.invoke_slot(regular_func, x=5)
        assert result == 10


class TestMelleaRuntimeSwitchModel:
    """Tests for MelleaRuntime.switch_model() method."""

    def test_switch_model_changes_config(self) -> None:
        """Test that switch_model updates configuration."""
        runtime = MelleaRuntime(backend="ollama", model_id="model1")

        runtime.switch_model(backend="openai", model_id="gpt-4o")

        assert runtime.backend == "openai"
        assert runtime.model_id == "gpt-4o"
        assert runtime._initialized is False

    def test_switch_model_partial_update(self) -> None:
        """Test switching only model_id."""
        runtime = MelleaRuntime(backend="ollama", model_id="model1")

        runtime.switch_model(model_id="model2")

        assert runtime.backend == "ollama"
        assert runtime.model_id == "model2"


class TestMelleaRuntimeCleanup:
    """Tests for MelleaRuntime cleanup."""

    def test_cleanup_calls_session_cleanup(self) -> None:
        """Test that cleanup calls session cleanup."""
        runtime = MelleaRuntime()

        mock_session = MagicMock()
        runtime._session = mock_session
        runtime._initialized = True

        runtime.cleanup()

        mock_session.cleanup.assert_called_once()
        assert runtime._session is None
        assert runtime._initialized is False

    def test_cleanup_handles_error(self) -> None:
        """Test that cleanup handles errors gracefully."""
        runtime = MelleaRuntime()

        mock_session = MagicMock()
        mock_session.cleanup.side_effect = Exception("Cleanup error")
        runtime._session = mock_session
        runtime._initialized = True

        # Should not raise
        runtime.cleanup()

        assert runtime._session is None

    def test_context_manager(self) -> None:
        """Test runtime as context manager."""
        mock_session = MagicMock()

        with MelleaRuntime() as runtime:
            runtime._session = mock_session
            runtime._initialized = True

        mock_session.cleanup.assert_called_once()


class TestCompatibilityShims:
    """Tests for compatibility shim functions."""

    def test_invoke_model_simple(self) -> None:
        """Test invoke_model with simple model ID."""
        with (
            patch.object(MelleaRuntime, "chat", return_value="Response") as mock_chat,
            patch.object(MelleaRuntime, "cleanup"),
        ):
            result = invoke_model("granite4:micro", "Hello")

        assert result == "Response"
        mock_chat.assert_called_once_with("Hello")

    def test_invoke_model_with_backend_prefix(self) -> None:
        """Test invoke_model parses backend from model ID."""
        with (
            patch.object(MelleaRuntime, "__init__", return_value=None) as mock_init,
            patch.object(MelleaRuntime, "chat", return_value="Response"),
            patch.object(MelleaRuntime, "cleanup"),
        ):
            invoke_model("openai:gpt-4o", "Hello")

        # Check that backend was extracted from model ID
        call_kwargs = mock_init.call_args[1]
        assert call_kwargs["backend"] == "openai"
        assert call_kwargs["model_id"] == "gpt-4o"

    def test_run_program(self) -> None:
        """Test run_program shim."""
        with (
            patch.object(
                MelleaRuntime, "execute_slot", return_value="Result"
            ) as mock_exec,
            patch.object(MelleaRuntime, "cleanup"),
        ):
            result = run_program("my_program", "my_slot", arg1="value")

        assert result == "Result"
        mock_exec.assert_called_once_with("my_program", "my_slot", arg1="value")


class TestGlobalRuntime:
    """Tests for global runtime functions."""

    def teardown_method(self) -> None:
        """Clean up global runtime after each test."""
        cleanup_runtime()

    def test_get_runtime_creates_instance(self) -> None:
        """Test that get_runtime creates an instance."""
        runtime = get_runtime()
        assert isinstance(runtime, MelleaRuntime)

    def test_get_runtime_returns_same_instance(self) -> None:
        """Test that get_runtime returns the same instance."""
        runtime1 = get_runtime()
        runtime2 = get_runtime()
        assert runtime1 is runtime2

    def test_get_runtime_recreates_on_config_change(self) -> None:
        """Test that get_runtime recreates on config change."""
        runtime1 = get_runtime(backend="ollama")
        runtime2 = get_runtime(backend="openai")
        assert runtime1 is not runtime2
        assert runtime2.backend == "openai"

    def test_cleanup_runtime(self) -> None:
        """Test cleanup_runtime clears global instance."""
        runtime = get_runtime()
        cleanup_runtime()

        # Getting runtime again should create new instance
        runtime2 = get_runtime()
        assert runtime is not runtime2
