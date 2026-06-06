"""Console email provider (dev only) — prints email to stdout (M84)."""

from __future__ import annotations

from app.services.email.base import EmailProvider


class ConsoleEmailProvider(EmailProvider):
    """Prints emails to stdout for local development.

    Dev only — it is intentionally fine for links/tokens to appear here, since
    there is no real inbox in local development.
    """

    def send(self, to: str, subject: str, html: str, text: str) -> None:
        print(f"[email:console] to={to} subject={subject}")
        print(text)
