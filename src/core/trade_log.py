import json
import os
import time
from datetime import datetime, timedelta, timezone

from core.db import get_db, is_db_available

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
    except Exception:
        pass
    return False


def append_trade(user_id, exchange, ticker, side, price, volume, strategy, uuid, fee_amount=0.0, path=TRADE_LOG_PATH):
    ts = time.time()
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
    }
    if is_db_available():
        try:
            get_db().table("trade_logs").insert({
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
            }).execute()
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
    except Exception:
        pass


def _trim_trade_log(path):
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > TRADE_LOG_MAX_LINES:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-TRADE_LOG_MAX_LINES:])
    except Exception:
        pass


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


def read_trades(user_id, period="all", path=TRADE_LOG_PATH):
    cutoff = _period_cutoff_ts(period)
    if not os.path.exists(path):
        return []
    result = []
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
            result.append(rec)
    return result
