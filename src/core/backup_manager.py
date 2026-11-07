# -*- coding: utf-8 -*-
"""Supabase 정기 백업 및 로컬 SQLite 스냅샷 관리 모듈."""

import asyncio
import json
import os
import shutil
import sqlite3
import time
import zipfile
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.bot_logger import get_logger
from core.db import get_db, is_db_available
from core import gdrive_client
from core.secret_crypto import decrypt_secret, encrypt_secret

logger = get_logger("backup_manager")

KST = timezone(timedelta(hours=9))

BACKUP_TABLES = [
    "users",
    "orders",
    "trade_logs",
    "operational_events",
    "nl_logs",
    "system_config",
    "strategy_templates",
    "command_logs",
    "command_log_daily",
    "kr_stock_cache",
    "dca_schedules",
    "market_top_snapshots",
    "budget_ledger",
    "feedbacks",
]

TABLE_ORDER_KEYS = {
    "users": "user_id",
    "orders": "uuid",
    "system_config": "key",
    "command_log_daily": "day,user_id,command",
    "kr_stock_cache": "code",
    "market_top_snapshots": "exchange,snapshot_date,rank",
}

BACKUP_DIR = "data/backups"
STATE_FILE = "data/backup_state.json"
FALLBACK_SQLITE_PATH = "data/fallback_latest.sqlite3"

_backup_lock = asyncio.Lock()
_loop_task: Optional[asyncio.Task] = None


def _resolve_gdrive_credentials(rows: Optional[Dict[str, str]] = None) -> Tuple[str, str, str, str, str]:
    """Google Drive 연동 정보(Client ID, Secret, Refresh Token, User Email, Folder)를 조회합니다.
    
    우선순위:
    1. system_config DB 레코드 (웹 UI 인증)
    2. .env 환경변수 (레거시/수동 설정)
    """
    rows = rows or {}
    
    cid = rows.get("backup_gdrive_client_id", "").strip() or os.environ.get("GDRIVE_CLIENT_ID", "").strip()
    sec = rows.get("backup_gdrive_client_secret", "").strip() or os.environ.get("GDRIVE_CLIENT_SECRET", "").strip()
    
    # Refresh Token: DB 우선 (암호화되어 있으면 복호화), 없으면 .env 폴백
    raw_token = rows.get("backup_gdrive_refresh_token", "").strip()
    refresh_tok = ""
    if raw_token:
        try:
            refresh_tok = decrypt_secret(raw_token).strip()
        except Exception:
            refresh_tok = raw_token.strip()
    if not refresh_tok:
        refresh_tok = os.environ.get("GDRIVE_REFRESH_TOKEN", "").strip()
        
    user_email = rows.get("backup_gdrive_user_email", "").strip()
    folder = rows.get("backup_gdrive_folder", "").strip() or os.environ.get("GDRIVE_FOLDER", "supabot-backups").strip()
    
    return cid, sec, refresh_tok, user_email, folder


def get_backup_config() -> Dict[str, Any]:
    """system_config 또는 환경변수에서 백업 설정을 조회합니다."""
    # 기본값
    cfg = {
        "enabled": True,
        "schedule_type": "interval",  # "interval" 또는 "weekly"
        "interval_hours": 24,         # interval 모드 기본 24시간
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],  # 0=월..6=일
        "time_of_day": "04:00",       # KST 기준 실행 시각
        "local_max_keep": 7,
        "gdrive_max_keep": 14,
        "gdrive_enabled": False,
        "gdrive_folder": os.environ.get("GDRIVE_FOLDER", "supabot-backups"),
        "gdrive_user_email": "",
    }

    rows: Dict[str, str] = {}
    if is_db_available():
        try:
            resp = get_db().table("system_config").select("key,value").execute()
            rows = {r["key"]: r["value"] for r in (resp.data or [])}

            if "backup_enabled" in rows:
                cfg["enabled"] = rows["backup_enabled"].lower() in ("true", "1", "yes")
            if "backup_schedule_type" in rows:
                cfg["schedule_type"] = rows["backup_schedule_type"]
            if "backup_interval_hours" in rows:
                cfg["interval_hours"] = int(rows["backup_interval_hours"])
            if "backup_days_of_week" in rows:
                val = rows["backup_days_of_week"]
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except Exception:
                        val = [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
                if isinstance(val, list):
                    cfg["days_of_week"] = [int(x) for x in val]
            if "backup_time_of_day" in rows:
                cfg["time_of_day"] = rows["backup_time_of_day"]
            if "backup_local_max_keep" in rows:
                cfg["local_max_keep"] = int(rows["backup_local_max_keep"])
            if "backup_gdrive_max_keep" in rows:
                cfg["gdrive_max_keep"] = int(rows["backup_gdrive_max_keep"])
            if "backup_gdrive_folder" in rows:
                cfg["gdrive_folder"] = rows["backup_gdrive_folder"]
        except Exception as e:
            logger.warning("Failed to load backup config from system_config: %s", e)

    cid, sec, tok, user_email, folder = _resolve_gdrive_credentials(rows)
    cfg["gdrive_enabled"] = bool(cid and sec and tok)
    cfg["gdrive_user_email"] = user_email
    if folder:
        cfg["gdrive_folder"] = folder

    return cfg


def save_backup_config(updates: Dict[str, Any]) -> bool:
    """백업 설정을 system_config에 저장합니다."""
    if not is_db_available():
        return False

    key_map = {
        "enabled": "backup_enabled",
        "schedule_type": "backup_schedule_type",
        "interval_hours": "backup_interval_hours",
        "days_of_week": "backup_days_of_week",
        "time_of_day": "backup_time_of_day",
        "local_max_keep": "backup_local_max_keep",
        "gdrive_max_keep": "backup_gdrive_max_keep",
        "gdrive_folder": "backup_gdrive_folder",
    }

    db = get_db()
    for prop, val in updates.items():
        if prop in key_map:
            db_key = key_map[prop]
            if isinstance(val, (list, dict)):
                val_str = json.dumps(val)
            elif isinstance(val, bool):
                val_str = "true" if val else "false"
            else:
                val_str = str(val)
            try:
                db.table("system_config").upsert({"key": db_key, "value": val_str}).execute()
            except Exception as e:
                logger.error("Failed to save backup config key %s: %s", db_key, e)
                return False
    return True


def load_backup_state() -> Dict[str, Any]:
    """data/backup_state.json에서 마지막 백업 상태를 읽어옵니다."""
    if not os.path.exists(STATE_FILE):
        return {
            "last_attempt_at": None,
            "last_success_at": None,
            "last_status": "none",
            "last_error": None,
            "last_backup_file": None,
            "last_backup_size": 0,
            "last_gdrive_file_id": None,
            "table_counts": {},
            "total_rows": 0,
        }
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load backup state: %s", e)
        return {"last_status": "unknown"}


def save_backup_state(state: Dict[str, Any]) -> None:
    """data/backup_state.json에 백업 상태를 저장합니다."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp_path = f"{STATE_FILE}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, STATE_FILE)
        try:
            os.chmod(STATE_FILE, 0o600)
        except Exception:
            pass
    except Exception as e:
        logger.error("Failed to save backup state: %s", e)


def list_local_backup_files() -> List[Dict[str, Any]]:
    """로컬 BACKUP_DIR 내 보관 중인 ZIP 백업 파일 목록을 최신순으로 반환합니다."""
    local_files: List[Dict[str, Any]] = []
    if os.path.exists(BACKUP_DIR):
        for fname in os.listdir(BACKUP_DIR):
            if fname.endswith(".zip") and fname.startswith("supabot-backup-"):
                fpath = os.path.join(BACKUP_DIR, fname)
                try:
                    stat = os.stat(fpath)
                    local_files.append({
                        "filename": fname,
                        "sizeBytes": stat.st_size,
                        "createdAt": stat.st_mtime,
                    })
                except Exception:
                    continue
        local_files.sort(key=lambda x: x["createdAt"], reverse=True)
    return local_files


def dump_supabase_table(table_name: str, batch_size: int = 1000) -> List[Dict[str, Any]]:
    """Supabase 테이블을 1000행 단위 페이지네이션으로 전수 조회합니다."""
    db = get_db()
    all_rows = []
    start = 0
    order_col = TABLE_ORDER_KEYS.get(table_name, "id")

    while True:
        end = start + batch_size - 1
        resp = db.table(table_name).select("*").order(order_col).range(start, end).execute()
        rows = resp.data or []
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < batch_size:
            break
        start += batch_size

    return all_rows


def _sqlite_type(value: Any) -> str:
    """Python 값을 SQLite 컬럼 타입 문자열로 매핑합니다."""
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "REAL"
    return "TEXT"


def _serialize_value(value: Any) -> Any:
    """SQLite 저장을 위해 dict/list/bool 등을 직렬화합니다."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def create_sqlite_snapshot(tables_data: Dict[str, List[Dict[str, Any]]], output_path: str) -> None:
    """메모리의 테이블 데이터들을 SQLite 데이터베이스 파일로 저장합니다."""
    tmp_path = f"{output_path}.tmp"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    conn = sqlite3.connect(tmp_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=MEMORY;")
        cursor.execute("PRAGMA synchronous=OFF;")

        for table_name, rows in tables_data.items():
            if not rows:
                cursor.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" (id TEXT);')
                continue

            # 컬럼 타입 추론
            col_types = {}
            for row in rows:
                for k, v in row.items():
                    if k not in col_types and v is not None:
                        col_types[k] = _sqlite_type(v)
            for k in rows[0].keys():
                col_types.setdefault(k, "TEXT")

            col_defs = ", ".join(f'"{col}" {dtype}' for col, dtype in col_types.items())
            cursor.execute(f'CREATE TABLE "{table_name}" ({col_defs});')

            cols = list(col_types.keys())
            placeholders = ", ".join("?" for _ in cols)
            col_list_str = ", ".join(f'"{c}"' for c in cols)
            insert_sql = f'INSERT INTO "{table_name}" ({col_list_str}) VALUES ({placeholders})'

            batch_values = []
            for row in rows:
                row_vals = tuple(_serialize_value(row.get(col)) for col in cols)
                batch_values.append(row_vals)

            cursor.executemany(insert_sql, batch_values)

        conn.commit()
        cursor.execute("PRAGMA synchronous=FULL;")
        cursor.execute("VACUUM;")
    finally:
        conn.close()

    os.replace(tmp_path, output_path)
    try:
        os.chmod(output_path, 0o600)
    except Exception:
        pass


def package_backup_zip(
    sqlite_path: str,
    manifest: Dict[str, Any],
    output_zip_path: str,
    extra_files: Optional[List[str]] = None,
) -> None:
    """SQLite 스냅샷 파일과 메타데이터(manifest.json) 및 추가 보조 파일을 ZIP으로 압축합니다."""
    tmp_zip = f"{output_zip_path}.tmp"
    if os.path.exists(tmp_zip):
        os.remove(tmp_zip)

    with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # SQLite 파일 추가
        zf.write(sqlite_path, arcname=os.path.basename(sqlite_path))
        # manifest.json 추가
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

        # 로컬 보조 파일 추가 (data/users.json 등)
        if extra_files:
            for fpath in extra_files:
                if os.path.exists(fpath):
                    zf.write(fpath, arcname=f"local_data/{os.path.basename(fpath)}")

    os.replace(tmp_zip, output_zip_path)
    try:
        os.chmod(output_zip_path, 0o600)
    except Exception:
        pass


def prune_local_backups(max_keep: int) -> List[str]:
    """로컬 BACKUP_DIR 내 오래된 백업 파일(.zip, .sqlite3)을 정리합니다."""
    if not os.path.exists(BACKUP_DIR):
        return []

    deleted = []
    # .zip 파일 정리
    zip_files = []
    for fname in os.listdir(BACKUP_DIR):
        if fname.endswith(".zip") and fname.startswith("supabot-backup-"):
            full_path = os.path.join(BACKUP_DIR, fname)
            zip_files.append((os.path.getmtime(full_path), full_path))

    zip_files.sort(reverse=True)
    if len(zip_files) > max_keep:
        for _, path in zip_files[max_keep:]:
            try:
                os.remove(path)
                deleted.append(path)
                logger.info("Pruned old local backup: %s", path)
            except Exception as e:
                logger.warning("Failed to delete local backup %s: %s", path, e)

    # .sqlite3 파일 정리
    sqlite_files = []
    for fname in os.listdir(BACKUP_DIR):
        if fname.endswith(".sqlite3") and fname.startswith("supabot-backup-"):
            full_path = os.path.join(BACKUP_DIR, fname)
            sqlite_files.append((os.path.getmtime(full_path), full_path))

    sqlite_files.sort(reverse=True)
    if len(sqlite_files) > max_keep:
        for _, path in sqlite_files[max_keep:]:
            try:
                os.remove(path)
                deleted.append(path)
            except Exception as e:
                logger.warning("Failed to delete local sqlite snapshot %s: %s", path, e)

    return deleted


def prune_gdrive_backups(access_token: str, max_keep: int, folder_name: str) -> List[str]:
    """Google Drive 백업 폴더 내의 오래된 백업 파일을 정리합니다."""
    deleted = []
    try:
        files = gdrive_client.list_gdrive_backups(access_token, folder_name=folder_name)
        if len(files) > max_keep:
            for item in files[max_keep:]:
                try:
                    gdrive_client.delete_file_from_gdrive(access_token, item["id"])
                    deleted.append(item["filename"])
                    logger.info("Pruned old Google Drive backup: %s (id: %s)", item["filename"], item["id"])
                except Exception as e:
                    logger.warning("Failed to delete Google Drive backup %s: %s", item["id"], e)
    except Exception as e:
        logger.error("Failed to prune Google Drive backups: %s", e)
    return deleted


def execute_full_backup_sync() -> Dict[str, Any]:
    """동기적으로 전체 백업 프로세스를 수행합니다 (asyncio.to_thread로 호출)."""
    start_time = time.time()
    now_kst = datetime.now(KST)
    timestamp_str = now_kst.strftime("%Y%m%d-%H%M%S")

    cfg = get_backup_config()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    sqlite_filename = f"supabot-backup-{timestamp_str}.sqlite3"
    sqlite_path = os.path.join(BACKUP_DIR, sqlite_filename)
    zip_filename = f"supabot-backup-{timestamp_str}.zip"
    zip_path = os.path.join(BACKUP_DIR, zip_filename)

    state = load_backup_state()
    state["last_attempt_at"] = now_kst.isoformat()
    save_backup_state(state)

    if not is_db_available():
        err_msg = "Supabase DB is not available for backup"
        logger.error(err_msg)
        state["last_status"] = "error"
        state["last_error"] = err_msg
        save_backup_state(state)
        return {"status": "error", "error": err_msg}

    # 1. 14개 테이블 덤프
    logger.info("Starting Supabase dump for %d tables...", len(BACKUP_TABLES))
    tables_data = {}
    table_counts = {}
    total_rows = 0

    try:
        for tname in BACKUP_TABLES:
            rows = dump_supabase_table(tname)
            tables_data[tname] = rows
            table_counts[tname] = len(rows)
            total_rows += len(rows)

        # 2. SQLite 스냅샷 파일 생성
        logger.info("Writing SQLite snapshot to %s...", sqlite_path)
        create_sqlite_snapshot(tables_data, sqlite_path)

        # 3. 최신 fallback DB 복사 (원자적)
        try:
            os.makedirs(os.path.dirname(FALLBACK_SQLITE_PATH), exist_ok=True)
            tmp_fb = f"{FALLBACK_SQLITE_PATH}.tmp"
            shutil.copyfile(sqlite_path, tmp_fb)
            os.replace(tmp_fb, FALLBACK_SQLITE_PATH)
            logger.info("Updated latest fallback DB: %s", FALLBACK_SQLITE_PATH)
        except Exception as e:
            logger.warning("Failed to update fallback SQLite file: %s", e)

        # 4. ZIP 아카이브 패키징
        elapsed_sec = round(time.time() - start_time, 2)
        manifest = {
            "created_at": now_kst.isoformat(),
            "elapsed_seconds": elapsed_sec,
            "total_tables": len(BACKUP_TABLES),
            "total_rows": total_rows,
            "table_counts": table_counts,
            "sqlite_file": sqlite_filename,
        }
        extra_files = ["data/users.json", "data/db_sync_queue.json"]
        package_backup_zip(sqlite_path, manifest, zip_path, extra_files=extra_files)
        zip_size = os.path.getsize(zip_path)
        logger.info("Created backup ZIP archive: %s (%d bytes)", zip_path, zip_size)

        # 5. 로컬 보존 정책 (Prune)
        prune_local_backups(cfg.get("local_max_keep", 7))

        # 6. Google Drive 업로드 (설정되어 있는 경우)
        gdrive_file_id = None
        gdrive_error: Optional[str] = None
        
        db_rows: Dict[str, str] = {}
        if is_db_available():
            try:
                resp = get_db().table("system_config").select("key,value").execute()
                db_rows = {r["key"]: r["value"] for r in (resp.data or [])}
            except Exception as e:
                logger.warning("Failed to read system_config for gdrive credentials: %s", e)

        gdrive_cid, gdrive_sec, gdrive_tok, _, resolved_folder = _resolve_gdrive_credentials(db_rows)

        if gdrive_cid and gdrive_sec and gdrive_tok:
            try:
                logger.info("Refreshing Google Drive access token...")
                token_res = gdrive_client.refresh_access_token(gdrive_cid, gdrive_sec, gdrive_tok)
                access_token = token_res["access_token"]
                folder_name = resolved_folder or cfg.get("gdrive_folder", "supabot-backups")

                logger.info("Uploading backup to Google Drive folder '%s'...", folder_name)
                upload_res = gdrive_client.upload_file_to_gdrive(
                    access_token=access_token,
                    file_path=zip_path,
                    filename=zip_filename,
                    folder_name=folder_name,
                )
                gdrive_file_id = upload_res.get("id")
                logger.info("Successfully uploaded backup to Google Drive (file_id: %s)", gdrive_file_id)

                # Google Drive 보존 정책 (Prune)
                prune_gdrive_backups(access_token, cfg.get("gdrive_max_keep", 14), folder_name)
            except Exception as e:
                logger.error("Failed to upload/prune Google Drive backup: %s", e, exc_info=True)
                gdrive_error = f"GDrive upload failed: {e}"

        # 상태 업데이트
        status_val = "partial_error" if gdrive_error else "success"
        state["last_success_at"] = now_kst.isoformat()
        state["last_status"] = status_val
        state["last_error"] = gdrive_error
        state["last_backup_file"] = zip_filename
        state["last_backup_size"] = zip_size
        state["last_gdrive_file_id"] = gdrive_file_id
        state["table_counts"] = table_counts
        state["total_rows"] = total_rows
        save_backup_state(state)

        return {
            "status": status_val,
            "error": gdrive_error,
            "file": zip_filename,
            "size": zip_size,
            "gdrive_id": gdrive_file_id,
            "total_rows": total_rows,
            "elapsed": elapsed_sec,
        }

    except Exception as e:
        logger.error("Backup execution failed: %s", e, exc_info=True)
        state["last_status"] = "error"
        state["last_error"] = str(e)
        save_backup_state(state)
        return {"status": "error", "error": str(e)}


async def trigger_backup() -> Dict[str, Any]:
    """비동기적으로 전체 백업을 트리거합니다 (락 보호)."""
    async with _backup_lock:
        return await asyncio.to_thread(execute_full_backup_sync)


def should_run_backup(now: Optional[datetime] = None) -> bool:
    """설정에 따라 지금 백업을 실행해야 하는지 판단합니다."""
    cfg = get_backup_config()
    if not cfg.get("enabled", True):
        return False

    if now is None:
        now = datetime.now(KST)

    state = load_backup_state()
    last_success_str = state.get("last_success_at")
    last_success = None
    if last_success_str:
        try:
            last_success = datetime.fromisoformat(last_success_str)
            if last_success.tzinfo is None:
                last_success = last_success.replace(tzinfo=KST)
        except Exception:
            last_success = None

    sched_type = cfg.get("schedule_type", "interval")

    if sched_type == "interval":
        interval_hours = cfg.get("interval_hours", 24)
        if last_success is None:
            return True
        return (now - last_success) >= timedelta(hours=interval_hours)

    elif sched_type == "weekly":
        # 요일 확인 (0=월..6=일)
        days = cfg.get("days_of_week", [0, 1, 2, 3, 4, 5, 6])
        if now.weekday() not in days:
            return False

        # 시간대 확인
        time_str = cfg.get("time_of_day", "04:00")
        try:
            target_hour, target_min = [int(x) for x in time_str.split(":")]
        except Exception:
            target_hour, target_min = 4, 0

        target_time = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
        if now < target_time:
            return False

        # 오늘 이미 성공했는지 확인
        if last_success and last_success.date() == now.date():
            return False

        return True

    return False


async def backup_loop(check_interval: int = 600):
    """백그라운드에서 주기적으로 백업 조건을 확인하고 실행합니다."""
    logger.info("Backup loop started (check interval: %ds)", check_interval)
    while True:
        try:
            if should_run_backup():
                logger.info("Backup condition met. Starting scheduled backup...")
                res = await trigger_backup()
                if res.get("status") in ("error", "partial_error"):
                    try:
                        from core.operational_events import append_operational_event
                        append_operational_event(
                            "error",
                            "backup_loop",
                            "Scheduled backup failed",
                            res.get("error") or "Scheduled backup failed",
                        )
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Error in backup loop: %s", e, exc_info=True)
            try:
                from core.operational_events import append_operational_event
                append_operational_event("error", "backup_loop", "Scheduled backup failed", str(e))
            except Exception:
                pass
        await asyncio.sleep(check_interval)


def start_backup_loop(application=None, check_interval: int = 600):
    """백업 백그라운드 태스크를 시작합니다."""
    global _loop_task
    if _loop_task is None:
        _loop_task = asyncio.create_task(backup_loop(check_interval))
        logger.info("Backup background task spawned")
