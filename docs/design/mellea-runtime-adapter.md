# Mellea Runtime Adapter Layer Design

This document describes the design for bridging the playground's execution model to mellea 0.3.0's session-based API.

## Overview

The runtime adapter layer provides compatibility between:
- **Playground execution model**: programs, compositions, models, and runs executed in K8s containers
- **Mellea 0.3.0 API**: session-based interactions with `start_session()`, `m.chat()`, `m.instruct()`, and `@generative`

## Design Decisions

### 1. Session Scope: One Session Per Run

**Decision**: Create one `MelleaSession` per composition/program run.

**Rationale**:
- A single run represents one logical execution unit
- Session maintains conversation context across multiple node executions
- Allows context sharing between nodes (e.g., summarizer can reference earlier outputs)
- Clean lifecycle: session starts with run, ends when run completes
- Memory isolation: each run has independent context

**Alternative considered**: Session per program node
- Rejected because: loses cross-node context, increases backend overhead

### 2. Adapter Location: User Container

**Decision**: The adapter module lives inside the user container, not the API server.

**Rationale**:
- Execution isolation: each run executes in its own K8s pod
- Lower latency: LLM calls originate from execution container
- Better scaling: no central bottleneck in API server
- Security: credentials injected as K8s secrets into pod
- Simpler architecture: code generator imports adapter directly

**Implementation**: The adapter module (`mellea_runtime.py`) is installed in the base container image.

### 3. Model ID Mapping

**Decision**: Map playground `ModelAsset` to mellea `backend_name` + `model_id` via configuration.

The playground's `ModelAsset` contains:
```python
class ModelAsset:
    provider: ModelProvider  # OLLAMA, OPENAI, WATSONX, HUGGINGFACE, LITELLM
    model_id: str            # e.g., "llama3.2:3b", "gpt-5.1"
    model_options: dict      # temperature, max_tokens, etc.
```

Maps to mellea's `start_session()`:
```python
m = start_session(
    backend_name='ollama',      # from provider
    model_id='llama3.2:3b',     # from model_id
    model_options={'temperature': 0.7}  # from model_options
)
```

**Provider mapping**:
| Playground Provider | Mellea Backend |
|---------------------|----------------|
| `OLLAMA`            | `'ollama'`     |
| `OPENAI`            | `'openai'`     |
| `WATSONX`           | `'watsonx'`    |
| `HUGGINGFACE`       | `'hf'`         |
| `LITELLM`           | `'litellm'`    |

### 4. Generative Slot Invocation

**Decision**: The adapter provides a unified interface for invoking `@generative` functions.

The code generator produces code like:
```python
from mellea_runtime import MelleaRuntime

# Initialize runtime (one per run)
runtime = MelleaRuntime(
    backend='ollama',
    model_id='granite4:micro'
)

# Execute a @generative slot
result = runtime.execute_slot(
    module_name='my_program.generators',
    slot_name='summarize',
    text="Long text to summarize...",
    max_words=100
)
```

The adapter dynamically imports and invokes the slot:
```python
def execute_slot(self, module_name: str, slot_name: str, **kwargs):
    module = importlib.import_module(module_name)
    slot_fn = getattr(module, slot_name)

    # Slot is a @generative decorated function
    return self.session.instruct(
        slot_fn.format_for_llm(),
        grounding_context=kwargs
    )
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    K8s Run Pod                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │                  Generated Code                          │ │
│ │  (composition_runner.py or program entrypoint)           │ │
│ └────────────────────────┬──────────────────────────────────┘ │
│                          │                                  │
│                          ▼                                  │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │              MelleaRuntime Adapter                       │ │
│ │  - Session management                                    │ │
│ │  - Model invocation (chat/instruct)                      │ │
│ │  - Slot execution                                        │ │
│ │  - Logging and metrics                                   │ │
│ └────────────────────────┬──────────────────────────────────┘ │
│                          │                                  │
│                          ▼                                  │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │              mellea 0.3.0 Library                        │ │
│ │  - start_session()                                       │ │
│ │  - MelleaSession (chat, instruct, query)                 │ │
│ │  - @generative decorator                                 │ │
│ │  - Backends (ollama, openai, watsonx, hf, litellm)       │ │
│ └────────────────────────┬──────────────────────────────────┘ │
│                          │                                  │
│                          ▼                                  │
│                    LLM Backend                              │
│              (Ollama, OpenAI, etc.)                         │
└─────────────────────────────────────────────────────────────┘
```

## API Contract

### MelleaRuntime Class

```python
class MelleaRuntime:
    """Runtime adapter for mellea 0.3.0 in the playground."""

    def __init__(
        self,
        backend: str = 'ollama',
        model_id: str | None = None,
        model_options: dict | None = None,
        run_id: str | None = None,
    ):
        """Initialize the runtime with backend configuration.

        Args:
            backend: Backend name ('ollama', 'openai', 'watsonx', 'hf', 'litellm')
            model_id: Model identifier (e.g., 'granite4:micro', 'gpt-5.1')
            model_options: Backend-specific options (temperature, max_tokens, etc.)
            run_id: Optional run ID for logging correlation
        """

    def chat(
        self,
        message: str,
        *,
        images: list | None = None,
        format: type | None = None,
        **options
    ) -> str:
        """Send a chat message and get a response.

        Args:
            message: The message to send
            images: Optional list of images for multimodal models
            format: Optional Pydantic model for structured output
            **options: Additional model options to override defaults

        Returns:
            The model's response text (or parsed object if format specified)
        """

    def instruct(
        self,
        description: str,
        *,
        requirements: list[str] | None = None,
        examples: list[str] | None = None,
        context: dict[str, str] | None = None,
        format: type | None = None,
        **options
    ) -> str:
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
        """

    def execute_slot(
        self,
        module_name: str,
        slot_name: str,
        **kwargs
    ) -> Any:
        """Execute a @generative slot from a program module.

        Args:
            module_name: Python module path (e.g., 'my_program.slots')
            slot_name: Name of the @generative decorated function
            **kwargs: Arguments to pass to the slot

        Returns:
            Slot output
        """

    def invoke_slot(
        self,
        slot_fn: Callable,
        **kwargs
    ) -> Any:
        """Execute a @generative slot directly (already imported).

        Args:
            slot_fn: The @generative decorated function
            **kwargs: Arguments to pass to the slot

        Returns:
            Slot output
        """

    def cleanup(self) -> None:
        """Clean up session resources."""

    @property
    def session(self) -> MelleaSession:
        """Access the underlying MelleaSession for advanced usage."""
```

### Compatibility Shims

For backward compatibility with existing playground patterns:

```python
# Legacy: run_program(program_id, **kwargs)
# New: Use MelleaRuntime with the program's @generative slots

def run_program(program_id: str, **kwargs) -> dict:
    """Compatibility shim for legacy program execution.

    Deprecated: Use MelleaRuntime.execute_slot() instead.
    """
    # Load program metadata
    # Initialize MelleaRuntime with program's model config
    # Execute the program's main slot

# Legacy: invoke_model(model_id, prompt)
# New: MelleaRuntime.chat() or .instruct()

def invoke_model(model_id: str, prompt: str, **kwargs) -> str:
    """Compatibility shim for direct model invocation.

    Deprecated: Use MelleaRuntime.chat() instead.
    """
    # Parse model_id to extract provider/model
    # Create temporary MelleaRuntime
    # Call chat() or instruct()
```

## Code Generator Updates

The `CodeGenerator` class needs updates to produce mellea 0.3.0 compatible code:

### Before (current)
```python
# Generated code uses undefined invoke_model/run_program
result = invoke_model("model-abc", prompt)
result = run_program("program-xyz", input=data)
```

### After (mellea 0.3.0)
```python
from mellea_runtime import MelleaRuntime

# Initialize runtime (happens once at start)
runtime = MelleaRuntime(
    backend='ollama',
    model_id='granite4:micro',
    run_id=os.environ.get('MELLEA_RUN_ID')
)

# Model node: use chat or instruct
model_abc_output = runtime.chat("What is the capital of France?")

# Program node: execute @generative slot
program_xyz_output = runtime.execute_slot(
    'my_program.main',
    'generate_summary',
    text=input_data
)

# Cleanup at end
runtime.cleanup()
```

## Environment Variables

The runtime adapter reads configuration from environment variables (injected by K8s):

| Variable | Description | Example |
|----------|-------------|---------|
| `MELLEA_RUN_ID` | Run identifier for logging | `run-abc123` |
| `MELLEA_BACKEND` | Default backend name | `ollama` |
| `MELLEA_MODEL_ID` | Default model ID | `granite4:micro` |
| `MELLEA_MODEL_OPTIONS` | JSON model options | `{"temperature": 0.7}` |
| `OLLAMA_HOST` | Ollama API endpoint | `http://ollama:11434` |
| `OPENAI_API_KEY` | OpenAI API key | (secret) |
| `WATSONX_API_KEY` | WatsonX API key | (secret) |

## Implementation Plan

### Phase 1: Core Adapter Module
1. Create `mellea_runtime.py` module with `MelleaRuntime` class
2. Implement `chat()` and `instruct()` methods
3. Implement `execute_slot()` for @generative functions
4. Add logging integration with NodeLogger

### Phase 2: Code Generator Updates
1. Update `CodeGenerator` to import `MelleaRuntime`
2. Generate runtime initialization code
3. Update model node generation to use `runtime.chat()`
4. Update program node generation to use `runtime.execute_slot()`

### Phase 3: Base Image Updates
1. Add `mellea==0.3.0` to base image dependencies
2. Include `mellea_runtime.py` in base image
3. Configure environment variables in K8s job specs

### Phase 4: Testing & Migration
1. Unit tests for adapter module
2. Integration tests with mock backends
3. End-to-end tests with real compositions
4. Migration guide for existing programs

## Open Questions

1. **Context persistence**: Should session context persist across multiple runs of the same composition (for iterative refinement)?
   - Current design: No, each run is independent
   - Future consideration: Optional context checkpointing

2. **Multi-model compositions**: How to handle compositions using multiple models (e.g., different backends)?
   - Current design: Create multiple MelleaRuntime instances
   - Consider: Runtime.switch_model() method

3. **Streaming**: Should the adapter support streaming responses?
   - Not in initial version
   - Future: Add `stream=True` parameter to chat/instruct

## References

- [Mellea 0.3.0 API Reference](../mellea-0.3.0-api-reference.md)
- [Code Generator](../../backend/src/mellea_api/services/code_generator.py)
- [Composition Executor](../../backend/src/mellea_api/services/composition_executor.py)
