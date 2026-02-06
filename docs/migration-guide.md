# Migration Guide: Upgrading to mellea 0.3.0

This guide helps you migrate programs from earlier mellea versions to 0.3.0.

## Overview of Changes

mellea 0.3.0 introduces a unified API while maintaining backward compatibility for core features:

| Feature | Pre-0.3.0 | 0.3.0 |
|---------|-----------|-------|
| Session creation | Provider-specific factories | `start_session(backend_name, model_id)` |
| Model options | Scattered parameters | Single `model_options` dict |
| Backends | Separate classes | Unified adapter system |

### Unchanged APIs

The following remain compatible:

- `@generative` decorator - signature and behavior unchanged
- `MelleaSession.chat()` - parameters compatible
- `MelleaSession.instruct()` - parameters compatible
- `Requirement` - validation system unchanged
- `SamplingStrategy` - all strategies available

---

## Migration Steps

### Step 1: Update Session Creation

**Before (0.2.x):**
```python
# Provider-specific factory functions
from mellea.providers.ollama import create_ollama_session

session = create_ollama_session(model="granite4:micro")
```

**After (0.3.0):**
```python
from mellea import start_session

session = start_session(backend_name='ollama', model_id='granite4:micro')
```

### Step 2: Update Model Options

**Before (0.2.x):**
```python
session = create_session(
    model="gpt-4",
    temperature=0.7,
    max_tokens=1024
)
```

**After (0.3.0):**
```python
session = start_session(
    backend_name='openai',
    model_id='gpt-4o',
    model_options={
        'temperature': 0.7,
        'max_tokens': 1024
    }
)
```

### Step 3: Update Imports

**Before (0.2.x):**
```python
from mellea import MelleaSession, generative
from mellea.providers.openai import OpenAIBackend
```

**After (0.3.0):**
```python
from mellea import start_session, MelleaSession, generative
# Backends are selected by name, no direct imports needed
```

---

## @generative Slots (No Changes Required)

The `@generative` decorator remains unchanged:

```python
from mellea import generative

@generative
def summarize(text: str, max_words: int = 50) -> str:
    """Summarize the given text.

    Args:
        text: Text to summarize
        max_words: Maximum word count

    Returns:
        Concise summary
    """
    ...
```

The playground detects these slots via AST analysis - no migration needed.

---

## Backend Names Mapping

| Old Provider | 0.3.0 Backend Name |
|--------------|-------------------|
| Ollama provider | `'ollama'` |
| OpenAI provider | `'openai'` |
| WatsonX provider | `'watsonx'` |
| HuggingFace provider | `'hf'` |
| LiteLLM provider | `'litellm'` |

---

## Playground Runtime Adapter

Programs running in the playground can use the `MelleaRuntime` adapter:

```python
from mellea_api.runtime import MelleaRuntime, get_runtime

# Option 1: Direct instantiation
runtime = MelleaRuntime(backend='ollama', model_id='granite4:micro')
response = runtime.chat("Hello!")
runtime.cleanup()

# Option 2: Context manager
with MelleaRuntime(backend='ollama') as runtime:
    response = runtime.chat("Hello!")

# Option 3: Global singleton
runtime = get_runtime(backend='ollama')
response = runtime.chat("Hello!")
```

### Environment Variables

The runtime reads configuration from environment variables when not explicitly provided:

| Variable | Description | Example |
|----------|-------------|---------|
| `MELLEA_BACKEND` | Backend name | `ollama` |
| `MELLEA_MODEL_ID` | Model identifier | `granite4:micro` |
| `MELLEA_MODEL_OPTIONS` | JSON model options | `{"temperature": 0.7}` |
| `MELLEA_RUN_ID` | Run ID for logging | `run-abc123` |

---

## Testing Your Migration

1. **Update dependencies:**
   ```toml
   # pyproject.toml
   dependencies = [
       "mellea>=0.3.0",
   ]
   ```

2. **Run locally:**
   ```bash
   pip install mellea>=0.3.0
   python your_program.py
   ```

3. **Verify slots are detected:**
   ```python
   from mellea_api.services.program_validator import get_program_validator

   validator = get_program_validator()
   slots = validator.detect_slots(Path("./your_program"))
   print(f"Found {len(slots)} slots")
   ```

---

## Common Issues

### Import Errors

**Error:** `ImportError: cannot import name 'create_ollama_session'`

**Solution:** Replace with `start_session(backend_name='ollama', ...)`

### Model ID Format

**Error:** `Unknown model ID format`

**Solution:** Remove backend prefix from model_id:
```python
# Wrong
start_session('ollama', model_id='ollama:granite4:micro')

# Correct
start_session('ollama', model_id='granite4:micro')
```

### Missing Backend

**Error:** `Backend 'xyz' not found`

**Solution:** Use a supported backend: `ollama`, `openai`, `watsonx`, `hf`, `litellm`

---

## Resources

- [Mellea 0.3.0 API Reference](./mellea-0.3.0-api-reference.md)
- [Backend Configuration](./backend-configuration.md)
- [Mellea GitHub Repository](https://github.com/ibm-granite/mellea)
