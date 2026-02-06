"""Email service for sending notifications via SMTP."""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from mellea_api.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications.

    Provides methods to send emails via SMTP for run completion notifications.

    Example:
        ```python
        service = get_email_service()

        # Send a run completion email
        await service.send_run_completed_email(
            to_email="user@example.com",
            to_name="John Doe",
            run_id="run-123",
            program_name="My Program",
            status="succeeded",
        )
        ```
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the EmailService.

        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()

    def _create_smtp_connection(self) -> smtplib.SMTP:
        """Create and configure an SMTP connection.

        Returns:
            Configured SMTP connection

        Raises:
            smtplib.SMTPException: If connection fails
        """
        smtp = smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port)

        if self.settings.smtp_use_tls:
            smtp.starttls()

        if self.settings.smtp_username and self.settings.smtp_password:
            smtp.login(self.settings.smtp_username, self.settings.smtp_password)

        return smtp

    def _send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> bool:
        """Send an email synchronously.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML body content
            text_content: Plain text body (optional)

        Returns:
            True if email was sent successfully
        """
        if not self.settings.smtp_enabled:
            logger.debug("SMTP is disabled, skipping email to %s", to_email)
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.settings.smtp_from_name} <{self.settings.smtp_from_email}>"
        msg["To"] = to_email

        if text_content:
            msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        try:
            with self._create_smtp_connection() as smtp:
                smtp.sendmail(self.settings.smtp_from_email, [to_email], msg.as_string())
            logger.info("Email sent to %s: %s", to_email, subject)
            return True
        except smtplib.SMTPException as e:
            logger.error("Failed to send email to %s: %s", to_email, e)
            return False

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> bool:
        """Send an email asynchronously.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML body content
            text_content: Plain text body (optional)

        Returns:
            True if email was sent successfully
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._send_email, to_email, subject, html_content, text_content
        )

    async def send_run_completed_email(
        self,
        to_email: str,
        to_name: str,
        run_id: str,
        program_name: str,
        status: str,
        duration_seconds: float | None = None,
        error_message: str | None = None,
        action_url: str | None = None,
    ) -> bool:
        """Send a run completion notification email.

        Args:
            to_email: Recipient email address
            to_name: Recipient display name
            run_id: ID of the completed run
            program_name: Name of the program that was run
            status: Final status (succeeded, failed, cancelled)
            duration_seconds: How long the run took
            error_message: Error message if run failed
            action_url: URL to view the run details

        Returns:
            True if email was sent successfully
        """
        status_emoji = {"succeeded": "✅", "failed": "❌", "cancelled": "⏹️"}.get(
            status.lower(), "📋"
        )
        status_color = {"succeeded": "#22c55e", "failed": "#ef4444", "cancelled": "#f59e0b"}.get(
            status.lower(), "#6b7280"
        )
        status_text = status.capitalize()

        duration_text = ""
        if duration_seconds is not None:
            minutes = int(duration_seconds // 60)
            seconds = int(duration_seconds % 60)
            duration_text = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

        subject = f"{status_emoji} Run {status_text}: {program_name}"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f3f4f6;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <tr>
            <td style="background-color: #ffffff; border-radius: 8px; padding: 32px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <h1 style="margin: 0 0 24px 0; font-size: 24px; color: #111827;">
                    {status_emoji} Run {status_text}
                </h1>

                <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px;">
                    Hi {to_name},
                </p>

                <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px;">
                    Your run for <strong>{program_name}</strong> has completed.
                </p>

                <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f9fafb; border-radius: 6px; padding: 16px; margin-bottom: 24px;">
                    <tr>
                        <td style="padding: 8px 0;">
                            <span style="color: #6b7280; font-size: 14px;">Status:</span>
                            <span style="color: {status_color}; font-weight: 600; font-size: 14px; margin-left: 8px;">{status_text}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0;">
                            <span style="color: #6b7280; font-size: 14px;">Run ID:</span>
                            <span style="color: #374151; font-family: monospace; font-size: 13px; margin-left: 8px;">{run_id[:8]}...</span>
                        </td>
                    </tr>
                    {"<tr><td style='padding: 8px 0;'><span style='color: #6b7280; font-size: 14px;'>Duration:</span><span style='color: #374151; font-size: 14px; margin-left: 8px;'>" + duration_text + "</span></td></tr>" if duration_text else ""}
                    {"<tr><td style='padding: 8px 0;'><span style='color: #ef4444; font-size: 14px;'>Error:</span><span style='color: #374151; font-size: 14px; margin-left: 8px;'>" + (error_message or "")[:200] + "</span></td></tr>" if error_message else ""}
                </table>

                {"<a href='" + action_url + "' style='display: inline-block; background-color: #2563eb; color: #ffffff; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500; font-size: 14px;'>View Run Details</a>" if action_url else ""}

                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 32px 0 16px 0;">

                <p style="margin: 0; color: #9ca3af; font-size: 12px;">
                    This is an automated notification from Mellea Playground.
                    You can manage your notification preferences in your account settings.
                </p>
            </td>
        </tr>
    </table>
</body>
</html>
"""

        text_content = f"""
Run {status_text}: {program_name}

Hi {to_name},

Your run for {program_name} has completed.

Status: {status_text}
Run ID: {run_id}
{"Duration: " + duration_text if duration_text else ""}
{"Error: " + (error_message or "")[:200] if error_message else ""}

{"View run details: " + action_url if action_url else ""}

---
This is an automated notification from Mellea Playground.
"""

        return await self.send_email(to_email, subject, html_content, text_content)


# Global service instance
_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    """Get the global EmailService instance."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


def reset_email_service() -> None:
    """Reset the global EmailService instance (for testing)."""
    global _email_service
    _email_service = None
