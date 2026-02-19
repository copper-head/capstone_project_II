"""Gemini LLM client for calendar event extraction.

Wraps the Google ``google-genai`` SDK to extract structured calendar events
from conversation transcripts.  Handles prompt construction, API calls,
response parsing, validation, and a single retry on malformed responses.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from cal_ai.exceptions import ExtractionError, MalformedResponseError
from cal_ai.models.extraction import (
    ExtractionResult,
    LLMResponseSchema,
    ValidatedEvent,
)
from cal_ai.prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for extracting calendar events via Google Gemini.

    Wraps the ``google.genai.Client`` to call Gemini with structured JSON
    output and Pydantic-based parsing/validation.

    Args:
        api_key: Google Gemini API key.
        model: Model identifier to use for generation.  Defaults to
            ``"gemini-2.0-flash"``.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_events(
        self,
        transcript_text: str,
        owner_name: str,
        current_datetime: datetime,
        calendar_context: str = "",
    ) -> ExtractionResult:
        """Extract calendar events from a conversation transcript.

        Builds system and user prompts, calls the Gemini API with
        structured JSON output, then parses and validates the response.
        On a parse failure the call is retried **once**; a second failure
        returns a graceful empty result rather than raising.

        Args:
            transcript_text: The conversation transcript (plain text).
            owner_name: Display name of the calendar owner.
            current_datetime: The current date/time, used by the LLM to
                resolve relative time references.
            calendar_context: Pre-formatted calendar context text (from
                :func:`~cal_ai.calendar.context.fetch_calendar_context`).
                When non-empty, the LLM can match conversation references
                to existing calendar events for update/delete decisions.
                Defaults to ``""`` (no context).

        Returns:
            An :class:`ExtractionResult` with extracted events (possibly
            empty) and a human-readable summary.

        Raises:
            ExtractionError: If the Gemini API is unreachable or returns
                a non-recoverable error.
        """
        system_prompt = build_system_prompt(
            owner_name=owner_name,
            current_datetime=current_datetime.isoformat(),
            calendar_context=calendar_context,
        )
        user_prompt = build_user_prompt(transcript_text)

        logger.debug("System prompt sent to Gemini:\n%s", system_prompt)
        logger.debug("User prompt sent to Gemini:\n%s", user_prompt)

        config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=LLMResponseSchema,
        )

        # Attempt extraction with one retry on malformed responses.
        last_error: MalformedResponseError | None = None
        for attempt in range(1, 3):  # attempts 1 and 2
            raw_text = self._call_api(user_prompt, config)
            logger.debug("Raw LLM response (attempt %d):\n%s", attempt, raw_text)

            try:
                result = self._parse_response(raw_text)
            except MalformedResponseError as exc:
                last_error = exc
                if attempt == 1:
                    logger.warning(
                        "Malformed LLM response on attempt %d, retrying: %s",
                        attempt,
                        exc,
                    )
                    continue
                # Second failure -- fall through to graceful failure.
            else:
                # Successful parse.
                self._log_extraction(result)
                return result

        # Both attempts failed -- return graceful empty result.
        logger.error(
            "LLM response malformed after 2 attempts. "
            "Raw response: %s | Error: %s",
            last_error.raw_response if last_error else "<unknown>",
            last_error,
        )
        graceful = ExtractionResult(
            events=[],
            summary=(
                f"Extraction failed: LLM returned unparseable response "
                f"after 2 attempts. Error: {last_error}"
            ),
        )
        logger.info("Extraction summary: %s", graceful.summary)
        return graceful

    # ------------------------------------------------------------------
    # Validation helper
    # ------------------------------------------------------------------

    def validate_events(
        self,
        result: ExtractionResult,
        current_datetime: datetime,  # noqa: ARG002
    ) -> list[ValidatedEvent]:
        """Convert extracted events into validated events with parsed datetimes.

        Parses ISO 8601 strings into ``datetime`` objects and applies a
        1-hour default for missing end times.  Events that fail validation
        are logged and skipped rather than raising.

        Args:
            result: The raw extraction result from the LLM.
            current_datetime: Current datetime (reserved for future use).

        Returns:
            A list of :class:`ValidatedEvent` instances.
        """
        validated: list[ValidatedEvent] = []
        for event in result.events:
            try:
                validated.append(ValidatedEvent.from_extracted(event))
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Skipping event '%s': validation failed: %s",
                    event.title,
                    exc,
                )
        return validated

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_api(
        self,
        user_prompt: str,
        config: genai_types.GenerateContentConfig,
    ) -> str:
        """Call the Gemini API and return the raw response text.

        Args:
            user_prompt: The user-facing prompt content.
            config: Generation config including system instruction, schema,
                and response MIME type.

        Returns:
            The raw text content from the first candidate.

        Raises:
            ExtractionError: On API-level failures (network, auth, etc.).
        """
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=config,
            )
        except genai_errors.APIError as exc:
            logger.error("Gemini API error: %s", exc)
            raise ExtractionError(f"Gemini API call failed: {exc}") from exc

        return response.text or ""

    def _parse_response(self, raw_text: str) -> ExtractionResult:
        """Parse raw JSON text into an :class:`ExtractionResult`.

        Splits comma-separated ``attendees`` and ``assumptions`` strings
        into lists.  Optional fields (``end_time``, ``location``) are
        natively ``None`` from the LLM schema and require no conversion.

        Args:
            raw_text: The raw JSON string from the Gemini response.

        Returns:
            A validated :class:`ExtractionResult`.

        Raises:
            MalformedResponseError: If the JSON is invalid or does not
                conform to the expected schema.
        """
        if not raw_text or not raw_text.strip():
            raise MalformedResponseError(
                "Empty response from LLM", raw_response=raw_text or ""
            )

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise MalformedResponseError(
                f"Invalid JSON: {exc}", raw_response=raw_text
            ) from exc

        try:
            # Convert "none" sentinels and comma-separated strings.
            events_raw = data.get("events", [])
            converted_events = [self._convert_event(e) for e in events_raw]
            data["events"] = converted_events

            return ExtractionResult.model_validate(data)
        except Exception as exc:
            raise MalformedResponseError(
                f"Schema validation failed: {exc}", raw_response=raw_text
            ) from exc

    @staticmethod
    def _convert_event(event_data: dict) -> dict:
        """Convert a single event dict from LLM schema to internal schema.

        Splits comma-separated ``attendees`` and ``assumptions`` strings
        into Python lists.  Optional fields are already ``None`` from the
        LLM schema (no sentinel conversion needed).

        Args:
            event_data: A single event dictionary from the LLM response.

        Returns:
            The converted event dictionary ready for Pydantic validation.
        """
        result = dict(event_data)

        # Split comma-separated attendees into a list.
        attendees = result.get("attendees")
        if attendees is None or (isinstance(attendees, str) and not attendees.strip()):
            result["attendees"] = []
        elif isinstance(attendees, str):
            result["attendees"] = [
                name.strip() for name in attendees.split(",") if name.strip()
            ]

        # Split comma-separated assumptions into a list.
        assumptions = result.get("assumptions")
        if assumptions is None or (
            isinstance(assumptions, str) and not assumptions.strip()
        ):
            result["assumptions"] = []
        elif isinstance(assumptions, str):
            result["assumptions"] = [
                a.strip() for a in assumptions.split(",") if a.strip()
            ]

        return result

    def _log_extraction(self, result: ExtractionResult) -> None:
        """Log extraction results at appropriate levels.

        Each event's reasoning is logged at INFO (demo-visible).
        The overall summary is logged at INFO.

        Args:
            result: The parsed extraction result.
        """
        for event in result.events:
            logger.info(
                "Extracted event: '%s' | confidence=%s | reasoning: %s",
                event.title,
                event.confidence,
                event.reasoning,
            )
        logger.info("Extraction summary: %s", result.summary)
