"""Unit tests for GeminiClient (25 tests).

All tests use mocks -- no real Gemini API calls are made.  The tests cover
happy-path extraction, ambiguous events, owner perspective, relative time
resolution, malformed response handling, confidence levels, logging output,
API integration details, and edge cases.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from cal_ai.exceptions import ExtractionError
from cal_ai.llm import GeminiClient
from cal_ai.models.extraction import LLMResponseSchema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response_json(events: list[dict], summary: str = "Extraction complete.") -> str:
    """Build a JSON string mimicking the raw Gemini response.

    Uses the LLMResponseSchema convention: optional fields use ``null``
    (Python ``None``) when absent.
    """
    return json.dumps({"events": events, "summary": summary})


def _single_lunch_event() -> dict:
    """Return a single valid LLM-response event dict (Optional schema)."""
    return {
        "title": "Lunch with Bob",
        "start_time": "2026-02-19T12:00:00",
        "end_time": "2026-02-19T13:00:00",
        "location": "Cafe Roma",
        "attendees": "Alice, Bob",
        "confidence": "high",
        "reasoning": "Both speakers explicitly agreed to lunch at noon.",
        "assumptions": None,
        "action": "create",
    }


def _mock_client(response_text: str) -> GeminiClient:
    """Create a ``GeminiClient`` with a mocked ``genai.Client``.

    The mock's ``models.generate_content`` returns *response_text* on every
    call.
    """
    with patch("cal_ai.llm.genai.Client"):
        client = GeminiClient(api_key="fake-key")

    mock_response = MagicMock()
    mock_response.text = response_text
    client._client.models.generate_content = MagicMock(return_value=mock_response)
    return client


def _mock_client_multi(response_texts: list[str]) -> GeminiClient:
    """Create a ``GeminiClient`` whose ``generate_content`` returns different
    text on successive calls (using ``side_effect``).
    """
    with patch("cal_ai.llm.genai.Client"):
        client = GeminiClient(api_key="fake-key")

    responses = []
    for text in response_texts:
        mock_resp = MagicMock()
        mock_resp.text = text
        responses.append(mock_resp)

    client._client.models.generate_content = MagicMock(side_effect=responses)
    return client


_CURRENT_DT = datetime(2026, 2, 18, 10, 0, 0)


# ---------------------------------------------------------------------------
# Happy Path (3 tests)
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Basic extraction scenarios that should succeed without retries."""

    def test_extract_single_event_happy_path(self) -> None:
        """SPEC.md example: single lunch event extracted correctly."""
        response = _make_llm_response_json([_single_lunch_event()])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Alice: Want to grab lunch Thursday at noon?\nBob: Sure, Cafe Roma?",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert len(result.events) == 1
        event = result.events[0]
        assert event.title == "Lunch with Bob"
        assert event.start_time == "2026-02-19T12:00:00"
        assert event.end_time == "2026-02-19T13:00:00"
        assert event.location == "Cafe Roma"
        assert "Alice" in event.attendees
        assert "Bob" in event.attendees

    def test_extract_multiple_events(self) -> None:
        """Conversation with two distinct events extracts both."""
        events = [
            _single_lunch_event(),
            {
                "title": "Team standup",
                "start_time": "2026-02-20T09:00:00",
                "end_time": "2026-02-20T09:30:00",
                "location": "Conference Room B",
                "attendees": "Alice, Bob, Charlie",
                "confidence": "high",
                "reasoning": "Standup explicitly scheduled.",
                "assumptions": None,
                "action": "create",
            },
        ]
        response = _make_llm_response_json(events, summary="Found 2 events.")
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="<two-event conversation>",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert len(result.events) == 2
        titles = {e.title for e in result.events}
        assert "Lunch with Bob" in titles
        assert "Team standup" in titles

    def test_extract_no_events(self) -> None:
        """Small-talk conversation yields zero events with a non-empty summary."""
        response = _make_llm_response_json(
            [], summary="No calendar events found in the conversation."
        )
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Alice: Nice weather today.\nBob: Yeah, really nice.",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert len(result.events) == 0
        assert result.summary  # non-empty


# ---------------------------------------------------------------------------
# Ambiguous Events (2 tests)
# ---------------------------------------------------------------------------


class TestAmbiguousEvents:
    """Events with incomplete information should still be extracted."""

    def test_extract_ambiguous_event_no_time(self) -> None:
        """'Meet up sometime this week' produces a low-confidence event with assumptions."""
        event = {
            "title": "Meet up with Bob",
            "start_time": "2026-02-20T09:00:00",
            "end_time": None,
            "location": None,
            "attendees": "Alice, Bob",
            "confidence": "low",
            "reasoning": "Vague mention of meeting sometime this week.",
            "assumptions": "Assumed Friday at 09:00 as default",
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Alice: We should meet up sometime this week.\nBob: Sure, maybe.",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert len(result.events) == 1
        assert result.events[0].confidence == "low"
        assert len(result.events[0].assumptions) > 0

    def test_extract_ambiguous_event_no_location(self) -> None:
        """Event with time but no location sets location to None and notes it."""
        event = {
            "title": "Coffee with Carol",
            "start_time": "2026-02-19T15:00:00",
            "end_time": "2026-02-19T16:00:00",
            "location": None,
            "attendees": "Alice, Carol",
            "confidence": "medium",
            "reasoning": "Carol suggested coffee at 3pm but no location given.",
            "assumptions": "No location specified",
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Carol: Coffee at 3 tomorrow?\nAlice: Sounds good!",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert len(result.events) == 1
        assert result.events[0].location is None
        assert len(result.events[0].assumptions) > 0


# ---------------------------------------------------------------------------
# Owner Perspective (2 tests)
# ---------------------------------------------------------------------------


class TestOwnerPerspective:
    """Confidence varies based on owner's involvement in the event."""

    def test_owner_perspective_owner_involved(self) -> None:
        """Owner directly participates -- confidence should be high."""
        event = {
            "title": "Lunch with Bob",
            "start_time": "2026-02-19T12:00:00",
            "end_time": "2026-02-19T13:00:00",
            "location": "Cafe Roma",
            "attendees": "Alice, Bob",
            "confidence": "high",
            "reasoning": "Alice directly agreed to lunch with Bob.",
            "assumptions": None,
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Alice: Let's do lunch.\nBob: Sure!",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert result.events[0].confidence == "high"
        assert "Alice" in result.events[0].attendees

    def test_owner_perspective_overheard_conversation(self) -> None:
        """Owner overhears others' meeting -- confidence should be low."""
        event = {
            "title": "Bob and Carol meeting",
            "start_time": "2026-02-19T14:00:00",
            "end_time": "2026-02-19T15:00:00",
            "location": None,
            "attendees": "Bob, Carol",
            "confidence": "low",
            "reasoning": (
                "Alice overheard Bob and Carol scheduling a meeting."
                " Alice is not involved."
            ),
            "assumptions": None,
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Bob: Carol, can we meet at 2pm?\nCarol: Sure, see you then.",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert result.events[0].confidence == "low"
        assert "overheard" in result.events[0].reasoning.lower() or \
               "not involved" in result.events[0].reasoning.lower()


# ---------------------------------------------------------------------------
# Relative Time Resolution (3 tests)
# ---------------------------------------------------------------------------


class TestRelativeTimeResolution:
    """LLM resolves relative time references to absolute ISO datetimes."""

    def test_relative_time_next_thursday(self) -> None:
        """'next Thursday' from 2026-02-18 (Wednesday) resolves to 2026-02-26."""
        event = {
            "title": "Dentist appointment",
            "start_time": "2026-02-26T10:00:00",
            "end_time": "2026-02-26T11:00:00",
            "location": "Dental Office",
            "attendees": "Alice",
            "confidence": "high",
            "reasoning": "Alice mentioned a dentist appointment next Thursday.",
            "assumptions": "Resolved 'next Thursday' to 2026-02-26",
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Alice: I have a dentist appointment next Thursday at 10.",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert "2026-02-26" in result.events[0].start_time

    def test_relative_time_tomorrow(self) -> None:
        """'tomorrow' from 2026-02-18 resolves to 2026-02-19."""
        event = {
            "title": "Coffee with Bob",
            "start_time": "2026-02-19T09:00:00",
            "end_time": None,
            "location": None,
            "attendees": "Alice, Bob",
            "confidence": "medium",
            "reasoning": "Bob suggested coffee tomorrow.",
            "assumptions": "Resolved 'tomorrow' to 2026-02-19, defaulted time to 09:00",
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Bob: Want coffee tomorrow?\nAlice: Maybe.",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert "2026-02-19" in result.events[0].start_time

    def test_relative_time_this_weekend(self) -> None:
        """'this weekend' resolves to a Saturday or Sunday."""
        event = {
            "title": "Hiking",
            "start_time": "2026-02-21T10:00:00",
            "end_time": "2026-02-21T14:00:00",
            "location": "Mountain Trail",
            "attendees": "Alice, Bob",
            "confidence": "medium",
            "reasoning": "Alice and Bob plan to go hiking this weekend.",
            "assumptions": "Resolved 'this weekend' to Saturday 2026-02-21",
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Alice: Let's go hiking this weekend.\nBob: Great idea!",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        # 2026-02-21 is a Saturday (weekday() == 5)
        start_str = result.events[0].start_time
        start_dt = datetime.fromisoformat(start_str)
        assert start_dt.weekday() in (5, 6)  # Saturday or Sunday


# ---------------------------------------------------------------------------
# Malformed Response Handling (4 tests)
# ---------------------------------------------------------------------------


class TestMalformedResponseHandling:
    """Retry and graceful failure on bad LLM responses."""

    def test_malformed_json_retry_success(self, caplog: pytest.LogCaptureFixture) -> None:
        """First call returns invalid JSON, second call succeeds -- retry works."""
        valid_response = _make_llm_response_json(
            [_single_lunch_event()], summary="Found 1 event."
        )
        client = _mock_client_multi(["NOT VALID JSON {{", valid_response])

        with caplog.at_level(logging.WARNING, logger="cal_ai.llm"):
            result = client.extract_events(
                transcript_text="test transcript",
                owner_name="Alice",
                current_datetime=_CURRENT_DT,
            )

        assert len(result.events) == 1
        assert client._client.models.generate_content.call_count == 2
        assert any("retry" in r.message.lower() or "malformed" in r.message.lower()
                    for r in caplog.records if r.levelno >= logging.WARNING)

    def test_malformed_json_retry_still_bad_graceful_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Both calls return invalid JSON -- graceful empty result."""
        client = _mock_client_multi(["BAD JSON 1", "BAD JSON 2"])

        with caplog.at_level(logging.ERROR, logger="cal_ai.llm"):
            result = client.extract_events(
                transcript_text="test transcript",
                owner_name="Alice",
                current_datetime=_CURRENT_DT,
            )

        assert len(result.events) == 0
        assert "fail" in result.summary.lower() or "error" in result.summary.lower()
        assert client._client.models.generate_content.call_count == 2
        assert any(r.levelno >= logging.ERROR for r in caplog.records)

    def test_llm_returns_empty_response(self) -> None:
        """Empty string response triggers retry (treated as malformed)."""
        valid_response = _make_llm_response_json(
            [_single_lunch_event()], summary="Found 1 event."
        )
        client = _mock_client_multi(["", valid_response])

        result = client.extract_events(
            transcript_text="test transcript",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert len(result.events) == 1
        assert client._client.models.generate_content.call_count == 2

    def test_llm_returns_events_missing_required_fields(self) -> None:
        """Valid JSON but missing required 'title' field -- schema validation fails, retry."""
        bad_event = {
            "start_time": "2026-02-19T12:00:00",
            "end_time": None,
            "location": None,
            "attendees": "Alice",
            "confidence": "high",
            "reasoning": "Missing title.",
            "assumptions": None,
            "action": "create",
            # no "title" field
        }
        bad_response = _make_llm_response_json([bad_event])
        good_response = _make_llm_response_json(
            [_single_lunch_event()], summary="Found 1 event."
        )
        client = _mock_client_multi([bad_response, good_response])

        result = client.extract_events(
            transcript_text="test transcript",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert len(result.events) == 1
        assert result.events[0].title == "Lunch with Bob"
        assert client._client.models.generate_content.call_count == 2


# ---------------------------------------------------------------------------
# Confidence Levels (3 tests)
# ---------------------------------------------------------------------------


class TestConfidenceLevels:
    """Confidence values are preserved from the LLM response."""

    def test_confidence_levels_explicit_plan_is_high(self) -> None:
        """Clear plan with full details should have high confidence."""
        event = _single_lunch_event()
        event["confidence"] = "high"
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Alice: Lunch at noon Thursday at Cafe Roma?\nBob: I'll be there.",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert result.events[0].confidence == "high"

    def test_confidence_levels_vague_mention_is_low(self) -> None:
        """'maybe we could meet' yields low confidence."""
        event = {
            "title": "Possible meetup",
            "start_time": "2026-02-20T09:00:00",
            "end_time": None,
            "location": None,
            "attendees": "Alice, Bob",
            "confidence": "low",
            "reasoning": "Very vague suggestion with no commitment.",
            "assumptions": "Assumed next available day, defaulted time to 09:00",
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Alice: Maybe we could meet sometime?\nBob: Yeah, maybe.",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert result.events[0].confidence == "low"

    def test_confidence_levels_medium_partial_info(self) -> None:
        """Day mentioned but no time yields medium confidence."""
        event = {
            "title": "Meeting on Friday",
            "start_time": "2026-02-20T09:00:00",
            "end_time": None,
            "location": None,
            "attendees": "Alice, Bob",
            "confidence": "medium",
            "reasoning": "Day is specified but no time given.",
            "assumptions": "Defaulted time to 09:00",
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="Bob: Let's meet Friday.\nAlice: Ok.",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert result.events[0].confidence == "medium"


# ---------------------------------------------------------------------------
# Logging (3 tests)
# ---------------------------------------------------------------------------


class TestLogging:
    """Extraction logging at the correct levels."""

    def test_reasoning_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Event reasoning is logged at INFO level."""
        response = _make_llm_response_json([_single_lunch_event()])
        client = _mock_client(response)

        with caplog.at_level(logging.INFO, logger="cal_ai.llm"):
            client.extract_events(
                transcript_text="test",
                owner_name="Alice",
                current_datetime=_CURRENT_DT,
            )

        # The reasoning text should appear in an INFO record
        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("Both speakers explicitly agreed" in msg for msg in info_messages)

    def test_extraction_summary_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Extraction summary is logged at INFO level."""
        response = _make_llm_response_json(
            [_single_lunch_event()], summary="Extracted 1 lunch event."
        )
        client = _mock_client(response)

        with caplog.at_level(logging.INFO, logger="cal_ai.llm"):
            client.extract_events(
                transcript_text="test",
                owner_name="Alice",
                current_datetime=_CURRENT_DT,
            )

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("Extracted 1 lunch event" in msg for msg in info_messages)

    def test_raw_llm_response_is_logged_at_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Raw LLM response text is logged at DEBUG level."""
        raw_json = _make_llm_response_json([_single_lunch_event()])
        client = _mock_client(raw_json)

        with caplog.at_level(logging.DEBUG, logger="cal_ai.llm"):
            client.extract_events(
                transcript_text="test",
                owner_name="Alice",
                current_datetime=_CURRENT_DT,
            )

        debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        # The raw JSON should appear in a DEBUG message
        assert any("Lunch with Bob" in msg for msg in debug_messages)


# ---------------------------------------------------------------------------
# API Integration (3 tests)
# ---------------------------------------------------------------------------


class TestAPIIntegration:
    """Verify correct arguments are passed to the Gemini SDK."""

    def test_system_prompt_sent_to_gemini(self) -> None:
        """System prompt (with owner name and datetime) is passed via config."""
        response = _make_llm_response_json([_single_lunch_event()])
        client = _mock_client(response)

        client.extract_events(
            transcript_text="test",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        call_kwargs = client._client.models.generate_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        system_instruction = config.system_instruction
        assert "Alice" in system_instruction
        assert "2026-02-18" in system_instruction

    def test_calendar_context_forwarded_to_system_prompt(self) -> None:
        """calendar_context text appears in the system prompt sent to Gemini."""
        response = _make_llm_response_json([_single_lunch_event()])
        client = _mock_client(response)

        context_text = "[1] Team Standup | 2026-02-19T09:00 - 2026-02-19T10:00"
        client.extract_events(
            transcript_text="test",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
            calendar_context=context_text,
        )

        call_kwargs = client._client.models.generate_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        system_instruction = config.system_instruction
        assert "Team Standup" in system_instruction
        assert "[1]" in system_instruction

    def test_empty_calendar_context_shows_no_events_message(self) -> None:
        """Empty calendar_context produces 'No existing calendar events' in prompt."""
        response = _make_llm_response_json([_single_lunch_event()])
        client = _mock_client(response)

        client.extract_events(
            transcript_text="test",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
            calendar_context="",
        )

        call_kwargs = client._client.models.generate_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        system_instruction = config.system_instruction
        assert "No existing calendar events" in system_instruction

    def test_response_schema_sent_to_gemini(self) -> None:
        """Generation config includes response_mime_type and response_schema."""
        response = _make_llm_response_json([_single_lunch_event()])
        client = _mock_client(response)

        client.extract_events(
            transcript_text="test",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        call_kwargs = client._client.models.generate_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.response_mime_type == "application/json"
        assert config.response_schema is LLMResponseSchema

    def test_extract_events_called_with_correct_model(self) -> None:
        """generate_content is called with the configured model name."""
        response = _make_llm_response_json([_single_lunch_event()])
        with patch("cal_ai.llm.genai.Client"):
            client = GeminiClient(api_key="fake-key", model="gemini-2.0-flash")

        mock_resp = MagicMock()
        mock_resp.text = response
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        client.extract_events(
            transcript_text="test",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        call_kwargs = client._client.models.generate_content.call_args
        assert call_kwargs.kwargs.get("model") == "gemini-2.0-flash"


# ---------------------------------------------------------------------------
# Edge Cases (3 tests)
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Boundary conditions and conversion edge cases."""

    def test_api_error_handling(self) -> None:
        """Gemini API raising an error results in ExtractionError."""
        from google.genai import errors as genai_errors

        with patch("cal_ai.llm.genai.Client"):
            client = GeminiClient(api_key="fake-key")

        client._client.models.generate_content = MagicMock(
            side_effect=genai_errors.APIError(
                code=503, response_json={"error": "Service unavailable"}
            )
        )

        with pytest.raises(ExtractionError):
            client.extract_events(
                transcript_text="test",
                owner_name="Alice",
                current_datetime=_CURRENT_DT,
            )

    def test_null_optional_fields_passthrough(self) -> None:
        """JSON null values for optional fields are passed through as Python None."""
        event = {
            "title": "Meeting",
            "start_time": "2026-02-19T10:00:00",
            "end_time": None,
            "location": None,
            "attendees": "Alice",
            "confidence": "high",
            "reasoning": "Test event.",
            "assumptions": None,
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="test",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert result.events[0].end_time is None
        assert result.events[0].location is None

    def test_end_time_default_one_hour(self) -> None:
        """When end_time is None, validate_events applies a 1-hour default."""
        event = {
            "title": "Quick chat",
            "start_time": "2026-02-19T14:00:00",
            "end_time": None,
            "location": None,
            "attendees": "Alice",
            "confidence": "high",
            "reasoning": "Quick chat scheduled.",
            "assumptions": None,
            "action": "create",
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="test",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        validated = client.validate_events(result, _CURRENT_DT)

        assert len(validated) == 1
        assert validated[0].start_time == datetime(2026, 2, 19, 14, 0, 0)
        assert validated[0].end_time == datetime(2026, 2, 19, 14, 0, 0) + timedelta(hours=1)

    def test_existing_event_id_present(self) -> None:
        """existing_event_id is extracted from LLM response for update actions."""
        event = {
            "title": "Updated meeting",
            "start_time": "2026-02-19T14:00:00",
            "end_time": "2026-02-19T15:00:00",
            "location": "Room A",
            "attendees": "Alice, Bob",
            "confidence": "high",
            "reasoning": "Rescheduled existing meeting.",
            "assumptions": None,
            "action": "update",
            "existing_event_id": 3,
        }
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="test",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert len(result.events) == 1
        assert result.events[0].existing_event_id == 3
        assert result.events[0].action == "update"

    def test_existing_event_id_absent(self) -> None:
        """existing_event_id defaults to None when not in LLM response."""
        event = _single_lunch_event()
        response = _make_llm_response_json([event])
        client = _mock_client(response)

        result = client.extract_events(
            transcript_text="test",
            owner_name="Alice",
            current_datetime=_CURRENT_DT,
        )

        assert len(result.events) == 1
        assert result.events[0].existing_event_id is None
