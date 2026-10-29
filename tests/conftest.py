import os
import sys
import asyncio
import dotenv
import pytest


# config/.env가 로드되더라도 SUPABASE_URL/SUPABASE_SERVICE_KEY는 테스트 중에 비워둔다 (라이브 네트워크/타임아웃 방지)
_orig_load_dotenv = dotenv.load_dotenv

def _mock_load_dotenv(*args, **kwargs):
    res = _orig_load_dotenv(*args, **kwargs)
    os.environ["SUPABASE_URL"] = ""
    os.environ["SUPABASE_SERVICE_KEY"] = ""
    return res

dotenv.load_dotenv = _mock_load_dotenv

os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_KEY"] = ""
os.environ.setdefault("SESSION_SECRET", "test-session-secret-for-testing-only-1234567890123456")
os.environ.setdefault("USER_SECRET_KEY", "bW9jay1mZXJuZXQta2V5LWZvci10ZXN0aW5nLTEyMzQ1Ng==")


@pytest.fixture(autouse=True)
def clean_test_snooze():
    """테스트 간 스누즈 파일 오염 방지."""
    snooze_path = "data/snooze.json"
    if os.path.exists(snooze_path):
        try:
            os.remove(snooze_path)
        except OSError:
            pass
    yield
    if os.path.exists(snooze_path):
        try:
            os.remove(snooze_path)
        except OSError:
            pass

