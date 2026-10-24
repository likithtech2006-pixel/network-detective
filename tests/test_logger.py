"""Tests for src.utils.logger setup."""

from pathlib import Path
from src.utils.logger import logger, setup_logger


def test_setup_logger() -> None:
    setup_logger("DEBUG")
    logger.info("Test info message from test_setup_logger")
    logger.debug("Test debug message from test_setup_logger")

    project_root = Path(__file__).resolve().parent.parent
    logs_dir = project_root / "logs"
    assert logs_dir.is_dir()
    assert (logs_dir / "network_detective.log").exists()
