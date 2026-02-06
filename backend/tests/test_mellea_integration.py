"""Integration tests for mellea 0.3.0 compatibility.

These tests verify the playground works with actual mellea 0.3.0 programs,
including:
- Importing programs with @generative slots
- Building environments with mellea installed
- Executing mellea programs
- Running compositions with program and model nodes
- Verifying logs and output capture

NOTE: Some tests require an LLM backend (Ollama) to be running.
Tests that require live backends are marked with @pytest.mark.live_backend
and can be skipped with: pytest -m "not live_backend"
"""

import os
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mellea_api.runtime import (
    MelleaRuntime,
    MelleaRuntimeError,
    SlotExecutionError,
    cleanup_runtime,
    configure_runtime,
    get_runtime,
    invoke_model,
    log_node,
    run_program,
)
from mellea_api.services.code_generator import CodeGenerator
from mellea_api.services.program_validator import ProgramValidator, get_program_validator

# =============================================================================
# Test fixtures: Sample mellea programs
# =============================================================================


SIMPLE_GENERATIVE_PROGRAM = textwrap.dedent('''
    """A simple mellea program with a @generative slot."""

    from mellea import generative


    @generative
    def classify_sentiment(text: str) -> str:
        """Classify the sentiment of the given text.

        Returns exactly one of: positive, negative, neutral
        """
        ...


    @generative
    def summarize(text: str, max_words: int = 50) -> str:
        """Summarize the given text in a concise way."""
        ...
''')


PROGRAM_WITH_VERIFIER = textwrap.dedent('''
    """A mellea program with validation helpers."""

    import json
    from mellea import generative


    def is_valid_json(output: str) -> bool:
        """Verify output is valid JSON."""
        try:
            json.loads(output)
            return True
        except json.JSONDecodeError:
            return False


    @generative
    def extract_contact_info(text: str) -> str:
        """Extract contact information as JSON.

        Output must be valid JSON containing 'name', 'email', and 'phone' fields if present.
        """
        ...
''')


CHAT_PROGRAM = textwrap.dedent('''
    """A simple chat program using mellea session."""

    from mellea import start_session


    def chat_with_model(prompt: str, backend: str = "ollama", model_id: str = "granite4:micro") -> str:
        """Send a chat message to an LLM."""
        session = start_session(backend_name=backend, model_id=model_id)
        response = session.chat(prompt)
        return response.content
''')


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_program_dir():
    """Create a temporary directory with a sample mellea program."""
    with tempfile.TemporaryDirectory() as tmpdir:
        program_dir = Path(tmpdir) / "sample_program"
        program_dir.mkdir()

        # Create program file
        (program_dir / "slots.py").write_text(SIMPLE_GENERATIVE_PROGRAM)

        # Create __init__.py
        (program_dir / "__init__.py").write_text('"""Sample mellea program."""\n')

        # Create pyproject.toml
        (program_dir / "pyproject.toml").write_text(
            textwrap.dedent('''
                [project]
                name = "sample-program"
                version = "0.1.0"
                requires-python = ">=3.11"
                dependencies = [
                    "mellea>=0.3.0",
                ]
            ''')
        )

        yield program_dir


@pytest.fixture
def temp_program_with_verifier():
    """Create a temporary directory with a program using verifiers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        program_dir = Path(tmpdir) / "verified_program"
        program_dir.mkdir()

        (program_dir / "extractors.py").write_text(PROGRAM_WITH_VERIFIER)
        (program_dir / "__init__.py").write_text('"""Program with verifiers."""\n')

        yield program_dir


@pytest.fixture
def program_validator():
    """Get a program validator instance."""
    return get_program_validator()


@pytest.fixture
def code_generator():
    """Get a code generator instance."""
    return CodeGenerator()


@pytest.fixture(autouse=True)
def cleanup_global_runtime():
    """Clean up global runtime after each test."""
    yield
    cleanup_runtime()


# =============================================================================
# Test: Detecting @generative slots
# =============================================================================


class TestSlotDetection:
    """Tests for detecting @generative decorated functions."""

    def test_detect_generative_slots(
        self, program_validator: ProgramValidator, temp_program_dir: Path
    ):
        """Test that @generative slots are correctly detected."""
        slots = program_validator.detect_slots(temp_program_dir)

        assert len(slots) == 2

        slot_names = [s.name for s in slots]
        assert "classify_sentiment" in slot_names
        assert "summarize" in slot_names

    def test_slot_metadata_extraction(
        self, program_validator: ProgramValidator, temp_program_dir: Path
    ):
        """Test that slot metadata is correctly extracted."""
        slots = program_validator.detect_slots(temp_program_dir)

        # Find classify_sentiment slot
        sentiment_slot = next(s for s in slots if s.name == "classify_sentiment")

        assert sentiment_slot.qualified_name == "slots.classify_sentiment"
        assert "@generative" in sentiment_slot.decorators
        assert sentiment_slot.source_file == "slots.py"
        assert sentiment_slot.signature is not None

        # Check signature
        args = sentiment_slot.signature.args
        assert len(args) == 1
        assert args[0]["name"] == "text"
        assert args[0]["type"] == "str"

    def test_detect_slots_with_helpers(
        self, program_validator: ProgramValidator, temp_program_with_verifier: Path
    ):
        """Test detecting slots in programs with helper functions."""
        slots = program_validator.detect_slots(temp_program_with_verifier)

        assert len(slots) == 1

        slot = slots[0]
        assert slot.name == "extract_contact_info"
        assert "@generative" in slot.decorators

    def test_analyze_source_code_directly(self, program_validator: ProgramValidator):
        """Test analyzing source code without files."""
        result = program_validator.analyze_source_code(
            SIMPLE_GENERATIVE_PROGRAM, "test_program.py"
        )

        assert result["valid"] is True
        assert result["error"] is None
        assert len(result["slots"]) == 2


class TestDependencyExtraction:
    """Tests for extracting dependencies from programs."""

    def test_extract_dependencies_from_pyproject(
        self, program_validator: ProgramValidator, temp_program_dir: Path
    ):
        """Test extracting dependencies from pyproject.toml."""
        deps = program_validator.extract_dependencies(temp_program_dir)

        assert deps.source.value == "pyproject"
        assert any(p.name == "mellea" for p in deps.packages)

    def test_extract_python_version(
        self, program_validator: ProgramValidator, temp_program_dir: Path
    ):
        """Test that Python version requirement is extracted."""
        deps = program_validator.extract_dependencies(temp_program_dir)

        assert deps.python_version is not None
        assert "3.11" in deps.python_version


# =============================================================================
# Test: MelleaRuntime initialization
# =============================================================================


class TestMelleaRuntimeIntegration:
    """Integration tests for MelleaRuntime with actual mellea library."""

    def test_runtime_initialization(self):
        """Test that MelleaRuntime initializes correctly."""
        runtime = MelleaRuntime(backend="ollama", model_id="granite4:micro")

        assert runtime.backend == "ollama"
        assert runtime.model_id == "granite4:micro"
        assert runtime._initialized is False  # Lazy initialization

    def test_runtime_env_var_configuration(self):
        """Test runtime reads configuration from environment variables."""
        with patch.dict(
            os.environ,
            {
                "MELLEA_BACKEND": "openai",
                "MELLEA_MODEL_ID": "gpt-4o",
                "MELLEA_MODEL_OPTIONS": '{"temperature": 0.7}',
            },
        ):
            runtime = MelleaRuntime()

            assert runtime.backend == "openai"
            assert runtime.model_id == "gpt-4o"
            assert runtime._model_options == {"temperature": 0.7}

    def test_runtime_session_lazy_init(self):
        """Test that session is lazily initialized on first use."""
        runtime = MelleaRuntime()

        # Session should be None before first use
        assert runtime._session is None
        assert runtime._initialized is False

    def test_runtime_context_manager(self):
        """Test runtime works as context manager."""
        with MelleaRuntime(backend="ollama") as runtime:
            assert runtime.backend == "ollama"

        # Should be cleaned up
        assert runtime._session is None
        assert runtime._initialized is False

    def test_runtime_model_switching(self):
        """Test switching models reinitializes the runtime."""
        runtime = MelleaRuntime(backend="ollama", model_id="model1")

        runtime.switch_model(model_id="model2")

        assert runtime.model_id == "model2"
        assert runtime._initialized is False

    def test_global_runtime_singleton(self):
        """Test get_runtime returns singleton instance."""
        runtime1 = get_runtime(backend="ollama")
        runtime2 = get_runtime()

        assert runtime1 is runtime2

        # Changing config creates new instance
        runtime3 = get_runtime(backend="openai")
        assert runtime1 is not runtime3


# =============================================================================
# Test: Code generation for compositions
# =============================================================================


class TestCompositionCodeGeneration:
    """Tests for generating code from composition graphs."""

    def test_generate_simple_composition(self, code_generator: CodeGenerator):
        """Test generating code for a simple program-to-model composition."""
        nodes = [
            {
                "id": "input-1",
                "data": {
                    "category": "utility",
                    "utilityType": "input",
                    "label": "user_text",
                    "dataType": "string",
                },
            },
            {
                "id": "program-1",
                "data": {
                    "category": "program",
                    "label": "Sentiment Classifier",
                    "programId": "sentiment_classifier",
                },
            },
            {
                "id": "output-1",
                "data": {
                    "category": "utility",
                    "utilityType": "output",
                    "label": "result",
                },
            },
        ]
        edges = [
            {"source": "input-1", "target": "program-1", "targetHandle": "input"},
            {"source": "program-1", "target": "output-1"},
        ]

        result = code_generator.generate(nodes, edges)

        assert result.code is not None
        assert "run_program" in result.code
        assert "sentiment_classifier" in result.code
        assert len(result.execution_order) == 3
        assert len(result.inputs) == 1
        assert len(result.outputs) == 1
        assert result.inputs[0].name == "user_text"

    def test_generate_model_node_code(self, code_generator: CodeGenerator):
        """Test generating code for a model node."""
        nodes = [
            {
                "id": "input-1",
                "data": {
                    "category": "utility",
                    "utilityType": "input",
                    "label": "prompt",
                },
            },
            {
                "id": "model-1",
                "data": {
                    "category": "model",
                    "label": "GPT-4",
                    "modelId": "openai:gpt-4o",
                },
            },
            {
                "id": "output-1",
                "data": {
                    "category": "utility",
                    "utilityType": "output",
                    "label": "response",
                },
            },
        ]
        edges = [
            {"source": "input-1", "target": "model-1"},
            {"source": "model-1", "target": "output-1"},
        ]

        result = code_generator.generate(nodes, edges)

        assert "invoke_model" in result.code
        assert "openai:gpt-4o" in result.code

    def test_generate_code_with_node_logging(self, code_generator: CodeGenerator):
        """Test that node logging calls are included."""
        code_generator.set_options(include_node_logging=True)

        nodes = [
            {
                "id": "program-1",
                "data": {
                    "category": "program",
                    "label": "Test Program",
                    "programId": "test_prog",
                },
            },
        ]
        edges: list[dict[str, Any]] = []

        result = code_generator.generate(nodes, edges)

        assert "log_node" in result.code
        assert "configure_runtime" in result.code

    def test_generate_standalone_script(self, code_generator: CodeGenerator):
        """Test generating a standalone script with runtime stubs."""
        nodes = [
            {
                "id": "model-1",
                "data": {
                    "category": "model",
                    "label": "Model",
                    "modelId": "granite4:micro",
                },
            },
        ]
        edges: list[dict[str, Any]] = []

        script = code_generator.generate_standalone(nodes, edges)

        # Should include stub implementations
        assert "async def run_program" in script
        assert "async def invoke_model" in script
        assert "[STUB]" in script


# =============================================================================
# Test: Slot execution (mocked)
# =============================================================================


class TestSlotExecution:
    """Tests for executing @generative slots (mocked)."""

    def test_execute_slot_module_not_found(self):
        """Test error handling when module is not found."""
        runtime = MelleaRuntime()

        with pytest.raises(SlotExecutionError, match="Failed to import module"):
            runtime.execute_slot("nonexistent_module", "slot_name")

    def test_execute_slot_function_not_found(self, temp_program_dir: Path):
        """Test error handling when function is not found in module."""
        # Add the temp program to Python path
        sys.path.insert(0, str(temp_program_dir.parent))

        try:
            runtime = MelleaRuntime()

            with pytest.raises(SlotExecutionError, match="not found in module"):
                runtime.execute_slot("sample_program.slots", "nonexistent_slot")
        finally:
            sys.path.remove(str(temp_program_dir.parent))

    def test_invoke_regular_function(self):
        """Test invoking a regular (non-generative) function."""
        runtime = MelleaRuntime()
        runtime._session = MagicMock()
        runtime._initialized = True

        def double(x: int) -> int:
            return x * 2

        result = runtime.invoke_slot(double, x=5)
        assert result == 10

    def test_invoke_slot_with_mocked_session(self):
        """Test invoking a @generative slot with mocked session."""
        runtime = MelleaRuntime()

        # Mock the session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.value = "positive"
        mock_session.instruct.return_value = mock_result

        runtime._session = mock_session
        runtime._initialized = True

        # Create a mock @generative slot
        mock_slot = MagicMock()
        mock_slot.format_for_llm.return_value = "Classify sentiment: {text}"
        mock_slot.parse.return_value = "positive"

        result = runtime.invoke_slot(mock_slot, text="I love this!")

        assert result == "positive"
        mock_slot.format_for_llm.assert_called_once()


# =============================================================================
# Test: Node logging
# =============================================================================


class TestNodeLogging:
    """Tests for node-level logging during composition execution."""

    def test_configure_runtime_sets_up_logging(self):
        """Test that configure_runtime sets up the logging infrastructure."""
        # Should not raise
        configure_runtime()

    def test_log_node_captures_messages(self, capsys):
        """Test that log_node outputs to stdout for capture."""
        configure_runtime()

        log_node("node-123", "Starting execution")

        captured = capsys.readouterr()
        assert "node-123" in captured.out
        assert "Starting execution" in captured.out


# =============================================================================
# Test: Compatibility shims
# =============================================================================


class TestCompatibilityShims:
    """Tests for backward compatibility shim functions."""

    def test_invoke_model_parses_backend_prefix(self):
        """Test invoke_model extracts backend from model ID."""
        with (
            patch.object(MelleaRuntime, "__init__", return_value=None) as mock_init,
            patch.object(MelleaRuntime, "chat", return_value="Response"),
            patch.object(MelleaRuntime, "cleanup"),
        ):
            invoke_model("openai:gpt-4o", "Hello")

            # Verify backend was extracted
            call_kwargs = mock_init.call_args[1]
            assert call_kwargs["backend"] == "openai"
            assert call_kwargs["model_id"] == "gpt-4o"

    def test_run_program_delegates_to_execute_slot(self):
        """Test run_program calls execute_slot."""
        with (
            patch.object(
                MelleaRuntime, "execute_slot", return_value="Result"
            ) as mock_exec,
            patch.object(MelleaRuntime, "cleanup"),
        ):
            result = run_program("my_module", "my_slot", arg="value")

            assert result == "Result"
            mock_exec.assert_called_once_with("my_module", "my_slot", arg="value")


# =============================================================================
# Test: Full integration with live backend (optional)
# =============================================================================


@pytest.mark.live_backend
class TestLiveBackendIntegration:
    """Integration tests requiring a live LLM backend.

    These tests are skipped by default and require:
    - Ollama running locally with granite4:micro model

    Run with: pytest -m live_backend
    """

    @pytest.fixture
    def check_ollama_available(self):
        """Skip tests if Ollama is not available."""
        try:
            import ollama

            ollama.list()
        except Exception:
            pytest.skip("Ollama not available")

    def test_runtime_session_initialization(self, check_ollama_available):
        """Test that runtime session initializes correctly with live backend."""
        runtime = MelleaRuntime(backend="ollama", model_id="granite4:micro")

        # This will trigger session initialization
        try:
            session = runtime.session
            assert session is not None
            assert runtime._initialized is True
        except MelleaRuntimeError as e:
            pytest.skip(f"Could not initialize session: {e}")
        finally:
            runtime.cleanup()

    def test_simple_chat_interaction(self, check_ollama_available):
        """Test a simple chat interaction with live backend."""
        with MelleaRuntime(backend="ollama", model_id="granite4:micro") as runtime:
            try:
                response = runtime.chat("What is 2 + 2? Reply with just the number.")
                assert response is not None
                assert len(response) > 0
            except MelleaRuntimeError as e:
                pytest.skip(f"Chat failed: {e}")

    def test_instruct_with_requirements(self, check_ollama_available):
        """Test structured generation with requirements."""
        with MelleaRuntime(backend="ollama", model_id="granite4:micro") as runtime:
            try:
                result = runtime.instruct(
                    "Generate a single word that describes the weather.",
                    requirements=["Output must be a single word", "No punctuation"],
                )
                assert result is not None
                # Should be a single word
                assert len(result.strip().split()) <= 2
            except MelleaRuntimeError as e:
                pytest.skip(f"Instruct failed: {e}")


# =============================================================================
# Test: Environment builder integration
# =============================================================================


class TestEnvironmentBuilderIntegration:
    """Tests for environment builder with mellea dependency injection."""

    def test_mellea_dependency_injected(self, temp_program_dir: Path):
        """Test that mellea is automatically added to program dependencies."""
        from mellea_api.core.config import Settings
        from mellea_api.models.assets import DependencySpec, PackageRef
        from mellea_api.models.common import DependencySource
        from mellea_api.services.environment_builder import EnvironmentBuilderService

        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(data_dir=Path(tmpdir))
            settings.ensure_data_dirs()

            builder = EnvironmentBuilderService(settings=settings)

            # Create deps without mellea
            deps = DependencySpec(
                source=DependencySource.MANUAL,
                packages=[PackageRef(name="requests", version="2.31.0")],
                pythonVersion="3.12",
            )

            # Should inject mellea
            result = builder.ensure_mellea_dependency(deps)

            assert any(p.name == "mellea" for p in result.packages)
            mellea_pkg = next(p for p in result.packages if p.name == "mellea")
            assert mellea_pkg.version == builder.MELLEA_VERSION

    def test_dockerfile_includes_mellea(self, temp_program_dir: Path):
        """Test that generated Dockerfile includes mellea."""
        from mellea_api.core.config import Settings
        from mellea_api.models.assets import DependencySpec, PackageRef
        from mellea_api.models.common import DependencySource
        from mellea_api.services.environment_builder import EnvironmentBuilderService

        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(data_dir=Path(tmpdir))
            settings.ensure_data_dirs()

            builder = EnvironmentBuilderService(settings=settings)

            deps = DependencySpec(
                source=DependencySource.MANUAL,
                packages=[PackageRef(name="mellea", version=">=0.3.0")],
                pythonVersion="3.12",
            )

            dockerfile, requirements = builder.generate_deps_dockerfile(deps)

            assert "mellea" in requirements
