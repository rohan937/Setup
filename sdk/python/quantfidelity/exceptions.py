"""Exception classes for the QuantFidelity Python SDK.

Hierarchy:
  QuantFidelityError
  ├── QuantFidelityConnectionError  — cannot reach the server
  ├── QuantFidelityAPIError         — server returned a non-2xx response
  └── QuantFidelityValidationError  — client-side validation failure
"""
from __future__ import annotations


class QuantFidelityError(Exception):
    """Base exception for all QuantFidelity SDK errors."""


class QuantFidelityConnectionError(QuantFidelityError):
    """Raised when the SDK cannot reach the QuantFidelity server.

    This wraps network-level errors (connection refused, DNS failure, timeout).
    """


class QuantFidelityAPIError(QuantFidelityError):
    """Raised when the QuantFidelity API returns a non-2xx HTTP status code.

    Attributes
    ----------
    status_code:
        The HTTP status code returned by the API (e.g. 400, 404, 422, 500).
    response_text:
        The raw response body as a string.
    response_json:
        Parsed JSON body, or None if the response was not valid JSON.
    """

    def __init__(
        self,
        status_code: int,
        response_text: str,
        response_json: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.response_text = response_text
        self.response_json = response_json
        # Extract a readable message from the response if possible
        detail = ""
        if response_json and isinstance(response_json.get("detail"), str):
            detail = response_json["detail"]
        elif response_json and isinstance(response_json.get("detail"), list):
            detail = "; ".join(
                e.get("msg", str(e)) for e in response_json["detail"]
            )
        else:
            detail = response_text[:200]
        super().__init__(f"API error {status_code}: {detail}")


class QuantFidelityValidationError(QuantFidelityError):
    """Raised for client-side payload validation errors.

    The backend is always the source of truth; this class catches obvious
    mistakes (wrong types, empty required lists) before an HTTP round-trip.
    """
