"""Email package (M84): provider selection + high-level send helpers.

SECURITY: raw tokens are embedded only in the action link passed to a provider.
They are never logged here. In dev the ConsoleEmailProvider prints the link by
design (there is no real inbox locally).
"""

from __future__ import annotations

import sys

from app.services.email import templates
from app.services.email.base import EmailProvider
from app.services.email.console import ConsoleEmailProvider
from app.services.email.resend import ResendEmailProvider

__all__ = [
    "EmailProvider",
    "ConsoleEmailProvider",
    "ResendEmailProvider",
    "get_email_provider",
    "send_verification_email",
    "send_password_reset_email",
]


def get_email_provider(settings) -> EmailProvider:
    """Return the configured email provider.

    Uses Resend when ``email_provider == 'resend'`` and an API key is set;
    otherwise falls back to the console provider. If Resend is requested but no
    key is configured, prints a one-line warning to stderr and falls back.
    """
    if settings.email_provider == "resend":
        if settings.resend_api_key:
            return ResendEmailProvider(
                api_key=settings.resend_api_key,
                default_from=settings.email_from,
            )
        print(
            "[email] QF_EMAIL_PROVIDER=resend but QF_RESEND_API_KEY is empty; "
            "falling back to console provider.",
            file=sys.stderr,
        )
    return ConsoleEmailProvider()


def send_verification_email(settings, user, raw_token: str) -> None:
    """Send an email-verification message to *user* with *raw_token*."""
    link = f"{settings.email_link_base}/verify-email?token={raw_token}"
    subject, html, text = templates.verification_email(
        user.display_name, link, settings.email_verification_expire_hours
    )
    get_email_provider(settings).send(user.email, subject, html, text)


def send_password_reset_email(settings, user, raw_token: str) -> None:
    """Send a password-reset message to *user* with *raw_token*."""
    link = f"{settings.email_link_base}/reset-password?token={raw_token}"
    subject, html, text = templates.password_reset_email(
        user.display_name, link, settings.password_reset_expire_hours
    )
    get_email_provider(settings).send(user.email, subject, html, text)
