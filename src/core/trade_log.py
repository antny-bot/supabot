import json
import os
import time
from datetime import datetime, timedelta, timezone

from core.bot_logger import get_logger
from core.db import get_db, is_db_available

_log = get_logger("trade_log")

TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "data/trades.jsonl")
TRADE_LOG_MAX_LINES = 10_000

KST = timezone(timedelta(hours=9))


def is_trade_logged(uuid, path=TRADE_LOG_PATH) -> bool:
    """해당 uuid가 이미 체결 기록(DB 또는 파일)에 존재하는지 확인한다(중복 기록 방지).

    DB의 uuid 인덱스 조회를 우선 사용. DB 미사용/조회 실패 시에만 파일을 줄 단위로
    JSON 파싱해 정확히 일치하는지 확인한다(이전엔 라인 부분문자열 매칭이었음 — L3).
    """
    if is_db_available():
        try:
            res = get_db().table("trade_logs").select("id").eq("uuid", uuid).execute()
            if res.data:
                return True
            return False
        except Exception:
            pass
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("uuid") == uuid:
                    return True
    except Exception as e:
        _log.debug("Failed in trade_log file operation: %s", e)
    return False


def append_trade(
    user_id,
    exchange,
    ticker,
    side,
    price,
    volume,
    strategy,
    uuid,
    fee_amount=0.0,
    group_no=None,
    template_id=None,
    path=TRADE_LOG_PATH,
):
    ts = time.time()
    normalized_group_no = int(group_no) if group_no is not None else None
    normalized_template_id = int(template_id) if template_id is not None else None
    record = {
        "ts": ts,
        "user_id": str(user_id),
        "exchange": exchange,
        "ticker": ticker,
        "side": side,
        "price": float(price),
        "volume": float(volume),
        "strategy": strategy,
        "uuid": uuid,
        "fee_amount": float(fee_amount),
        "group_no": normalized_group_no,
        "template_id": normalized_template_id,
    }
    if is_db_available():
        db_row = {
            "user_id": str(user_id),
            "exchange": exchange,
            "ticker": ticker,
            "side": side,
            "price": float(price),
            "volume": float(volume),
            "strategy": strategy,
            "uuid": uuid,
            "executed_at": ts,
            "fee_amount": float(fee_amount),
        }
        if normalized_group_no is not None:
            db_row["group_no"] = normalized_group_no
        if normalized_template_id is not None:
            db_row["template_id"] = normalized_template_id
        try:
            get_db().table("trade_logs").insert(db_row).execute()
        except Exception:
            popped = False
            if "template_id" in db_row:
                db_row.pop("template_id", None)
                popped = True
            if "group_no" in db_row:
                db_row.pop("group_no", None)
                popped = True
            if popped:
                try:
                    get_db().table("trade_logs").insert(db_row).execute()
                except Exception:
                    pass
    try:
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.chmod(path, 0o600)
        _trim_trade_log(path)
    except Exception as e:
        _log.debug("Failed in trade_log file operation: %s", e)


def _trim_trade_log(path):
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > TRADE_LOG_MAX_LINES:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-TRADE_LOG_MAX_LINES:])
    except Exception as e:
        _log.debug("Failed in trade_log file operation: %s", e)


def _period_cutoff_ts(period):
    now = datetime.now(KST)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    if period == "week":
        return (now - timedelta(days=7)).timestamp()
    if period == "month":
        return (now - timedelta(days=30)).timestamp()
    return 0.0


def clear_user_trades(user_id, path=TRADE_LOG_PATH) -> int:
    """해당 유저의 체결 내역을 DB(trade_logs)와 파일(jsonl)에서 모두 제거한다."""
    user_id = str(user_id)
    if is_db_available():
        try:
            get_db().table("trade_logs").delete().eq("user_id", user_id).execute()
        except Exception:
            pass
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    removed = 0
    kept = []
    for line in lines:
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        if rec.get("user_id") == user_id:
            removed += 1
        else:
            kept.append(line)
    if removed:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(kept)
        os.chmod(path, 0o600)
    return removed


def _match_ticker_filter(record_ticker: str, filter_ticker: str | None) -> bool:
    if not filter_ticker:
        return True
    rt = str(record_ticker or "").upper()
    ft = str(filter_ticker or "").upper().strip()
    if rt == ft:
        return True
    if rt.replace("KRW-", "") == ft.replace("KRW-", ""):
        return True
    return False


def read_trades(user_id, period="all", path=None, group_no=None, ticker=None):
    if path is None:
        path = TRADE_LOG_PATH
    cutoff = _period_cutoff_ts(period)
    target_group = int(group_no) if group_no is not None else None
    result = []

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("user_id") != str(user_id):
                    continue
                if rec.get("ts", 0) < cutoff:
                    continue
                if target_group is not None:
                    rec_gno = rec.get("group_no")
                    if rec_gno is None or int(rec_gno) != target_group:
                        continue
                if ticker and not _match_ticker_filter(rec.get("ticker", ""), ticker):
                    continue
                result.append(rec)
        return result

    # 로컬 파일이 없을 때 DB 폴백 조회
    if is_db_available():
        try:
            q = get_db().table("trade_logs").select("*").eq("user_id", str(user_id)).order("executed_at", desc=False)
            if cutoff > 0:
                q._params["executed_at"] = f"gte.{cutoff}"
            if target_group is not None:
                q._params["group_no"] = f"eq.{target_group}"
            rows = q.execute().data or []
            for r in rows:
                if ticker and not _match_ticker_filter(r.get("ticker", ""), ticker):
                    continue
                result.append({
                    "ts": float(r.get("executed_at") or 0),
                    "user_id": str(r.get("user_id") or ""),
                    "exchange": r.get("exchange", ""),
                    "ticker": r.get("ticker", ""),
                    "side": r.get("side", ""),
                    "price": float(r.get("price") or 0),
                    "volume": float(r.get("volume") or 0),
                    "strategy": r.get("strategy", "manual"),
                    "uuid": r.get("uuid"),
                    "fee_amount": float(r.get("fee_amount") or 0),
                    "group_no": r.get("group_no"),
                })
        except Exception as e:
            _log.debug("Failed to read trades from DB fallback: %s", e)

    return result
