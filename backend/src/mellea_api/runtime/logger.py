"""Node-level logging for composition execution.

This module provides utilities for generated composition code to emit
node-level logs that can be viewed in the builder UI.
"""

import os
from datetime import datetime
from typing import Any

import httpx

# Runtime configuration
_config: dict[str, Any] = {
    "run_id": None,
    "api_base_url": None,
    "enabled": True,
}


def configure_runtime(
    run_id: str | None = None,
    api_base_url: str | None = None,
    enabled: bool = True,
) -> None:
    """Configure the runtime logger.

    This is typically called at the start of composition execution to set up
    the logging context.

    Args:
        run_id: The composition run ID
        api_base_url: Base URL for the Mellea API (e.g., "http://localhost:8000/api/v1")
        enabled: Whether logging is enabled
    """
    _config["run_id"] = run_id or os.environ.get("MELLEA_RUN_ID")
    _config["api_base_url"] = api_base_url or os.environ.get(
        "MELLEA_API_URL", "http://localhost:8000/api/v1"
    )
    _config["enabled"] = enabled


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def log_node(node_id: str, message: str, include_timestamp: bool = True) -> None:
    """Log a message for a specific node.

    This sends the log message to the backend API where it's stored in the
    node's execution state and can be viewed in the builder UI.

    Args:
        node_id: The node ID to log to
        message: The log message
        include_timestamp: Whether to include a timestamp prefix
    """
    if not _config["enabled"]:
        return

    run_id = _config["run_id"]
    api_base_url = _config["api_base_url"]

    if not run_id or not api_base_url:
        # Fall back to printing if not configured
        print(f"[{node_id}] {message}")
        return

    try:
        timestamp = _get_timestamp() if include_timestamp else None
        with httpx.Client(timeout=5.0) as client:
            client.post(
                f"{api_base_url}/composition-runs/{run_id}/nodes/{node_id}/logs",
                json={"message": message, "timestamp": timestamp},
            )
    except Exception as e:
        # Don't let logging failures break execution
        print(f"[LOG ERROR] Failed to log to node {node_id}: {e}")
        print(f"[{node_id}] {message}")


class NodeLogger:
    """Logger instance for a specific node.

    Provides a convenient way to log messages for a single node without
    having to pass the node_id on every call.

    Example:
        ```python
        logger = NodeLogger("node-1")
        logger.info("Starting execution")
        logger.debug("Processing item: %s", item)
        logger.error("Failed to process: %s", error)
        ```
    """

    def __init__(self, node_id: str) -> None:
        """Initialize the node logger.

        Args:
            node_id: The node ID this logger is for
        """
        self.node_id = node_id

    def _log(self, level: str, message: str, *args: Any) -> None:
        """Log a message with the given level."""
        if args:
            message = message % args
        formatted = f"[{level.upper()}] {message}"
        log_node(self.node_id, formatted)

    def debug(self, message: str, *args: Any) -> None:
        """Log a debug message."""
        self._log("DEBUG", message, *args)

    def info(self, message: str, *args: Any) -> None:
        """Log an info message."""
        self._log("INFO", message, *args)

    def warning(self, message: str, *args: Any) -> None:
        """Log a warning message."""
        self._log("WARN", message, *args)

    def error(self, message: str, *args: Any) -> None:
        """Log an error message."""
        self._log("ERROR", message, *args)

    def log(self, message: str, *args: Any) -> None:
        """Log a message without level prefix."""
        if args:
            message = message % args
        log_node(self.node_id, message)


def get_node_logger(node_id: str) -> NodeLogger:
    """Get a logger instance for a specific node.

    Args:
        node_id: The node ID to create a logger for

    Returns:
        NodeLogger instance for the specified node
    """
    return NodeLogger(node_id)
