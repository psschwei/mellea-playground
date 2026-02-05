"""Mellea runtime module for composition execution.

This module provides utilities for the generated composition code to
interact with the Mellea backend during execution.

Key components:
- MelleaRuntime: Adapter for mellea 0.3.0 session-based API
- NodeLogger: Node-level logging for composition UI
- Compatibility shims: invoke_model(), run_program()
"""

from mellea_api.runtime.logger import NodeLogger, configure_runtime, get_node_logger, log_node
from mellea_api.runtime.mellea_runtime import (
    MelleaRuntime,
    MelleaRuntimeError,
    SessionNotInitializedError,
    SlotExecutionError,
    cleanup_runtime,
    get_runtime,
    invoke_model,
    run_program,
)

__all__ = [
    # Logging
    "NodeLogger",
    "get_node_logger",
    "log_node",
    "configure_runtime",
    # Runtime adapter
    "MelleaRuntime",
    "MelleaRuntimeError",
    "SessionNotInitializedError",
    "SlotExecutionError",
    # Convenience functions
    "get_runtime",
    "cleanup_runtime",
    # Compatibility shims
    "invoke_model",
    "run_program",
]
