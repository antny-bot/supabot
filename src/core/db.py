import os

from supabase import Client, ClientOptions, create_client

_client: Client | None = None

_TIMEOUT = int(os.environ.get("SUPABASE_TIMEOUT", "30"))


def get_db() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _client = create_client(
            url, key,
            options=ClientOptions(
                postgrest_client_timeout=_TIMEOUT,
                storage_client_timeout=_TIMEOUT,
            ),
        )
    return _client


def is_db_available() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"))
