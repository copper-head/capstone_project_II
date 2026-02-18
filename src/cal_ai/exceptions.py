"""Custom exceptions for the cal-ai extraction pipeline.

These exceptions provide structured error handling for LLM response parsing
and event extraction failures.
"""

from __future__ import annotations


class MalformedResponseError(Exception):
    """Raised when the LLM response cannot be parsed or validated.

    This covers JSON parse failures and Pydantic schema validation errors.
    The caller (GeminiClient) catches this to trigger a retry before
    falling back to a graceful empty result.

    Attributes:
        raw_response: The raw LLM output that failed to parse.
    """

    def __init__(self, message: str, raw_response: str = "") -> None:
        super().__init__(message)
        self.raw_response = raw_response


class ExtractionError(Exception):
    """Raised for unrecoverable extraction failures.

    This covers scenarios where the extraction pipeline cannot produce
    a result at all (e.g., API connectivity errors, authentication failures).
    Unlike :class:`MalformedResponseError`, retrying is not expected to help.
    """
