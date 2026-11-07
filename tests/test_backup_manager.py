# -*- coding: utf-8 -*-
import json
import os
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from core import backup_manager, db

KST = timezone(timedelta(hours=9))


@pytest.fixture
def temp_backup_env(tmp_path, monkeypatch):
    backup_dir = tmp_path / "data" / "backups"
    backup_dir.mkdir(parents=True)
    state_file = tmp_path / "data" / "backup_state.json"
    fallback_file = tmp_path / "data" / "fallback_latest.sqlite3"

    monkeypatch.setattr(backup_manager, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(backup_manager, "STATE_FILE", str(state_file))
    monkeypatch.setattr(backup_manager, "FALLBACK_SQLITE_PATH", str(fallback_file))
    monkeypatch.setattr(db, "_FALLBACK_DB_PATH", str(fallback_file))

    return {
        "backup_dir": backup_dir,
        "state_file": state_file,
        "fallback_file": fallback_file,
    }


def test_create_sqlite_snapshot(temp_backup_env):
    output_path = os.path.join(temp_backup_env["backup_dir"], "test.sqlite3")
    tables_data = {
        "users": [
            {"user_id": "u1", "username": "alice", "preferences": {"theme": "dark"}},
            {"user_id": "u2", "username": "bob", "preferences": {"theme": "light"}},
        ],
        "orders": [],
    }

    backup_manager.create_sqlite_snapshot(tables_data, output_path)
    assert os.path.exists(output_path)

    # SQLite 데이터 검증
    conn = sqlite3.connect(output_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM "users"')
    rows = cursor.fetchall()
    assert len(rows) == 2
    assert rows[0]["username"] == "alice"
    assert json.loads(rows[0]["preferences"]) == {"theme": "dark"}

    cursor.execute('SELECT * FROM "orders"')
    assert cursor.fetchall() == []
    conn.close()


def test_package_backup_zip(temp_backup_env, tmp_path):
    sqlite_path = os.path.join(temp_backup_env["backup_dir"], "snapshot.sqlite3")
    with open(sqlite_path, "wb") as f:
        f.write(b"sqlite format 3\x00")

    extra_file = tmp_path / "extra.json"
    extra_file.write_text('{"status": "ok"}', encoding="utf-8")

    manifest = {"test": 123, "rows": 10}
    zip_path = os.path.join(temp_backup_env["backup_dir"], "snapshot.zip")

    backup_manager.package_backup_zip(
        sqlite_path=sqlite_path,
        manifest=manifest,
        output_zip_path=zip_path,
        extra_files=[str(extra_file)],
    )

    assert os.path.exists(zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert "snapshot.sqlite3" in namelist
        assert "manifest.json" in namelist
        assert f"local_data/{extra_file.name}" in namelist
        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest_data["test"] == 123


def test_prune_local_backups(temp_backup_env):
    backup_dir = temp_backup_env["backup_dir"]
    # 5개의 .zip 파일 생성
    for i in range(5):
        p = os.path.join(backup_dir, f"supabot-backup-2026110{i}-120000.zip")
        with open(p, "w") as f:
            f.write(f"content {i}")
        # 시간차 설정
        mtime = 1000 + i * 100
        os.utime(p, (mtime, mtime))

    deleted = backup_manager.prune_local_backups(max_keep=2)
    assert len(deleted) == 3
    remaining = [f for f in os.listdir(backup_dir) if f.endswith(".zip")]
    assert len(remaining) == 2
    assert "supabot-backup-20261104-120000.zip" in remaining
    assert "supabot-backup-20261103-120000.zip" in remaining


def test_should_run_backup_interval(temp_backup_env, monkeypatch):
    monkeypatch.setattr(backup_manager, "get_backup_config", lambda: {
        "enabled": True,
        "schedule_type": "interval",
        "interval_hours": 24,
    })

    # 상태 파일 없음 -> 실행 필요
    assert backup_manager.should_run_backup() is True

    # 마지막 성공 10시간 전 -> 실행 불필요
    now = datetime(2026, 11, 7, 12, 0, tzinfo=KST)
    state = {
        "last_success_at": (now - timedelta(hours=10)).isoformat()
    }
    backup_manager.save_backup_state(state)
    assert backup_manager.should_run_backup(now=now) is False

    # 마지막 성공 25시간 전 -> 실행 필요
    state = {
        "last_success_at": (now - timedelta(hours=25)).isoformat()
    }
    backup_manager.save_backup_state(state)
    assert backup_manager.should_run_backup(now=now) is True


def test_should_run_backup_weekly(temp_backup_env, monkeypatch):
    # 2026-11-07은 토요일 (weekday 5)
    sat = datetime(2026, 11, 7, 5, 0, tzinfo=KST)
    assert sat.weekday() == 5

    # 요일 불일치 (월요일 0만 설정)
    monkeypatch.setattr(backup_manager, "get_backup_config", lambda: {
        "enabled": True,
        "schedule_type": "weekly",
        "days_of_week": [0],
        "time_of_day": "04:00",
    })
    assert backup_manager.should_run_backup(now=sat) is False

    # 요일 일치 (토요일 5 포함), 시간 04:00 지남, 오늘 미실행
    monkeypatch.setattr(backup_manager, "get_backup_config", lambda: {
        "enabled": True,
        "schedule_type": "weekly",
        "days_of_week": [5],
        "time_of_day": "04:00",
    })
    assert backup_manager.should_run_backup(now=sat) is True

    # 오늘 이미 실행됨
    backup_manager.save_backup_state({"last_success_at": sat.replace(hour=4, minute=10).isoformat()})
    assert backup_manager.should_run_backup(now=sat) is False


def test_execute_full_backup_sync_end_to_end(temp_backup_env, monkeypatch):
    monkeypatch.setattr(backup_manager, "is_db_available", lambda: True)

    # 14개 테이블 목킹
    def mock_dump(table_name):
        return [{"id": 1, "name": f"row_in_{table_name}"}]

    monkeypatch.setattr(backup_manager, "dump_supabase_table", mock_dump)

    # GDrive 목킹
    monkeypatch.setenv("GDRIVE_CLIENT_ID", "cid")
    monkeypatch.setenv("GDRIVE_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("GDRIVE_REFRESH_TOKEN", "rtok")

    with patch("core.gdrive_client.refresh_access_token", return_value={"access_token": "mock_token"}), \
         patch("core.gdrive_client.upload_file_to_gdrive", return_value={"id": "gdrive_file_123"}), \
         patch("core.gdrive_client.list_gdrive_backups", return_value=[]):

        res = backup_manager.execute_full_backup_sync()
        assert res["status"] == "success"
        assert res["gdrive_id"] == "gdrive_file_123"
        assert res["total_rows"] == 14

    # fallback_latest.sqlite3 생성 확인 및 query_fallback 테스트
    assert os.path.exists(temp_backup_env["fallback_file"])
    assert db.is_fallback_available() is True

    fb_rows = db.query_fallback("users")
    assert len(fb_rows) == 1
    assert fb_rows[0]["name"] == "row_in_users"


def test_execute_full_backup_sync_aborts_on_table_dump_error(temp_backup_env, monkeypatch):
    monkeypatch.setattr(backup_manager, "is_db_available", lambda: True)

    # 기존 fallback_latest.sqlite3 파일 생성
    fallback_path = temp_backup_env["fallback_file"]
    backup_manager.create_sqlite_snapshot(
        {"users": [{"user_id": "keep_me", "username": "original"}]},
        str(fallback_path),
    )

    def mock_dump_with_error(table_name):
        if table_name == "orders":
            raise RuntimeError("Supabase 503 Service Unavailable")
        return [{"id": 1}]

    monkeypatch.setattr(backup_manager, "dump_supabase_table", mock_dump_with_error)

    res = backup_manager.execute_full_backup_sync()
    assert res["status"] == "error"
    assert "Supabase 503 Service Unavailable" in res["error"]

    state = backup_manager.load_backup_state()
    assert state["last_status"] == "error"

    # 기존 fallback_latest.sqlite3가 빈 DB로 덮어써지지 않고 유지되었는지 검증
    fb_rows = db.query_fallback("users")
    assert len(fb_rows) == 1
    assert fb_rows[0]["user_id"] == "keep_me"


def test_query_fallback_restores_boolean_and_json(temp_backup_env):
    fallback_path = str(temp_backup_env["fallback_file"])
    backup_manager.create_sqlite_snapshot(
        {
            "users": [
                {"user_id": "u1", "is_admin": True, "is_active": False, "preferences": {"a": 1}},
            ]
        },
        fallback_path,
    )

    rows = db.query_fallback("users")
    assert len(rows) == 1
    row = rows[0]
    assert row["is_admin"] is True
    assert row["is_active"] is False
    assert row["preferences"] == {"a": 1}


def test_execute_full_backup_sync_partial_error_on_gdrive_failure(temp_backup_env, monkeypatch):
    monkeypatch.setattr(backup_manager, "is_db_available", lambda: True)
    monkeypatch.setattr(
        backup_manager,
        "dump_supabase_table",
        lambda table_name: [{"id": 1, "name": f"row_in_{table_name}"}],
    )

    monkeypatch.setenv("GDRIVE_CLIENT_ID", "cid")
    monkeypatch.setenv("GDRIVE_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("GDRIVE_REFRESH_TOKEN", "rtok")

    with patch("core.gdrive_client.refresh_access_token", side_effect=RuntimeError("OAuth token expired")):
        res = backup_manager.execute_full_backup_sync()
        assert res["status"] == "partial_error"
        assert "GDrive upload failed" in res["error"]

    state = backup_manager.load_backup_state()
    assert state["last_status"] == "partial_error"
    assert "OAuth token expired" in state["last_error"]


def test_resolve_gdrive_credentials_db_priority(monkeypatch):
    monkeypatch.setenv("GDRIVE_CLIENT_ID", "env_cid")
    monkeypatch.setenv("GDRIVE_CLIENT_SECRET", "env_sec")
    monkeypatch.setenv("GDRIVE_REFRESH_TOKEN", "env_tok")
    monkeypatch.setenv("GDRIVE_FOLDER", "env_folder")

    # 1. DB에 아무것도 없으면 .env 사용
    cid, sec, tok, email, folder = backup_manager._resolve_gdrive_credentials({})
    assert cid == "env_cid"
    assert sec == "env_sec"
    assert tok == "env_tok"
    assert folder == "env_folder"
    assert email == ""

    # 2. DB에 설정이 있으면 DB 값 우선
    db_rows = {
        "backup_gdrive_client_id": "db_cid",
        "backup_gdrive_client_secret": "db_sec",
        "backup_gdrive_refresh_token": "db_tok",
        "backup_gdrive_user_email": "admin@gmail.com",
        "backup_gdrive_folder": "my-supabot-backups",
    }
    cid, sec, tok, email, folder = backup_manager._resolve_gdrive_credentials(db_rows)
    assert cid == "db_cid"
    assert sec == "db_sec"
    assert tok == "db_tok"
    assert email == "admin@gmail.com"
    assert folder == "my-supabot-backups"


def test_resolve_gdrive_credentials_encrypted_token(monkeypatch):
    monkeypatch.setenv("USER_SECRET_KEY", "uO_v_YqG23L_u-N2_O4zB_Jc0X0oK9_Hq_T_z123456=")
    from core.secret_crypto import encrypt_secret
    
    raw_token = "secret_refresh_token_abc"
    enc = encrypt_secret(raw_token)
    assert enc.startswith("enc:v1:")

    db_rows = {
        "backup_gdrive_refresh_token": enc,
    }
    _, _, tok, _, _ = backup_manager._resolve_gdrive_credentials(db_rows)
    assert tok == raw_token
