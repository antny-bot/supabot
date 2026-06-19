"""종목명-코드 캐시 관리 API (kr_stock_cache 테이블)."""
import asyncio
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ..db import get_db
from ._auth import get_admin_user

router = APIRouter()


class StockEntry(BaseModel):
    name: str
    code: str


# ── 목록 조회 ──────────────────────────────────────────────────────────────────

@router.get("/api/stock-cache")
async def list_stock_cache(
    search: str = Query("", alias="search"),
    _=Depends(get_admin_user),
):
    db = get_db()
    if search:
        s = search.strip()
        rows = (
            await db.table("kr_stock_cache")
            .select("name,code,updated_at")
            .or_(f"name.ilike.%{s}%,code.ilike.%{s}%")
            .order("name")
            .execute()
        ).data
        return rows

    rows = []
    page_size = 1000
    offset = 0
    while True:
        chunk = (
            await db.table("kr_stock_cache")
            .select("name,code,updated_at")
            .order("name")
            .range(offset, offset + page_size - 1)
            .execute()
        ).data
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size
    return rows


# ── 단건 추가/수정 ──────────────────────────────────────────────────────────────

@router.post("/api/stock-cache")
async def upsert_stock(entry: StockEntry, _=Depends(get_admin_user)):
    if not entry.name.strip() or not entry.code.strip():
        raise HTTPException(status_code=400, detail="name과 code는 필수입니다.")
    code = entry.code.strip().zfill(6)
    name = entry.name.strip()
    db = get_db()
    await db.table("kr_stock_cache").upsert({"name": name, "code": code}).execute()
    rows = (await db.table("kr_stock_cache").select("name,code,updated_at").eq("name", name).execute()).data
    return rows[0] if rows else {"name": name, "code": code}


# ── 단건 삭제 ──────────────────────────────────────────────────────────────────

@router.delete("/api/stock-cache/{name}")
async def delete_stock(name: str, _=Depends(get_admin_user)):
    db = get_db()
    await db.table("kr_stock_cache").delete().eq("name", name).execute()
    return {"ok": True}


# ── CSV 업로드 ─────────────────────────────────────────────────────────────────

@router.post("/api/stock-cache/upload")
async def upload_csv(
    file: UploadFile = File(...),
    overwrite: bool = Query(True),
    _=Depends(get_admin_user),
):
    """CSV 형식: 헤더 행 name,code 또는 code,name (순서 무관, 헤더 필수).

    overwrite=true  → 중복 이름: 코드 덮어쓰기 (upsert)
    overwrite=false → 중복 이름: 건너뜀
    """
    content = await file.read()
    text = content.decode("utf-8-sig").strip()  # BOM 처리
    reader = csv.DictReader(io.StringIO(text))

    # 헤더 검증
    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
    if "name" not in fieldnames or "code" not in fieldnames:
        raise HTTPException(
            status_code=400,
            detail="CSV 헤더에 'name'과 'code' 열이 필요합니다.",
        )

    db = get_db()
    added = skipped = errors = 0

    for row in reader:
        name = (row.get("name") or row.get("Name") or "").strip()
        code = (row.get("code") or row.get("Code") or "").strip().zfill(6)
        if not name or not code:
            errors += 1
            continue

        if not overwrite:
            # 중복 체크
            existing = (
                await db.table("kr_stock_cache").select("name").eq("name", name).execute()
            ).data
            if existing:
                skipped += 1
                continue

        await db.table("kr_stock_cache").upsert({"name": name, "code": code}).execute()
        added += 1

    return {"added": added, "skipped": skipped, "errors": errors}


# ── KRX 전체 종목 갱신 (FinanceDataReader) ──────────────────────────────────────

def _fetch_krx_listing():
    import FinanceDataReader as fdr
    df = fdr.StockListing("KRX")
    records = []
    for _, row in df.iterrows():
        name = str(row.get("Name") or "").strip()
        code = str(row.get("Code") or "").strip().zfill(6)
        if name and code:
            records.append({"name": name, "code": code})
    return records


@router.post("/api/stock-cache/refresh")
async def refresh_from_krx(_=Depends(get_admin_user)):
    """FinanceDataReader로 KRX(코스피+코스닥+코넥스) 전체 종목명/코드를 받아 일괄 upsert."""
    try:
        records = await asyncio.get_event_loop().run_in_executor(None, _fetch_krx_listing)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KRX 종목 목록 조회 실패: {e}")

    if not records:
        raise HTTPException(status_code=502, detail="KRX 종목 목록이 비어있습니다.")

    db = get_db()
    CHUNK = 500
    for i in range(0, len(records), CHUNK):
        await db.table("kr_stock_cache").upsert(records[i:i + CHUNK]).execute()

    return {"added": len(records)}


# ── CSV 다운로드 ───────────────────────────────────────────────────────────────

@router.get("/api/stock-cache/export")
async def export_csv(_=Depends(get_admin_user)):
    db = get_db()
    rows = []
    page_size = 1000
    offset = 0
    while True:
        chunk = (
            await db.table("kr_stock_cache")
            .select("name,code,updated_at")
            .order("name")
            .range(offset, offset + page_size - 1)
            .execute()
        ).data
        rows.extend(chunk)
        if len(chunk) < page_size:
            break
        offset += page_size
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["name", "code", "updated_at"])
    for r in rows:
        writer.writerow([r["name"], r["code"], (r.get("updated_at") or "")[:19]])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kr_stock_cache.csv"},
    )
