import os
import json
import asyncio
import time
from core.bot_logger import get_logger
from core.db import get_db, is_db_available

_log = get_logger("db_sync")
_queue_file = "data/db_sync_queue.json"
_queue = []
_lock = asyncio.Lock()
_loop_task = None

def _load_queue():
    global _queue
    if not os.path.exists(_queue_file):
        _queue = []
        return
    try:
        with open(_queue_file, "r", encoding="utf-8") as f:
            _queue = json.load(f)
    except Exception as e:
        _log.error("Failed to load DB sync queue", exc_info=e)
        _queue = []

def _save_queue():
    os.makedirs(os.path.dirname(_queue_file), exist_ok=True)
    try:
        with open(_queue_file, "w", encoding="utf-8") as f:
            json.dump(_queue, f, indent=2, ensure_ascii=False)
        os.chmod(_queue_file, 0o600)
    except Exception as e:
        _log.error("Failed to save DB sync queue", exc_info=e)

async def enqueue_task(action: str, table: str, key_col: str, key_val: str, data: dict = None):
    """실패한 DB 쓰기/삭제 작업을 동기화 큐에 보관"""
    async with _lock:
        # 중복된 작업 제거 (동일 테이블의 동일 키에 대한 작업은 최신 것으로 덮어씀)
        global _queue
        _queue = [
            t for t in _queue 
            if not (t["table"] == table and t["key_val"] == key_val)
        ]
        
        task = {
            "action": action,      # "upsert" | "delete"
            "table": table,        # "users" | "orders"
            "key_col": key_col,    # "user_id" | "uuid"
            "key_val": key_val,
            "data": data,
            "timestamp": time.time()
        }
        _queue.append(task)
        _save_queue()
        _log.info(f"Enqueued DB sync task: {action} on {table} (key: {key_val})")

async def test_db_connection() -> bool:
    """DB 연결 정상 작동 여부 검사 (단순 select로 헬스체크)"""
    if not is_db_available():
        return False
    try:
        await get_db().table("system_config").select("key").limit(1).execute_async()
        return True
    except Exception:
        return False

async def _process_queue():
    """큐에 쌓인 작업을 순차적으로 DB에 재시도 반영"""
    global _queue
    if not _queue:
        return

    if not await test_db_connection():
        return

    _log.info("DB Connection recovered. Starting DB sync process...")
    
    async with _lock:
        # 큐 순서대로 처리하고, 실패한 task 이후는 시도하지 않고 그대로 큐에 남긴다.
        # 처리 도중 사라진 task가 없도록 "맨 앞부터 성공한 개수"만 잘라낸다 — 실패
        # task 1개를 제외한 나머지 전체 길이로 성공 개수를 추정하면 break 이후
        # 아직 시도조차 안 된 task들까지 큐에서 통째로 사라진다(과거 버그).
        processed = 0
        for task in list(_queue):
            action = task["action"]
            table = task["table"]
            key_col = task["key_col"]
            key_val = task["key_val"]
            data = task["data"]

            try:
                db = get_db()
                if action == "upsert":
                    await db.table(table).upsert(data).execute_async()
                elif action == "delete":
                    await db.table(table).delete().eq(key_col, key_val).execute_async()
                _log.info(f"Successfully synced task: {action} on {table} ({key_val})")
                processed += 1
            except Exception as e:
                from core.db import SupabaseAPIError
                if isinstance(e, SupabaseAPIError) and 400 <= e.status_code < 500 and e.status_code not in (401, 403, 429):
                    _log.error(f"Permanent failure for task: {action} on {table} ({key_val}) due to status {e.status_code}. Discarding task.", exc_info=e)
                    processed += 1
                    continue
                _log.error(f"Failed to sync task: {action} on {table} ({key_val}), will retry later", exc_info=e)
                break

        if processed > 0:
            _queue = _queue[processed:]
            _save_queue()
            _log.info(f"DB sync iteration finished: {processed} tasks synced, {len(_queue)} tasks remaining")

async def sync_loop(interval=30):
    """주기적으로 큐를 처리하는 루프"""
    _load_queue()
    while True:
        try:
            await _process_queue()
        except Exception as e:
            _log.error("Error in DB sync loop processing", exc_info=e)
        await asyncio.sleep(interval)

def start_sync_loop(application=None, interval=30):
    """백그라운드 동기화 태스크 기동"""
    global _loop_task
    if _loop_task is None:
        _loop_task = asyncio.create_task(sync_loop(interval))
        _log.info("DB sync background loop started")
