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

    async def rpc(self, func_name: str, params: dict | None = None) -> _APIResponse:
        url = f"{self._base}/rpc/{func_name}"
        resp = await self._client.post(
            url,
            json=params or {},
            timeout=15.0,
        )
        if not resp.is_success:
            raise RuntimeError(f"Supabase RPC [{resp.status_code}]: {resp.text[:300]}")
        data = resp.json() if resp.text.strip() else None
        return _APIResponse(data=data)

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

async def get_supabase_health_stats(db=None) -> dict | None:
    """Supabase 데이터베이스 용량 및 무료 티어(500MB) 상태 계산"""
    try:
        if db is None:
            db = get_db()
    except Exception:
        return None

    limit_mb = 500.0  # Supabase 무료 티어 한도: 500MB

    db_size_bytes = None
    source = "estimated"
    try:
        if hasattr(db, "rpc"):
            rpc_res = await db.rpc("get_db_size_bytes")
            if isinstance(rpc_res.data, (int, float)):
                db_size_bytes = int(rpc_res.data)
                source = "database_actual"
    except Exception:
        pass

    table_counts = {}
    tables = [
        ("users", 2048),
        ("orders", 1200),
        ("trade_logs", 800),
        ("operational_events", 1500),
        ("kr_stock_cache", 500),
        ("command_logs", 500),
        ("user_daily_summary", 600),
        ("daily_stats", 600),
    ]

    estimated_data_bytes = 0
    for tbl, row_size in tables:
        try:
            cnt = (await db.table(tbl).select("*", count="exact").limit(0).execute()).count or 0
            table_counts[tbl] = cnt
            estimated_data_bytes += cnt * row_size
        except Exception:
            table_counts[tbl] = 0

    if db_size_bytes is None:
        # PostgreSQL 시스템 카탈로그, WAL 및 인덱스 오버헤드 (~32MB) + 테이블 추정치
        base_overhead_bytes = 32 * 1024 * 1024
        db_size_bytes = base_overhead_bytes + estimated_data_bytes

    used_mb = round(db_size_bytes / (1024 * 1024), 2)
    remaining_mb = max(0.0, round(limit_mb - used_mb, 2))
    usage_pct = min(100.0, round((used_mb / limit_mb) * 100, 1))

    if usage_pct < 75.0:
        health_status = "healthy"
    elif usage_pct < 90.0:
        health_status = "warning"
    else:
        health_status = "critical"

    return {
        "limit_mb": limit_mb,
        "used_mb": used_mb,
        "remaining_mb": remaining_mb,
        "usage_pct": usage_pct,
        "health_status": health_status,
        "source": source,
        "table_counts": table_counts,
    }
