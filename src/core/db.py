import os

import requests as _requests

_client = None


class _APIResponse:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    def __init__(self, session, method, url, params=None, json=None, extra_headers=None):
        self._session = session
        self._method = method
        self._url = url
        self._params = dict(params or {})
        self._json = json
        self._extra_headers = extra_headers or {}

    def execute(self) -> _APIResponse:
        resp = self._session.request(
            self._method, self._url,
            params=self._params,
            json=self._json,
            headers=self._extra_headers,
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(f"Supabase [{resp.status_code}]: {resp.text[:300]}")
        data = resp.json() if resp.text.strip() else []
        count = None
        cr = resp.headers.get("content-range", "")
        if cr and "/" in cr:
            try:
                count = int(cr.split("/")[-1])
            except ValueError:
                pass
        return _APIResponse(data=data, count=count)


class _FilteredQuery(_Query):
    def eq(self, column: str, value) -> "_FilteredQuery":
        self._params[column] = f"eq.{value}"
        return self

    def in_(self, column: str, values: list) -> "_FilteredQuery":
        self._params[column] = "in.({})".format(",".join(str(v) for v in values))
        return self


class _Table:
    def __init__(self, session, url: str):
        self._session = session
        self._url = url

    def select(self, columns: str = "*", count: str | None = None) -> _Query:
        params = {"select": columns}
        if count:
            params["count"] = count
        return _Query(self._session, "GET", self._url, params=params)

    def insert(self, data) -> _Query:
        return _Query(self._session, "POST", self._url, json=data,
                      extra_headers={"Prefer": "return=minimal"})

    def upsert(self, data) -> _Query:
        return _Query(self._session, "POST", self._url, json=data,
                      extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"})

    def update(self, data) -> _FilteredQuery:
        return _FilteredQuery(self._session, "PATCH", self._url, json=data)

    def delete(self) -> _FilteredQuery:
        return _FilteredQuery(self._session, "DELETE", self._url)


class _SupabaseClient:
    def __init__(self, url: str, key: str):
        self._base = f"{url.rstrip('/')}/rest/v1"
        self._session = _requests.Session()
        self._session.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })

    def table(self, name: str) -> _Table:
        return _Table(self._session, f"{self._base}/{name}")


def get_db() -> _SupabaseClient:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _client = _SupabaseClient(url, key)
    return _client


def is_db_available() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"))
