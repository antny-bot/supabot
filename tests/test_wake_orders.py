import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiohttp import web
import internal_api


@pytest.mark.asyncio
async def test_internal_wake_orders_handler_sets_event():
    fake_req = MagicMock()
    with patch("internal_api._verify_webhook_request", new=AsyncMock(return_value=True)):
        with patch("main._order_wake_event", new=asyncio.Event()) as ev:
            resp = await internal_api._internal_wake_orders_handler(fake_req)
            assert resp.status == 200
            assert ev.is_set()


@pytest.mark.asyncio
async def test_internal_wake_orders_handler_unauthorized():
    fake_req = MagicMock()
    with patch("internal_api._verify_webhook_request", new=AsyncMock(return_value=False)):
        resp = await internal_api._internal_wake_orders_handler(fake_req)
        assert resp.status == 401
