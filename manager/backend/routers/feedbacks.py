import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import get_db
from ._auth import get_admin_user, get_current_user

logger = logging.getLogger("manager.feedbacks")

router = APIRouter()

VALID_CATEGORIES = {"bug", "feature", "inquiry"}
VALID_STATUSES = {"new", "in_progress", "resolved", "dismissed"}


class FeedbackCreate(BaseModel):
    category: str = Field("feature", description="bug | feature | inquiry")
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    browser_info: Optional[str] = None


class FeedbackUpdate(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)


class AdminFeedbackUpdate(BaseModel):
    status: Optional[str] = None
    admin_note: Optional[str] = None


# ── 사용자용 API ─────────────────────────────────────────────────────────────

@router.post("/api/feedbacks")
async def submit_feedback(
    payload: FeedbackCreate,
    current_user: dict = Depends(get_current_user),
):
    category = payload.category if payload.category in VALID_CATEGORIES else "feature"
    user_id = str(current_user.get("bot_user_id") or current_user.get("email") or "anonymous")
    user_email = current_user.get("email") or ""

    feedback_id = uuid.uuid4().hex
    now_iso = datetime.now(timezone.utc).isoformat()

    row = {
        "id": feedback_id,
        "user_id": user_id,
        "user_email": user_email,
        "category": category,
        "title": payload.title.strip(),
        "content": payload.content.strip(),
        "browser_info": payload.browser_info,
        "status": "new",
        "admin_note": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    try:
        db = get_db()
        await db.table("feedbacks").insert(row).execute()
        return JSONResponse(row, status_code=201)
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail="피드백 등록에 실패했습니다.")


@router.get("/api/feedbacks/my")
async def get_my_feedbacks(
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user.get("bot_user_id") or current_user.get("email") or "")
    user_email = current_user.get("email") or ""

    try:
        db = get_db()
        # user_id 또는 user_email 매칭
        res = await db.table("feedbacks").select("*").order("created_at", desc=True).execute()
        all_rows = res.data or []
        my_rows = [r for r in all_rows if str(r.get("user_id")) == user_id or (user_email and r.get("user_email") == user_email)]
        return JSONResponse({"reports": my_rows})
    except Exception as e:
        logger.error(f"Failed to fetch my feedbacks: {e}")
        raise HTTPException(status_code=500, detail="내 피드백 목록 조회 실패")


@router.patch("/api/feedbacks/my/{feedback_id}")
async def update_my_feedback(
    feedback_id: str,
    payload: FeedbackUpdate,
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user.get("bot_user_id") or current_user.get("email") or "")
    user_email = current_user.get("email") or ""

    db = get_db()
    existing_res = await db.table("feedbacks").select("*").eq("id", feedback_id).execute()
    rows = existing_res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="피드백을 찾을 수 없습니다.")

    target = rows[0]
    if str(target.get("user_id")) != user_id and target.get("user_email") != user_email:
        raise HTTPException(status_code=403, detail="본인이 작성한 피드백만 수정할 수 있습니다.")

    updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.category and payload.category in VALID_CATEGORIES:
        updates["category"] = payload.category
    if payload.title is not None:
        updates["title"] = payload.title.strip()
    if payload.content is not None:
        updates["content"] = payload.content.strip()

    await db.table("feedbacks").update(updates).eq("id", feedback_id).execute()
    updated_res = await db.table("feedbacks").select("*").eq("id", feedback_id).execute()
    return JSONResponse(updated_res.data[0] if updated_res.data else {**target, **updates})


@router.delete("/api/feedbacks/my/{feedback_id}")
async def delete_my_feedback(
    feedback_id: str,
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user.get("bot_user_id") or current_user.get("email") or "")
    user_email = current_user.get("email") or ""

    db = get_db()
    existing_res = await db.table("feedbacks").select("*").eq("id", feedback_id).execute()
    rows = existing_res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="피드백을 찾을 수 없습니다.")

    target = rows[0]
    if str(target.get("user_id")) != user_id and target.get("user_email") != user_email:
        raise HTTPException(status_code=403, detail="본인이 작성한 피드백만 삭제할 수 있습니다.")

    await db.table("feedbacks").delete().eq("id", feedback_id).execute()
    return JSONResponse({"success": True})


# ── 관리자용 API ─────────────────────────────────────────────────────────────

@router.get("/api/admin/feedbacks")
async def get_admin_feedbacks(
    status: Optional[str] = Query(None, description="new | in_progress | resolved | dismissed"),
    category: Optional[str] = Query(None, description="bug | feature | inquiry"),
    days: Optional[int] = Query(None, description="최근 N일"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _=Depends(get_admin_user),
):
    try:
        db = get_db()
        q = db.table("feedbacks").select("*").order("created_at", desc=True)
        res = await q.execute()
        rows = res.data or []

        # 사용자 매핑용 users 정보 가져오기
        try:
            users_res = await db.table("users").select("user_id,username,manager_email").execute()
            user_map = {str(u["user_id"]): u.get("username") or u.get("manager_email") or "" for u in (users_res.data or [])}
        except Exception:
            user_map = {}

        for r in rows:
            uid = str(r.get("user_id", ""))
            r["username"] = user_map.get(uid) or r.get("user_email") or uid

        # 필터링
        if status and status in VALID_STATUSES:
            rows = [r for r in rows if r.get("status") == status]
        if category and category in VALID_CATEGORIES:
            rows = [r for r in rows if r.get("category") == category]
        if days and days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            filtered = []
            for r in rows:
                c_str = r.get("created_at")
                if c_str:
                    try:
                        # ISO parse
                        dt = datetime.fromisoformat(c_str.replace("Z", "+00:00"))
                        if dt >= cutoff:
                            filtered.append(r)
                    except Exception:
                        filtered.append(r)
                else:
                    filtered.append(r)
            rows = filtered

        total_items = len(rows)
        safe_page_size = max(1, min(page_size, 100))
        total_pages = max(1, (total_items + safe_page_size - 1) // safe_page_size)
        safe_page = min(max(1, page), total_pages)
        start_idx = (safe_page - 1) * safe_page_size
        end_idx = start_idx + safe_page_size

        page_rows = rows[start_idx:end_idx]

        return JSONResponse({
            "reports": page_rows,
            "pagination": {
                "page": safe_page,
                "pageSize": safe_page_size,
                "totalItems": total_items,
                "totalPages": total_pages,
                "hasPrev": safe_page > 1,
                "hasNext": safe_page < total_pages,
            },
        })
    except Exception as e:
        logger.error(f"Failed to fetch admin feedbacks: {e}")
        raise HTTPException(status_code=500, detail="관리자 피드백 목록 조회 실패")


@router.patch("/api/admin/feedbacks/{feedback_id}")
async def update_admin_feedback(
    feedback_id: str,
    payload: AdminFeedbackUpdate,
    _=Depends(get_admin_user),
):
    db = get_db()
    existing = await db.table("feedbacks").select("*").eq("id", feedback_id).execute()
    rows = existing.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="피드백을 찾을 수 없습니다.")

    updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.status:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="유효하지 않은 상태값입니다.")
        updates["status"] = payload.status
    if payload.admin_note is not None:
        updates["admin_note"] = payload.admin_note

    await db.table("feedbacks").update(updates).eq("id", feedback_id).execute()
    updated_res = await db.table("feedbacks").select("*").eq("id", feedback_id).execute()
    return JSONResponse(updated_res.data[0] if updated_res.data else {**rows[0], **updates})


@router.delete("/api/admin/feedbacks/{feedback_id}")
async def delete_admin_feedback(
    feedback_id: str,
    _=Depends(get_admin_user),
):
    db = get_db()
    existing = await db.table("feedbacks").select("*").eq("id", feedback_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="피드백을 찾을 수 없습니다.")

    await db.table("feedbacks").delete().eq("id", feedback_id).execute()
    return JSONResponse({"success": True})
