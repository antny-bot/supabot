import json
import os
import time

from core.bot_logger import get_logger
from core.db import get_db, is_db_available

_log = get_logger("order_manager")

# fire-and-forget 백그라운드 태스크에 대한 강한 참조를 보관한다.
# asyncio는 태스크를 weak-ref로만 잡으므로, create_task() 결과를 어디에도 저장하지
# 않으면 완료 전 GC되어 주문 DB upsert/delete가 유실될 수 있다(공식 문서 경고).
_bg_tasks: set = set()


def _track_task(task):
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


# Supabase(PostgREST) 단일 GET 응답 기본 상한(max-rows=1000). 주문이 이보다 많으면
# 한 번의 select로는 일부만 돌아와 나머지 주문이 추적에서 누락된다 → 페이지네이션 필수.
_DB_PAGE_SIZE = 1000


class OrderManager:
    def __init__(self, file_path="data/orders.json"):
        self.file_path = file_path
        self.orders = self._load_orders()
        self._uuid_set = {o["uuid"] for o in self.orders}
        self.on_order_added = None

    def has_order(self, uuid) -> bool:
        """O(1) 멤버십 조회. sync_orders 등 핫 경로의 O(N) 재스캔을 대체한다."""
        return uuid in self._uuid_set

    @staticmethod
    def _fetch_all_orders() -> list:
        """1000건 상한을 넘는 주문도 누락 없이 모두 읽어온다(동기 페이지네이션)."""
        all_rows = []
        start = 0
        while True:
            rows = get_db().table("orders").select("*").range(start, start + _DB_PAGE_SIZE - 1).execute().data or []
            all_rows.extend(rows)
            if len(rows) < _DB_PAGE_SIZE:
                break
            start += _DB_PAGE_SIZE
        return all_rows

    @staticmethod
    async def _fetch_all_orders_async() -> list:
        """1000건 상한을 넘는 주문도 누락 없이 모두 읽어온다(비동기 페이지네이션)."""
        all_rows = []
        start = 0
        while True:
            res = await get_db().table("orders").select("*").range(start, start + _DB_PAGE_SIZE - 1).execute_async()
            rows = res.data or []
            all_rows.extend(rows)
            if len(rows) < _DB_PAGE_SIZE:
                break
            start += _DB_PAGE_SIZE
        return all_rows

    def _load_orders(self) -> list:
        if is_db_available():
            try:
                rows = self._fetch_all_orders()
                _log.info("Loaded orders from DB", extra={"event": "orders_loaded_db", "count": len(rows)})
                return rows
            except Exception as e:
                _log.error("Failed to load orders from DB, falling back to file", exc_info=e, extra={"event": "db_orders_load_error"})
        return self._load_orders_from_file()

    def _load_orders_from_file(self) -> list:
        if not os.path.exists(self.file_path):
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            _log.error("Failed to load orders from file", exc_info=e, extra={"event": "orders_load_error"})
            return []

    def reload_from_db(self) -> bool:
        """폴링 사이클 시작 시 DB 상태를 인메모리에 반영한다. DB 미사용 환경에서는 no-op."""
        if not is_db_available():
            return False
        try:
            self.orders = self._fetch_all_orders()
            self._uuid_set = {o["uuid"] for o in self.orders}
            _log.info("Reloaded orders from DB", extra={"event": "orders_reloaded_db", "count": len(self.orders)})
            return True
        except Exception as e:
            _log.error("Failed to reload orders from DB", exc_info=e, extra={"event": "db_orders_reload_error"})
            return False

    async def reload_from_db_async(self) -> bool:
        """폴링 사이클 시작 시 DB 상태를 비동기로 인메모리에 반영한다."""
        if not is_db_available():
            return False
        try:
            self.orders = await self._fetch_all_orders_async()
            self._uuid_set = {o["uuid"] for o in self.orders}
            _log.info("Reloaded orders from DB (async)", extra={"event": "orders_reloaded_db_async", "count": len(self.orders)})
            return True
        except Exception as e:
            _log.error("Failed to reload orders from DB (async)", exc_info=e, extra={"event": "db_orders_reload_error_async"})
            return False

    def save_orders(self):
        if is_db_available():
            try:
                if self.orders:
                    get_db().table("orders").upsert(self.orders).execute()
                return
            except Exception as e:
                _log.error("Failed to save orders to DB", exc_info=e, extra={"event": "db_orders_save_error"})
        self._save_orders_to_file()

    def _save_orders_to_file(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.orders, f, indent=2, ensure_ascii=False)
            os.chmod(self.file_path, 0o600)
        except Exception as e:
            _log.error("Failed to save orders to file", exc_info=e, extra={"event": "orders_save_error"})

    def _db_upsert(self, order: dict):
        if not is_db_available():
            self._save_orders_to_file()
            return

        async def _run():
            try:
                await get_db().table("orders").upsert(order).execute_async()
            except Exception as e:
                _log.error("Failed to upsert order (async)", exc_info=e, extra={"event": "db_order_upsert_error", "uuid": order.get("uuid")})
                self._save_orders_to_file()
                from core.db_sync import enqueue_task
                try:
                    await enqueue_task("upsert", "orders", "uuid", order.get("uuid"), order)
                except Exception as ex:
                    _log.error("Failed to enqueue upsert task", exc_info=ex)

        import asyncio
        try:
            loop = asyncio.get_running_loop()
            _track_task(loop.create_task(_run()))
        except RuntimeError:
            try:
                get_db().table("orders").upsert(order).execute()
            except Exception as e:
                _log.error("Failed to upsert order in fallback", exc_info=e)
                self._save_orders_to_file()

    def _db_delete(self, uuid: str):
        if not is_db_available():
            self._save_orders_to_file()
            return

        async def _run():
            try:
                await get_db().table("orders").delete().eq("uuid", uuid).execute_async()
            except Exception as e:
                _log.error("Failed to delete order (async)", exc_info=e, extra={"event": "db_order_delete_error", "uuid": uuid})
                self._save_orders_to_file()
                from core.db_sync import enqueue_task
                try:
                    await enqueue_task("delete", "orders", "uuid", uuid)
                except Exception as ex:
                    _log.error("Failed to enqueue delete task", exc_info=ex)

        import asyncio
        try:
            loop = asyncio.get_running_loop()
            _track_task(loop.create_task(_run()))
        except RuntimeError:
            try:
                get_db().table("orders").delete().eq("uuid", uuid).execute()
            except Exception as e:
                _log.error("Failed to delete order in fallback", exc_info=e)
                self._save_orders_to_file()

    def add_order(self, user_id, exchange, ticker, uuid, price, volume, side="bid", strategy="manual", target_rsi=None, linked_to=None, status="wait", stop_price=None, trailing_stop_pct=None, group_no=None):
        self.remove_order(uuid, save=False)
        order = {
            "user_id": str(user_id),
            "exchange": exchange,
            "ticker": ticker,
            "uuid": uuid,
            "price": float(price),
            "volume": float(volume),
            "filled_volume": 0.0,
            "side": side,
            "strategy": strategy,
            "target_rsi": target_rsi,
            "linked_to": linked_to,
            "status": status,
            "created_at": time.time(),
            "next_check_at": 0.0,
            "reorder_of": None,
            "stop_price": float(stop_price) if stop_price is not None else None,
            "trailing_stop_pct": float(trailing_stop_pct) if trailing_stop_pct is not None else None,
            "group_no": int(group_no) if group_no is not None else None,
        }
        self.orders.append(order)
        self._uuid_set.add(order["uuid"])
        self._db_upsert(order)
        if self.on_order_added:
            self.on_order_added()

    def update_order_fill(self, uuid, filled_volume, status):
        for o in self.orders:
            if o["uuid"] == uuid:
                o["filled_volume"] = float(filled_volume)
                o["status"] = status
                self._db_upsert(o)
                return True
        return False

    def update_order_status(self, uuid, status):
        for o in self.orders:
            if o["uuid"] == uuid:
                o["status"] = status
                self._db_upsert(o)
                return True
        return False

    def update_order_stop_price(self, uuid, stop_price):
        for o in self.orders:
            if o["uuid"] == uuid:
                o["stop_price"] = float(stop_price) if stop_price is not None else None
                self._db_upsert(o)
                return True
        return False

    def mark_reorder_pending(self, uuid, next_check_at):
        for o in self.orders:
            if o["uuid"] == uuid:
                o["status"] = "pending_reorder"
                o["next_check_at"] = float(next_check_at)
                self._db_upsert(o)
                return True
        return False

    def update_next_check_at(self, uuid, next_check_at):
        for o in self.orders:
            if o["uuid"] == uuid:
                o["next_check_at"] = float(next_check_at)
                self._db_upsert(o)
                return True
        return False

    def replace_order_uuid(self, old_uuid, new_uuid):
        for o in self.orders:
            if o["uuid"] == old_uuid:
                self._db_delete(old_uuid)
                self._uuid_set.discard(old_uuid)
                self._uuid_set.add(new_uuid)
                o["reorder_of"] = old_uuid
                o["uuid"] = new_uuid
                o["status"] = "wait"
                o["next_check_at"] = 0.0
                o["created_at"] = time.time()
                self._db_upsert(o)
                return True
        return False

    def remove_order(self, uuid, save=True):
        before = len(self.orders)
        self.orders = [o for o in self.orders if o["uuid"] != uuid]
        removed = len(self.orders) != before
        self._uuid_set.discard(uuid)
        if removed and save:
            self._db_delete(uuid)
        return removed

    def get_user_orders(self, user_id, exchange=None):
        if exchange:
            return [o for o in self.orders if o["user_id"] == str(user_id) and o["exchange"] == exchange]
        return [o for o in self.orders if o["user_id"] == str(user_id)]

    def get_strategy_orders(self, user_id, strategy):
        return [o for o in self.orders if o["user_id"] == str(user_id) and o["strategy"] == strategy]

    def get_next_group_no(self, user_id) -> int:
        nums = [o["group_no"] for o in self.orders
                if o["user_id"] == str(user_id) and o.get("group_no")]
        return (max(nums) + 1) if nums else 1

    def get_orders_by_group_no(self, user_id, group_no) -> list:
        return [o for o in self.orders
                if o["user_id"] == str(user_id) and o.get("group_no") == int(group_no)]

    def clear_user_orders(self, user_id) -> int:
        """해당 유저의 모든 주문 추적을 DB+메모리에서 제거한다. 거래소 취소는 호출자 책임."""
        user_id = str(user_id)
        uuids = [o["uuid"] for o in self.orders if o["user_id"] == user_id]
        if is_db_available():
            try:
                get_db().table("orders").delete().eq("user_id", user_id).execute()
            except Exception as e:
                _log.error("Failed to clear user orders in DB", exc_info=e, extra={"event": "db_orders_clear_error", "user_id": user_id})
        self.orders = [o for o in self.orders if o["user_id"] != user_id]
        for u in uuids:
            self._uuid_set.discard(u)
        if not is_db_available():
            self._save_orders_to_file()
        return len(uuids)
