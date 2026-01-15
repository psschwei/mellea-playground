"""LogService for real-time log streaming via Redis pub/sub."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime

import redis.asyncio as redis

from mellea_api.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """A single log entry."""

    run_id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    is_complete: bool = False


class LogService:
    """Service for publishing and subscribing to run logs via Redis pub/sub.

    This service enables real-time log streaming by:
    - Publishing log updates to Redis channels when runs produce output
    - Allowing clients to subscribe to log streams for specific runs

    Channel naming convention: `run:{run_id}:logs`

    Example:
        ```python
        log_service = get_log_service()

        # Publish logs (called from RunExecutor)
        await log_service.publish_logs(run_id, "Hello, World!")

        # Subscribe to logs (for WebSocket streaming)
        async for entry in log_service.subscribe(run_id):
            print(entry.content)
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the LogService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._redis: redis.Redis | None = None
        self._pubsub_clients: dict[str, redis.client.PubSub] = {}

    def _get_channel_name(self, run_id: str) -> str:
        """Get the Redis channel name for a run's logs.

        Args:
            run_id: The run ID

        Returns:
            Channel name in format `run:{run_id}:logs`
        """
        return f"run:{run_id}:logs"

    async def _get_redis(self) -> redis.Redis:
        """Get or create the Redis connection.

        Returns:
            Redis client instance
        """
        if self._redis is None:
            self._redis = redis.from_url(
                self.settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def publish_logs(
        self,
        run_id: str,
        content: str,
        is_complete: bool = False,
    ) -> int:
        """Publish log content to a run's log channel.

        Args:
            run_id: The run ID to publish logs for
            content: The log content to publish
            is_complete: Whether this is the final log message

        Returns:
            Number of subscribers that received the message
        """
        try:
            client = await self._get_redis()
            channel = self._get_channel_name(run_id)

            # Create message payload
            message = {
                "run_id": run_id,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
                "is_complete": is_complete,
            }

            # Publish as JSON string
            import json

            payload = json.dumps(message)
            subscriber_count = await client.publish(channel, payload)

            logger.debug(
                "Published logs for run %s to %d subscribers (complete=%s)",
                run_id,
                subscriber_count,
                is_complete,
            )

            return subscriber_count
        except Exception as e:
            logger.error("Failed to publish logs for run %s: %s", run_id, e)
            return 0

    async def subscribe(
        self,
        run_id: str,
        timeout: float = 0.1,
    ) -> AsyncGenerator[LogEntry, None]:
        """Subscribe to log updates for a specific run.

        This is an async generator that yields LogEntry objects as they
        are published. Use this for WebSocket streaming.

        Args:
            run_id: The run ID to subscribe to
            timeout: Timeout in seconds for each poll iteration

        Yields:
            LogEntry objects as logs are published
        """
        import json

        client = await self._get_redis()
        pubsub = client.pubsub()
        channel = self._get_channel_name(run_id)

        try:
            await pubsub.subscribe(channel)
            logger.debug("Subscribed to logs for run %s", run_id)

            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=timeout,
                )

                if message is not None and message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        entry = LogEntry(
                            run_id=data["run_id"],
                            content=data["content"],
                            timestamp=datetime.fromisoformat(data["timestamp"]),
                            is_complete=data.get("is_complete", False),
                        )
                        yield entry

                        # Stop if this is the final message
                        if entry.is_complete:
                            logger.debug(
                                "Received completion signal for run %s", run_id
                            )
                            break
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(
                            "Failed to parse log message for run %s: %s", run_id, e
                        )

                # Small sleep to prevent tight loop
                await asyncio.sleep(0.01)

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            logger.debug("Unsubscribed from logs for run %s", run_id)

    def publish_logs_sync(
        self,
        run_id: str,
        content: str,
        is_complete: bool = False,
    ) -> None:
        """Synchronous wrapper to publish logs (fire-and-forget).

        This schedules the async publish as a background task.
        Use this from synchronous code paths.

        Args:
            run_id: The run ID to publish logs for
            content: The log content to publish
            is_complete: Whether this is the final log message
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule as background task
                asyncio.create_task(
                    self.publish_logs(run_id, content, is_complete)
                )
            else:
                # Run synchronously if no event loop
                loop.run_until_complete(
                    self.publish_logs(run_id, content, is_complete)
                )
        except RuntimeError:
            # No event loop available - skip publishing
            logger.warning(
                "No event loop available for publishing logs for run %s", run_id
            )

    async def close(self) -> None:
        """Close Redis connections."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
            logger.debug("LogService Redis connection closed")


# Global service instance
_log_service: LogService | None = None


def get_log_service() -> LogService:
    """Get the global LogService instance."""
    global _log_service
    if _log_service is None:
        _log_service = LogService()
    return _log_service


def reset_log_service() -> None:
    """Reset the global LogService instance (for testing)."""
    global _log_service
    _log_service = None
