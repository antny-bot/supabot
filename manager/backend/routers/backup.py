# -*- coding: utf-8 -*-
import json
import os
import re
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from ..bot_client import download_bot_backup_file, get_bot_backup_status, trigger_bot_backup
from ..db import get_db
from ._auth import get_admin_user, get_current_user

router = APIRouter()

BACKUP_DIR = "data/backups"
STATE_FILE = "data/backup_state.json"


@router.get("/api/backup/config")
async def api_get_backup_config(_=Depends(get_admin_user)):
    """현재 백업 주기 및 보존 설정 조회."""
    try:
        cfg = {
            "enabled": True,
            "schedule_type": "interval",  # "interval" | "weekly"
            "interval_hours": 24,         # 기본 24시간
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],  # 0=월..6=일
            "time_of_day": "04:00",
            "local_max_keep": 7,
            "gdrive_max_keep": 14,
            "gdrive_enabled": False,
            "gdrive_folder": os.environ.get("GDRIVE_FOLDER", "supabot-backups"),
        }

        # Google Drive 환경변수 확인 (로컬 폴백)
        gdrive_cid = os.environ.get("GDRIVE_CLIENT_ID", "").strip()
        gdrive_sec = os.environ.get("GDRIVE_CLIENT_SECRET", "").strip()
        gdrive_tok = os.environ.get("GDRIVE_REFRESH_TOKEN", "").strip()
        cfg["gdrive_enabled"] = bool(gdrive_cid and gdrive_sec and gdrive_tok)

        rows = (await get_db().table("system_config").select("key,value").execute()).data or []
        row_dict = {r["key"]: r["value"] for r in rows}

        if "backup_enabled" in row_dict:
            cfg["enabled"] = row_dict["backup_enabled"].lower() in ("true", "1", "yes")
        if "backup_schedule_type" in row_dict:
            cfg["schedule_type"] = row_dict["backup_schedule_type"]
        if "backup_interval_hours" in row_dict:
            cfg["interval_hours"] = int(row_dict["backup_interval_hours"])
        if "backup_days_of_week" in row_dict:
            val = row_dict["backup_days_of_week"]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    val = [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
            if isinstance(val, list):
                cfg["days_of_week"] = [int(x) for x in val]
        if "backup_time_of_day" in row_dict:
            cfg["time_of_day"] = row_dict["backup_time_of_day"]
        if "backup_local_max_keep" in row_dict:
            cfg["local_max_keep"] = int(row_dict["backup_local_max_keep"])
        if "backup_gdrive_max_keep" in row_dict:
            cfg["gdrive_max_keep"] = int(row_dict["backup_gdrive_max_keep"])
        if "backup_gdrive_folder" in row_dict:
            cfg["gdrive_folder"] = row_dict["backup_gdrive_folder"]

        # 봇 컨테이너의 Google Drive 연동 상태 및 폴더 설정 우선 반영
        ok, bot_res = await get_bot_backup_status()
        if ok and isinstance(bot_res, dict):
            bot_cfg = bot_res.get("config") or {}
            if "gdrive_enabled" in bot_cfg:
                cfg["gdrive_enabled"] = bool(bot_cfg["gdrive_enabled"])
            if "backup_gdrive_folder" not in row_dict and bot_cfg.get("gdrive_folder"):
                cfg["gdrive_folder"] = bot_cfg["gdrive_folder"]

        return JSONResponse(cfg)
    except Exception as e:
        return JSONResponse({"error": f"Failed to get backup config: {str(e)}"}, status_code=500)


@router.post("/api/backup/config")
async def api_save_backup_config(request: Request, _=Depends(get_admin_user)):
    """백업 주기 및 보존 설정 저장."""
    try:
        body = await request.json()
        db = get_db()

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

        for prop, db_key in key_map.items():
            if prop in body:
                val = body[prop]
                if isinstance(val, (list, dict)):
                    val_str = json.dumps(val)
                elif isinstance(val, bool):
                    val_str = "true" if val else "false"
                else:
                    val_str = str(val)
                await db.table("system_config").upsert({"key": db_key, "value": val_str}).execute()

        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": f"Failed to save backup config: {str(e)}"}, status_code=500)


@router.get("/api/backup/status")
async def api_get_backup_status(_=Depends(get_admin_user)):
    """최근 백업 상태 및 로컬 파일 목록 반환."""
    try:
        state = {
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

        # 1. 봇 컨테이너의 백업 상태 및 로컬 파일 목록 우선 조회
        ok, bot_res = await get_bot_backup_status()
        if ok and isinstance(bot_res, dict) and "state" in bot_res:
            if isinstance(bot_res.get("state"), dict):
                state.update(bot_res["state"])
            return JSONResponse({
                "state": state,
                "local_files": bot_res.get("local_files", []),
            })

        # 2. 봇 연결 실패 시 로컬 파일시스템 폴백 조회
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    state.update(json.load(f))
            except Exception:
                pass

        local_files = []
        if os.path.exists(BACKUP_DIR):
            for fname in os.listdir(BACKUP_DIR):
                if fname.endswith(".zip") and fname.startswith("supabot-backup-"):
                    fpath = os.path.join(BACKUP_DIR, fname)
                    stat = os.stat(fpath)
                    local_files.append({
                        "filename": fname,
                        "sizeBytes": stat.st_size,
                        "createdAt": stat.st_mtime,
                    })
            local_files.sort(key=lambda x: x["createdAt"], reverse=True)

        return JSONResponse({
            "state": state,
            "local_files": local_files,
        })
    except Exception as e:
        return JSONResponse({"error": f"Failed to get backup status: {str(e)}"}, status_code=500)


@router.post("/api/backup/trigger")
async def api_trigger_backup(_=Depends(get_admin_user)):
    """즉시 백업 실행 요청."""
    try:
        # 봇 프로세스의 webhook 호출
        ok, res = await trigger_bot_backup()
        if ok:
            return JSONResponse(res)

        return JSONResponse(
            {"error": f"Backup failed: {res.get('error', 'Bot webhook unreachable')}"},
            status_code=500,
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/backup/download/{filename}")
async def api_download_backup(filename: str, _=Depends(get_admin_user)):
    """로컬 백업 ZIP 파일 다운로드."""
    # 파일명 디렉토리 순회 공격(Path Traversal) 방지
    if not re.match(r"^supabot-backup-[\w\-]+\.zip$", filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    fpath = os.path.join(BACKUP_DIR, filename)
    if os.path.exists(fpath):
        return FileResponse(
            path=fpath,
            filename=filename,
            media_type="application/zip",
        )

    # 분리 컨테이너 환경: 봇 컨테이너로부터 백업 파일 다운로드
    ok, content = await download_bot_backup_file(filename)
    if ok and isinstance(content, bytes):
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise HTTPException(status_code=404, detail="File not found")


@router.get("/api/backup/health")
async def api_get_backup_health(_=Depends(get_current_user)):
    """백업 스케줄러 Health 정보 조회 (대시보드 공통)."""
    from .dashboard import _build_backup_health
    health = await _build_backup_health(get_db())
    return JSONResponse(health)
