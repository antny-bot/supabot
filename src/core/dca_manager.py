"""정기 매수/매도(DCA·적립식/분할 매매) 스케줄 관리자 및 실행 엔진.

단일 종목에 대해 매일(daily), 특정 요일(days), 매주(weekly), 매월 1회(monthly) 주기로
현재가 기준 지정가(슬리피지 버퍼 적용) 매수/매도 주문을 자동 발행한다.
"""
import asyncio
import calendar
import json
import os
import re
import time
import uuid as _uuid
from datetime import datetime, timedelta

from core.bot_logger import get_logger
from core.db import get_db, is_db_available
from core.operational_events import append_operational_event
from core.parsers import (
    KST,
    exchange_display_name,
    is_us_stock_ticker,
    parse_number,
    validate_max_order,
)
from core import trading_gate

_log = get_logger("dca_manager")

_bg_tasks: set = set()


def _track_task(task):
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


WEEKDAY_KO_NAMES = ["월", "화", "수", "목", "금", "토", "일"]
_WEEKDAY_TOKEN_MAP = {
    "월": 0, "월요일": 0, "mon": 0, "monday": 0,
    "화": 1, "화요일": 1, "tue": 1, "tuesday": 1,
    "수": 2, "수요일": 2, "wed": 2, "wednesday": 2,
    "목": 3, "목요일": 3, "thu": 3, "thursday": 3,
    "금": 4, "금요일": 4, "fri": 4, "friday": 4,
    "토": 5, "토요일": 5, "sat": 5, "saturday": 5,
    "일": 6, "일요일": 6, "sun": 6, "sunday": 6,
}

DEFAULT_DCA_EXEC_TIME = "09:05"
_DCA_RETRY_DELAY_SECONDS = 300
_DCA_MAX_CONSECUTIVE_FAILS = 3
_dca_fail_counts: dict[str, int] = {}


def parse_dca_schedule(raw: str) -> dict:
    """주기 문자열을 파싱하여 {frequency, days_of_week, day_of_month} 딕셔너리를 반환한다.

    지원 형식 예시:
    - 매일: "매일", "daily", "every", "1d"
    - 매주 1회: "매주월", "매주금요일", "매주:수", "월요일", "월", "weekly:mon", "매주"
    - 특정 요일: "월,수,금", "월수금", "화목", "평일", "주말", "mon,wed,fri"
    - 매월 1회: "매월15일", "매월1일", "15일", "매월말일", "말일", "monthly:15", "매월"
    """
    text = str(raw or "").strip().lower()
    if not text:
        raise ValueError("주기를 입력해 주세요. (예: 매일, 매주월, 월수금, 매월15일)")

    # 1. 매일
    if text in ("매일", "매일마다", "daily", "every", "everyday", "1d"):
        return {"frequency": "daily", "days_of_week": None, "day_of_month": None}

    # 2. 평일 / 주말
    if text in ("평일", "주중", "weekdays", "weekday"):
        return {"frequency": "days", "days_of_week": [0, 1, 2, 3, 4], "day_of_month": None}
    if text in ("주말", "weekend", "weekends"):
        return {"frequency": "days", "days_of_week": [5, 6], "day_of_month": None}

    # 3. 매월 N일 / 말일
    if text in ("매월", "월간", "monthly"):
        return {"frequency": "monthly", "days_of_week": None, "day_of_month": 1}
    if text in ("매월말일", "매월말", "말일", "월말", "monthly:last"):
        return {"frequency": "monthly", "days_of_week": None, "day_of_month": 31}

    m_month = re.match(r"^(?:매월|월간|monthly)?[:\s_-]*(\d{1,2})일?$", text)
    if m_month and ("매월" in text or "월간" in text or "monthly" in text or text.endswith("일")):
        day_num = int(m_month.group(1))
        if not 1 <= day_num <= 31:
            raise ValueError("매월 실행일은 1~31 사이여야 합니다.")
        return {"frequency": "monthly", "days_of_week": None, "day_of_month": day_num}

    # 4. 매주 / 특정 요일
    if text in ("매주", "주간", "weekly"):
        return {"frequency": "weekly", "days_of_week": [0], "day_of_month": None}

    cleaned = re.sub(r"^(?:매주|주간|weekly)[:\s_-]*", "", text).strip()
    if "," in cleaned or "/" in cleaned or "·" in cleaned:
        parts = [p.strip() for p in re.split(r"[,/·]+", cleaned) if p.strip()]
        days = []
        for p in parts:
            if p not in _WEEKDAY_TOKEN_MAP:
                raise ValueError(f"알 수 없는 요일입니다: {p}")
            days.append(_WEEKDAY_TOKEN_MAP[p])
        unique_days = sorted(set(days))
        freq = "weekly" if len(unique_days) == 1 else "days"
        return {"frequency": freq, "days_of_week": unique_days, "day_of_month": None}

    if cleaned in _WEEKDAY_TOKEN_MAP:
        return {"frequency": "weekly", "days_of_week": [_WEEKDAY_TOKEN_MAP[cleaned]], "day_of_month": None}

    # 붙여 쓴 한글 요일 조합 (예: "월수금", "화목", "월화수목금")
    if all(ch in "월화수목금토일" for ch in cleaned) and len(cleaned) >= 1:
        unique_days = sorted({_WEEKDAY_TOKEN_MAP[ch] for ch in cleaned})
        freq = "weekly" if len(unique_days) == 1 else "days"
        return {"frequency": freq, "days_of_week": unique_days, "day_of_month": None}

    raise ValueError(
        "지원하지 않는 주기 형식입니다.\n"
        "예: 매일, 매주월, 월수금, 평일, 매월15일, 매월말일"
    )


def format_dca_schedule(sched: dict) -> str:
    """스케줄의 주기 및 시각을 한국어 설명 문자열로 포매팅한다."""
    freq = sched.get("frequency", "daily")
    exec_time = sched.get("exec_time") or DEFAULT_DCA_EXEC_TIME
    if freq == "daily":
        freq_str = "매일"
    elif freq == "weekly":
        days = sched.get("days_of_week") or [0]
        day_name = WEEKDAY_KO_NAMES[int(days[0]) % 7]
        freq_str = f"매주 {day_name}요일"
    elif freq == "days":
        days = sched.get("days_of_week") or []
        if days == [0, 1, 2, 3, 4]:
            freq_str = "평일(월~금)"
        elif days == [5, 6]:
            freq_str = "주말(토·일)"
        else:
            names = ",".join(WEEKDAY_KO_NAMES[int(d) % 7] for d in days)
            freq_str = f"매주 {names}요일"
    elif freq == "monthly":
        dom = int(sched.get("day_of_month") or 1)
        freq_str = "매월 말일" if dom >= 31 else f"매월 {dom}일"
    else:
        freq_str = str(freq)
    return f"{freq_str} {exec_time} (KST)"


def parse_dca_amount(raw: str) -> tuple[str, float]:
    """금액(예산) 또는 수량 문자열을 파싱하여 (amount_type, amount) 튜플을 반환한다.

    - 수량 기준("volume"): "2주", "0.01개", "0.5코인", "qty:2", "수량:0.5"
    - 금액 기준("budget"): "10만", "10만원", "50000", "50000원", "$100", "100달러"
    """
    text = str(raw or "").strip()
    if not text:
        raise ValueError("주문 금액 또는 수량을 입력해 주세요.")

    lowered = text.lower()
    for prefix in ("qty:", "vol:", "volume:", "수량:"):
        if lowered.startswith(prefix):
            val = parse_number(text[len(prefix):].rstrip("주개코인씩 "))
            if val <= 0:
                raise ValueError("수량은 0보다 커야 합니다.")
            return "volume", float(val)

    m_vol = re.match(r"^([0-9][0-9,._]*)\s*(주|개|코인)(?:씩)?$", text)
    if m_vol:
        val = parse_number(m_vol.group(1))
        if val <= 0:
            raise ValueError("수량은 0보다 커야 합니다.")
        return "volume", float(val)

    cleaned = text.lstrip("$").strip()
    cleaned = re.sub(r"(?:달러|불|원)?(?:씩|어치)?$", "", cleaned).strip()
    val = parse_number(cleaned)
    if val <= 0:
        raise ValueError("금액은 0보다 커야 합니다.")
    return "budget", float(val)


def parse_dca_time(raw: str) -> str:
    """실행 시각 문자열을 HH:MM 형식으로 정규화한다."""
    text = str(raw or "").strip()
    m_colon = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if m_colon:
        h, m = int(m_colon.group(1)), int(m_colon.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
        raise ValueError("시간은 00:00 ~ 23:59 범위여야 합니다.")

    m_ko = re.match(r"^(\d{1,2})시(?:\s*(\d{1,2})분?)?$", text)
    if m_ko:
        h = int(m_ko.group(1))
        m = int(m_ko.group(2) or 0)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
        raise ValueError("시간은 00:00 ~ 23:59 범위여야 합니다.")

    raise ValueError("실행 시각은 HH:MM (예: 09:05, 14:00) 형식으로 입력해 주세요.")


def is_dca_time_token(raw: str) -> bool:
    try:
        parse_dca_time(raw)
        return True
    except ValueError:
        return False


def parse_dca_max_runs(raw: str) -> int | None:
    """총 실행 횟수 문자열을 파싱한다. (예: '10회', '12번', '무기한')"""
    text = str(raw or "").strip().lower()
    if text in ("", "-", "무기한", "무제한", "infinite", "unlimited", "none"):
        return None
    for prefix in ("count:", "runs:", "횟수:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    m = re.match(r"^(\d+)\s*(?:회|번|회분)?$", text)
    if m:
        val = int(m.group(1))
        if val <= 0:
            raise ValueError("총 실행 횟수는 1회 이상이어야 합니다.")
        return val
    raise ValueError("총 실행 횟수는 '10회' 같은 숫자 형식으로 입력해 주세요.")


def is_dca_max_runs_token(raw: str) -> bool:
    text = str(raw or "").strip().lower()
    if text in ("무기한", "무제한", "infinite", "unlimited"):
        return True
    if text.startswith(("count:", "runs:", "횟수:")):
        return True
    return bool(re.match(r"^\d+\s*(?:회|번|회분)$", text))


def compute_next_run_at(
    frequency: str,
    exec_time: str = DEFAULT_DCA_EXEC_TIME,
    days_of_week: list[int] | None = None,
    day_of_month: int | None = None,
    now: datetime | float | None = None,
    after_current: bool = False,
) -> float:
    """KST 기준 다음 실행 예정 시각의 Unix timestamp를 계산한다.

    after_current=True 이면 오늘/이번 주기가 아직 안 지났더라도 무조건 다음 주기로 넘긴다
    (방금 주문을 실행한 직후 다음 회차 시각을 구할 때 사용).
    """
    if now is None:
        now_dt = datetime.now(KST)
    elif isinstance(now, (int, float)):
        now_dt = datetime.fromtimestamp(float(now), tz=KST)
    elif getattr(now, "tzinfo", None) is None:
        now_dt = now.replace(tzinfo=KST)
    else:
        now_dt = now.astimezone(KST)

    h_str, m_str = (exec_time or DEFAULT_DCA_EXEC_TIME).split(":")
    hour, minute = int(h_str), int(m_str)

    if frequency == "daily":
        candidate = now_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if after_current or candidate <= now_dt:
            candidate += timedelta(days=1)
        return candidate.timestamp()

    if frequency in ("weekly", "days"):
        target_days = sorted(set(int(d) % 7 for d in (days_of_week or [0])))
        for offset in range(0, 8):
            day_dt = now_dt + timedelta(days=offset)
            if day_dt.weekday() not in target_days:
                continue
            candidate = day_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if offset == 0 and (after_current or candidate <= now_dt):
                continue
            return candidate.timestamp()
        # fallback
        return (now_dt + timedelta(days=7)).replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()

    if frequency == "monthly":
        dom = max(1, min(int(day_of_month or 1), 31))
        year, month = now_dt.year, now_dt.month
        last_day = calendar.monthrange(year, month)[1]
        candidate = now_dt.replace(
            day=min(dom, last_day), hour=hour, minute=minute, second=0, microsecond=0
        )
        if after_current or candidate <= now_dt:
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            last_day_next = calendar.monthrange(year, month)[1]
            candidate = candidate.replace(year=year, month=month, day=min(dom, last_day_next))
        return candidate.timestamp()

    raise ValueError(f"Unsupported DCA frequency: {frequency}")


class DcaManager:
    """정기 매수/매도 스케줄 상태 관리 (Supabase DB 우선 + 로컬 JSON 파일 폴백)."""

    def __init__(self, file_path: str = "data/dca_schedules.json"):
        self.file_path = file_path
        self._db_table_supported = True
        self.schedules: list[dict] = self._load_schedules()
        self.on_schedule_changed = None

    def _load_schedules(self) -> list[dict]:
        if is_db_available() and self._db_table_supported:
            try:
                rows = get_db().table("dca_schedules").select("*").execute().data or []
                _log.info("Loaded DCA schedules from DB", extra={"event": "dca_loaded_db", "count": len(rows)})
                return rows
            except Exception as e:
                _log.warning("Failed to load dca_schedules from DB, falling back to file: %s", e)
        return self._load_from_file()

    def _load_from_file(self) -> list[dict]:
        if not os.path.exists(self.file_path):
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception as e:
            _log.error("Failed to load DCA schedules from file", exc_info=e)
            return []

    def _save_to_file(self):
        dir_name = os.path.dirname(self.file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.schedules, f, indent=2, ensure_ascii=False)
            os.chmod(self.file_path, 0o600)
        except Exception as e:
            _log.error("Failed to save DCA schedules to file", exc_info=e)

    def _db_upsert(self, sched: dict):
        self._save_to_file()
        if not is_db_available() or not self._db_table_supported:
            return

        sched_copy = dict(sched)

        async def _run():
            try:
                await get_db().table("dca_schedules").upsert(sched_copy).execute_async()
            except Exception as e:
                _log.warning("Failed to upsert dca_schedule to DB (using file fallback): %s", e)

        try:
            loop = asyncio.get_running_loop()
            _track_task(loop.create_task(_run()))
        except RuntimeError:
            try:
                get_db().table("dca_schedules").upsert(sched_copy).execute()
            except Exception as e:
                _log.warning("Failed to upsert dca_schedule in sync fallback: %s", e)

    def _db_delete(self, schedule_id: str):
        self._save_to_file()
        if not is_db_available() or not self._db_table_supported:
            return

        async def _run():
            try:
                await get_db().table("dca_schedules").delete().eq("id", schedule_id).execute_async()
            except Exception as e:
                _log.warning("Failed to delete dca_schedule from DB: %s", e)

        try:
            loop = asyncio.get_running_loop()
            _track_task(loop.create_task(_run()))
        except RuntimeError:
            try:
                get_db().table("dca_schedules").delete().eq("id", schedule_id).execute()
            except Exception as e:
                _log.warning("Failed to delete dca_schedule in sync fallback: %s", e)

    async def reload_from_db_async(self) -> bool:
        if not is_db_available() or not self._db_table_supported:
            return False
        pending = [t for t in list(_bg_tasks) if not t.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        try:
            res = await get_db().table("dca_schedules").select("*").execute_async()
            self.schedules = res.data or []
            return True
        except Exception as e:
            _log.debug("Failed to reload dca_schedules from DB (using local state): %s", e)
            return False

    def get_next_group_no(self, user_id: str, order_manager=None) -> int:
        uid = str(user_id)
        nums = [
            int(s["group_no"])
            for s in self.schedules
            if str(s.get("user_id")) == uid and s.get("group_no")
        ]
        if order_manager is not None and hasattr(order_manager, "get_next_group_no"):
            try:
                om_next = int(order_manager.get_next_group_no(uid))
                if om_next > 1:
                    nums.append(om_next - 1)
            except Exception:
                pass
        try:
            from core.trade_log import read_trades
            for t in read_trades(uid, period="all"):
                if t.get("group_no"):
                    nums.append(int(t["group_no"]))
        except Exception:
            pass
        return (max(nums) + 1) if nums else 1

    def add_schedule(
        self,
        *,
        user_id: str,
        exchange: str,
        ticker: str,
        side: str,
        frequency: str,
        amount_type: str,
        amount: float,
        exec_time: str = DEFAULT_DCA_EXEC_TIME,
        days_of_week: list[int] | None = None,
        day_of_month: int | None = None,
        max_runs: int | None = None,
        group_no: int | None = None,
        now: float | None = None,
    ) -> dict:
        now_ts = float(now if now is not None else time.time())
        next_run = compute_next_run_at(
            frequency=frequency,
            exec_time=exec_time,
            days_of_week=days_of_week,
            day_of_month=day_of_month,
            now=now_ts,
            after_current=False,
        )
        if group_no is None:
            group_no = self.get_next_group_no(user_id)
        sched_id = f"dca_{_uuid.uuid4().hex[:8]}"
        sched = {
            "id": sched_id,
            "user_id": str(user_id),
            "exchange": exchange,
            "ticker": ticker,
            "side": "ask" if side in ("ask", "sell", "매도") else "bid",
            "frequency": frequency,
            "days_of_week": list(days_of_week) if days_of_week is not None else None,
            "day_of_month": int(day_of_month) if day_of_month is not None else None,
            "exec_time": exec_time,
            "amount_type": amount_type,
            "amount": float(amount),
            "max_runs": int(max_runs) if max_runs is not None else None,
            "run_count": 0,
            "next_run_at": float(next_run),
            "last_run_at": None,
            "status": "active",
            "group_no": int(group_no),
            "created_at": now_ts,
        }
        self.schedules.append(sched)
        self._db_upsert(sched)
        if self.on_schedule_changed:
            self.on_schedule_changed()
        return sched

    def get_schedule_by_group_no(self, user_id: str, group_no: int) -> dict | None:
        uid = str(user_id)
        target = int(group_no)
        for s in self.schedules:
            if str(s.get("user_id")) == uid and s.get("group_no") is not None and int(s["group_no"]) == target:
                return s
        return None

    def get_user_schedules(self, user_id: str, exchange: str | None = None, active_only: bool = True) -> list[dict]:
        uid = str(user_id)
        results = []
        for s in self.schedules:
            if str(s.get("user_id")) != uid:
                continue
            if exchange and s.get("exchange") != exchange:
                continue
            if active_only and s.get("status") != "active":
                continue
            results.append(s)
        return results

    def get_schedule(self, schedule_id: str, user_id: str | None = None) -> dict | None:
        for s in self.schedules:
            if s.get("id") == schedule_id:
                if user_id is not None and str(s.get("user_id")) != str(user_id):
                    return None
                return s
        return None

    def remove_schedule(self, schedule_id: str, user_id: str | None = None) -> bool:
        target = self.get_schedule(schedule_id, user_id=user_id)
        if not target:
            return False
        self.schedules = [s for s in self.schedules if s.get("id") != schedule_id]
        _dca_fail_counts.pop(schedule_id, None)
        self._db_delete(schedule_id)
        if self.on_schedule_changed:
            self.on_schedule_changed()
        return True

    def defer_schedule(self, schedule_id: str, next_run_at: float) -> bool:
        for s in self.schedules:
            if s.get("id") == schedule_id:
                s["next_run_at"] = float(next_run_at)
                self._db_upsert(s)
                return True
        return False

    def advance_schedule(self, schedule_id: str, now_ts: float | None = None, increment_run: bool = True) -> dict | None:
        """회차 실행(또는 스킵) 후 다음 주기로 next_run_at을 갱신한다.
        max_runs에 도달하면 status='completed'로 전환하고 목록에서 제거한다.
        """
        now_val = float(now_ts if now_ts is not None else time.time())
        for s in list(self.schedules):
            if s.get("id") != schedule_id:
                continue
            if increment_run:
                s["run_count"] = int(s.get("run_count") or 0) + 1
                s["last_run_at"] = now_val
            max_runs = s.get("max_runs")
            if max_runs is not None and int(s.get("run_count") or 0) >= int(max_runs):
                s["status"] = "completed"
                self.schedules = [x for x in self.schedules if x.get("id") != schedule_id]
                _dca_fail_counts.pop(schedule_id, None)
                self._db_delete(schedule_id)
                return s
            s["next_run_at"] = compute_next_run_at(
                frequency=s["frequency"],
                exec_time=s.get("exec_time") or DEFAULT_DCA_EXEC_TIME,
                days_of_week=s.get("days_of_week"),
                day_of_month=s.get("day_of_month"),
                now=now_val,
                after_current=True,
            )
            self._db_upsert(s)
            return s
        return None

    def clear_user_schedules(self, user_id: str) -> int:
        uid = str(user_id)
        ids = [s["id"] for s in self.schedules if str(s.get("user_id")) == uid]
        self.schedules = [s for s in self.schedules if str(s.get("user_id")) != uid]
        for sid in ids:
            _dca_fail_counts.pop(sid, None)
            self._db_delete(sid)
        return len(ids)

    def nearest_next_run_delay(self, now_ts: float | None = None) -> float | None:
        """활성 스케줄 중 가장 빨리 도래하는 시각까지 남은 초(seconds)를 반환한다."""
        now_val = float(now_ts if now_ts is not None else time.time())
        active_times = [
            float(s.get("next_run_at") or 0)
            for s in self.schedules
            if s.get("status") == "active"
        ]
        if not active_times:
            return None
        return max(1.0, min(active_times) - now_val)


def _compute_dca_limit_price(ex_obj, exchange: str, ticker: str, side: str, current_price: float, ticker_info: dict | None = None) -> float:
    """현재가 기준 슬리피지 버퍼(0.1%)를 적용한 지정가를 산출한다.
    - 매수(bid): 현재가 × 1.001 (호가 내림 시 현재가보다 낮아지면 현재가 이상으로 보정, 상한가 이하 클램핑)
    - 매도(ask): 현재가 × 0.999 (하한가 이상 클램핑)
    """
    if side == "bid":
        raw_price = current_price * 1.001
        price = float(ex_obj.adjust_price_to_tick(raw_price, ticker))
        cur_tick_price = float(ex_obj.adjust_price_to_tick(current_price, ticker))
        if price < cur_tick_price:
            price = cur_tick_price
        if ticker_info and ticker_info.get("upper_limit_price"):
            upper = float(ticker_info["upper_limit_price"])
            if upper > 0 and price > upper:
                price = float(ex_obj.adjust_price_to_tick(upper, ticker))
    else:
        raw_price = current_price * 0.999
        price = float(ex_obj.adjust_price_to_tick(raw_price, ticker))
        if price <= 0:
            price = float(ex_obj.adjust_price_to_tick(current_price, ticker))
        if ticker_info and ticker_info.get("lower_limit_price"):
            lower = float(ticker_info["lower_limit_price"])
            if lower > 0 and price < lower:
                price = float(ex_obj.adjust_price_to_tick(lower, ticker))
    return price


async def execute_due_dca_schedules(
    application,
    dca_manager: DcaManager,
    exchange_adapter,
    order_manager,
    user_manager,
    now_ts: float | None = None,
) -> int:
    """실행 시각(next_run_at)이 도래한 정기 매수/매도 스케줄을 실행한다."""
    now_val = float(now_ts if now_ts is not None else time.time())
    due_list = [
        dict(s) for s in dca_manager.schedules
        if s.get("status") == "active" and float(s.get("next_run_at") or 0) <= now_val
    ]
    if not due_list:
        return 0

    executed_count = 0
    for sched in due_list:
        sched_id = sched["id"]
        if not dca_manager.get_schedule(sched_id):
            continue

        # 1. 글로벌 거래 중지(kill-switch) 확인
        if trading_gate.is_trading_halted():
            dca_manager.defer_schedule(sched_id, now_val + _DCA_RETRY_DELAY_SECONDS)
            continue

        user_id = str(sched["user_id"])
        exchange = sched["exchange"]
        ticker = sched["ticker"]
        side = sched.get("side", "bid")
        action_label = "매수" if side == "bid" else "매도"
        ex_label = exchange_display_name(exchange)

        user = user_manager.get_user(user_id)
        if not user or not user.get("is_active"):
            dca_manager.remove_schedule(sched_id)
            continue

        ex_obj = exchange_adapter.get_exchange(exchange)
        if ex_obj is None:
            dca_manager.remove_schedule(sched_id)
            continue

        if exchange == "toss" and str(ticker).isdigit():
            await exchange_adapter.ensure_toss_kr_calendar(user_id)

        # 2. 주식 거래소 정규장 오픈 여부 확인 -> 휴장일/장외 시간이면 다음 개장 시각으로 연기
        if not ex_obj.is_market_open(ticker) or not getattr(ex_obj, "is_order_placement_allowed", lambda t: True)(ticker):
            next_open = ex_obj.next_check_timestamp(ticker)
            if next_open <= now_val:
                next_open = now_val + _DCA_RETRY_DELAY_SECONDS
            dca_manager.defer_schedule(sched_id, next_open)
            continue

        # 3. 현재가 조회
        try:
            ticker_info = await exchange_adapter.get_ticker(exchange, ticker, user_id=user_id)
        except Exception as e:
            _log.warning("DCA ticker fetch failed for %s %s: %s", exchange, ticker, e)
            ticker_info = None

        current_price = float(ticker_info.get("trade_price", 0)) if ticker_info else 0.0
        if current_price <= 0:
            fails = _dca_fail_counts.get(sched_id, 0) + 1
            _dca_fail_counts[sched_id] = fails
            if fails >= _DCA_MAX_CONSECUTIVE_FAILS:
                _dca_fail_counts.pop(sched_id, None)
                dca_manager.advance_schedule(sched_id, now_ts=now_val, increment_run=False)
                await _safe_notify(
                    application, user_id,
                    f"⚠️ [{ex_label}] {ticker} 정기 {action_label} 건너뜀\n"
                    f"• 사유: 현재가 조회 {fails}회 연속 실패\n"
                    f"• 다음 예정 시각에 다시 실행됩니다.",
                )
            else:
                dca_manager.defer_schedule(sched_id, now_val + _DCA_RETRY_DELAY_SECONDS)
            continue

        # 4. 목표 지정가 및 주문 수량 계산
        price = _compute_dca_limit_price(ex_obj, exchange, ticker, side, current_price, ticker_info)
        amount_type = sched.get("amount_type", "budget")
        raw_amount = float(sched.get("amount") or 0)

        if amount_type == "volume":
            volume = ex_obj.round_volume(raw_amount)
        else:
            effective_budget = raw_amount * 0.999 if side == "bid" else raw_amount
            volume = ex_obj.round_volume(effective_budget / price) if price > 0 else 0

        is_usd = is_us_stock_ticker(exchange, ticker)
        if ex_obj.requires_integer_volume() and volume <= 0:
            dca_manager.advance_schedule(sched_id, now_ts=now_val, increment_run=False)
            price_str = f"${price:,.2f}" if is_usd else f"{price:,.0f}원"
            budget_str = f"${raw_amount:,.2f}" if is_usd else f"{raw_amount:,.0f}원"
            await _safe_notify(
                application, user_id,
                f"⚠️ [{ex_label}] {ticker} 정기 {action_label} 건너뜀\n"
                f"• 사유: 설정 예산({budget_str})이 1주 가격({price_str})보다 적어 주문 수량이 0주입니다.\n"
                f"• 다음 주기에 다시 시도합니다.",
            )
            continue

        if volume <= 0:
            dca_manager.advance_schedule(sched_id, now_ts=now_val, increment_run=False)
            continue

        order_total = price * volume
        min_amt = exchange_adapter.get_min_order_amount(exchange)
        if not is_usd and order_total < min_amt:
            dca_manager.advance_schedule(sched_id, now_ts=now_val, increment_run=False)
            await _safe_notify(
                application, user_id,
                f"⚠️ [{ex_label}] {ticker} 정기 {action_label} 건너뜀\n"
                f"• 사유: 주문 금액({order_total:,.0f}원)이 최소 주문 금액({min_amt:,.0f}원) 미만입니다.",
            )
            continue

        if side == "bid":
            ok, err_msg = validate_max_order(user, order_total, is_usd=is_usd)
            if not ok:
                dca_manager.advance_schedule(sched_id, now_ts=now_val, increment_run=False)
                await _safe_notify(application, user_id, f"⚠️ [{ex_label}] {ticker} 정기 매수 보류\n• {err_msg}")
                continue
            gate_ok, gate_msg = trading_gate.check_can_place_order(
                user, order_manager.get_user_orders(user_id), order_total, is_usd=is_usd
            )
            if not gate_ok:
                dca_manager.advance_schedule(sched_id, now_ts=now_val, increment_run=False)
                await _safe_notify(application, user_id, f"⚠️ [{ex_label}] {ticker} 정기 매수 보류\n• {gate_msg}")
                continue

        # 5. 실주문 제출
        try:
            res = await exchange_adapter.create_order(user_id, exchange, ticker, side, price, volume)
        except Exception as e:
            _log.error("DCA order placement exception for %s %s", exchange, ticker, exc_info=e)
            res = None

        if res and "uuid" in res:
            _dca_fail_counts.pop(sched_id, None)
            group_no = sched.get("group_no")
            order_manager.add_order(
                user_id, exchange, ticker, res["uuid"], price, volume,
                side=side, strategy="dca", status="wait", group_no=group_no,
            )
            updated = dca_manager.advance_schedule(sched_id, now_ts=now_val, increment_run=True)
            executed_count += 1

            run_count = updated["run_count"] if updated else int(sched.get("run_count") or 0) + 1
            max_runs = sched.get("max_runs")
            progress_str = f"{run_count}/{max_runs}회" if max_runs else f"누적 {run_count}회"
            price_str = f"${price:,.2f}" if is_usd else f"{price:,.0f}원"
            vol_str = f"{int(volume):,}주" if ex_obj.requires_integer_volume() else f"{volume:.4f}개"
            group_tag = f" [#{group_no}]" if group_no else ""

            done_note = ""
            if updated and updated.get("status") == "completed":
                done_note = f"\n🎉 설정한 총 {max_runs}회 실행이 모두 완료되어 전략이 종료되었습니다."
            elif updated:
                next_dt = datetime.fromtimestamp(updated["next_run_at"], tz=KST).strftime("%Y-%m-%d %H:%M")
                done_note = f"\n• 다음 실행: {next_dt} (KST)"

            await _safe_notify(
                application, user_id,
                f"📅 [{ex_label}] {ticker} 정기 {action_label} 주문 접수{group_tag} ({progress_str})\n"
                f"• 주문가: {price_str} (현재가 기준 지정가)\n"
                f"• 수량: {vol_str}"
                f"{done_note}",
            )
        else:
            fails = _dca_fail_counts.get(sched_id, 0) + 1
            _dca_fail_counts[sched_id] = fails
            append_operational_event("warning", "dca_manager", f"DCA order failed ({fails})", f"{exchange} {ticker} {side}")
            if fails >= _DCA_MAX_CONSECUTIVE_FAILS:
                _dca_fail_counts.pop(sched_id, None)
                dca_manager.advance_schedule(sched_id, now_ts=now_val, increment_run=False)
                await _safe_notify(
                    application, user_id,
                    f"❌ [{ex_label}] {ticker} 정기 {action_label} 주문 {fails}회 연속 실패로 이번 회차를 건너뜁니다.\n"
                    f"• 잔고 또는 API 키 상태를 확인해 주세요.",
                )
            else:
                dca_manager.defer_schedule(sched_id, now_val + _DCA_RETRY_DELAY_SECONDS)

        await asyncio.sleep(0.2)

    return executed_count


async def _safe_notify(application, chat_id: str, text: str):
    if not application or not getattr(application, "bot", None):
        return
    try:
        await application.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        _log.warning("Failed to send DCA notification to %s: %s", chat_id, e)


# ── 예수금(가용 현금) 일일 점검 및 전략 모니터링 가이드 ────────────────────────

_USD_KRW_APPROX = 1380.0
_daily_cash_alert_sent: dict[tuple[str, str], str] = {}  # (user_id, exchange) -> "YYYY-MM-DD"
_cash_last_checked_ts: dict[str, float] = {}  # user_id -> timestamp
_CASH_CHECK_INTERVAL_SECONDS = 3600.0  # 백그라운드 루프 내 유저별 최소 재점검 간격 (1시간)


def extract_available_cash(exchange: str, balances) -> float | None:
    """거래소 잔고 응답에서 주문 가능한 가용 예수금(KRW)을 추출한다.
    - 업비트/빗썸(list): currency=='KRW' 항목의 balance (locked 제외 가용 금액)
    - 한국투자증권/토스증권(dict): cash 필드
    조회 실패(None) 시 None 반환.
    """
    if balances is None:
        return None
    if exchange in ("kis", "toss"):
        if isinstance(balances, dict):
            try:
                return float(balances.get("cash", 0.0) or 0.0)
            except (TypeError, ValueError):
                return 0.0
        return None
    if isinstance(balances, list):
        for item in balances:
            if isinstance(item, dict) and str(item.get("currency", "")).upper() == "KRW":
                try:
                    return float(item.get("balance", 0.0) or 0.0)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0
    return None


def _runs_in_next_7_days(sched: dict, now_ts: float) -> int:
    """향후 7일 동안 해당 스케줄이 실행될 예상 횟수를 반환한다."""
    freq = sched.get("frequency", "daily")
    if freq == "daily":
        runs = 7
    elif freq == "weekly":
        runs = 1
    elif freq == "days":
        days = sched.get("days_of_week") or []
        runs = max(1, len(days))
    elif freq == "monthly":
        next_run = float(sched.get("next_run_at") or 0)
        runs = 1 if (next_run > 0 and next_run <= now_ts + 7 * 86400) else 1
    else:
        runs = 1

    max_runs = sched.get("max_runs")
    if max_runs is not None:
        rem = max(0, int(max_runs) - int(sched.get("run_count") or 0))
        runs = min(runs, rem)
    return runs


async def analyze_user_cash_sufficiency(
    user_id: str,
    dca_manager: DcaManager | None,
    order_manager,
    exchange_adapter,
    now_ts: float | None = None,
) -> list[dict]:
    """유저의 활성 매수 전략(정기 매수 DCA + 장외예약/재주문대기 매수 주문) 대비
    거래소별 예수금(가용 현금) 충분 여부를 분석해 가이드 리스트를 반환한다.
    """
    now_val = float(now_ts if now_ts is not None else time.time())
    uid = str(user_id)

    active_bid_dca = []
    if dca_manager is not None:
        active_bid_dca = [
            s for s in dca_manager.get_user_schedules(uid, active_only=True)
            if s.get("side", "bid") == "bid"
        ]

    user_orders = order_manager.get_user_orders(uid) if order_manager is not None else []
    # 아직 거래소에 제출되지 않아 예수금이 잠기지 않은 대기 전략 주문(예약/재주문대기/장외대기) 및 RSI 매수 주문
    pending_cash_orders = [
        o for o in user_orders
        if o.get("side") == "bid" and o.get("status") in ("reserved", "pending_reorder", "market_closed")
    ]

    target_exchanges = sorted(
        set(s["exchange"] for s in active_bid_dca)
        | set(o["exchange"] for o in pending_cash_orders)
    )
    if not target_exchanges:
        return []

    reports: list[dict] = []
    for ex in target_exchanges:
        try:
            balances = await exchange_adapter.get_balances(uid, ex) if exchange_adapter else None
        except Exception as e:
            _log.warning("Cash check get_balances failed for %s %s: %s", uid, ex, e)
            balances = None

        cash = extract_available_cash(ex, balances)
        if cash is None:
            continue

        ex_dca = [s for s in active_bid_dca if s["exchange"] == ex]
        ex_orders = [o for o in pending_cash_orders if o["exchange"] == ex]

        dca_next_krw = 0.0
        dca_weekly_krw = 0.0
        for s in ex_dca:
            tk = s["ticker"]
            is_usd = is_us_stock_ticker(ex, tk)
            amt_type = s.get("amount_type", "budget")
            raw_amt = float(s.get("amount") or 0.0)

            if amt_type == "budget":
                per_run_krw = raw_amt * _USD_KRW_APPROX if is_usd else raw_amt
            else:
                cur_price = 0.0
                if exchange_adapter:
                    try:
                        t_info = await exchange_adapter.get_ticker(ex, tk, user_id=uid)
                        cur_price = float(t_info.get("trade_price", 0) or 0) if t_info else 0.0
                    except Exception:
                        cur_price = 0.0
                per_run_krw = (cur_price * raw_amt * _USD_KRW_APPROX) if is_usd else (cur_price * raw_amt)

            runs_7d = _runs_in_next_7_days(s, now_val)
            dca_next_krw += per_run_krw
            dca_weekly_krw += per_run_krw * runs_7d

        reserved_krw = 0.0
        for o in ex_orders:
            tk = o["ticker"]
            is_usd = is_us_stock_ticker(ex, tk)
            o_val = float(o.get("price") or 0.0) * float(o.get("volume") or 0.0)
            reserved_krw += (o_val * _USD_KRW_APPROX) if is_usd else o_val

        next_required_krw = dca_next_krw + reserved_krw
        weekly_required_krw = dca_weekly_krw + reserved_krw

        shortfall_next = max(0.0, next_required_krw - cash)
        shortfall_weekly = max(0.0, weekly_required_krw - cash)

        if dca_next_krw > 0:
            avail_after_reserved = max(0.0, cash - reserved_krw)
            estimated_runs_left = int(avail_after_reserved // dca_next_krw)
        else:
            estimated_runs_left = None

        ex_label = exchange_display_name(ex)
        if shortfall_next > 0:
            status = "short_next"
            guide_msg = (
                f"🚨 [{ex_label}] 예수금 부족! "
                f"현재 가용 {cash:,.0f}원 / 다음 매수 필요 {next_required_krw:,.0f}원 "
                f"→ 최소 {shortfall_next:,.0f}원(7일 권장 {shortfall_weekly:,.0f}원)을 계좌에 채워주세요."
            )
        elif shortfall_weekly > 0:
            status = "warn_weekly"
            runs_note = f" (현재 약 {estimated_runs_left}회 실행 가능)" if estimated_runs_left is not None else ""
            guide_msg = (
                f"⚠️ [{ex_label}] 향후 7일 예수금 부족 예상{runs_note}: "
                f"현재 가용 {cash:,.0f}원 / 7일 필요 {weekly_required_krw:,.0f}원 "
                f"→ 원활한 전략 실행을 위해 {shortfall_weekly:,.0f}원 이상 충전을 권장합니다."
            )
        else:
            status = "ok"
            runs_note = f" (약 {estimated_runs_left}회분 여유)" if estimated_runs_left is not None else ""
            guide_msg = (
                f"✅ [{ex_label}] 예수금 양호: 가용 {cash:,.0f}원 "
                f"(다음 1회 필요 {next_required_krw:,.0f}원 / 7일 필요 {weekly_required_krw:,.0f}원){runs_note}"
            )

        reports.append({
            "exchange": ex,
            "exchange_name": ex_label,
            "available_cash": round(cash),
            "next_required_krw": round(next_required_krw),
            "weekly_required_krw": round(weekly_required_krw),
            "shortfall_next_krw": round(shortfall_next),
            "shortfall_weekly_krw": round(shortfall_weekly),
            "estimated_runs_left": estimated_runs_left,
            "schedules_count": len(ex_dca),
            "reserved_orders_count": len(ex_orders),
            "status": status,
            "guide_message": guide_msg,
        })

    return reports


def format_cash_health_section(cash_reports: list[dict], html: bool = True) -> str:
    """전략 모니터링(/status, /dca, /report)에 표시할 예수금 점검 섹션 문자열을 생성한다."""
    if not cash_reports:
        return ""
    header = "💵 <b>계좌 예수금 & 전략 가용성 체크</b>" if html else "💵 [계좌 예수금 & 전략 가용성 체크]"
    lines = [header]
    for r in cash_reports:
        msg = r.get("guide_message", "")
        if html:
            import html as _html
            msg = _html.escape(msg)
            if r.get("status") == "short_next":
                msg = f"<b>{msg}</b>"
        lines.append(f"• {msg}")
    return "\n".join(lines)


async def check_daily_cash_alerts(
    application,
    dca_manager: DcaManager,
    order_manager,
    exchange_adapter,
    user_manager,
    now_ts: float | None = None,
) -> int:
    """매일 1회 활성 매수 전략을 가진 유저의 계좌 예수금을 점검하여,
    부족(short_next 또는 warn_weekly) 시 텔레그램 알람 및 충전 가이드를 발송한다.
    """
    now_val = float(now_ts if now_ts is not None else time.time())
    now_dt = datetime.fromtimestamp(now_val, tz=KST)
    today_str = now_dt.strftime("%Y-%m-%d")

    user_ids = set(
        str(s["user_id"]) for s in dca_manager.schedules
        if s.get("status") == "active" and s.get("side", "bid") == "bid"
    )
    if order_manager is not None:
        for o in order_manager.orders:
            if o.get("side") == "bid" and o.get("status") in ("reserved", "pending_reorder", "market_closed"):
                user_ids.add(str(o["user_id"]))

    sent_count = 0
    for uid in sorted(user_ids):
        user = user_manager.get_user(uid) if user_manager else None
        if not user or not user.get("is_active"):
            continue

        last_checked = _cash_last_checked_ts.get(uid, 0.0)
        if now_ts is None and (now_val - last_checked) < _CASH_CHECK_INTERVAL_SECONDS:
            continue
        _cash_last_checked_ts[uid] = now_val

        # 아직 오늘 알람을 안 보낸 거래소가 있는지 먼저 확인
        reports = await analyze_user_cash_sufficiency(uid, dca_manager, order_manager, exchange_adapter, now_ts=now_val)
        due_alerts = []
        for r in reports:
            if r["status"] in ("short_next", "warn_weekly"):
                dedup_key = (uid, r["exchange"])
                if _daily_cash_alert_sent.get(dedup_key) != today_str:
                    due_alerts.append(r)

        if not due_alerts:
            continue

        alert_lines = [
            f"🔔 [{today_str}] 전략 계좌 예수금 일일 점검 알림",
            "",
        ]
        for r in due_alerts:
            alert_lines.append(f"• {r['guide_message']}")
            _daily_cash_alert_sent[(uid, r["exchange"])] = today_str
            append_operational_event(
                "warning",
                "cash_monitor",
                f"Cash insufficiency ({r['status']}) on {r['exchange']}",
                r["guide_message"],
            )

        alert_lines.append("")
        alert_lines.append("💡 전략 주문이 예수금 부족으로 실패하지 않도록 미리 계좌에 입금해 주세요. (/status, /dca, /report에서도 상시 확인 가능)")
        await _safe_notify(application, uid, "\n".join(alert_lines))
        sent_count += 1

    return sent_count
