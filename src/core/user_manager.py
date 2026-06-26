import json
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from core.bot_logger import get_logger
from core.db import get_db, is_db_available
from core.secret_crypto import can_decrypt_secrets, decrypt_secret, encrypt_secret, has_secret_key, is_encrypted_secret

_log = get_logger("user_manager")

KST = timezone(timedelta(hours=9))

# fire-and-forget DB 쓰기 태스크 강한 참조 보관 (asyncio weak-ref GC로 유실 방지).
_bg_tasks: set = set()


def _track_task(task):
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


class UserManager:
    SECRET_EXCHANGE_FIELDS = {
        "upbit": ("access_key", "secret_key"),
        "bithumb": ("access_key", "secret_key"),
        "kis": ("app_key", "app_secret", "account_no"),
        "toss": ("client_id", "client_secret"),
    }
    SECRET_LLM_FIELDS = ("gemini_api_key",)

    DEFAULT_PREFERENCES = {
        "default_exchange": "upbit",
        "asset_min_display_krw": 10000,
        "rsi_buy_range": "25-30",
        "rsi_sell_range": "65-75",
        "rsi_order_count": 5,
        "rsi_budget_krw": None,
        "signal_alerts": True,
        "signal_rsi_threshold": 30,
        "signal_bb_alert": False,
        "rsi_interval": "day",
        "max_order_krw": None,
        "max_open_exposure_krw": None,
        "stop_loss_pct": None,
        "quiet_hours_start": None,
        "quiet_hours_end": None,
        "llm_enabled": False,
        "llm_model": "gemini-2.5-flash-lite",
        "poll_active_interval": 60,
        "poll_no_order_interval": 300,
        "signal_analysis_interval": 300,
    }

    def __init__(self, file_path="data/users.json"):
        self.file_path = file_path
        self.users = self._load_users()
        if self._ensure_all_user_defaults():
            self.save_users()

    # ── Load ──────────────────────────────────────────────────────────────────

    def _load_users(self) -> dict:
        if is_db_available():
            try:
                rows = get_db().table("users").select("*").execute().data
                users = {row["user_id"]: self._db_row_to_user(row) for row in rows}
                _log.info("Loaded users from DB", extra={"event": "users_loaded_db", "count": len(users)})
                return users
            except Exception as e:
                _log.error("Failed to load users from DB, falling back to file", exc_info=e, extra={"event": "db_users_load_error"})
        return self._load_users_from_file()

    def reload_from_db(self) -> bool:
        """관리자 /dbsync 등에서 DB 상태를 인메모리에 즉시 반영한다.

        manager UI는 users 테이블에 직접 쓰기 때문에(승인/비활성화/watchlist 등),
        봇 프로세스가 재시작 전까지 그 변경을 모른다 — 이 메서드가 유일한 풀(pull) 경로다.
        DB 미사용 환경에서는 no-op.
        """
        if not is_db_available():
            return False
        try:
            rows = get_db().table("users").select("*").execute().data
            self.users = {row["user_id"]: self._db_row_to_user(row) for row in rows}
            _log.info("Reloaded users from DB", extra={"event": "users_reloaded_db", "count": len(self.users)})
            return True
        except Exception as e:
            _log.error("Failed to reload users from DB", exc_info=e, extra={"event": "db_users_reload_error"})
            return False

    def refresh_user(self, user_id) -> bool:
        """단일 유저 row만 DB에서 다시 읽어 인메모리에 반영한다.

        manager UI가 승인/비활성화 등으로 DB를 직접 갱신한 뒤, 해당 유저가 곧바로
        /start 등을 호출했을 때 전체 reload_from_db() 없이 가볍게 동기화하기 위함.
        DB 미사용 환경, 또는 해당 유저 row가 없으면 no-op.
        """
        if not is_db_available():
            return False
        try:
            rows = get_db().table("users").select("*").eq("user_id", str(user_id)).execute().data
            if not rows:
                return False
            self.users[str(user_id)] = self._db_row_to_user(rows[0])
            return True
        except Exception as e:
            _log.error("Failed to refresh user from DB", exc_info=e, extra={"event": "db_user_refresh_error", "user_id": str(user_id)})
            return False

    def _load_users_from_file(self) -> dict:
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            _log.error("Failed to load users from file", exc_info=e, extra={"event": "users_load_error"})
            return {}

    # ── DB ↔ memory conversion ────────────────────────────────────────────────

    @staticmethod
    def _db_row_to_user(row: dict) -> dict:
        return {
            "username": row.get("username", ""),
            "is_admin": row.get("is_admin", False),
            "is_active": row.get("status") == "active",
            "status": row.get("status", "pending"),
            "preferences": row.get("preferences") or {},
            "exchanges": row.get("exchanges") or {},
            "llm": row.get("llm") or {},
            "api_validation": row.get("api_validation") or {},
        }

    @staticmethod
    def _user_to_db_row(user_id: str, user: dict) -> dict:
        # Prefer explicit status; derive from is_active only as fallback
        status = user.get("status") or ("active" if user.get("is_active") else "pending")
        return {
            "user_id": user_id,
            "username": user.get("username", ""),
            "is_admin": bool(user.get("is_admin", False)),
            "status": status,
            "preferences": user.get("preferences") or {},
            "exchanges": user.get("exchanges") or {},
            "llm": user.get("llm") or {},
            "api_validation": user.get("api_validation") or {},
        }

    # ── Save ──────────────────────────────────────────────────────────────────

    def save_users(self):
        """Full-table upsert — used on startup. Prefer _upsert_user() for single-row writes."""
        if is_db_available():
            try:
                rows = [self._user_to_db_row(uid, u) for uid, u in self.users.items()]
                if rows:
                    get_db().table("users").upsert(rows).execute()
                return
            except Exception as e:
                _log.error("Failed to save users to DB", exc_info=e, extra={"event": "db_users_save_error"})
        self._save_users_to_file()

    def _save_users_to_file(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
            os.chmod(self.file_path, 0o600)
        except Exception as e:
            _log.error("Failed to save users to file", exc_info=e, extra={"event": "users_save_error"})

    def _upsert_user(self, user_id: str):
        """Single-user DB upsert — called after every in-memory mutation."""
        if not is_db_available():
            self._save_users_to_file()
            return
        user = self.users.get(str(user_id))
        if not user:
            return
        db_row = self._user_to_db_row(str(user_id), user)

        async def _run():
            try:
                await get_db().table("users").upsert(db_row).execute_async()
            except Exception as e:
                _log.error("Failed to upsert user (async)", exc_info=e, extra={"event": "db_user_upsert_error", "user_id": user_id})
                self._save_users_to_file()
                from core.db_sync import enqueue_task
                try:
                    await enqueue_task("upsert", "users", "user_id", str(user_id), db_row)
                except Exception as ex:
                    _log.error("Failed to enqueue user upsert task", exc_info=ex)

        import asyncio
        try:
            loop = asyncio.get_running_loop()
            _track_task(loop.create_task(_run()))
        except RuntimeError:
            try:
                get_db().table("users").upsert(db_row).execute()
            except Exception as e:
                _log.error("Failed to upsert user in fallback", exc_info=e)
                self._save_users_to_file()

    # ── Default / migration helpers ───────────────────────────────────────────

    def get_user(self, user_id):
        stored_user = self.users.get(str(user_id))
        if stored_user and self._ensure_user_defaults(stored_user):
            self._upsert_user(user_id)
        return self._decrypt_user_copy(stored_user) if stored_user else None

    def _ensure_all_user_defaults(self):
        changed = False
        for user in self.users.values():
            changed = self._ensure_user_defaults(user) or changed
            changed = self._migrate_user_secrets(user) or changed
        return changed

    def _ensure_user_defaults(self, user):
        changed = False
        preferences = user.setdefault("preferences", {})
        for key, value in self.DEFAULT_PREFERENCES.items():
            if key not in preferences:
                preferences[key] = value
                changed = True
        user.setdefault("exchanges", {})
        llm = user.setdefault("llm", {})
        if "gemini_api_key" not in llm:
            llm["gemini_api_key"] = ""
            changed = True
        if "api_validation" not in user:
            user["api_validation"] = {}
            changed = True
        defaults = {
            "upbit": {"access_key": "", "secret_key": "", "watchlist": []},
            "bithumb": {"access_key": "", "secret_key": "", "watchlist": []},
            "kis": {
                "app_key": "",
                "app_secret": "",
                "account_no": "",
                "product_code": "01",
                "env": "paper",
                "watchlist": [],
            },
            "toss": {
                "client_id": "",
                "client_secret": "",
                "account_seq": None,
                "watchlist": [],
            },
        }
        for exchange, exchange_defaults in defaults.items():
            if exchange not in user["exchanges"]:
                user["exchanges"][exchange] = dict(exchange_defaults)
                changed = True
            else:
                for key, value in exchange_defaults.items():
                    if key not in user["exchanges"][exchange]:
                        user["exchanges"][exchange][key] = value
                        changed = True
        return changed

    def _migrate_user_secrets(self, user):
        if not has_secret_key() or not can_decrypt_secrets():
            return False
        changed = False
        for exchange, fields in self.SECRET_EXCHANGE_FIELDS.items():
            exchange_data = user.get("exchanges", {}).get(exchange, {})
            for field in fields:
                value = exchange_data.get(field, "")
                if value and not is_encrypted_secret(value):
                    exchange_data[field] = encrypt_secret(value)
                    changed = True
        llm = user.get("llm", {})
        for field in self.SECRET_LLM_FIELDS:
            value = llm.get(field, "")
            if value and not is_encrypted_secret(value):
                llm[field] = encrypt_secret(value)
                changed = True
        return changed

    def _decrypt_user_copy(self, user):
        user_copy = deepcopy(user)
        secret_error = False
        for exchange, fields in self.SECRET_EXCHANGE_FIELDS.items():
            exchange_data = user_copy.get("exchanges", {}).get(exchange, {})
            for field in fields:
                if field in exchange_data:
                    try:
                        exchange_data[field] = decrypt_secret(exchange_data[field])
                    except ValueError:
                        exchange_data[field] = ""
                        secret_error = True
        llm = user_copy.get("llm", {})
        for field in self.SECRET_LLM_FIELDS:
            if field in llm:
                try:
                    llm[field] = decrypt_secret(llm[field])
                except ValueError:
                    llm[field] = ""
                    secret_error = True
        if secret_error:
            user_copy["_secret_error"] = "USER_SECRET_KEY cannot decrypt one or more stored secrets"
        return user_copy

    def _encrypt_secret_for_storage(self, value):
        text = str(value or "").strip()
        if not text:
            return ""
        if not has_secret_key() and not is_encrypted_secret(text):
            raise ValueError("USER_SECRET_KEY is required to store user secrets")
        return encrypt_secret(text)

    # ── Mutations ─────────────────────────────────────────────────────────────

    def add_user(self, user_id, username, is_admin=False):
        user_id_str = str(user_id)
        if user_id_str not in self.users:
            self.users[user_id_str] = {
                "username": username,
                "is_admin": is_admin,
                "is_active": is_admin,
                "status": "active" if is_admin else "pending",
                "preferences": dict(self.DEFAULT_PREFERENCES),
                "exchanges": {
                    "upbit": {"access_key": "", "secret_key": "", "watchlist": []},
                    "bithumb": {"access_key": "", "secret_key": "", "watchlist": []},
                    "kis": {
                        "app_key": "",
                        "app_secret": "",
                        "account_no": "",
                        "product_code": "01",
                        "env": "paper",
                        "watchlist": [],
                    },
                    "toss": {
                        "client_id": "",
                        "client_secret": "",
                        "account_seq": None,
                        "watchlist": [],
                    },
                },
                "llm": {"gemini_api_key": ""},
                "api_validation": {},
            }
            self._upsert_user(user_id_str)
            return True
        return False

    def update_preference(self, user_id, key, value):
        user = self.users.get(str(user_id))
        if not user:
            return False
        user["preferences"][key] = value
        self._upsert_user(user_id)
        return True

    def update_gemini_api_key(self, user_id, api_key):
        user = self.users.get(str(user_id))
        if not user:
            return False
        user.setdefault("llm", {})["gemini_api_key"] = self._encrypt_secret_for_storage(api_key)
        self._upsert_user(user_id)
        return True

    def update_exchange_keys(self, user_id, exchange, access_key, secret_key):
        user = self.users.get(str(user_id))
        if user and exchange in user["exchanges"]:
            user["exchanges"][exchange]["access_key"] = self._encrypt_secret_for_storage(access_key)
            user["exchanges"][exchange]["secret_key"] = self._encrypt_secret_for_storage(secret_key)
            self._upsert_user(user_id)
            return True
        return False

    def update_api_validation_status(self, user_id, exchange, is_valid, message=""):
        user = self.users.get(str(user_id))
        if not user:
            return False
        user.setdefault("api_validation", {})[exchange] = {
            "ok": bool(is_valid),
            "checked_at": datetime.now(KST).isoformat(timespec="seconds"),
            "message": str(message or ""),
        }
        self._upsert_user(user_id)
        return True

    def update_toss_keys(self, user_id, client_id, client_secret):
        user = self.users.get(str(user_id))
        if user and "toss" in user["exchanges"]:
            user["exchanges"]["toss"]["client_id"] = self._encrypt_secret_for_storage(client_id)
            user["exchanges"]["toss"]["client_secret"] = self._encrypt_secret_for_storage(client_secret)
            user["exchanges"]["toss"]["account_seq"] = None
            self._upsert_user(user_id)
            return True
        return False

    def update_toss_account_seq(self, user_id, account_seq):
        user = self.users.get(str(user_id))
        if user and "toss" in user["exchanges"]:
            user["exchanges"]["toss"]["account_seq"] = account_seq
            self._upsert_user(user_id)
            return True
        return False

    def update_kis_keys(self, user_id, app_key, app_secret, account_no, product_code="01", env="paper"):
        user = self.users.get(str(user_id))
        if user and "kis" in user["exchanges"]:
            user["exchanges"]["kis"]["app_key"] = self._encrypt_secret_for_storage(app_key)
            user["exchanges"]["kis"]["app_secret"] = self._encrypt_secret_for_storage(app_secret)
            user["exchanges"]["kis"]["account_no"] = self._encrypt_secret_for_storage(account_no)
            user["exchanges"]["kis"]["product_code"] = product_code
            user["exchanges"]["kis"]["env"] = env
            self._upsert_user(user_id)
            return True
        return False

    def set_active(self, user_id, status=True):
        user = self.users.get(str(user_id))
        if user:
            user["is_active"] = status
            user["status"] = "active" if status else "inactive"
            self._upsert_user(user_id)
            return True
        return False

    def add_watchlist(self, user_id, exchange, ticker):
        user = self.users.get(str(user_id))
        if user and exchange in user["exchanges"]:
            if ticker not in user["exchanges"][exchange]["watchlist"]:
                user["exchanges"][exchange]["watchlist"].append(ticker.upper())
                self._upsert_user(user_id)
                return True
        return False

    def remove_watchlist(self, user_id, exchange, ticker):
        user = self.users.get(str(user_id))
        if user and exchange in user["exchanges"]:
            if ticker.upper() in user["exchanges"][exchange]["watchlist"]:
                user["exchanges"][exchange]["watchlist"].remove(ticker.upper())
                self._upsert_user(user_id)
                return True
        return False

    def initialize_admin(self, admin_chat_id):
        if not admin_chat_id:
            return False
        admin_id_str = str(admin_chat_id)
        if admin_id_str not in self.users:
            _log.info("Registering initial admin", extra={"event": "admin_init", "user_id": admin_id_str})
            return self.add_user(admin_id_str, "SystemAdmin", is_admin=True)
        return True


def is_quiet_hours(user: dict) -> bool:
    prefs = user.get("preferences", {})
    start = prefs.get("quiet_hours_start")
    end = prefs.get("quiet_hours_end")
    if not start or not end:
        return False
    now_str = datetime.now(KST).strftime("%H:%M")
    if start <= end:
        return start <= now_str < end
    return now_str >= start or now_str < end
