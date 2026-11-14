"""Manager-side price cache for Toss market data.

Real-time price queries for order placement stay in the bot process.
This cache is used by manager back-office (reports, dashboards, PnL)
to avoid hammering Toss API with per-request market data calls.
"""

from __future__ import annotations

import asyncio
import time
from datetime import timezone, timedelta

KST = timezone(timedelta(hours=9))

TTL_SECONDS = 300  # 5분


class PriceCache:
    """Simple async in-memory price cache.

    Stores last fetched price per (user_id, exchange, ticker) with TTL.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple, dict] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(user_id: str, exchange: str, ticker: str) -> tuple:
        return (str(user_id), str(exchange).lower(), str(ticker).upper())

    async def get(self, user_id: str, exchange: str, ticker: str) -> float | None:
        now = int(time.time())
        k = self._key(user_id, exchange, ticker)
        async with self._lock:
            cached = self._cache.get(k)
            if cached and (now - cached["fetched_at"]) < TTL_SECONDS:
                return float(cached["price"])
        return None

    async def set(self, user_id: str, exchange: str, ticker: str, price: float) -> None:
        k = self._key(user_id, exchange, ticker)
        async with self._lock:
            self._cache[k] = {
                "price": float(price),
                "fetched_at": int(time.time()),
            }

    async def get_or_fetch(
        self,
        user_id: str,
        exchange: str,
        ticker: str,
        fetch_fn,
    ) -> float | None:
        """캐시에서 조회. 캐시 미스면 fetch_fn(ticker) 호출 후 저장.

        Args:
            user_id: 사용자 ID
            exchange: 거래소 코드
            ticker: 종목 코드
            fetch_fn: async callable, ticker -> price or None
        """
        cached = await self.get(user_id, exchange, ticker)
        if cached is not None:
            return cached
        price = await fetch_fn(ticker)
        if price is not None:
            await self.set(user_id, exchange, ticker, price)
        return price

    def clear(self) -> None:
        self._cache.clear()

    def stats(self) -> dict:
        return {
            "cached_count": len(self._cache),
            "ttl_seconds": TTL_SECONDS,
        }


# 전역 싱글톤 (manager 프로세스 단위)
price_cache = PriceCache()
