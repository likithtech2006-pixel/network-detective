"""Tests for src.utils.helpers utility functions."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.helpers import format_path, tcp_check, timestamp_now


def test_timestamp_now() -> None:
    now = timestamp_now()
    assert isinstance(now, datetime)
    assert now.tzinfo == timezone.utc


def test_format_path() -> None:
    assert format_path([]) == ""
    assert format_path(["router-a"]) == "router-a"
    assert format_path(["router-a", "router-b", "server-d"]) == "router-a → router-b → server-d"


def test_tcp_check_failure() -> None:
    async def _test() -> None:
        with patch("asyncio.open_connection", side_effect=OSError("Network unreachable")):
            result = await tcp_check("192.168.1.99", 80, timeout=0.1)
            assert result is False

    asyncio.run(_test())


def test_tcp_check_success() -> None:
    async def _test() -> None:
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        mock_reader = MagicMock()
        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            result = await tcp_check("192.168.1.1", 80, timeout=1.0)
            assert result is True
            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()

    asyncio.run(_test())
