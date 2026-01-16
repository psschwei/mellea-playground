"""Tests for QuotaService."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from mellea_api.models.common import RunExecutionStatus
from mellea_api.models.user import UserQuotas
from mellea_api.services.quota import (
    QuotaExceededError,
    QuotaService,
    QuotaUsage,
)


@pytest.fixture
def mock_settings(tmp_path):
    """Create mock settings with a temporary data directory."""
    settings = MagicMock()
    settings.data_dir = tmp_path
    (tmp_path / "metadata").mkdir(parents=True, exist_ok=True)
    return settings


@pytest.fixture
def quota_service(mock_settings):
    """Create a QuotaService with mock settings."""
    return QuotaService(settings=mock_settings)


@pytest.fixture
def user_quotas():
    """Create default user quotas."""
    return UserQuotas(
        max_concurrent_runs=3,
        max_runs_per_day=50,
        max_cpu_hours_per_month=100,
        max_storage_mb=5000,
    )


@pytest.fixture
def mock_run_service():
    """Create a mock RunService."""
    return MagicMock()


class TestQuotaUsageModel:
    """Tests for the QuotaUsage model."""

    def test_quota_usage_defaults(self):
        """Test QuotaUsage has correct defaults."""
        usage = QuotaUsage(user_id="user-123")

        assert usage.user_id == "user-123"
        assert usage.id == "user-123"  # Auto-set from user_id
        assert usage.runs_today == 0
        assert usage.cpu_hours_month == 0.0

    def test_quota_usage_id_matches_user_id(self):
        """Test that id is automatically set to user_id."""
        usage = QuotaUsage(user_id="test-user")
        assert usage.id == "test-user"


class TestGetUserUsage:
    """Tests for getting user quota usage."""

    def test_get_user_usage_new_user(self, quota_service):
        """Test getting usage for a new user returns zeros."""
        usage = quota_service.get_user_usage("new-user")

        assert usage.user_id == "new-user"
        assert usage.runs_today == 0
        assert usage.cpu_hours_month == 0.0

    def test_get_user_usage_resets_daily_counter(self, quota_service):
        """Test that daily counter resets when date changes."""
        # Create usage from yesterday
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        old_usage = QuotaUsage(
            user_id="user-123",
            runs_today=10,
            runs_today_date=yesterday,
        )
        quota_service._save_usage(old_usage)

        # Get usage - should reset daily counter
        usage = quota_service.get_user_usage("user-123")

        assert usage.runs_today == 0
        assert usage.runs_today_date == quota_service._get_today_key()

    def test_get_user_usage_resets_monthly_counter(self, quota_service):
        """Test that monthly counter resets when month changes."""
        # Create usage from last month
        old_usage = QuotaUsage(
            user_id="user-123",
            cpu_hours_month=50.0,
            cpu_hours_month_key="2020-01",  # Old month
        )
        quota_service._save_usage(old_usage)

        # Get usage - should reset monthly counter
        usage = quota_service.get_user_usage("user-123")

        assert usage.cpu_hours_month == 0.0
        assert usage.cpu_hours_month_key == quota_service._get_month_key()


class TestConcurrentRunsCheck:
    """Tests for concurrent runs quota check."""

    def test_check_concurrent_runs_under_limit(
        self, quota_service, user_quotas, mock_run_service
    ):
        """Test that check passes when under concurrent limit."""
        # Mock 2 active runs (limit is 3)
        mock_run_service.list_runs.return_value = [
            MagicMock(status=RunExecutionStatus.RUNNING),
            MagicMock(status=RunExecutionStatus.QUEUED),
        ]

        # Should not raise
        quota_service.check_concurrent_runs("user-123", user_quotas, mock_run_service)

    def test_check_concurrent_runs_at_limit(
        self, quota_service, user_quotas, mock_run_service
    ):
        """Test that check fails when at concurrent limit."""
        # Mock 3 active runs (limit is 3)
        mock_run_service.list_runs.return_value = [
            MagicMock(status=RunExecutionStatus.RUNNING),
            MagicMock(status=RunExecutionStatus.QUEUED),
            MagicMock(status=RunExecutionStatus.STARTING),
        ]

        with pytest.raises(QuotaExceededError) as exc_info:
            quota_service.check_concurrent_runs("user-123", user_quotas, mock_run_service)

        assert exc_info.value.quota_type == "concurrent_runs"
        assert exc_info.value.current == 3
        assert exc_info.value.limit == 3

    def test_check_concurrent_runs_ignores_completed(
        self, quota_service, user_quotas, mock_run_service
    ):
        """Test that completed runs don't count toward concurrent limit."""
        mock_run_service.list_runs.return_value = [
            MagicMock(status=RunExecutionStatus.RUNNING),
            MagicMock(status=RunExecutionStatus.SUCCEEDED),  # Completed
            MagicMock(status=RunExecutionStatus.FAILED),  # Completed
        ]

        # Should not raise (only 1 active run)
        quota_service.check_concurrent_runs("user-123", user_quotas, mock_run_service)


class TestDailyRunsCheck:
    """Tests for daily runs quota check."""

    def test_check_daily_runs_under_limit(self, quota_service, user_quotas):
        """Test that check passes when under daily limit."""
        # Record 49 runs (limit is 50)
        for _ in range(49):
            quota_service.record_run_created("user-123")

        # Should not raise
        quota_service.check_daily_runs("user-123", user_quotas)

    def test_check_daily_runs_at_limit(self, quota_service, user_quotas):
        """Test that check fails when at daily limit."""
        # Record 50 runs (limit is 50)
        for _ in range(50):
            quota_service.record_run_created("user-123")

        with pytest.raises(QuotaExceededError) as exc_info:
            quota_service.check_daily_runs("user-123", user_quotas)

        assert exc_info.value.quota_type == "daily_runs"
        assert exc_info.value.current == 50
        assert exc_info.value.limit == 50


class TestMonthlyCpuHoursCheck:
    """Tests for monthly CPU hours quota check."""

    def test_check_monthly_cpu_hours_under_limit(self, quota_service, user_quotas):
        """Test that check passes when under CPU hours limit."""
        # Record 99 CPU hours (limit is 100)
        quota_service.record_cpu_hours("user-123", 99.0)

        # Should not raise
        quota_service.check_monthly_cpu_hours("user-123", user_quotas)

    def test_check_monthly_cpu_hours_over_limit(self, quota_service, user_quotas):
        """Test that check fails when over CPU hours limit."""
        # Record 101 CPU hours (limit is 100)
        quota_service.record_cpu_hours("user-123", 101.0)

        with pytest.raises(QuotaExceededError) as exc_info:
            quota_service.check_monthly_cpu_hours("user-123", user_quotas)

        assert exc_info.value.quota_type == "cpu_hours"
        assert exc_info.value.current == 101.0
        assert exc_info.value.limit == 100.0

    def test_check_monthly_cpu_hours_with_requested(self, quota_service, user_quotas):
        """Test that requested hours are considered in the check."""
        # Record 95 CPU hours
        quota_service.record_cpu_hours("user-123", 95.0)

        # Request 10 more hours would exceed limit
        with pytest.raises(QuotaExceededError):
            quota_service.check_monthly_cpu_hours(
                "user-123", user_quotas, requested_hours=10.0
            )


class TestCheckCanCreateRun:
    """Tests for the combined quota check."""

    def test_check_can_create_run_passes(
        self, quota_service, user_quotas, mock_run_service
    ):
        """Test that all checks pass for a new user."""
        mock_run_service.list_runs.return_value = []

        # Should not raise
        quota_service.check_can_create_run("user-123", user_quotas, mock_run_service)

    def test_check_can_create_run_fails_concurrent(
        self, quota_service, user_quotas, mock_run_service
    ):
        """Test that check fails when concurrent limit exceeded."""
        mock_run_service.list_runs.return_value = [
            MagicMock(status=RunExecutionStatus.RUNNING),
            MagicMock(status=RunExecutionStatus.RUNNING),
            MagicMock(status=RunExecutionStatus.RUNNING),
        ]

        with pytest.raises(QuotaExceededError) as exc_info:
            quota_service.check_can_create_run("user-123", user_quotas, mock_run_service)

        assert exc_info.value.quota_type == "concurrent_runs"


class TestRecordRunCreated:
    """Tests for recording run creation."""

    def test_record_run_created_increments_counter(self, quota_service):
        """Test that recording a run increments the daily counter."""
        quota_service.record_run_created("user-123")
        usage = quota_service.get_user_usage("user-123")
        assert usage.runs_today == 1

        quota_service.record_run_created("user-123")
        usage = quota_service.get_user_usage("user-123")
        assert usage.runs_today == 2


class TestRecordCpuHours:
    """Tests for recording CPU hours."""

    def test_record_cpu_hours_adds_to_total(self, quota_service):
        """Test that recording CPU hours adds to the monthly total."""
        quota_service.record_cpu_hours("user-123", 1.5)
        usage = quota_service.get_user_usage("user-123")
        assert usage.cpu_hours_month == 1.5

        quota_service.record_cpu_hours("user-123", 2.5)
        usage = quota_service.get_user_usage("user-123")
        assert usage.cpu_hours_month == 4.0


class TestCalculateCpuHours:
    """Tests for CPU hours calculation."""

    def test_calculate_cpu_hours_basic(self, quota_service):
        """Test basic CPU hours calculation."""
        start = datetime.utcnow()
        end = start + timedelta(hours=2)

        hours = quota_service.calculate_cpu_hours(start, end, cpu_cores=1.0)

        assert abs(hours - 2.0) < 0.01

    def test_calculate_cpu_hours_multiple_cores(self, quota_service):
        """Test CPU hours calculation with multiple cores."""
        start = datetime.utcnow()
        end = start + timedelta(hours=1)

        hours = quota_service.calculate_cpu_hours(start, end, cpu_cores=4.0)

        assert abs(hours - 4.0) < 0.01

    def test_calculate_cpu_hours_none_times(self, quota_service):
        """Test that None times return 0 hours."""
        hours = quota_service.calculate_cpu_hours(None, None)
        assert hours == 0.0


class TestGetQuotaStatus:
    """Tests for getting quota status."""

    def test_get_quota_status_returns_all_quotas(
        self, quota_service, user_quotas, mock_run_service
    ):
        """Test that quota status includes all quota types."""
        mock_run_service.list_runs.return_value = [
            MagicMock(status=RunExecutionStatus.RUNNING),
        ]
        quota_service.record_run_created("user-123")
        quota_service.record_cpu_hours("user-123", 10.0)

        status = quota_service.get_quota_status("user-123", user_quotas, mock_run_service)

        assert "concurrent_runs" in status
        assert status["concurrent_runs"]["current"] == 1
        assert status["concurrent_runs"]["limit"] == 3
        assert status["concurrent_runs"]["remaining"] == 2

        assert "daily_runs" in status
        assert status["daily_runs"]["current"] == 1
        assert status["daily_runs"]["limit"] == 50

        assert "cpu_hours_month" in status
        assert status["cpu_hours_month"]["current"] == 10.0
        assert status["cpu_hours_month"]["limit"] == 100

        assert "storage_mb" in status
        assert status["storage_mb"]["limit"] == 5000
