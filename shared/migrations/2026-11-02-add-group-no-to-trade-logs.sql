-- trade_logs 테이블에 group_no 및 template_id 컬럼 추가 (배치/전략별 체결 추적용)
-- Supabase SQL Editor에서 실행
ALTER TABLE trade_logs ADD COLUMN IF NOT EXISTS template_id BIGINT;
ALTER TABLE trade_logs ADD COLUMN IF NOT EXISTS group_no INTEGER;

CREATE INDEX IF NOT EXISTS idx_trade_logs_template_id ON trade_logs(template_id);
CREATE INDEX IF NOT EXISTS idx_trade_logs_group_no    ON trade_logs(group_no);
