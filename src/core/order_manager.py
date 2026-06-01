import json
import os
import time

from core.bot_logger import get_logger
from core.db import get_db, is_db_available

_log = get_logger("order_manager")


class OrderManager:
    def __init__(self, file_path="data/orders.json"):
        self.file_path = file_path
        self.orders = self._load_orders()
        self.on_order_added = None

    def _load_orders(self) -> list:
        if is_db_available():
            try:
                rows = get_db().table("orders").select("*").execute().data
                _log.info("Loaded orders from DB", extra={"event": "orders_loaded_db", "count": len(rows)})
                return rows or []
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
        try:
            get_db().table("orders").upsert(order).execute()
        except Exception as e:
            _log.error("Failed to upsert order", exc_info=e, extra={"event": "db_order_upsert_error", "uuid": order.get("uuid")})
            self._save_orders_to_file()

    def _db_delete(self, uuid: str):
        if not is_db_available():
            self._save_orders_to_file()
            return
        try:
            get_db().table("orders").delete().eq("uuid", uuid).execute()
        except Exception as e:
            _log.error("Failed to delete order", exc_info=e, extra={"event": "db_order_delete_error", "uuid": uuid})
            self._save_orders_to_file()

    def add_order(self, user_id, exchange, ticker, uuid, price, volume, side="bid", strategy="manual", target_rsi=None, linked_to=None, status="wait", stop_price=None, trailing_stop_pct=None):
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
        }
        self.orders.append(order)
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
        if removed and save:
            self._db_delete(uuid)
        return removed

    def get_user_orders(self, user_id, exchange=None):
        if exchange:
            return [o for o in self.orders if o["user_id"] == str(user_id) and o["exchange"] == exchange]
        return [o for o in self.orders if o["user_id"] == str(user_id)]

    def get_strategy_orders(self, user_id, strategy):
        return [o for o in self.orders if o["user_id"] == str(user_id) and o["strategy"] == strategy]
