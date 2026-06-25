import os
import httpx

_client = None

class _APIResponse:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count

class _Query:
    def __init__(self, client, method, url, params=None, json=None, extra_headers=None):
        self._client = client
        self._method = method
        self._url = url
        self._params = dict(params or {})
        self._json = json
        self._extra_headers = extra_headers or {}

    async def execute(self) -> _APIResponse:
        resp = await self._client.request(
            self._method, self._url,
            params=self._params,
            json=self._json,
            headers=self._extra_headers,
            timeout=30.0,
        )
        if not resp.is_success:
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

    def is_(self, column: str, value: str) -> "_FilteredQuery":
        self._params[column] = f"is.{value}"
        return self

    def in_(self, column: str, values: list) -> "_FilteredQuery":
        self._params[column] = "in.({})".format(",".join(str(v) for v in values))
        return self

    def order(self, column: str, desc: bool = False) -> "_FilteredQuery":
        self._params["order"] = f"{column}.{'desc' if desc else 'asc'}"
        return self

    def limit(self, n: int) -> "_FilteredQuery":
        self._params["limit"] = n
        return self

    def or_(self, expr: str) -> "_FilteredQuery":
        self._params["or"] = f"({expr})"
        return self

    def range(self, start: int, end: int) -> "_FilteredQuery":
        self._extra_headers["Range-Unit"] = "items"
        self._extra_headers["Range"] = f"{start}-{end}"
        return self

class _Table:
    def __init__(self, client, url: str):
        self._client = client
        self._url = url

    def select(self, columns: str = "*", count: str | None = None) -> _FilteredQuery:
        params = {"select": columns}
        extra_headers = {}
        if count:
            extra_headers["Prefer"] = f"count={count}"
        return _FilteredQuery(self._client, "GET", self._url, params=params, extra_headers=extra_headers)

    def insert(self, data) -> _Query:
        return _Query(self._client, "POST", self._url, json=data,
                      extra_headers={"Prefer": "return=minimal"})

    def upsert(self, data) -> _Query:
        return _Query(self._client, "POST", self._url, json=data,
                      extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"})

    def update(self, data) -> _FilteredQuery:
        return _FilteredQuery(self._client, "PATCH", self._url, json=data,
                              extra_headers={"Prefer": "return=representation"})

    def delete(self) -> _FilteredQuery:
        return _FilteredQuery(self._client, "DELETE", self._url)

class _SupabaseClient:
    def __init__(self, url: str, key: str):
        self._base = f"{url.rstrip('/')}/rest/v1"
        self._client = httpx.AsyncClient(headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })

    def table(self, name: str) -> _Table:
        return _Table(self._client, f"{self._base}/{name}")

    async def close(self):
        await self._client.aclose()

def get_db() -> _SupabaseClient:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _client = _SupabaseClient(url, key)
    return _client

async def get_stock_name_map() -> dict[str, str]:
    """kr_stock_cache 테이블을 읽어 {code: name} 맵을 구성합니다."""
    db = get_db()
    rows = []
    page_size = 1000
    offset = 0
    try:
        while True:
            res = await db.table("kr_stock_cache").select("name,code").range(offset, offset + page_size - 1).execute()
            chunk = res.data or []
            rows.extend(chunk)
            if len(chunk) < page_size:
                break
            offset += page_size
    except Exception:
        pass
    return {row["code"]: row["name"] for row in rows if "code" in row and "name" in row}
