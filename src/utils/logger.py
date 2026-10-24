"""Logging configuration using Loguru with console colors and file rotation."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from loguru import logger


class InterceptHandler(logging.Handler):
    """Intercept standard logging messages and redirect them to Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        """Forward Python standard logging record to Loguru."""
        # Prevent recursive loops from our own logger
        if record.name.startswith("network_detective"):
            return

        try:
            level: Any = logger.level(record.levelname).name
        except Exception:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        opt_logger = logger.opt(depth=depth, exception=record.exc_info)
        if hasattr(opt_logger, "log"):
            opt_logger.log(level, record.getMessage())
        else:
            method = getattr(opt_logger, str(record.levelname).lower(), opt_logger.info)
            method(record.getMessage())


def setup_logger(log_level: str = "INFO") -> None:
    """Configure Loguru logger with console output, file rotation, and error capture.

    Args:
        log_level: Minimum log level for console output (DEBUG, INFO, WARNING, ERROR).
    """
    normalized_level = log_level.upper().strip()

    # Determine logs directory relative to project root or current directory
    project_root = Path(__file__).resolve().parent.parent.parent
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    app_log_file = logs_dir / "network_detective.log"
    error_log_file = logs_dir / "network_detective_error.log"

    # Reset any existing handlers
    logger.remove()

    # Console Handler (colored, formatted)
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    logger.add(
        sys.stdout,
        level=normalized_level,
        format=console_format,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # Main Log File (rotated at 10 MB, retain 5 zipped archives)
    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{name}:{function}:{line} - {message}"
    )
    logger.add(
        str(app_log_file),
        level="DEBUG",
        format=file_format,
        rotation="10 MB",
        retention=5,
        compression="zip",
        encoding="utf-8",
        backtrace=True,
        diagnose=False,
    )

    # Error Log File (dedicated sink for errors/exceptions)
    logger.add(
        str(error_log_file),
        level="ERROR",
        format=file_format,
        rotation="10 MB",
        retention=5,
        compression="zip",
        encoding="utf-8",
        backtrace=True,
        diagnose=True,
    )

    # Route standard library logs (uvicorn, sqlalchemy, apscheduler) through Loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for lib in ("uvicorn", "uvicorn.error", "uvicorn.access", "apscheduler", "sqlalchemy.engine"):
        _log = logging.getLogger(lib)
        _log.handlers = [InterceptHandler()]
        _log.propagate = False

    logger.info("Logger initialized at level: {} (logs directory: {})", normalized_level, logs_dir)


__all__ = ["setup_logger", "logger"]
