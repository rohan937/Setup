"""Abstract email provider interface (M84)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmailProvider(ABC):
    """A pluggable transport for sending transactional email."""

    @abstractmethod
    def send(self, to: str, subject: str, html: str, text: str) -> None:
        """Send an email. Implementations must not log secrets or tokens."""
        raise NotImplementedError
