"""Mellea 0.3.0 runtime adapter for the playground.

This module provides the MelleaRuntime class that bridges the playground's
execution model to mellea 0.3.0's session-based API.

Example:
    ```python
    from mellea_runtime import MelleaRuntime

    # Initialize runtime
    runtime = MelleaRuntime(backend='ollama', model_id='granite4:micro')

    # Simple chat
    response = runtime.chat("What is the capital of France?")

    # Structured generation
    result = runtime.instruct(
        "Generate a haiku about programming",
        requirements=["Must have exactly 3 lines"]
    )

    # Execute a @generative slot
    output = runtime.execute_slot(
        'my_program.generators',
        'summarize',
        text="Long text...",
        max_words=100
    )

    # Cleanup
    runtime.cleanup()
    ```
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pydantic import BaseModel

# Type alias for backend names
BackendName = Literal["ollama", "hf", "openai", "watsonx", "litellm"]

logger = logging.getLogger(__name__)

# Provider name mapping: playground -> mellea backend
PROVIDER_TO_BACKEND: dict[str, str] = {
    "OLLAMA": "ollama",
    "ollama": "ollama",
    "OPENAI": "openai",
    "openai": "openai",
    "WATSONX": "watsonx",
    "watsonx": "watsonx",
    "HUGGINGFACE": "hf",
    "huggingface": "hf",
    "hf": "hf",
    "LITELLM": "litellm",
    "litellm": "litellm",
}

# Default model per backend
DEFAULT_MODELS: dict[str, str] = {
    "ollama": "granite4:micro",
    "openai": "gpt-4o",
    "watsonx": "ibm/granite-3-3-8b-instruct",
    "hf": "meta-llama/Llama-3.2-3B-Instruct",
    "litellm": "gpt-4o",
}


class MelleaRuntimeError(Exception):
    """Base exception for MelleaRuntime errors."""

    pass


class SessionNotInitializedError(MelleaRuntimeError):
    """Raised when trying to use runtime before session is initialized."""

    pass


class SlotExecutionError(MelleaRuntimeError):
    """Raised when slot execution fails."""

    pass


class MelleaRuntime:
    """Runtime adapter for mellea 0.3.0 in the playground.

    Provides a unified interface for:
    - Chat interactions (m.chat())
    - Instruction-based generation (m.instruct())
    - Executing @generative decorated functions

    The runtime manages a single MelleaSession instance for the duration
    of a run, maintaining conversation context across multiple operations.
    """

    def __init__(
        self,
        backend: str | None = None,
        model_id: str | None = None,
        model_options: dict[str, Any] | None = None,
        run_id: str | None = None,
        node_id: str | None = None,
    ) -> None:
        """Initialize the runtime with backend configuration.

        Configuration can be provided directly or via environment variables:
        - MELLEA_BACKEND: Backend name
        - MELLEA_MODEL_ID: Model identifier
        - MELLEA_MODEL_OPTIONS: JSON model options
        - MELLEA_RUN_ID: Run ID for logging

        Args:
            backend: Backend name ('ollama', 'openai', 'watsonx', 'hf', 'litellm')
            model_id: Model identifier (e.g., 'granite4:micro', 'gpt-4o')
            model_options: Backend-specific options (temperature, max_tokens, etc.)
            run_id: Optional run ID for logging correlation
            node_id: Optional node ID for node-level logging
        """
        # Resolve configuration from args or environment
        self._backend = self._resolve_backend(backend)
        self._model_id = model_id or os.environ.get(
            "MELLEA_MODEL_ID", DEFAULT_MODELS.get(self._backend, "granite4:micro")
        )
        self._model_options = model_options or self._parse_model_options()
        self._run_id = run_id or os.environ.get("MELLEA_RUN_ID")
        self._node_id = node_id

        # Session is lazily initialized
        self._session: Any = None
        self._initialized = False

        logger.info(
            "MelleaRuntime configured: backend=%s, model=%s, run_id=%s",
            self._backend,
            self._model_id,
            self._run_id,
        )

    def _resolve_backend(self, backend: str | None) -> str:
        """Resolve backend name from argument or environment."""
        raw = backend or os.environ.get("MELLEA_BACKEND", "ollama")
        resolved = PROVIDER_TO_BACKEND.get(raw, raw)
        if resolved not in DEFAULT_MODELS:
            logger.warning("Unknown backend '%s', defaulting to 'ollama'", resolved)
            return "ollama"
        return resolved

    def _parse_model_options(self) -> dict[str, Any]:
        """Parse model options from environment variable."""
        options_str = os.environ.get("MELLEA_MODEL_OPTIONS", "")
        if not options_str:
            return {}
        try:
            result: dict[str, Any] = json.loads(options_str)
            return result
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse MELLEA_MODEL_OPTIONS: %s", e)
            return {}

    def _ensure_session(self) -> None:
        """Ensure the mellea session is initialized."""
        if self._initialized:
            return

        try:
            from mellea import start_session

            # Cast to literal type for type checker
            backend: BackendName = self._backend  # type: ignore[assignment]
            self._session = start_session(
                backend_name=backend,
                model_id=self._model_id,
                model_options=self._model_options if self._model_options else None,
            )
            self._initialized = True
            logger.info("MelleaSession initialized")
        except ImportError as e:
            raise MelleaRuntimeError(
                "mellea library not installed. Install with: pip install mellea>=0.3.0"
            ) from e
        except Exception as e:
            raise MelleaRuntimeError(f"Failed to initialize mellea session: {e}") from e

    @property
    def session(self) -> Any:
        """Access the underlying MelleaSession for advanced usage.

        Returns:
            The MelleaSession instance

        Raises:
            SessionNotInitializedError: If session hasn't been initialized
        """
        self._ensure_session()
        return self._session

    @property
    def backend(self) -> str:
        """Get the configured backend name."""
        return self._backend

    @property
    def model_id(self) -> str:
        """Get the configured model ID."""
        return self._model_id

    def chat(
        self,
        message: str,
        *,
        images: list[Any] | None = None,
        format: type[BaseModel] | None = None,
        **options: Any,
    ) -> str | Any:
        """Send a chat message and get a response.

        Args:
            message: The message to send
            images: Optional list of images for multimodal models
            format: Optional Pydantic model for structured output
            **options: Additional model options to override defaults

        Returns:
            The model's response text (or parsed object if format specified)

        Raises:
            MelleaRuntimeError: If the chat call fails
        """
        self._ensure_session()

        try:
            # Merge options
            merged_options = {**self._model_options, **options} if options else None

            response = self._session.chat(
                message,
                images=images,
                format=format,
                model_options=merged_options,
            )

            # Extract text from Message object if needed
            if hasattr(response, "content"):
                return response.content
            return str(response)

        except Exception as e:
            raise MelleaRuntimeError(f"Chat failed: {e}") from e

    def instruct(
        self,
        description: str,
        *,
        requirements: list[str] | None = None,
        examples: list[str] | None = None,
        context: dict[str, str] | None = None,
        format: type[BaseModel] | None = None,
        **options: Any,
    ) -> str | Any:
        """Generate output following instructions with optional validation.

        Args:
            description: What to generate
            requirements: Validation requirements for the output
            examples: In-context learning examples
            context: Grounding context (variables to include in prompt)
            format: Optional Pydantic model for structured output
            **options: Additional model options

        Returns:
            Generated output (or parsed object if format specified)

        Raises:
            MelleaRuntimeError: If the instruct call fails
        """
        self._ensure_session()

        try:
            # Merge options
            merged_options = {**self._model_options, **options} if options else None

            result = self._session.instruct(
                description,
                requirements=requirements,
                icl_examples=examples,
                grounding_context=context,
                format=format,
                model_options=merged_options,
            )

            # Extract text from ModelOutputThunk if needed
            if hasattr(result, "value"):
                return result.value
            return str(result)

        except Exception as e:
            raise MelleaRuntimeError(f"Instruct failed: {e}") from e

    def execute_slot(
        self,
        module_name: str,
        slot_name: str,
        **kwargs: Any,
    ) -> Any:
        """Execute a @generative slot from a program module.

        Dynamically imports the specified module and invokes the
        @generative decorated function with the given arguments.

        Args:
            module_name: Python module path (e.g., 'my_program.slots')
            slot_name: Name of the @generative decorated function
            **kwargs: Arguments to pass to the slot

        Returns:
            Slot output

        Raises:
            SlotExecutionError: If slot execution fails
        """
        try:
            # Import the module
            module = importlib.import_module(module_name)

            # Get the slot function
            if not hasattr(module, slot_name):
                raise SlotExecutionError(
                    f"Slot '{slot_name}' not found in module '{module_name}'"
                )

            slot_fn = getattr(module, slot_name)
            return self.invoke_slot(slot_fn, **kwargs)

        except ImportError as e:
            raise SlotExecutionError(
                f"Failed to import module '{module_name}': {e}"
            ) from e
        except SlotExecutionError:
            raise
        except Exception as e:
            raise SlotExecutionError(
                f"Failed to execute slot '{slot_name}' from '{module_name}': {e}"
            ) from e

    def invoke_slot(
        self,
        slot_fn: Callable[..., Any],
        **kwargs: Any,
    ) -> Any:
        """Execute a @generative slot directly (already imported).

        The slot function must be decorated with @generative from mellea.

        Args:
            slot_fn: The @generative decorated function
            **kwargs: Arguments to pass to the slot

        Returns:
            Slot output

        Raises:
            SlotExecutionError: If slot execution fails
        """
        self._ensure_session()

        try:
            # Check if it's a GenerativeSlot
            if hasattr(slot_fn, "format_for_llm"):
                # It's a @generative decorated function
                result = self._session.instruct(
                    slot_fn.format_for_llm(),
                    grounding_context=kwargs,
                )

                # Parse the result using the slot's parser if available
                if hasattr(slot_fn, "parse"):
                    return slot_fn.parse(result)

                # Extract value from ModelOutputThunk
                if hasattr(result, "value"):
                    return result.value
                return str(result)
            else:
                # It's a regular function, just call it
                return slot_fn(**kwargs)

        except Exception as e:
            slot_name = getattr(slot_fn, "__name__", str(slot_fn))
            raise SlotExecutionError(
                f"Failed to invoke slot '{slot_name}': {e}"
            ) from e

    def switch_model(
        self,
        backend: str | None = None,
        model_id: str | None = None,
        model_options: dict[str, Any] | None = None,
    ) -> None:
        """Switch to a different model configuration.

        Creates a new session with the specified configuration.
        The previous session is cleaned up.

        Args:
            backend: New backend name (or keep current if None)
            model_id: New model ID (or keep current if None)
            model_options: New model options (or keep current if None)
        """
        # Cleanup old session
        self.cleanup()

        # Update configuration
        if backend is not None:
            self._backend = self._resolve_backend(backend)
        if model_id is not None:
            self._model_id = model_id
        if model_options is not None:
            self._model_options = model_options

        # Reset initialization flag - session will be created on next use
        self._initialized = False

        logger.info(
            "Model switched to: backend=%s, model=%s",
            self._backend,
            self._model_id,
        )

    def cleanup(self) -> None:
        """Clean up session resources.

        Should be called when the runtime is no longer needed.
        """
        if self._session is not None:
            try:
                if hasattr(self._session, "cleanup"):
                    self._session.cleanup()
            except Exception as e:
                logger.warning("Error during session cleanup: %s", e)
            finally:
                self._session = None
                self._initialized = False

        logger.info("MelleaRuntime cleaned up")

    def __enter__(self) -> MelleaRuntime:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - ensures cleanup."""
        self.cleanup()


# =============================================================================
# Compatibility Shims
# =============================================================================


def invoke_model(
    model_id: str,
    prompt: str,
    *,
    backend: str | None = None,
    **kwargs: Any,
) -> str:
    """Compatibility shim for direct model invocation.

    This function provides backward compatibility with the legacy
    invoke_model() interface. New code should use MelleaRuntime.chat()
    or MelleaRuntime.instruct() instead.

    Args:
        model_id: Model identifier (e.g., 'ollama:granite4:micro', 'openai:gpt-4o')
        prompt: The prompt to send
        backend: Optional backend override
        **kwargs: Additional model options

    Returns:
        Model response text

    Example:
        ```python
        # Legacy usage
        response = invoke_model("ollama:granite4:micro", "Hello!")

        # Recommended usage
        runtime = MelleaRuntime(backend='ollama', model_id='granite4:micro')
        response = runtime.chat("Hello!")
        ```
    """
    # Parse model_id if it contains backend prefix
    resolved_backend = backend
    resolved_model = model_id

    if ":" in model_id and backend is None:
        parts = model_id.split(":", 1)
        if parts[0].lower() in PROVIDER_TO_BACKEND:
            resolved_backend = parts[0]
            resolved_model = parts[1]

    with MelleaRuntime(
        backend=resolved_backend,
        model_id=resolved_model,
        model_options=kwargs if kwargs else None,
    ) as runtime:
        return runtime.chat(prompt)


def run_program(
    program_id: str,
    slot_name: str = "main",
    *,
    module_name: str | None = None,
    backend: str | None = None,
    model_id: str | None = None,
    **kwargs: Any,
) -> Any:
    """Compatibility shim for legacy program execution.

    This function provides backward compatibility with the legacy
    run_program() interface. New code should use MelleaRuntime.execute_slot()
    instead.

    Args:
        program_id: Program identifier (used as module name if module_name not provided)
        slot_name: Name of the @generative slot to execute (default: "main")
        module_name: Python module path (defaults to program_id)
        backend: Backend name
        model_id: Model identifier
        **kwargs: Arguments to pass to the slot

    Returns:
        Slot output

    Example:
        ```python
        # Legacy usage
        result = run_program("my_program", "summarize", text="Long text...")

        # Recommended usage
        runtime = MelleaRuntime(backend='ollama')
        result = runtime.execute_slot('my_program', 'summarize', text="Long text...")
        ```
    """
    resolved_module = module_name or program_id

    with MelleaRuntime(backend=backend, model_id=model_id) as runtime:
        return runtime.execute_slot(resolved_module, slot_name, **kwargs)


# =============================================================================
# Module-level convenience functions
# =============================================================================

# Global runtime instance for simple usage
_global_runtime: MelleaRuntime | None = None


def get_runtime(
    backend: str | None = None,
    model_id: str | None = None,
    **kwargs: Any,
) -> MelleaRuntime:
    """Get a global MelleaRuntime instance.

    Creates a new instance if one doesn't exist or if configuration differs.

    Args:
        backend: Backend name
        model_id: Model identifier
        **kwargs: Additional configuration

    Returns:
        MelleaRuntime instance
    """
    global _global_runtime

    # Create new instance if needed
    if _global_runtime is None:
        _global_runtime = MelleaRuntime(backend=backend, model_id=model_id, **kwargs)
    elif (
        (backend is not None and backend != _global_runtime.backend)
        or (model_id is not None and model_id != _global_runtime.model_id)
    ):
        # Configuration changed, create new instance
        _global_runtime.cleanup()
        _global_runtime = MelleaRuntime(backend=backend, model_id=model_id, **kwargs)

    return _global_runtime


def cleanup_runtime() -> None:
    """Clean up the global runtime instance."""
    global _global_runtime
    if _global_runtime is not None:
        _global_runtime.cleanup()
        _global_runtime = None
