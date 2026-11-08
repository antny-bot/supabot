"""기존 DCA 템플릿 중 예산 모드(budget_mode)가 없는 템플릿을 unlimited로 표준화하는 1회성 마이그레이션 스크립트.

주의: 실DB에 자동으로 실행되지 않으며, 필요 시 관리자가 수동으로 검토 후 실행합니다.
실행 방법: python scripts/migrate_dca_unlimited_budget.py
"""
import asyncio
import os
import sys

# src 경로 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from core.db import get_db, is_db_available


async def migrate_dca_unlimited():
    if not is_db_available():
        print("[!] Supabase DB가 설정되어 있지 않습니다.")
        return

    db = get_db()
    res = await db.table("strategy_templates").select("id,name,strategy_type,params").execute_async()
    if not res or not res.data:
        print("[i] 템플릿이 없습니다.")
        return

    migrated_count = 0
    for tpl in res.data:
        stype = str(tpl.get("strategy_type") or "").lower()
        if stype != "dca":
            continue

        params = dict(tpl.get("params") or {})
        b_mode = str(params.get("budget_mode") or "").strip()
        # budget_mode가 명시되지 않았고 carryover_budget도 없는 경우에만 unlimited로 지정
        if not b_mode and "carryover_budget" not in params:
            params["budget_mode"] = "unlimited"
            await db.table("strategy_templates").update({"params": params}).eq("id", tpl["id"]).execute_async()
            print(f"[+] DCA #{tpl['id']} ({tpl.get('name')}): budget_mode='unlimited' 적용 완료")
            migrated_count += 1

    print(f"[*] 총 {migrated_count}건의 DCA 템플릿이 'unlimited'로 마이그레이션되었습니다.")


if __name__ == "__main__":
    asyncio.run(migrate_dca_unlimited())
