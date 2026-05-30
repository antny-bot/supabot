import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from cryptography.fernet import Fernet

from core.user_manager import UserManager


def test_user_manager_encrypts_new_exchange_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_SECRET_KEY", Fernet.generate_key().decode())
    path = tmp_path / "users.json"
    manager = UserManager(str(path))
    manager.add_user("1", "alice", is_admin=True)

    assert manager.update_exchange_keys("1", "upbit", "access-plain", "secret-plain")

    raw = path.read_text(encoding="utf-8")
    assert "access-plain" not in raw
    assert "secret-plain" not in raw
    stored = json.loads(raw)
    assert stored["1"]["exchanges"]["upbit"]["access_key"].startswith("enc:v1:")
    assert manager.get_user("1")["exchanges"]["upbit"]["access_key"] == "access-plain"


def test_user_manager_migrates_plaintext_secrets_on_load(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_SECRET_KEY", Fernet.generate_key().decode())
    path = tmp_path / "users.json"
    path.write_text(
        json.dumps(
            {
                "1": {
                    "username": "alice",
                    "is_admin": True,
                    "is_active": True,
                    "preferences": dict(UserManager.DEFAULT_PREFERENCES),
                    "exchanges": {
                        "upbit": {"access_key": "plain-access", "secret_key": "plain-secret", "watchlist": []},
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
                    "llm": {"gemini_api_key": "gemini-plain"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manager = UserManager(str(path))
    stored = json.loads(path.read_text(encoding="utf-8"))

    assert stored["1"]["exchanges"]["upbit"]["access_key"].startswith("enc:v1:")
    assert stored["1"]["llm"]["gemini_api_key"].startswith("enc:v1:")
    assert manager.get_user("1")["llm"]["gemini_api_key"] == "gemini-plain"


def test_user_manager_does_not_reencrypt_encrypted_values(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_SECRET_KEY", Fernet.generate_key().decode())
    path = tmp_path / "users.json"
    manager = UserManager(str(path))
    manager.add_user("1", "alice", is_admin=True)
    manager.update_gemini_api_key("1", "gemini-plain")
    first = json.loads(path.read_text(encoding="utf-8"))["1"]["llm"]["gemini_api_key"]

    manager = UserManager(str(path))
    second = json.loads(path.read_text(encoding="utf-8"))["1"]["llm"]["gemini_api_key"]

    assert second == first
    assert manager.get_user("1")["llm"]["gemini_api_key"] == "gemini-plain"


def test_user_manager_keeps_empty_secrets_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_SECRET_KEY", Fernet.generate_key().decode())
    path = tmp_path / "users.json"
    manager = UserManager(str(path))
    manager.add_user("1", "alice", is_admin=True)

    assert manager.update_exchange_keys("1", "upbit", "", "")

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["1"]["exchanges"]["upbit"]["access_key"] == ""
    assert stored["1"]["exchanges"]["upbit"]["secret_key"] == ""


def test_user_manager_rejects_new_secret_without_master_key(tmp_path, monkeypatch):
    monkeypatch.delenv("USER_SECRET_KEY", raising=False)
    path = tmp_path / "users.json"
    manager = UserManager(str(path))
    manager.add_user("1", "alice", is_admin=True)

    try:
        manager.update_gemini_api_key("1", "gemini-plain")
    except ValueError as exc:
        assert "USER_SECRET_KEY" in str(exc)
    else:
        raise AssertionError("secret writes should require USER_SECRET_KEY")


def test_user_manager_does_not_crash_on_malformed_master_key(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_SECRET_KEY", "not-a-fernet-key")
    path = tmp_path / "users.json"
    path.write_text(
        json.dumps(
            {
                "1": {
                    "username": "alice",
                    "is_admin": True,
                    "is_active": True,
                    "preferences": dict(UserManager.DEFAULT_PREFERENCES),
                    "exchanges": {
                        "upbit": {"access_key": "plain-access", "secret_key": "plain-secret", "watchlist": []}
                    },
                    "llm": {"gemini_api_key": "gemini-plain"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manager = UserManager(str(path))
    user = manager.get_user("1")

    assert user["username"] == "alice"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["1"]["exchanges"]["upbit"]["access_key"] == "plain-access"


def test_user_manager_does_not_crash_when_encrypted_secret_uses_different_key(tmp_path, monkeypatch):
    original_key = Fernet.generate_key().decode()
    monkeypatch.setenv("USER_SECRET_KEY", original_key)
    path = tmp_path / "users.json"
    manager = UserManager(str(path))
    manager.add_user("1", "alice", is_admin=True)
    manager.update_exchange_keys("1", "upbit", "access-plain", "secret-plain")

    monkeypatch.setenv("USER_SECRET_KEY", Fernet.generate_key().decode())
    manager = UserManager(str(path))
    user = manager.get_user("1")

    assert user["username"] == "alice"
    assert user["exchanges"]["upbit"]["access_key"] == ""
    assert user["exchanges"]["upbit"]["secret_key"] == ""
    assert user["_secret_error"] == "USER_SECRET_KEY cannot decrypt one or more stored secrets"
