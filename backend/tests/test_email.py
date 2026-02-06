"""Tests for email service."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from mellea_api.core.config import Settings
from mellea_api.services.email import EmailService


@pytest.fixture
def temp_settings():
    """Create settings with a temporary data directory."""
    with TemporaryDirectory() as temp_dir:
        settings = Settings(
            data_dir=Path(temp_dir),
            smtp_enabled=True,
            smtp_host="localhost",
            smtp_port=587,
            smtp_username="test",
            smtp_password="testpass",
            smtp_use_tls=True,
            smtp_from_email="noreply@test.local",
            smtp_from_name="Test System",
        )
        settings.ensure_data_dirs()
        yield settings


@pytest.fixture
def disabled_settings():
    """Create settings with SMTP disabled."""
    with TemporaryDirectory() as temp_dir:
        settings = Settings(
            data_dir=Path(temp_dir),
            smtp_enabled=False,
        )
        settings.ensure_data_dirs()
        yield settings


@pytest.fixture
def email_service(temp_settings):
    """Create email service with test settings."""
    return EmailService(settings=temp_settings)


@pytest.fixture
def disabled_email_service(disabled_settings):
    """Create email service with SMTP disabled."""
    return EmailService(settings=disabled_settings)


class TestEmailService:
    """Tests for EmailService."""

    def test_email_disabled(self, disabled_email_service):
        """Test that emails are not sent when SMTP is disabled."""
        result = disabled_email_service._send_email(
            to_email="user@example.com",
            subject="Test",
            html_content="<p>Test</p>",
        )
        assert result is False

    @patch("mellea_api.services.email.smtplib.SMTP")
    def test_send_email_success(self, mock_smtp, email_service):
        """Test successful email sending."""
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = email_service._send_email(
            to_email="user@example.com",
            subject="Test Subject",
            html_content="<p>Hello</p>",
            text_content="Hello",
        )

        assert result is True
        mock_smtp.assert_called_once_with("localhost", 587)

    @patch("mellea_api.services.email.smtplib.SMTP")
    def test_send_email_with_tls(self, mock_smtp, email_service):
        """Test email uses TLS when configured."""
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)

        email_service._send_email(
            to_email="user@example.com",
            subject="Test",
            html_content="<p>Test</p>",
        )

        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("test", "testpass")

    @patch("mellea_api.services.email.smtplib.SMTP")
    def test_send_email_failure(self, mock_smtp, email_service):
        """Test email sending failure handling."""
        import smtplib

        mock_smtp.return_value.__enter__ = MagicMock(
            side_effect=smtplib.SMTPException("Connection failed")
        )
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = email_service._send_email(
            to_email="user@example.com",
            subject="Test",
            html_content="<p>Test</p>",
        )

        assert result is False


class TestRunCompletedEmail:
    """Tests for run completion emails."""

    @pytest.mark.asyncio
    @patch("mellea_api.services.email.smtplib.SMTP")
    async def test_send_run_completed_email_succeeded(self, mock_smtp, email_service):
        """Test sending successful run completion email."""
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = await email_service.send_run_completed_email(
            to_email="user@example.com",
            to_name="John Doe",
            run_id="run-12345678",
            program_name="My Test Program",
            status="succeeded",
            duration_seconds=125.5,
            action_url="https://mellea.local/runs/run-12345678",
        )

        assert result is True
        mock_instance.sendmail.assert_called_once()

        # Check email content
        call_args = mock_instance.sendmail.call_args
        email_body = call_args[0][2]  # Third arg is the message
        assert "Run Succeeded" in email_body
        assert "My Test Program" in email_body
        assert "John Doe" in email_body

    @pytest.mark.asyncio
    @patch("mellea_api.services.email.smtplib.SMTP")
    async def test_send_run_completed_email_failed(self, mock_smtp, email_service):
        """Test sending failed run completion email."""
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        result = await email_service.send_run_completed_email(
            to_email="user@example.com",
            to_name="Jane Doe",
            run_id="run-87654321",
            program_name="Failing Program",
            status="failed",
            error_message="Out of memory",
            action_url="https://mellea.local/runs/run-87654321",
        )

        assert result is True
        call_args = mock_instance.sendmail.call_args
        email_body = call_args[0][2]
        assert "Run Failed" in email_body
        assert "Out of memory" in email_body

    @pytest.mark.asyncio
    @patch("mellea_api.services.email.smtplib.SMTP")
    async def test_send_run_completed_email_with_duration(self, mock_smtp, email_service):
        """Test email includes duration when provided."""
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        await email_service.send_run_completed_email(
            to_email="user@example.com",
            to_name="Test User",
            run_id="run-123",
            program_name="Test",
            status="succeeded",
            duration_seconds=90,
        )

        call_args = mock_instance.sendmail.call_args
        email_body = call_args[0][2]
        assert "1m 30s" in email_body

    @pytest.mark.asyncio
    async def test_send_run_completed_email_disabled(self, disabled_email_service):
        """Test no email sent when SMTP disabled."""
        result = await disabled_email_service.send_run_completed_email(
            to_email="user@example.com",
            to_name="Test User",
            run_id="run-123",
            program_name="Test",
            status="succeeded",
        )

        assert result is False


class TestEmailFormatting:
    """Tests for email content formatting."""

    @pytest.mark.asyncio
    @patch("mellea_api.services.email.smtplib.SMTP")
    async def test_email_subject_format(self, mock_smtp, email_service):
        """Test email subject includes status emoji."""
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        await email_service.send_run_completed_email(
            to_email="user@example.com",
            to_name="Test",
            run_id="run-123",
            program_name="Test Program",
            status="succeeded",
        )

        call_args = mock_instance.sendmail.call_args
        email_body = call_args[0][2]
        # Check for success emoji in subject
        assert "Subject:" in email_body

    @pytest.mark.asyncio
    @patch("mellea_api.services.email.smtplib.SMTP")
    async def test_email_truncates_long_errors(self, mock_smtp, email_service):
        """Test that long error messages are truncated."""
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        long_error = "A" * 500

        await email_service.send_run_completed_email(
            to_email="user@example.com",
            to_name="Test",
            run_id="run-123",
            program_name="Test",
            status="failed",
            error_message=long_error,
        )

        call_args = mock_instance.sendmail.call_args
        email_body = call_args[0][2]
        # Error should be truncated to 200 chars
        assert "A" * 201 not in email_body
