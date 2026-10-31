-- KOSPI/KOSDAQ TOP N 전략(PR #105) 스키마. 전부 멱등(IF NOT EXISTS)이라 여러 번 실행해도 안전하다.
-- Supabase SQL Editor에서 실행.
-- ── KOSPI / KOSDAQ TOP N DCA & Budget Ledger ────────────────────────────────
ALTER TABLE orders ADD COLUMN IF NOT EXISTS template_id BIGINT;
ALTER TABLE trade_logs ADD COLUMN IF NOT EXISTS template_id BIGINT;
CREATE INDEX IF NOT EXISTS idx_orders_template_id     ON orders(template_id);
CREATE INDEX IF NOT EXISTS idx_trade_logs_template_id ON trade_logs(template_id);

-- 일별 시장별 마스터 TOP 50 프리징 스냅샷 테이블
CREATE TABLE IF NOT EXISTS market_top_snapshots (
  snapshot_date DATE        NOT NULL,             -- KST 기준 영업일 (예: 2026-10-30)
  market        TEXT        NOT NULL,             -- 'KOSPI' | 'KOSDAQ' | 'UPBIT_KRW' | 'BITHUMB_KRW'
  top_n         INTEGER     NOT NULL DEFAULT 50,  -- 마스터 스냅샷 크기 (기본 50위)
  items         JSONB       NOT NULL DEFAULT '[]'::jsonb, -- [{"rank":1,"code":"005930","name":"삼성전자","price":58000,"market_cap":...}, ...]
  frozen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),       -- 최초 프리징 확정 시각
  PRIMARY KEY (snapshot_date, market, top_n)
);
ALTER TABLE market_top_snapshots ENABLE ROW LEVEL SECURITY;
GRANT ALL ON TABLE market_top_snapshots TO service_role;

-- 전략별 예산 증감(+/-) 감사 원장 테이블 (Budget Audit Ledger)
CREATE TABLE IF NOT EXISTS budget_ledger (
  id                          BIGSERIAL PRIMARY KEY,
  user_id                     TEXT             NOT NULL,
  template_id                 BIGINT           NOT NULL,
  budget_epoch                INTEGER          NOT NULL DEFAULT 1, -- Reset 실행 시 +1 증가하는 세대 번호
  plan_revision_no            INTEGER          NOT NULL DEFAULT 1, -- 적용된 Budget Plan 버전 (v1, v2...)
  group_no                    INTEGER,                             -- 배치 실행 번호 (수동 조정/초기화 시 NULL 가능)
  credit_date                 DATE,                                -- DAILY_CREDIT 중복 방지용 영업일 (YYYY-MM-DD)
  entry_type                  TEXT             NOT NULL,           -- DAILY_CREDIT | BUY_ORDER_SPEND | ORDER_CANCEL_REFUND | SELL_PROCEEDS_RECYCLE | PLAN_CHANGE_DIFF | PLAN_CAP_ADJUST | MANUAL_TOPUP | RESET
  delta_krw                   DOUBLE PRECISION NOT NULL,           -- 증감액 (+충전/환원/재투입, -매수차감/삭감)
  balance_after_krw           DOUBLE PRECISION NOT NULL,           -- 변동 직후 현재 가용 예산(carryover_budget) 잔액
  monthly_spent_after_krw     DOUBLE PRECISION NOT NULL,           -- 변동 직후 당월 누적 소진액(monthly_spent)
  monthly_remaining_after_krw DOUBLE PRECISION NOT NULL,           -- 변동 직후 당월 잔여 예산(monthly_budget - monthly_spent)
  ticker                      TEXT,                                -- 관련 종목코드 (매수/환원/매도재투입 시)
  order_uuid                  TEXT,                                -- 관련 주문 UUID (중복 환원/중복 차감 방지용)
  description                 TEXT             NOT NULL DEFAULT '',-- 감사 상세 사유
  created_at                  TIMESTAMPTZ      NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_budget_ledger_template ON budget_ledger(template_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_ledger_daily_credit
  ON budget_ledger(template_id, budget_epoch, credit_date)
  WHERE entry_type = 'DAILY_CREDIT' AND credit_date IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_budget_ledger_cancel_refund
  ON budget_ledger(template_id, budget_epoch, order_uuid)
  WHERE entry_type = 'ORDER_CANCEL_REFUND' AND order_uuid IS NOT NULL;
ALTER TABLE budget_ledger ENABLE ROW LEVEL SECURITY;
GRANT ALL ON TABLE budget_ledger TO service_role;
GRANT ALL ON SEQUENCE budget_ledger_id_seq TO service_role;
