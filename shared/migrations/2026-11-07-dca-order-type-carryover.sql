-- ── DCA Schedules: 시장가 주문 및 휴장/사이드카 이월 컬럼 추가 ─────────────
ALTER TABLE dca_schedules ADD COLUMN IF NOT EXISTS order_type TEXT DEFAULT 'limit';
ALTER TABLE dca_schedules ADD COLUMN IF NOT EXISTS carryover_mode TEXT DEFAULT 'next_day';
ALTER TABLE dca_schedules ADD COLUMN IF NOT EXISTS template_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_dca_schedules_template_id ON dca_schedules(template_id);
