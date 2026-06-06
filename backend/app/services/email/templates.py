"""Email templates for verification + password reset (M84).

Each builder returns a ``(subject, html, text)`` tuple.
"""

from __future__ import annotations

_BUTTON_STYLE = (
    "display:inline-block;padding:12px 24px;background:#2563eb;color:#ffffff;"
    "text-decoration:none;border-radius:6px;font-weight:600;"
    "font-family:Arial,Helvetica,sans-serif;"
)

_IGNORE_LINE = (
    "If you did not request this, you can safely ignore this email."
)


def _html_shell(greeting: str, intro: str, button_label: str, link: str,
                expire_hours: int) -> str:
    return f"""\
<div style="font-family:Arial,Helvetica,sans-serif;color:#111827;max-width:480px;">
  <p>{greeting}</p>
  <p>{intro}</p>
  <p>
    <a href="{link}" style="{_BUTTON_STYLE}">{button_label}</a>
  </p>
  <p style="color:#6b7280;font-size:13px;">Or paste this link: {link}</p>
  <p style="color:#6b7280;font-size:13px;">This link expires in {expire_hours} hours.</p>
  <p style="color:#6b7280;font-size:13px;">{_IGNORE_LINE}</p>
</div>"""


def _text_body(greeting: str, intro: str, link: str, expire_hours: int) -> str:
    return (
        f"{greeting}\n\n"
        f"{intro}\n\n"
        f"Or paste this link: {link}\n\n"
        f"This link expires in {expire_hours} hours.\n\n"
        f"{_IGNORE_LINE}\n"
    )


def verification_email(
    display_name: str, link: str, expire_hours: int
) -> tuple[str, str, str]:
    """Return ``(subject, html, text)`` for an email-verification message."""
    subject = "Verify your QuantFidelity email"
    greeting = f"Hi {display_name},"
    intro = "Please confirm your email address to finish setting up your account."
    html = _html_shell(greeting, intro, "Verify Email", link, expire_hours)
    text = _text_body(greeting, intro, link, expire_hours)
    return subject, html, text


def password_reset_email(
    display_name: str, link: str, expire_hours: int
) -> tuple[str, str, str]:
    """Return ``(subject, html, text)`` for a password-reset message."""
    subject = "Reset your QuantFidelity password"
    greeting = f"Hi {display_name},"
    intro = "We received a request to reset your password. Click below to choose a new one."
    html = _html_shell(greeting, intro, "Reset Password", link, expire_hours)
    text = _text_body(greeting, intro, link, expire_hours)
    return subject, html, text
