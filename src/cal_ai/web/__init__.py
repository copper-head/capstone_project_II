"""Web frontend package for cal-ai.

Provides a FastAPI application serving Jinja2 templates with a REST API
for pipeline execution and memory browsing.
"""

from cal_ai.web.app import create_app

__all__ = ["create_app"]
