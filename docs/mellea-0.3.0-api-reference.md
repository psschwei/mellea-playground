# Mellea 0.3.0 API Reference

This document provides a comprehensive mapping of mellea 0.3.0 API surface to playground concepts,
along with migration strategies for the 0.3.0 compatibility upgrade.

## Table of Contents

1. [Core API Surface](#core-api-surface)
2. [Session Management](#session-management)
3. [Generative Decorator](#generative-decorator)
4. [Backends and Model Configuration](#backends-and-model-configuration)
5. [Sampling Strategies](#sampling-strategies)
6. [Requirements and Validation](#requirements-and-validation)
7. [Playground Concept Mapping](#playground-concept-mapping)
8. [Migration Strategy](#migration-strategy)

---

## Core API Surface

### Module Exports

```python
from mellea import (
    MelleaSession,      # Main session class
    start_session,       # Factory function for creating sessions
    generative,          # Decorator for generative slots
    backends,            # Backend implementations
    model_ids,           # Pre-defined model identifiers
    stdlib,              # Standard library components
    formatters,          # Chat/template formatters
    helpers,             # Utility functions
    core,                # Core abstractions
)
```

### Quick Start Example

```python
from mellea import start_session, generative

# Create a session with Ollama backend
m = start_session(backend_name='ollama', model_id='granite4:micro')

# Simple chat
response = m.chat("What is the capital of France?")
print(response)

# Instruction-based generation
result = m.instruct(
    description="Generate a haiku about programming",
    requirements=["Must have exactly 3 lines"]
)
print(result)
```

---

## Session Management

### `start_session()`

Factory function for creating MelleaSession instances.

```python
def start_session(
    backend_name: Literal['ollama', 'hf', 'openai', 'watsonx', 'litellm'] = 'ollama',
    model_id: str | ModelIdentifier = IBM_GRANITE_4_MICRO,
    ctx: Context | None = None,
    *,
    model_options: dict | None = None,
    **backend_kwargs
) -> MelleaSession
```

**Parameters:**
- `backend_name`: Backend provider ('ollama', 'hf', 'openai', 'watsonx', 'litellm')
- `model_id`: Model identifier (string or ModelIdentifier)
- `ctx`: Optional pre-existing context
- `model_options`: Backend-specific model options
- `backend_kwargs`: Additional backend configuration

**Example:**
```python
# Ollama backend with specific model
m = start_session('ollama', model_id='llama3.2:3b')

# OpenAI backend with custom options
m = start_session(
    'openai',
    model_id='gpt-5.1',
    model_options={'temperature': 0.7}
)

# WatsonX backend
m = start_session(
    'watsonx',
    model_id='ibm/granite-3-3-8b-instruct'
)
```

### `MelleaSession`

Main session class for interacting with LLMs.

```python
class MelleaSession:
    def __init__(self, backend: Backend, ctx: Context | None = None)
```

**Key Methods:**

| Method | Description |
|--------|-------------|
| `chat()` | Simple chat message exchange |
| `instruct()` | Instruction-based generation with requirements |
| `query()` | Query an MObject for information |
| `clone()` | Create a copy of session with current context |
| `reset()` | Reset the context state |
| `cleanup()` | Clean up session resources |
| `last_prompt()` | Get the last prompt sent |
| `powerup()` | Extend session with additional methods |

---

## Session Methods

### `chat()`

Simple chat message with response.

```python
def chat(
    self,
    content: str,
    role: Message.Role = 'user',
    *,
    images: list[ImageBlock] | list[PILImage.Image] | None = None,
    user_variables: dict[str, str] | None = None,
    format: type[BaseModel] | None = None,
    model_options: dict | None = None,
    tool_calls: bool = False
) -> Message
```

**Example:**
```python
# Basic chat
response = m.chat("Explain quantum computing in simple terms")

# Chat with image
response = m.chat(
    "What's in this image?",
    images=[image_data]
)

# Chat with structured output
class Answer(BaseModel):
    text: str
    confidence: float

response = m.chat("What is 2+2?", format=Answer)
```

### `instruct()`

Instruction-based generation with validation.

```python
def instruct(
    self,
    description: str,
    *,
    images: list[ImageBlock] | list[PILImage.Image] | None = None,
    requirements: list[Requirement | str] | None = None,
    icl_examples: list[str | CBlock] | None = None,
    grounding_context: dict[str, str | CBlock | Component] | None = None,
    user_variables: dict[str, str] | None = None,
    prefix: str | CBlock | None = None,
    output_prefix: str | CBlock | None = None,
    strategy: SamplingStrategy | None = RejectionSamplingStrategy(),
    return_sampling_results: bool = False,
    format: type[BaseModel] | None = None,
    model_options: dict | None = None,
    tool_calls: bool = False
) -> ModelOutputThunk[str] | SamplingResult
```

**Example:**
```python
# Basic instruction
result = m.instruct("Write a function that calculates fibonacci numbers")

# With requirements
result = m.instruct(
    "Generate a JSON configuration",
    requirements=[
        "Must be valid JSON",
        "Must contain 'name' and 'version' fields"
    ]
)

# With ICL examples
result = m.instruct(
    "Convert the sentence to past tense",
    icl_examples=[
        "Input: I run fast\nOutput: I ran fast",
        "Input: She walks home\nOutput: She walked home"
    ],
    grounding_context={"sentence": "He writes code"}
)
```

### `query()`

Query an MObject for information.

```python
def query(
    self,
    obj: Any,
    query: str,
    *,
    format: type[BaseModel] | None = None,
    model_options: dict | None = None,
    tool_calls: bool = False
) -> ModelOutputThunk
```

---

## Generative Decorator

### `@generative`

Decorator that marks a function as a generative slot.

```python
from mellea import generative

@generative
def generate_poem(topic: str, style: str = "haiku") -> str:
    """Generate a poem about the given topic.

    Args:
        topic: Subject matter for the poem
        style: Poetry style (haiku, sonnet, free verse)

    Returns:
        The generated poem text
    """
    pass  # Implementation provided by mellea runtime
```

**Key Features:**
- Converts function to `GenerativeSlot`
- Function signature becomes the slot's schema
- Docstrings provide instructions to the model
- Type hints define input/output types

### `GenerativeSlot`

Wrapper class created by `@generative` decorator.

```python
class GenerativeSlot[P, R]:
    def __init__(self, func: Callable[P, R])

    def format_for_llm(self) -> TemplateRepresentation
    def parse(self, computed: ModelOutputThunk) -> S
    def parts(self) -> list[Component | CBlock]

    @staticmethod
    def extract_args_and_kwargs(*args, **kwargs) -> ExtractedArgs
```

**Invocation Pattern:**
```python
@generative
def summarize(text: str, max_words: int = 100) -> str:
    """Summarize the given text."""
    pass

# Usage with session
m = start_session('ollama')
slot = summarize

# The slot is invoked through session.instruct or similar
result = m.instruct(
    slot.format_for_llm(),
    grounding_context={"text": "Long text here...", "max_words": 50}
)
```

---

## Backends and Model Configuration

### Backend Types

| Backend | Module | Use Case |
|---------|--------|----------|
| Ollama | `backends.adapters` | Local inference with Ollama |
| HuggingFace | `backends.adapters` | HuggingFace Hub models |
| OpenAI | `backends.adapters` | OpenAI API |
| WatsonX | `backends.adapters` | IBM WatsonX |
| LiteLLM | `backends.adapters` | Multi-provider proxy |

### `ModelIdentifier`

Dataclass for cross-platform model identification.

```python
@dataclass
class ModelIdentifier:
    hf_model_name: str | None = None      # HuggingFace Hub name
    ollama_name: str | None = None         # Ollama model tag
    watsonx_name: str | None = None        # WatsonX model ID
    mlx_name: str | None = None            # MLX model name
    openai_name: str | None = None         # OpenAI model ID
    hf_tokenizer_name: str | None = None   # Optional tokenizer override
```

### Pre-defined Model IDs

```python
from mellea.model_ids import (
    # IBM Granite
    IBM_GRANITE_4_MICRO_3B,        # granite4:micro (default)
    IBM_GRANITE_3_3_8B,            # granite3.3:8b
    IBM_GRANITE_GUARDIAN_3_0_2B,   # granite3-guardian:2b

    # Meta Llama
    META_LLAMA_3_2_3B,             # llama3.2:3b
    META_LLAMA_3_3_70B,            # llama3.3:70b
    META_LLAMA_4_SCOUT_17B_16E_INSTRUCT,  # llama4:scout
    META_LLAMA_4_MAVERICK_17B_128E_INSTRUCT,  # llama4:maverick

    # Mistral
    MISTRALAI_MISTRAL_SMALL_24B,   # mistral-small:latest
    MISTRALAI_MISTRAL_LARGE_123B,  # mistral-large:latest

    # Microsoft
    MS_PHI_4_14B,                  # phi4:14b
    MS_PHI_4_MINI_REASONING_4B,    # phi4-mini-reasoning:3.8b

    # Qwen
    QWEN3_8B,                      # qwen3:8b
    QWEN3_14B,                     # qwen3:14b

    # DeepSeek
    DEEPSEEK_R1_8B,                # deepseek-r1:8b

    # OpenAI
    OPENAI_GPT_5_1,                # gpt-5.1
    OPENAI_GPT_OSS_20B,            # gpt-oss:20b
    OPENAI_GPT_OSS_120B,           # gpt-oss:120b
)
```

### `ModelOption`

Configuration for model inference parameters.

```python
from mellea.backends import ModelOption

# Model options are passed as dict to start_session or methods
model_options = {
    'temperature': 0.7,
    'max_tokens': 1024,
    'top_p': 0.9,
    'stop': ['\n\n'],
}
```

---

## Sampling Strategies

### Available Strategies

```python
from mellea.stdlib.sampling import (
    BaseSamplingStrategy,
    RejectionSamplingStrategy,   # Default - retry on failure
    RepairTemplateStrategy,       # Attempt to repair failed outputs
    MultiTurnStrategy,            # Multi-turn conversation repair
    SOFAISamplingStrategy,        # Two-stage solve/verify
)
```

### `RejectionSamplingStrategy`

Default strategy - retries generation if validation fails.

```python
strategy = RejectionSamplingStrategy(
    loop_budget=3,                # Max retry attempts
    requirements=[...]            # Validation requirements
)

result = m.instruct(
    "Generate valid JSON",
    strategy=strategy,
    requirements=["Must be valid JSON"]
)
```

### `SOFAISamplingStrategy`

Advanced two-stage strategy with separate solver and judge models.

```python
strategy = SOFAISamplingStrategy(
    s1_solver_backend=solver_backend,     # Primary generation
    s2_solver_backend=repair_backend,     # Repair model
    s2_solver_mode='continue_chat',       # 'fresh_start', 'continue_chat', 'best_attempt'
    loop_budget=3,
    judge_backend=judge_backend,          # Optional judge model
    feedback_strategy='simple'            # 'simple', 'first_error', 'all_errors'
)
```

---

## Requirements and Validation

### `Requirement`

Validation constraints for generated output.

```python
from mellea.core import Requirement, ValidationResult

# String requirement (uses LLM for validation)
req = Requirement("Must be valid JSON")

# Custom validation function
def validate_json(ctx: Context) -> ValidationResult:
    try:
        import json
        json.loads(ctx.last_output())
        return ValidationResult(passed=True)
    except:
        return ValidationResult(
            passed=False,
            error_message="Invalid JSON syntax"
        )

req = Requirement(
    description="Must be valid JSON",
    validation_fn=validate_json
)
```

### `Context`

Conversation context tracking.

```python
from mellea.core import Context

ctx = Context()

# Methods
ctx.add(component)              # Add to context
ctx.reset_to_new()              # Clear context
ctx.last_output()               # Get last model output
ctx.last_turn()                 # Get last context turn
ctx.as_list()                   # Get all turns as list
ctx.view_for_generation()       # Get formatted view for model
```

---

## Playground Concept Mapping

### Direct Mappings

| Playground Concept | Mellea 0.3.0 Equivalent |
|--------------------|-------------------------|
| Program execution | `MelleaSession` + `start_session()` |
| Model invocation | `m.chat()` / `m.instruct()` |
| `@generative` slot | `@generative` decorator (identical) |
| Model selection | `ModelIdentifier` + `start_session(backend_name, model_id)` |
| Model parameters | `model_options` dict parameter |
| Validation | `Requirement` + `SamplingStrategy` |

### Slot Detection

The playground detects `@generative` slots via AST analysis. This remains compatible with mellea 0.3.0:

```python
# Playground SlotMetadata maps to:
from mellea import generative

@generative
def my_slot(arg1: str, arg2: int = 10) -> str:
    """Docstring becomes instruction."""
    pass

# SlotMetadata extracted:
# - name: "my_slot"
# - qualifiedName: "module.my_slot"
# - signature: SlotSignature(name="my_slot", args=[...], returns={...})
# - decorators: ["@generative"]
```

### Model Provider Mapping

| Playground ModelProvider | Mellea Backend |
|--------------------------|----------------|
| `OLLAMA` | `'ollama'` |
| `HUGGINGFACE` | `'hf'` |
| `OPENAI` | `'openai'` |
| `WATSONX` | `'watsonx'` |
| `LITELLM` | `'litellm'` |

### Resource and Runtime Mapping

| Playground ResourceProfile | Mellea Equivalent |
|---------------------------|-------------------|
| `cpu_limit` | N/A (infrastructure concern) |
| `memory_limit` | N/A (infrastructure concern) |
| `timeout_seconds` | `model_options` timeout |

---

## Migration Strategy

### Phase 1: Runtime Adapter Layer

Create an adapter that wraps mellea 0.3.0 API for the playground:

```python
# mellea_runtime.py
from mellea import start_session, MelleaSession, generative
from mellea.model_ids import ModelIdentifier

class MelleaRuntime:
    """Adapter layer between playground and mellea 0.3.0."""

    def __init__(
        self,
        backend_name: str = 'ollama',
        model_id: str | ModelIdentifier = None,
        model_options: dict | None = None
    ):
        self.session = start_session(
            backend_name=backend_name,
            model_id=model_id,
            model_options=model_options
        )

    def execute_slot(self, slot_fn, **kwargs):
        """Execute a @generative slot with arguments."""
        slot = slot_fn  # Already decorated with @generative
        return self.session.instruct(
            slot.format_for_llm(),
            grounding_context=kwargs
        )

    def chat(self, message: str, **options):
        """Simple chat interaction."""
        return self.session.chat(message, **options)

    def cleanup(self):
        """Clean up session resources."""
        self.session.cleanup()
```

### Phase 2: Base Image Updates

Update container base images to include mellea 0.3.0:

```dockerfile
# Dockerfile.mellea-base
FROM python:3.13-slim

# Install mellea 0.3.0
RUN pip install mellea==0.3.0

# ... other dependencies
```

### Phase 3: Program Validator Updates

Extend validator to understand mellea 0.3.0 patterns:

```python
# Additional decorators to detect
MELLEA_DECORATORS = [
    "generative",      # Existing
    "verifier",        # Existing
    "requirement",     # Existing
    # No new decorators in 0.3.0
]

# The @generative decorator signature is unchanged
# AST detection remains the same
```

### Phase 4: Environment Builder Updates

Update environment builder to configure mellea 0.3.0:

```python
# environment_config.py
MELLEA_CONFIG = {
    'version': '0.3.0',
    'default_backend': 'ollama',
    'default_model': 'granite4:micro',
}
```

---

## API Compatibility Notes

### Breaking Changes from 0.2.x

1. **Session creation**: `start_session()` signature updated
   - Old: Provider-specific factory functions
   - New: Unified `start_session(backend_name, model_id)`

2. **Model options**: Consolidated into `model_options` dict
   - Old: Scattered parameters
   - New: Single dict for all options

3. **Backends**: Unified adapter system
   - Old: Separate backend classes
   - New: `backend_name` string + adapters

### Unchanged APIs

1. `@generative` decorator - signature and behavior unchanged
2. `MelleaSession.chat()` - parameters compatible
3. `MelleaSession.instruct()` - parameters compatible
4. `Requirement` - validation system unchanged
5. `SamplingStrategy` - all strategies available

---

## References

- [Mellea GitHub Repository](https://github.com/ibm-granite/mellea)
- [Mellea PyPI Package](https://pypi.org/project/mellea/)
- Playground ProgramValidator: `backend/src/mellea_api/services/program_validator.py`
- Playground RunExecutor: `backend/src/mellea_api/services/run_executor.py`
