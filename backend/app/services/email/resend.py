"""Resend email provider (M84).

Sends transactional email via the Resend HTTP API. The API key and any token in
the email body are NEVER logged.
"""

from __future__ import annotations

import httpx

from app.services.email.base import EmailProvider

_RESEND_ENDPOINT = "https://api.resend.com/emails"


class ResendEmailProvider(EmailProvider):
    """Sends email through Resend's REST API."""

    def __init__(self, api_key: str, default_from: str) -> None:
        self._api_key = api_key
        self._default_from = default_from

    def send(self, to: str, subject: str, html: str, text: str) -> None:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                _RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "from": self._default_from,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
            )
        if not (200 <= resp.status_code < 300):
            # Note: resp.text is the Resend API error body and never contains
            # our outbound api key. The key is only ever sent in the header.
            raise RuntimeError(
                f"Resend send failed: {resp.status_code} {resp.text}"
            )
