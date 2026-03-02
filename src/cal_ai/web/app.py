"""FastAPI application factory for the cal-ai web frontend.

Creates and configures the FastAPI app with Jinja2 templates, static file
serving, a config warning check, and API routes.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cal_ai.web.routes import router

_WEB_DIR = Path(__file__).parent
_TEMPLATE_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Sets up:
    - Jinja2 template rendering from ``web/templates/``.
    - Static file serving from ``web/static/`` mounted at ``/static``.
    - Config warning check for missing ``GEMINI_API_KEY``.
    - Health and API routes.

    Returns:
        A configured :class:`FastAPI` instance.
    """
    app = FastAPI(title="Cal-AI", description="Conversation-to-Calendar AI")

    # --- Jinja2 templates -------------------------------------------------
    templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))
    app.state.templates = templates

    # --- Config warning check ---------------------------------------------
    config_warnings: list[str] = []
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        config_warnings.append("Warning: GEMINI_API_KEY not configured. Pipeline runs will fail.")
    app.state.config_warnings = config_warnings

    # --- API routes -------------------------------------------------------
    app.include_router(router)

    # --- Static files (mount AFTER API routes to avoid path conflicts) ----
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app
