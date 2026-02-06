"""Pytest configuration for mellea-playground tests."""


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "live_backend: marks tests that require a live LLM backend (Ollama)",
    )
