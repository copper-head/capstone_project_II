"""Tests for cal-ai package structure and imports."""

from __future__ import annotations

import re
import subprocess
import sys


def test_package_is_importable() -> None:
    """``import cal_ai`` must succeed without errors."""
    import cal_ai  # noqa: F401


def test_package_has_version() -> None:
    """``cal_ai.__version__`` must be defined."""
    import cal_ai

    assert hasattr(cal_ai, "__version__")
    assert cal_ai.__version__ == "0.1.0"


def test_package_version_is_semver() -> None:
    """Version string must match semantic versioning format."""
    import cal_ai

    assert re.match(r"^\d+\.\d+\.\d+$", cal_ai.__version__)


def test_main_module_exists() -> None:
    """``python -m cal_ai`` must run and exit cleanly."""
    result = subprocess.run(
        [sys.executable, "-m", "cal_ai"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "Traceback" not in result.stderr


def test_config_module_importable() -> None:
    """Core config exports must be importable."""
    from cal_ai.config import ConfigError, load_settings  # noqa: F401


def test_logging_module_importable() -> None:
    """Core logging exports must be importable."""
    from cal_ai.log import get_logger, setup_logging  # noqa: F401
