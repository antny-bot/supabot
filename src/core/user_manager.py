import json
import os

class UserManager:
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
        user = self.users.get(str(user_id))
        if user and self._ensure_user_defaults(user):
            self.save_users()
        return user

    def _ensure_all_user_defaults(self):
        changed = False
        for user in self.users.values():
            changed = self._ensure_user_defaults(user) or changed
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
                "llm": {"gemini_api_key": ""}
            }
            self.save_users()
            return True
        return False

    def update_preference(self, user_id, key, value):
        user = self.get_user(user_id)
        if not user:
            return False
        user["preferences"][key] = value
        self.save_users()
        return True

    def update_gemini_api_key(self, user_id, api_key):
        user = self.get_user(user_id)
        if not user:
            return False
        user.setdefault("llm", {})["gemini_api_key"] = str(api_key or "").strip()
        self.save_users()
        return True

    def update_exchange_keys(self, user_id, exchange, access_key, secret_key):
        user = self.get_user(user_id)
        if user and exchange in user["exchanges"]:
            user["exchanges"][exchange]["access_key"] = access_key
            user["exchanges"][exchange]["secret_key"] = secret_key
            self.save_users()
            return True
        return False

    def update_kis_keys(self, user_id, app_key, app_secret, account_no, product_code="01", env="paper"):
        user = self.get_user(user_id)
        if user and "kis" in user["exchanges"]:
            user["exchanges"]["kis"]["app_key"] = app_key
            user["exchanges"]["kis"]["app_secret"] = app_secret
            user["exchanges"]["kis"]["account_no"] = account_no
            user["exchanges"]["kis"]["product_code"] = product_code
            user["exchanges"]["kis"]["env"] = env
            self.save_users()
            return True
        return False

    def set_active(self, user_id, status=True):
        user = self.get_user(user_id)
        if user:
            user["is_active"] = status
            self.save_users()
            return True
        return False

    def add_watchlist(self, user_id, exchange, ticker):
        user = self.get_user(user_id)
        if user and exchange in user["exchanges"]:
            if ticker not in user["exchanges"][exchange]["watchlist"]:
                user["exchanges"][exchange]["watchlist"].append(ticker.upper())
                self.save_users()
                return True
        return False

    def remove_watchlist(self, user_id, exchange, ticker):
        user = self.get_user(user_id)
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
