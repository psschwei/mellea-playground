"""QuotaService for enforcing user resource quotas."""

import logging
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from mellea_api.core.config import Settings, get_settings
from mellea_api.core.store import JsonStore
from mellea_api.models.common import RunExecutionStatus
from mellea_api.models.user import UserQuotas

logger = logging.getLogger(__name__)


class QuotaUsage(BaseModel):
    """Tracks quota usage for a user.

    Attributes:
        id: Same as user_id, used for JsonStore lookup
        user_id: ID of the user
        runs_today: Number of runs created today
        runs_today_date: Date for which runs_today is tracked (YYYY-MM-DD)
        cpu_hours_month: CPU hours used this month
        cpu_hours_month_key: Month for which cpu_hours is tracked (YYYY-MM)
        last_updated: When this usage record was last updated
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default="")  # Set to user_id for JsonStore compatibility
    user_id: str = Field(validation_alias="userId", serialization_alias="userId")
    runs_today: int = Field(
        default=0, validation_alias="runsToday", serialization_alias="runsToday"
    )
    runs_today_date: str = Field(
        default="", validation_alias="runsTodayDate", serialization_alias="runsTodayDate"
    )
    cpu_hours_month: float = Field(
        default=0.0, validation_alias="cpuHoursMonth", serialization_alias="cpuHoursMonth"
    )
    cpu_hours_month_key: str = Field(
        default="", validation_alias="cpuHoursMonthKey", serialization_alias="cpuHoursMonthKey"
    )
    last_updated: datetime = Field(
        default_factory=datetime.utcnow,
        validation_alias="lastUpdated",
        serialization_alias="lastUpdated",
    )

    def __init__(self, **data):
        super().__init__(**data)
        # Ensure id matches user_id for JsonStore compatibility
        if not self.id and self.user_id:
            object.__setattr__(self, "id", self.user_id)


class QuotaExceededError(Exception):
    """Raised when a user's quota would be exceeded."""

    def __init__(self, message: str, quota_type: str, current: float, limit: float):
        super().__init__(message)
        self.quota_type = quota_type
        self.current = current
        self.limit = limit


class QuotaService:
    """Service for enforcing user resource quotas.

    Manages quota checks and usage tracking for:
    - Concurrent runs limit
    - Daily run limit
    - Monthly CPU hours limit

    Example:
        ```python
        service = get_quota_service()

        # Check if user can create a new run
        service.check_can_create_run(user_id, user.quotas, run_service)

        # Record CPU hours after run completion
        service.record_cpu_hours(user_id, cpu_hours=1.5)

        # Get current usage
        usage = service.get_user_usage(user_id)
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the QuotaService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._usage_store: JsonStore[QuotaUsage] | None = None

    @property
    def usage_store(self) -> JsonStore[QuotaUsage]:
        """Get the quota usage store, initializing if needed."""
        if self._usage_store is None:
            file_path = self.settings.data_dir / "metadata" / "quota_usage.json"
            self._usage_store = JsonStore[QuotaUsage](
                file_path=file_path,
                collection_key="usage",
                model_class=QuotaUsage,
            )
        return self._usage_store

    def _get_today_key(self) -> str:
        """Get today's date key in YYYY-MM-DD format."""
        return datetime.utcnow().strftime("%Y-%m-%d")

    def _get_month_key(self) -> str:
        """Get current month key in YYYY-MM format."""
        return datetime.utcnow().strftime("%Y-%m")

    def get_user_usage(self, user_id: str) -> QuotaUsage:
        """Get quota usage for a user.

        Resets counters if date/month has changed.

        Args:
            user_id: User's unique identifier

        Returns:
            QuotaUsage record (created with zeros if not found)
        """
        usage = self.usage_store.get_by_id(user_id)

        if usage is None:
            return QuotaUsage(
                user_id=user_id,
                runs_today_date=self._get_today_key(),
                cpu_hours_month_key=self._get_month_key(),
            )

        # Reset daily counter if date changed
        today = self._get_today_key()
        if usage.runs_today_date != today:
            usage.runs_today = 0
            usage.runs_today_date = today

        # Reset monthly counter if month changed
        month = self._get_month_key()
        if usage.cpu_hours_month_key != month:
            usage.cpu_hours_month = 0.0
            usage.cpu_hours_month_key = month

        return usage

    def _save_usage(self, usage: QuotaUsage) -> None:
        """Save or update usage record."""
        usage.last_updated = datetime.utcnow()
        existing = self.usage_store.get_by_id(usage.user_id)
        if existing:
            self.usage_store.update(usage.user_id, usage)
        else:
            self.usage_store.create(usage)

    def get_concurrent_runs_count(
        self, user_id: str, run_service: "RunService"  # noqa: F821
    ) -> int:
        """Get count of currently active runs for a user.

        Args:
            user_id: User's unique identifier
            run_service: RunService instance for querying runs

        Returns:
            Number of runs in non-terminal states
        """
        active_statuses = {
            RunExecutionStatus.QUEUED,
            RunExecutionStatus.STARTING,
            RunExecutionStatus.RUNNING,
        }
        all_runs = run_service.list_runs(owner_id=user_id)
        return sum(1 for r in all_runs if r.status in active_statuses)

    def check_concurrent_runs(
        self,
        user_id: str,
        user_quotas: UserQuotas,
        run_service: "RunService",  # noqa: F821
    ) -> None:
        """Check if user can create another concurrent run.

        Args:
            user_id: User's unique identifier
            user_quotas: User's quota limits
            run_service: RunService instance for querying runs

        Raises:
            QuotaExceededError: If concurrent run limit would be exceeded
        """
        current = self.get_concurrent_runs_count(user_id, run_service)
        limit = user_quotas.max_concurrent_runs

        if current >= limit:
            raise QuotaExceededError(
                f"Concurrent run limit reached. You have {current} active runs "
                f"(limit: {limit}). Wait for existing runs to complete.",
                quota_type="concurrent_runs",
                current=current,
                limit=limit,
            )

    def check_daily_runs(self, user_id: str, user_quotas: UserQuotas) -> None:
        """Check if user can create another run today.

        Args:
            user_id: User's unique identifier
            user_quotas: User's quota limits

        Raises:
            QuotaExceededError: If daily run limit would be exceeded
        """
        usage = self.get_user_usage(user_id)
        current = usage.runs_today
        limit = user_quotas.max_runs_per_day

        if current >= limit:
            raise QuotaExceededError(
                f"Daily run limit reached. You've created {current} runs today "
                f"(limit: {limit}). Try again tomorrow.",
                quota_type="daily_runs",
                current=current,
                limit=limit,
            )

    def check_monthly_cpu_hours(
        self, user_id: str, user_quotas: UserQuotas, requested_hours: float = 0.0
    ) -> None:
        """Check if user has CPU hours remaining this month.

        Args:
            user_id: User's unique identifier
            user_quotas: User's quota limits
            requested_hours: Additional hours being requested (for pre-check)

        Raises:
            QuotaExceededError: If monthly CPU hours would be exceeded
        """
        usage = self.get_user_usage(user_id)
        current = usage.cpu_hours_month
        limit = float(user_quotas.max_cpu_hours_per_month)

        if current + requested_hours > limit:
            raise QuotaExceededError(
                f"Monthly CPU hour limit reached. You've used {current:.2f} hours "
                f"(limit: {limit} hours). Quota resets next month.",
                quota_type="cpu_hours",
                current=current,
                limit=limit,
            )

    def check_can_create_run(
        self,
        user_id: str,
        user_quotas: UserQuotas,
        run_service: "RunService",  # noqa: F821
    ) -> None:
        """Check all quotas for creating a new run.

        Args:
            user_id: User's unique identifier
            user_quotas: User's quota limits
            run_service: RunService instance for querying runs

        Raises:
            QuotaExceededError: If any quota would be exceeded
        """
        self.check_concurrent_runs(user_id, user_quotas, run_service)
        self.check_daily_runs(user_id, user_quotas)
        self.check_monthly_cpu_hours(user_id, user_quotas)

    def record_run_created(self, user_id: str) -> None:
        """Record that a run was created (increment daily counter).

        Args:
            user_id: User's unique identifier
        """
        usage = self.get_user_usage(user_id)
        usage.runs_today += 1
        self._save_usage(usage)
        logger.debug(f"User {user_id} now has {usage.runs_today} runs today")

    def record_cpu_hours(self, user_id: str, cpu_hours: float) -> None:
        """Record CPU hours used by a completed run.

        Args:
            user_id: User's unique identifier
            cpu_hours: CPU hours to add
        """
        usage = self.get_user_usage(user_id)
        usage.cpu_hours_month += cpu_hours
        self._save_usage(usage)
        logger.debug(
            f"User {user_id} has used {usage.cpu_hours_month:.2f} CPU hours this month"
        )

    def calculate_cpu_hours(
        self, started_at: datetime, completed_at: datetime, cpu_cores: float = 1.0
    ) -> float:
        """Calculate CPU hours for a run.

        Args:
            started_at: When the run started
            completed_at: When the run completed
            cpu_cores: Number of CPU cores used (default 1.0)

        Returns:
            CPU hours (duration in hours * cpu_cores)
        """
        if started_at is None or completed_at is None:
            return 0.0

        duration = completed_at - started_at
        hours = duration.total_seconds() / 3600
        return hours * cpu_cores

    def get_quota_status(
        self,
        user_id: str,
        user_quotas: UserQuotas,
        run_service: "RunService",  # noqa: F821
    ) -> dict:
        """Get current quota status for a user.

        Args:
            user_id: User's unique identifier
            user_quotas: User's quota limits
            run_service: RunService instance for querying runs

        Returns:
            Dictionary with quota status including usage and limits
        """
        usage = self.get_user_usage(user_id)
        concurrent_runs = self.get_concurrent_runs_count(user_id, run_service)

        return {
            "concurrent_runs": {
                "current": concurrent_runs,
                "limit": user_quotas.max_concurrent_runs,
                "remaining": max(0, user_quotas.max_concurrent_runs - concurrent_runs),
            },
            "daily_runs": {
                "current": usage.runs_today,
                "limit": user_quotas.max_runs_per_day,
                "remaining": max(0, user_quotas.max_runs_per_day - usage.runs_today),
                "resets_at": usage.runs_today_date,
            },
            "cpu_hours_month": {
                "current": round(usage.cpu_hours_month, 2),
                "limit": user_quotas.max_cpu_hours_per_month,
                "remaining": round(
                    max(0, user_quotas.max_cpu_hours_per_month - usage.cpu_hours_month), 2
                ),
                "resets_at": usage.cpu_hours_month_key,
            },
            "storage_mb": {
                "limit": user_quotas.max_storage_mb,
            },
        }


# Global service instance
_quota_service: QuotaService | None = None


def get_quota_service() -> QuotaService:
    """Get the global QuotaService instance."""
    global _quota_service
    if _quota_service is None:
        _quota_service = QuotaService()
    return _quota_service
