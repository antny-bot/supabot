"""In-memory metrics collector for operational observability."""
import threading
import time


class _MetricsCollector:
    def __init__(self):
        self._lock = threading.Lock()
        self._orders: dict = {}     # exchange → {"ok": int, "fail": int}
        self._latencies: dict = {}  # exchange → list[float] (ms, last 100)
        self._poll_ts: float | None = None
        self._signal_ts: float | None = None

    def record_order(self, exchange: str, ok: bool) -> None:
        with self._lock:
            bucket = self._orders.setdefault(exchange, {"ok": 0, "fail": 0})
            bucket["ok" if ok else "fail"] += 1

    def record_latency(self, exchange: str, ms: float) -> None:
        with self._lock:
            lst = self._latencies.setdefault(exchange, [])
            lst.append(ms)
            if len(lst) > 100:
                lst[:] = lst[-100:]

    def record_poll_ok(self) -> None:
        self._poll_ts = time.time()

    def record_signal_ok(self) -> None:
        self._signal_ts = time.time()

    def snapshot(self) -> dict:
        with self._lock:
            order_stats: dict = {}
            for ex, counts in self._orders.items():
                total = counts["ok"] + counts["fail"]
                order_stats[ex] = {
                    "ok": counts["ok"],
                    "fail": counts["fail"],
                    "total": total,
                    "success_rate": round(counts["ok"] / total * 100, 1) if total else None,
                }
            lat_stats: dict = {}
            for ex, lats in self._latencies.items():
                if lats:
                    s = sorted(lats)
                    lat_stats[ex] = {
                        "p50": s[len(s) // 2],
                        "p95": s[min(int(len(s) * 0.95), len(s) - 1)],
                        "count": len(s),
                    }
            return {
                "orders": order_stats,
                "latencies": lat_stats,
                "poll_last_ok": self._poll_ts,
                "signal_last_ok": self._signal_ts,
            }

    def ops_alerts(self, now: float | None = None) -> list:
        """Return alert strings for threshold breaches."""
        if now is None:
            now = time.time()
        issues = []
        snap = self.snapshot()
        for ex, s in snap["orders"].items():
            if s["total"] >= 5 and s["success_rate"] is not None and s["success_rate"] < 80:
                fail_rate = 100 - s["success_rate"]
                issues.append(
                    f"주문 실패율 높음 [{ex}]: {s['fail']}/{s['total']}건 "
                    f"({fail_rate:.0f}% 실패)"
                )
        poll_ts = snap.get("poll_last_ok")
        if poll_ts and now - poll_ts > 300:
            issues.append(
                f"주문 동기화 루프 {int((now - poll_ts) / 60)}분째 응답 없음"
            )
        sig_ts = snap.get("signal_last_ok")
        if sig_ts and now - sig_ts > 900:
            issues.append(
                f"신호 분석 루프 {int((now - sig_ts) / 60)}분째 응답 없음"
            )
        return issues


metrics = _MetricsCollector()
