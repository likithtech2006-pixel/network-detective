"""Fallback Loguru shim for environments without third-party loguru package."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any


class _Level:
    def __init__(self, name: str, no: int):
        self.name = name
        self.no = no


class _LoggerShim:
    """Lightweight compatibility wrapper mimicking Loguru's API using standard logging."""

    _is_shim: bool = True

    def __init__(self) -> None:
        self._logger = logging.getLogger("network_detective")
        self._logger.propagate = False
        self._logger.setLevel(logging.DEBUG)
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            self._logger.addHandler(handler)
        self._handlers: dict[int, logging.Handler] = {1: self._logger.handlers[0]}
        self._next_id = 2

    def _format_msg(self, msg: Any, *args: Any, **kwargs: Any) -> str:
        s = str(msg)
        if "{}" in s or "{" in s:
            try:
                return s.format(*args, **kwargs)
            except Exception:
                pass
        if args:
            try:
                return s % args
            except Exception:
                pass
        return s

    def log(self, level: Any, msg: Any, *args: Any, **kwargs: Any) -> None:
        lvl_no = logging.INFO
        if isinstance(level, str):
            lvl_no = getattr(logging, level.upper(), logging.INFO)
        elif isinstance(level, int):
            lvl_no = level
        self._logger.log(lvl_no, self._format_msg(msg, *args, **kwargs))

    def debug(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self.log("DEBUG", msg, *args, **kwargs)

    def info(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self.log("INFO", msg, *args, **kwargs)

    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self.log("WARNING", msg, *args, **kwargs)

    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self.log("ERROR", msg, *args, **kwargs)

    def exception(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self._logger.exception(self._format_msg(msg, *args, **kwargs))

    def trace(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self.log("DEBUG", msg, *args, **kwargs)

    def success(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self.log("INFO", msg, *args, **kwargs)

    def critical(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        self.log("CRITICAL", msg, *args, **kwargs)

    def remove(self, handler_id: Any = None) -> None:
        if handler_id is None:
            for h in list(self._logger.handlers):
                self._logger.removeHandler(h)
            self._handlers.clear()
        elif handler_id in self._handlers:
            self._logger.removeHandler(self._handlers[handler_id])
            del self._handlers[handler_id]

    def add(self, sink: Any, **kwargs: Any) -> int:
        h_id = self._next_id
        self._next_id += 1

        level_str = kwargs.get("level", "INFO")
        lvl = getattr(logging, str(level_str).upper(), logging.INFO)

        if isinstance(sink, (str, Path)):
            Path(sink).parent.mkdir(parents=True, exist_ok=True)
            handler: logging.Handler = logging.FileHandler(str(sink), encoding=kwargs.get("encoding", "utf-8"))
        elif sink in (sys.stdout, sys.stderr) or hasattr(sink, "write"):
            handler = logging.StreamHandler(sink)
        else:
            return h_id

        handler.setLevel(lvl)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
        self._logger.addHandler(handler)
        self._handlers[h_id] = handler
        return h_id

    def level(self, name: str) -> _Level:
        return _Level(name.upper(), getattr(logging, name.upper(), 20))

    def opt(self, *args: Any, **kwargs: Any) -> _LoggerShim:
        return self


logger = _LoggerShim()
