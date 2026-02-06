# Backend Configuration Guide

This guide explains how to configure LLM backends for mellea 0.3.0 programs in the playground.

## Supported Backends

| Backend | Description | Model Examples |
|---------|-------------|----------------|
| `ollama` | Local inference via Ollama | `granite4:micro`, `llama3.2:3b` |
| `openai` | OpenAI API | `gpt-4o`, `gpt-5.1` |
| `watsonx` | IBM WatsonX | `ibm/granite-3-3-8b-instruct` |
| `hf` | HuggingFace Hub | `meta-llama/Llama-3.2-3B-Instruct` |
| `litellm` | Multi-provider proxy | Various |

---

## Ollama (Default)

Local inference using [Ollama](https://ollama.ai/).

### Setup

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull granite4:micro
```

### Usage

```python
from mellea import start_session

session = start_session(
    backend_name='ollama',
    model_id='granite4:micro'
)

response = session.chat("Hello!")
```

### Available Models

| Model ID | Size | Description |
|----------|------|-------------|
| `granite4:micro` | 3B | IBM Granite 4 Micro (default) |
| `granite3.3:8b` | 8B | IBM Granite 3.3 |
| `llama3.2:3b` | 3B | Meta Llama 3.2 |
| `llama3.3:70b` | 70B | Meta Llama 3.3 |
| `mistral-small:latest` | 24B | Mistral Small |
| `phi4:14b` | 14B | Microsoft Phi-4 |
| `qwen3:8b` | 8B | Qwen 3 |

---

## OpenAI

Cloud inference via OpenAI API.

### Setup

```bash
export OPENAI_API_KEY="your-api-key"
```

### Usage

```python
from mellea import start_session

session = start_session(
    backend_name='openai',
    model_id='gpt-4o',
    model_options={'temperature': 0.7}
)

response = session.chat("Hello!")
```

### Available Models

| Model ID | Description |
|----------|-------------|
| `gpt-4o` | GPT-4 Omni |
| `gpt-5.1` | GPT-5.1 |
| `gpt-oss:20b` | GPT OSS 20B |
| `gpt-oss:120b` | GPT OSS 120B |

---

## IBM WatsonX

Enterprise AI via IBM WatsonX.

### Setup

```bash
export WATSONX_API_KEY="your-api-key"
export WATSONX_PROJECT_ID="your-project-id"
export WATSONX_URL="https://us-south.ml.cloud.ibm.com"
```

### Usage

```python
from mellea import start_session

session = start_session(
    backend_name='watsonx',
    model_id='ibm/granite-3-3-8b-instruct'
)

response = session.chat("Hello!")
```

### Available Models

| Model ID | Description |
|----------|-------------|
| `ibm/granite-3-3-8b-instruct` | IBM Granite 3.3 8B |
| `ibm/granite-4-micro-3b-instruct` | IBM Granite 4 Micro |
| `meta-llama/llama-3-2-3b-instruct` | Llama 3.2 3B |

---

## HuggingFace

Inference via HuggingFace Hub.

### Setup

```bash
export HF_TOKEN="your-token"
```

### Usage

```python
from mellea import start_session

session = start_session(
    backend_name='hf',
    model_id='meta-llama/Llama-3.2-3B-Instruct'
)

response = session.chat("Hello!")
```

---

## LiteLLM

Multi-provider proxy supporting 100+ models.

### Setup

Configure the underlying provider credentials as needed.

### Usage

```python
from mellea import start_session

session = start_session(
    backend_name='litellm',
    model_id='gpt-4o'  # Uses LiteLLM model routing
)

response = session.chat("Hello!")
```

---

## Model Options

All backends support common model options:

```python
model_options = {
    'temperature': 0.7,      # Sampling temperature (0.0-2.0)
    'max_tokens': 1024,       # Maximum output tokens
    'top_p': 0.9,             # Nucleus sampling
    'stop': ['\n\n'],         # Stop sequences
}

session = start_session(
    backend_name='ollama',
    model_id='granite4:micro',
    model_options=model_options
)
```

---

## Playground Environment Variables

When programs run in the playground, these environment variables configure the runtime:

| Variable | Description | Default |
|----------|-------------|---------|
| `MELLEA_BACKEND` | Backend name | `ollama` |
| `MELLEA_MODEL_ID` | Model identifier | `granite4:micro` |
| `MELLEA_MODEL_OPTIONS` | JSON options | `{}` |
| `MELLEA_RUN_ID` | Run correlation ID | - |

### Example Program

```python
"""Program that reads configuration from environment."""

import os
from mellea_api.runtime import MelleaRuntime

def main():
    # Runtime auto-configures from environment
    runtime = MelleaRuntime()

    print(f"Using backend: {runtime.backend}")
    print(f"Using model: {runtime.model_id}")

    response = runtime.chat("What is 2+2?")
    print(f"Response: {response}")

if __name__ == "__main__":
    main()
```

---

## Switching Models at Runtime

```python
from mellea_api.runtime import MelleaRuntime

runtime = MelleaRuntime(backend='ollama', model_id='granite4:micro')

# Chat with first model
response1 = runtime.chat("Hello!")

# Switch to different model
runtime.switch_model(model_id='llama3.2:3b')

# Chat with new model
response2 = runtime.chat("Hello again!")

runtime.cleanup()
```

---

## Troubleshooting

### Ollama Connection Refused

```
Error: Connection refused to localhost:11434
```

**Solution:** Start Ollama service:
```bash
ollama serve
```

### OpenAI Authentication Error

```
Error: Invalid API key
```

**Solution:** Set the `OPENAI_API_KEY` environment variable.

### Model Not Found

```
Error: Model 'xyz' not found
```

**Solution:** Pull the model first (Ollama) or verify the model ID.

---

## Resources

- [Mellea 0.3.0 API Reference](./mellea-0.3.0-api-reference.md)
- [Migration Guide](./migration-guide.md)
- [Ollama Documentation](https://ollama.ai/docs)
- [OpenAI API Reference](https://platform.openai.com/docs)
- [IBM WatsonX Documentation](https://www.ibm.com/products/watsonx-ai)
