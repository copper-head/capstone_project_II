"""Server-Sent Events support for the cal-ai web frontend.

Provides:

- :class:`PipelineLogCapture` -- a :class:`logging.Handler` that captures
  log messages from ``cal_ai.*`` loggers, synthesizes stage events from
  log message patterns, and forwards everything to a thread-safe queue.
- :func:`pipeline_sse_generator` -- an async generator that drains the
  queue and yields SSE-formatted strings.

Stage synthesis state machine
-----------------------------
The pipeline emits ``"Stage 1: ..."`` through ``"Stage 4: ..."`` explicitly,
but sub-stages 1b and 1c have no dedicated log lines.  The handler maps
log message patterns to synthetic stage events:

- ``"Stage 1: ..."`` -> stage 1 running
- ``"Memory context loaded"`` or ``"Memory load failed"`` -> stage 1b complete
- ``"Calendar context fetched"`` or ``"Calendar context unavailable"`` -> stage 1c complete
- ``"Stage 2: ..."`` -> boundary fallback (infer 1b/1c complete if not yet), stage 2 running
- ``"Stage 3: ..."`` -> stage 3 running (stage 2 complete)
- ``"Stage 4: ..."`` -> stage 4 running (stage 3 complete)

Terminal rule: on pipeline completion, mark any still-running stage
(especially stage 4) as complete before emitting ``done``.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import AsyncGenerator
from typing import Any


class PipelineLogCapture(logging.Handler):
    """Logging handler that captures pipeline logs and synthesizes stage events.

    Filters by thread ID for isolation when multiple pipelines could run
    (though the lock prevents concurrency, the filter is good practice).

    Uses a thread-safe :class:`queue.Queue` so events are immediately
    available regardless of event loop scheduling.

    Args:
        event_queue: The thread-safe queue to push events into.
        thread_id: The thread ID to filter on.
    """

    def __init__(
        self,
        event_queue: queue.Queue[dict[str, Any] | None],
        thread_id: int,
    ) -> None:
        super().__init__()
        self._queue = event_queue
        self._thread_id = thread_id

        # Stage synthesis state.
        self._current_stage: str | None = None
        self._stage_1b_emitted = False
        self._stage_1c_emitted = False

    def emit(self, record: logging.LogRecord) -> None:
        """Process a log record: synthesize stage events and forward as log event.

        Only processes records from ``cal_ai.*`` loggers on the target thread.
        """
        # Filter: only our pipeline thread and cal_ai loggers.
        if threading.get_ident() != self._thread_id:
            return
        if not record.name.startswith("cal_ai"):
            return

        message = record.getMessage()

        # --- Stage synthesis ---
        self._synthesize_stages(message)

        # --- Forward raw log line ---
        self._push_event(
            "log",
            {
                "message": message,
                "level": record.levelname,
                "logger": record.name,
            },
        )

    def mark_complete(self) -> None:
        """Terminal rule: mark any still-running stage as complete.

        Called after the pipeline finishes (or errors) to ensure the last
        stage (typically stage 4) is closed before emitting ``done``.
        """
        if self._current_stage is not None:
            self._push_event(
                "stage",
                {"name": self._current_stage, "status": "complete"},
            )
            self._current_stage = None

    def _synthesize_stages(self, message: str) -> None:
        """Map log message patterns to stage events."""
        # Stage 1: Loading and parsing transcript
        if message.startswith("Stage 1:"):
            self._transition_stage("1_parse")
            return

        # Stage 1b: Memory context
        if "Memory context loaded" in message or "Memory load failed" in message:
            if not self._stage_1b_emitted:
                self._stage_1b_emitted = True
                self._push_event(
                    "stage",
                    {"name": "1b_memory", "status": "complete"},
                )
            return

        # Stage 1c: Calendar context
        if "Calendar context fetched" in message or "Calendar context unavailable" in message:
            if not self._stage_1c_emitted:
                self._stage_1c_emitted = True
                self._push_event(
                    "stage",
                    {"name": "1c_calendar", "status": "complete"},
                )
            return

        # Stage 2: Extracting events -- boundary fallback for 1b/1c
        if message.startswith("Stage 2:"):
            if not self._stage_1b_emitted:
                self._stage_1b_emitted = True
                self._push_event(
                    "stage",
                    {"name": "1b_memory", "status": "complete"},
                )
            if not self._stage_1c_emitted:
                self._stage_1c_emitted = True
                self._push_event(
                    "stage",
                    {"name": "1c_calendar", "status": "complete"},
                )
            self._transition_stage("2_extract")
            return

        # Stage 3: Sync to Calendar
        if message.startswith("Stage 3:"):
            self._transition_stage("3_sync")
            return

        # Stage 4: Memory write path
        if message.startswith("Stage 4:"):
            self._transition_stage("4_memory_write")
            return

    def _transition_stage(self, new_stage: str) -> None:
        """Complete the current stage (if any) and start the new one."""
        if self._current_stage is not None:
            self._push_event(
                "stage",
                {"name": self._current_stage, "status": "complete"},
            )
        self._current_stage = new_stage
        self._push_event(
            "stage",
            {"name": new_stage, "status": "running"},
        )

    def _push_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Push an event dict to the thread-safe queue."""
        event = {"type": event_type, "data": data}
        self._queue.put_nowait(event)


async def pipeline_sse_generator(
    event_queue: queue.Queue[dict[str, Any] | None],
) -> AsyncGenerator[str, None]:
    """Async generator that drains the event queue and yields SSE strings.

    Reads events from *event_queue* until a sentinel ``None`` is received.
    Each event is formatted as an SSE ``event:`` / ``data:`` pair.

    Yields:
        SSE-formatted strings (``"event: <type>\\ndata: <json>\\n\\n"``).
    """
    while True:
        try:
            event = event_queue.get_nowait()
        except queue.Empty:
            import asyncio

            await asyncio.sleep(0.05)
            continue
        if event is None:
            break
        event_type = event["type"]
        data = event["data"]
        yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
