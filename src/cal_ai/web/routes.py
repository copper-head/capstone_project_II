"""Route handlers for the cal-ai web frontend.

Provides page-serving routes (``GET /``, ``GET /memory``) and API endpoints:
- ``GET /api/health`` -- health check.
- ``POST /api/pipeline/run`` -- run the pipeline with SSE streaming.
- ``GET /api/memories`` -- list all stored memories.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import queue
import tempfile
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from cal_ai.config import ConfigError, load_memory_settings, load_settings
from cal_ai.pipeline import run_pipeline
from cal_ai.web.schemas import (
    MemoryResponse,
    PipelineResultResponse,
)
from cal_ai.web.sse import PipelineLogCapture

router = APIRouter()
logger = logging.getLogger(__name__)


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

    Memory data is loaded client-side via ``GET /api/memories``.
    The template provides empty containers that ``memory.js`` populates.

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


# Maximum upload size (10 MB).  Exceeded uploads emit an SSE error event.
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
# Chunk size for streaming file uploads into the temp file.
_UPLOAD_CHUNK_SIZE = 64 * 1024


@router.post("/api/pipeline/run")
async def pipeline_run(
    request: Request,
    file: UploadFile | None = File(None),  # noqa: B008
    text: str | None = Form(None),  # noqa: B008
    dry_run: bool = Form(False),  # noqa: B008
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

    Note:
        Oversized uploads (exceeding ``_MAX_UPLOAD_BYTES``) are detected
        inside the SSE stream and reported as ``event: error`` with an
        ``event: done`` terminator (HTTP 200 is already committed).
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

    # Check text input size (same limit as file uploads).
    if has_text and len(text.encode("utf-8")) > _MAX_UPLOAD_BYTES:  # type: ignore[union-attr]
        return JSONResponse(
            status_code=422,
            content={"detail": "Text input exceeds 10 MB limit."},
        )

    # --- Atomic lock acquisition -------------------------------------------
    pipeline_lock: asyncio.Lock = request.app.state.pipeline_lock
    try:
        await asyncio.wait_for(pipeline_lock.acquire(), timeout=0.01)
    except TimeoutError:
        return JSONResponse(
            status_code=409,
            content={"detail": "A pipeline is already running. Please wait."},
        )

    # --- Build the SSE generator -------------------------------------------
    async def _generate() -> Any:  # noqa: C901
        event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        tmp_path: Path | None = None
        future: asyncio.Future[Any] | None = None

        try:
            # Write input to a temporary file (run_pipeline needs a
            # Path).  File uploads are streamed in chunks with a size
            # guard to prevent memory amplification.
            if has_file:
                suffix = (
                    Path(file.filename).suffix  # type: ignore[union-attr]
                    if file.filename  # type: ignore[union-attr]
                    else ".txt"
                )
                tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                    delete=False, suffix=suffix, mode="wb"
                )
                bytes_written = 0
                while True:
                    chunk = await file.read(  # type: ignore[union-attr]
                        _UPLOAD_CHUNK_SIZE
                    )
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > _MAX_UPLOAD_BYTES:
                        tmp.close()
                        Path(tmp.name).unlink(missing_ok=True)
                        yield _sse_event(
                            "error",
                            {"message": "Upload exceeds 10 MB limit."},
                        )
                        yield _sse_event("done", {})
                        return
                    tmp.write(chunk)
                tmp.close()
            else:
                content = (
                    text.encode("utf-8")  # type: ignore[union-attr]
                )
                suffix = ".txt"
                tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                    delete=False, suffix=suffix, mode="wb"
                )
                tmp.write(content)
                tmp.close()

            tmp_path = Path(tmp.name)

            # Resolve owner name.
            try:
                settings = load_settings()
                owner = settings.owner_name
            except ConfigError as exc:
                yield _sse_event("error", {"message": str(exc)})
                yield _sse_event("done", {})
                return

            # Two-phase synchronization: the thread reports its ID,
            # then waits for the handler to be attached before running
            # the pipeline.  This avoids losing early log messages.
            thread_id_event = threading.Event()
            handler_ready_event = threading.Event()
            thread_id_holder: list[int] = []

            def _run_in_thread() -> Any:
                thread_id_holder.append(threading.get_ident())
                thread_id_event.set()
                handler_ready_event.wait(timeout=10)

                return run_pipeline(
                    transcript_path=tmp_path,  # type: ignore[arg-type]
                    owner=owner,
                    dry_run=dry_run,
                )

            # Start the pipeline in a background thread.
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(None, _run_in_thread)

            # Wait for the thread to report its ID (poll to avoid
            # blocking the event loop or exhausting the thread pool).
            for _ in range(50):  # 50 * 0.1s = 5s max
                if thread_id_event.is_set():
                    break
                await asyncio.sleep(0.1)
            if not thread_id_holder:
                handler_ready_event.set()
                # Wait for thread to finish before cleanup.
                with contextlib.suppress(Exception):
                    await future
                yield _sse_event(
                    "error",
                    {"message": "Pipeline thread failed to start."},
                )
                yield _sse_event("done", {})
                return

            # Attach log handler, then unblock the pipeline thread.
            handler = PipelineLogCapture(
                event_queue=event_queue,
                thread_id=thread_id_holder[0],
            )
            root_logger = logging.getLogger("cal_ai")
            # Ensure INFO-level pipeline messages reach our handler
            # even when setup_logging() has not been called (the
            # effective level may inherit WARNING from the root logger).
            saved_level = root_logger.level
            if root_logger.getEffectiveLevel() > logging.DEBUG:
                root_logger.setLevel(logging.DEBUG)
            root_logger.addHandler(handler)
            handler_ready_event.set()

            try:
                # Drain the queue while the pipeline runs.
                while not future.done():
                    try:
                        event = event_queue.get_nowait()
                        if event is None:
                            break
                        yield _sse_event(event["type"], event["data"])
                    except queue.Empty:
                        await asyncio.sleep(0.05)
                        continue

                # Pipeline finished -- get the result or exception.
                result = await future

                # Terminal rule: mark last stage complete.
                handler.mark_complete()

                # Drain any remaining events in the queue.  Use a
                # timeout-based get to handle the case where the
                # pipeline thread has put events but the queue hasn't
                # propagated to this thread yet (observable under
                # coverage tracing or high-contention workloads).
                while True:
                    try:
                        event = event_queue.get(timeout=0.05)
                    except queue.Empty:
                        break
                    if event is None:
                        break
                    yield _sse_event(event["type"], event["data"])

                # Emit the result.
                resp = PipelineResultResponse.from_pipeline_result(result)
                yield _sse_event("result", resp.model_dump())
                yield _sse_event("done", {})

            except Exception as exc:
                handler.mark_complete()

                while True:
                    try:
                        event = event_queue.get(timeout=0.05)
                    except queue.Empty:
                        break
                    if event is None:
                        break
                    yield _sse_event(event["type"], event["data"])

                yield _sse_event("error", {"message": str(exc)})
                yield _sse_event("done", {})

            finally:
                root_logger.removeHandler(handler)
                root_logger.setLevel(saved_level)

        finally:
            # Ensure the worker thread has finished before releasing
            # the lock or deleting the temp file.  This prevents a
            # second request from starting while the worker is still
            # running and avoids deleting the file while the worker
            # still reads it.
            if future is not None and not future.done():
                # Client disconnected while pipeline is running.
                # We cannot await the future here because the generator
                # is being cancelled.  Instead, register a callback to
                # release the lock and clean up the temp file once the
                # pipeline thread actually finishes.
                _tmp = tmp_path  # capture for closure

                def _deferred_cleanup(_fut: Any) -> None:
                    pipeline_lock.release()
                    if _tmp is not None:
                        with contextlib.suppress(OSError):
                            _tmp.unlink(missing_ok=True)

                future.add_done_callback(_deferred_cleanup)
            else:
                # Normal completion or thread never started.
                pipeline_lock.release()
                if tmp_path is not None:
                    with contextlib.suppress(OSError):
                        tmp_path.unlink(missing_ok=True)

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
    from cal_ai.memory.store import MemoryStore

    try:
        memory_db_path = load_memory_settings()
    except ConfigError:
        return []

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
    """Format a single SSE event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
