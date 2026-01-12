# Mellea API Backend

FastAPI backend service for the Mellea playground platform.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Running

```bash
uvicorn mellea_api.main:app --reload
```
