"""Route handlers for the cal-ai web frontend.

Provides page-serving routes (``GET /``, ``GET /memory``) and API endpoints:
- ``GET /api/health`` -- health check.
- ``POST /api/pipeline/run`` -- run the pipeline with SSE streaming.
- ``GET /api/memories`` -- list all stored memories.
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from cal_ai.web.schemas import (
    MemoryResponse,
    PipelineResultResponse,
)
from cal_ai.web.sse import PipelineLogCapture, pipeline_sse_generator

router = APIRouter()
logger = logging.getLogger(__name__)

# Concurrency guard: only one pipeline run at a time.
_pipeline_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def index_page(request: Request) -> HTMLResponse:
    """Serve the pipeline page (split-view input/results layout).

    Passes ``config_warnings`` from ``app.state`` to the template context
    so the base layout can render the warning banner when needed.

    Args:
        request: The incoming HTTP request.

    Returns:
        Rendered ``index.html`` template.
    """
    templates = request.app.state.templates
    config_warnings: list[str] = getattr(request.app.state, "config_warnings", [])
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"config_warnings": config_warnings},
    )


@router.get("/memory", response_class=HTMLResponse)
async def memory_page(request: Request) -> HTMLResponse:
    """Serve the memory viewer page.

    Passes ``config_warnings`` from ``app.state`` to the template context
    so the base layout can render the warning banner when needed.

    Args:
        request: The incoming HTTP request.

    Returns:
        Rendered ``memory.html`` template.
    """
    templates = request.app.state.templates
    config_warnings: list[str] = getattr(request.app.state, "config_warnings", [])
    return templates.TemplateResponse(
        request=request,
        name="memory.html",
        context={"config_warnings": config_warnings},
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@router.get("/api/health")
async def health() -> dict[str, str]:
    """Return a simple health check response.

    Returns:
        A JSON object with ``{"status": "ok"}``.
    """
    return {"status": "ok"}


@router.post("/api/pipeline/run")
async def pipeline_run(
    request: Request,
    file: UploadFile | None = File(None),
    text: str | None = Form(None),
    dry_run: bool = Form(False),
) -> StreamingResponse:
    """Run the pipeline and stream results via Server-Sent Events.

    Accepts either a file upload or pasted text (exactly one must be
    provided).  Runs ``run_pipeline()`` in a background thread and
    streams stage progress, log lines, and the final result as SSE
    events.

    SSE event types:
        - ``event: stage`` -- stage name + status (running/complete).
        - ``event: log`` -- raw log line with level and logger name.
        - ``event: result`` -- full pipeline result JSON.
        - ``event: error`` -- error message on failure.
        - ``event: done`` -- signals stream end.

    Returns:
        A :class:`StreamingResponse` with ``text/event-stream`` media type.

    Raises:
        422: If neither file nor text is provided, or both are provided.
        409: If a pipeline is already running.
    """
    # --- Validate input: exactly one of file or text -----------------------
    has_file = file is not None and file.filename
    has_text = text is not None and text.strip()

    if not has_file and not has_text:
        return JSONResponse(
            status_code=422,
            content={"detail": "Provide either a file upload or text, not neither."},
        )

    if has_file and has_text:
        return JSONResponse(
            status_code=422,
            content={"detail": "Provide either a file upload or text, not both."},
        )

    # --- Atomic lock acquisition -------------------------------------------
    try:
        await asyncio.wait_for(_pipeline_lock.acquire(), timeout=0)
    except TimeoutError:
        return JSONResponse(
            status_code=409,
            content={"detail": "A pipeline is already running. Please wait."},
        )

    # --- Build the SSE generator -------------------------------------------
    async def _generate() -> Any:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        tmp_path: Path | None = None

        try:
            # Write input to a temporary file (run_pipeline requires a Path).
            if has_file:
                content = await file.read()  # type: ignore[union-attr]
                suffix = Path(file.filename).suffix if file.filename else ".txt"  # type: ignore[union-attr]
            else:
                content = text.encode("utf-8")  # type: ignore[union-attr]
                suffix = ".txt"

            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, mode="wb"
            )
            tmp.write(content)
            tmp.close()
            tmp_path = Path(tmp.name)

            # Resolve owner name.
            from cal_ai.config import ConfigError, load_settings

            try:
                settings = load_settings()
                owner = settings.owner_name
            except ConfigError as exc:
                yield _sse_event("error", {"message": str(exc)})
                yield _sse_event("done", {})
                return

            # Set up log capture.
            loop = asyncio.get_running_loop()

            # We need the thread ID before the thread starts, so we
            # capture it inside the thread function and signal back.
            thread_id_event = threading.Event()
            thread_id_holder: list[int] = []

            def _run_in_thread() -> Any:
                thread_id_holder.append(threading.get_ident())
                thread_id_event.set()

                from cal_ai.pipeline import run_pipeline

                return run_pipeline(
                    transcript_path=tmp_path,  # type: ignore[arg-type]
                    owner=owner,
                    dry_run=dry_run,
                )

            # Start the pipeline in a background thread.
            future = loop.run_in_executor(None, _run_in_thread)

            # Wait for the thread to report its ID.
            thread_id_event.wait(timeout=5)
            if not thread_id_holder:
                yield _sse_event("error", {"message": "Pipeline thread failed to start."})
                yield _sse_event("done", {})
                return

            # Attach the log handler.
            handler = PipelineLogCapture(
                queue=queue,
                loop=loop,
                thread_id=thread_id_holder[0],
            )
            root_logger = logging.getLogger("cal_ai")
            root_logger.addHandler(handler)

            try:
                # Drain the queue while the pipeline runs.
                while not future.done():
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=0.1)
                        if event is None:
                            break
                        yield _sse_event(event["type"], event["data"])
                    except TimeoutError:
                        continue

                # Pipeline finished -- get the result or exception.
                result = await asyncio.wrap_future(future)

                # Terminal rule: mark last stage complete.
                handler.mark_complete()

                # Drain any remaining events in the queue.
                while not queue.empty():
                    event = queue.get_nowait()
                    if event is None:
                        break
                    yield _sse_event(event["type"], event["data"])

                # Emit the result.
                response_model = PipelineResultResponse.from_pipeline_result(result)
                yield _sse_event("result", response_model.model_dump())
                yield _sse_event("done", {})

            except Exception as exc:
                # Pipeline raised -- emit error.
                handler.mark_complete()

                # Drain remaining events.
                while not queue.empty():
                    event = queue.get_nowait()
                    if event is None:
                        break
                    yield _sse_event(event["type"], event["data"])

                yield _sse_event("error", {"message": str(exc)})
                yield _sse_event("done", {})

            finally:
                root_logger.removeHandler(handler)

        finally:
            _pipeline_lock.release()
            # Clean up temp file.
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/memories")
async def list_memories() -> list[MemoryResponse]:
    """Return all stored memories as a flat JSON array.

    Memories are ordered by category then key.  Each entry includes
    ``category``, ``key``, ``value``, and ``confidence`` (no timestamps
    or source_count per interview decision).

    Returns an empty array when no memories exist or when config is
    unavailable.
    """
    from cal_ai.config import ConfigError, load_memory_settings
    from cal_ai.memory.store import MemoryStore

    try:
        memory_db_path = load_memory_settings()
    except ConfigError:
        return []

    # Check if the DB file exists before trying to open it.
    if not Path(memory_db_path).exists():
        return []

    store = MemoryStore(memory_db_path)
    try:
        memories = store.load_all()
    finally:
        store.close()

    return [
        MemoryResponse(
            category=m.category,
            key=m.key,
            value=m.value,
            confidence=m.confidence,
        )
        for m in memories
    ]


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE event string.

    Args:
        event_type: The SSE event name (e.g., ``"stage"``, ``"log"``).
        data: The event data dict to JSON-serialize.

    Returns:
        A formatted SSE event string.
    """
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
