import json
import os
import time

class OrderManager:
    def __init__(self, file_path="data/orders.json"):
        self.file_path = file_path
        self.orders = self._load_orders()
        self.on_order_added = None

    def _load_orders(self):
        if not os.path.exists(self.file_path):
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading orders: {e}")
            return []

    def save_orders(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.orders, f, indent=2, ensure_ascii=False)
            os.chmod(self.file_path, 0o600)
        except Exception as e:
            print(f"Error saving orders: {e}")

    def add_order(self, user_id, exchange, ticker, uuid, price, volume, side="bid", strategy="manual", target_rsi=None, linked_to=None, status="wait"):
        """주문 추가 (전략 및 연동 정보 포함)"""
        self.remove_order(uuid, save=False)
        self.orders.append({
            "user_id": str(user_id),
            "exchange": exchange,
            "ticker": ticker,
            "uuid": uuid,
            "price": float(price),
            "volume": float(volume),
            "filled_volume": 0.0,    # 부분 체결 추적용
            "side": side,            # bid(매수), ask(매도)
            "strategy": strategy,    # manual, grid, rsitrade
            "target_rsi": target_rsi,# RSI 전략용 목표 수치
            "linked_to": linked_to,   # 연동된 주문 정보 (매수-매도 쌍)
            "status": status,        # wait, partial, done, cancel
            "created_at": time.time(),
            "next_check_at": 0.0,
            "reorder_of": None,
        })
        self.save_orders()
        if self.on_order_added:
            self.on_order_added()

    def update_order_fill(self, uuid, filled_volume, status):
        """주문의 체결 수량 및 상태 업데이트"""
        for o in self.orders:
            if o["uuid"] == uuid:
                o["filled_volume"] = float(filled_volume)
                o["status"] = status
                self.save_orders()
                return True
        return False

    def update_order_status(self, uuid, status):
        """주문의 상태만 업데이트"""
        for o in self.orders:
            if o["uuid"] == uuid:
                o["status"] = status
                self.save_orders()
                return True
        return False

    def mark_reorder_pending(self, uuid, next_check_at):
        """증권사 전략 주문을 다음 정규장 재주문 대기 상태로 전환"""
        for o in self.orders:
            if o["uuid"] == uuid:
                o["status"] = "pending_reorder"
                o["next_check_at"] = float(next_check_at)
                self.save_orders()
                return True
        return False

    def update_next_check_at(self, uuid, next_check_at):
        for o in self.orders:
            if o["uuid"] == uuid:
                o["next_check_at"] = float(next_check_at)
                self.save_orders()
                return True
        return False

    def replace_order_uuid(self, old_uuid, new_uuid):
        """재주문 성공 시 기존 전략 의도는 유지하고 거래소 주문 ID만 교체"""
        for o in self.orders:
            if o["uuid"] == old_uuid:
                o["reorder_of"] = old_uuid
                o["uuid"] = new_uuid
                o["status"] = "wait"
                o["next_check_at"] = 0.0
                o["created_at"] = time.time()
                self.save_orders()
                return True
        return False

    def remove_order(self, uuid, save=True):
        before = len(self.orders)
        self.orders = [o for o in self.orders if o["uuid"] != uuid]
        if save and len(self.orders) != before:
            self.save_orders()
        return len(self.orders) != before

    def get_user_orders(self, user_id, exchange=None):
        if exchange:
            return [o for o in self.orders if o["user_id"] == str(user_id) and o["exchange"] == exchange]
        return [o for o in self.orders if o["user_id"] == str(user_id)]

    def get_strategy_orders(self, user_id, strategy):
        """특정 전략으로 실행 중인 모든 주문 조회"""
        return [o for o in self.orders if o["user_id"] == str(user_id) and o["strategy"] == strategy]
