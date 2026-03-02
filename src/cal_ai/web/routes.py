"""Route handlers for the cal-ai web frontend.

Provides the health check endpoint and will be extended with page and
API routes in subsequent tasks.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
async def health() -> dict[str, str]:
    """Return a simple health check response.

    Returns:
        A JSON object with ``{"status": "ok"}``.
    """
    return {"status": "ok"}
