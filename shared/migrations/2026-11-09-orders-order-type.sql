-- ── Orders: 주문 방식(market/limit) 및 템플릿 연결 컬럼 추가 ─────────────
-- order_manager.add_order가 order_type/template_id를 포함해 upsert하므로 컬럼이 없으면 모든 주문 저장이 실패한다.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_type TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS template_id BIGINT;
