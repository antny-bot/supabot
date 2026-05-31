import json
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from core.secret_crypto import can_decrypt_secrets, decrypt_secret, encrypt_secret, has_secret_key, is_encrypted_secret


KST = timezone(timedelta(hours=9))

class UserManager:
    SECRET_EXCHANGE_FIELDS = {
        "upbit": ("access_key", "secret_key"),
        "bithumb": ("access_key", "secret_key"),
        "kis": ("app_key", "app_secret", "account_no"),
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
        "rsi_interval": "day",
        "max_order_krw": None,
        "stop_loss_pct": None,
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

    def _load_users(self):
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading users: {e}")
            return {}

    def save_users(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
            os.chmod(self.file_path, 0o600)
        except Exception as e:
            print(f"Error saving users: {e}")

    def get_user(self, user_id):
        stored_user = self.users.get(str(user_id))
        if stored_user and self._ensure_user_defaults(stored_user):
            self.save_users()
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
        exchanges = user.setdefault("exchanges", {})
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
        }
        for exchange, exchange_defaults in defaults.items():
            if exchange not in exchanges:
                exchanges[exchange] = dict(exchange_defaults)
                changed = True
            else:
                for key, value in exchange_defaults.items():
                    if key not in exchanges[exchange]:
                        exchanges[exchange][key] = value
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

    def add_user(self, user_id, username, is_admin=False):
        user_id_str = str(user_id)
        if user_id_str not in self.users:
            self.users[user_id_str] = {
                "username": username,
                "is_admin": is_admin,
                "is_active": is_admin,  # 어드민은 즉시 활성화
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
                },
                "llm": {"gemini_api_key": ""},
                "api_validation": {},
            }
            self.save_users()
            return True
        return False

    def update_preference(self, user_id, key, value):
        user = self.users.get(str(user_id))
        if not user:
            return False
        user["preferences"][key] = value
        self.save_users()
        return True

    def update_gemini_api_key(self, user_id, api_key):
        user = self.users.get(str(user_id))
        if not user:
            return False
        user.setdefault("llm", {})["gemini_api_key"] = self._encrypt_secret_for_storage(api_key)
        self.save_users()
        return True

    def update_exchange_keys(self, user_id, exchange, access_key, secret_key):
        user = self.users.get(str(user_id))
        if user and exchange in user["exchanges"]:
            user["exchanges"][exchange]["access_key"] = self._encrypt_secret_for_storage(access_key)
            user["exchanges"][exchange]["secret_key"] = self._encrypt_secret_for_storage(secret_key)
            self.save_users()
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
        self.save_users()
        return True

    def update_kis_keys(self, user_id, app_key, app_secret, account_no, product_code="01", env="paper"):
        user = self.users.get(str(user_id))
        if user and "kis" in user["exchanges"]:
            user["exchanges"]["kis"]["app_key"] = self._encrypt_secret_for_storage(app_key)
            user["exchanges"]["kis"]["app_secret"] = self._encrypt_secret_for_storage(app_secret)
            user["exchanges"]["kis"]["account_no"] = self._encrypt_secret_for_storage(account_no)
            user["exchanges"]["kis"]["product_code"] = product_code
            user["exchanges"]["kis"]["env"] = env
            self.save_users()
            return True
        return False

    def set_active(self, user_id, status=True):
        user = self.users.get(str(user_id))
        if user:
            user["is_active"] = status
            self.save_users()
            return True
        return False

    def add_watchlist(self, user_id, exchange, ticker):
        user = self.users.get(str(user_id))
        if user and exchange in user["exchanges"]:
            if ticker not in user["exchanges"][exchange]["watchlist"]:
                user["exchanges"][exchange]["watchlist"].append(ticker.upper())
                self.save_users()
                return True
        return False

    def remove_watchlist(self, user_id, exchange, ticker):
        user = self.users.get(str(user_id))
        if user and exchange in user["exchanges"]:
            if ticker.upper() in user["exchanges"][exchange]["watchlist"]:
                user["exchanges"][exchange]["watchlist"].remove(ticker.upper())
                self.save_users()
                return True
        return False

    def initialize_admin(self, admin_chat_id):
        """환경 변수의 ADMIN_CHAT_ID를 기반으로 초기 관리자 등록"""
        if not admin_chat_id:
            return False
        
        admin_id_str = str(admin_chat_id)
        if admin_id_str not in self.users:
            print(f"⚙️ 초기 관리자 등록 중... (ID: {admin_id_str})")
            return self.add_user(admin_id_str, "SystemAdmin", is_admin=True)
        return True
