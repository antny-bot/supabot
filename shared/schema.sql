-- supabot Supabase Schema
-- Run in Supabase SQL Editor: https://supabase.com/dashboard/project/himkbnuvgyqlgmqkfpvc/sql

-- ── Users ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  user_id        TEXT PRIMARY KEY,
  username       TEXT NOT NULL DEFAULT '',
  is_admin       BOOLEAN NOT NULL DEFAULT false,
  status         TEXT NOT NULL DEFAULT 'pending',  -- pending|active|inactive|blocked|deleted
  preferences    JSONB NOT NULL DEFAULT '{}',
  exchanges      JSONB NOT NULL DEFAULT '{}',
  llm            JSONB NOT NULL DEFAULT '{}',
  api_validation JSONB NOT NULL DEFAULT '{}',
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_updated_at ON users;
CREATE TRIGGER users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Manager Access Linking ──────────────────────────────────────────────────
-- Supabase Auth 이메일과 봇 users 테이블을 연결하는 컬럼. 기존 운영 DB에는 아래 SQL로 추가:
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS manager_email TEXT;
-- CREATE UNIQUE INDEX IF NOT EXISTS users_manager_email_unique ON users (manager_email) WHERE manager_email IS NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS manager_email TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS users_manager_email_unique
  ON users (manager_email)
  WHERE manager_email IS NOT NULL;

-- Supabase Auth 초대 메일 발송 시각. 설정되어 있으면 manager 화면은 "초대 메일 발송" 대신
-- "비밀번호 재설정" 버튼을 보여준다 (중복 초대 방지). 기존 운영 DB에는 아래 SQL로 추가:
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS manager_invited_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS manager_invited_at TIMESTAMPTZ;

-- ── Orders ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
  uuid          TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL,
  exchange      TEXT NOT NULL,
  ticker        TEXT NOT NULL,
  price         DOUBLE PRECISION NOT NULL,
  volume        DOUBLE PRECISION NOT NULL,
  filled_volume DOUBLE PRECISION NOT NULL DEFAULT 0,
  side          TEXT NOT NULL,
  strategy      TEXT NOT NULL DEFAULT 'manual',
  target_rsi    DOUBLE PRECISION,
  linked_to     TEXT,
  status        TEXT NOT NULL DEFAULT 'wait',  -- wait|partial|done|cancel|pending_reorder
  created_at    DOUBLE PRECISION NOT NULL,     -- Unix timestamp
  next_check_at DOUBLE PRECISION NOT NULL DEFAULT 0,
  reorder_of    TEXT,
  stop_price    DOUBLE PRECISION,
  trailing_stop_pct DOUBLE PRECISION,
  auto_reorder  BOOLEAN NOT NULL DEFAULT false  -- 수동 주문도 장마감 취소 시 다음 정규장 재주문 대상으로 포함할지 (opt-in)
);

-- 기존 DB 호환성 유지용 ALTER TABLE 구문
ALTER TABLE orders ADD COLUMN IF NOT EXISTS trailing_stop_pct DOUBLE PRECISION;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS group_no INTEGER;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS auto_reorder BOOLEAN NOT NULL DEFAULT false;

-- ── Trade Logs ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trade_logs (
  id          BIGSERIAL PRIMARY KEY,
  user_id     TEXT NOT NULL,
  exchange    TEXT NOT NULL,
  ticker      TEXT NOT NULL,
  side        TEXT NOT NULL,
  price       DOUBLE PRECISION NOT NULL,
  volume      DOUBLE PRECISION NOT NULL,
  strategy    TEXT NOT NULL DEFAULT 'manual',
  uuid        TEXT,
  executed_at DOUBLE PRECISION NOT NULL,  -- Unix timestamp
  fee_amount  DOUBLE PRECISION NOT NULL DEFAULT 0
);

-- ── Operational Events ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS operational_events (
  id         BIGSERIAL PRIMARY KEY,
  level      TEXT NOT NULL DEFAULT 'info',
  source     TEXT NOT NULL DEFAULT '',
  message    TEXT NOT NULL DEFAULT '',
  details    TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,  -- ISO timestamp string (KST)
  read_at    TIMESTAMPTZ,
  archived_at TIMESTAMPTZ
);

ALTER TABLE operational_events ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ;
ALTER TABLE operational_events ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

-- ── NL Logs ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nl_logs (
  id           BIGSERIAL PRIMARY KEY,
  user_id      TEXT,
  raw_text     TEXT NOT NULL DEFAULT '',
  preprocessed TEXT,
  llm_action   TEXT,
  final_action TEXT,
  logged_at    DOUBLE PRECISION NOT NULL  -- Unix timestamp
);
ALTER TABLE nl_logs ADD COLUMN IF NOT EXISTS confirm_status TEXT;  -- auto|pending|confirmed|rejected|expired

-- ── System Config ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_config (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO system_config (key, value) VALUES
  ('poll_active_interval',    '60'),
  ('poll_no_order_interval',  '300'),
  ('signal_analysis_interval','300'),
  ('trading_halt',            '0')
ON CONFLICT (key) DO NOTHING;

-- ── Strategy Templates ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS strategy_templates (
  id            BIGSERIAL PRIMARY KEY,
  user_id       TEXT NOT NULL,
  name          TEXT NOT NULL,
  exchange      TEXT NOT NULL,
  ticker        TEXT NOT NULL,
  start_price   DOUBLE PRECISION NOT NULL,
  end_price     DOUBLE PRECISION NOT NULL,
  count         INTEGER NOT NULL,
  budget        DOUBLE PRECISION NOT NULL,
  strategy_type TEXT NOT NULL DEFAULT 'grid',
  params        JSONB DEFAULT '{}'::jsonb,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 기존 DB 호환성 유지용 ALTER TABLE 구문
ALTER TABLE strategy_templates ADD COLUMN IF NOT EXISTS strategy_type TEXT NOT NULL DEFAULT 'grid';
ALTER TABLE strategy_templates ADD COLUMN IF NOT EXISTS params JSONB DEFAULT '{}'::jsonb;


-- ── Command Logs ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS command_logs (
  id          BIGSERIAL PRIMARY KEY,
  user_id     TEXT NOT NULL,
  command     TEXT NOT NULL,           -- /buy, /sell, /price, /rsitrade, nl 등
  source      TEXT NOT NULL DEFAULT 'direct',  -- 'direct' | 'nl'
  exchange    TEXT,
  ticker      TEXT,
  created_at  DOUBLE PRECISION NOT NULL  -- Unix timestamp
);
CREATE INDEX IF NOT EXISTS idx_command_logs_user    ON command_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_command_logs_time    ON command_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_command_logs_command ON command_logs(command);

-- ── Command Log Daily (Analytics 요약 테이블) ──────────────────────────────
-- command_logs의 하루치 raw 로그를 매일 집계해 저장. pg_cron이 집계 후 raw를 삭제.
-- hour_of_day·weekday를 보존하므로 히트맵 등 모든 분석 그대로 지원.
CREATE TABLE IF NOT EXISTS command_log_daily (
  date        DATE     NOT NULL,
  user_id     TEXT     NOT NULL,
  command     TEXT     NOT NULL,
  source      TEXT     NOT NULL DEFAULT 'direct',
  hour_of_day SMALLINT NOT NULL,  -- 0-23 KST
  weekday     SMALLINT NOT NULL,  -- 0=월 6=일 (Python weekday() 일치)
  count       INTEGER  NOT NULL DEFAULT 1,
  PRIMARY KEY (date, user_id, command, source, hour_of_day)
);
CREATE INDEX IF NOT EXISTS idx_cmd_daily_date    ON command_log_daily(date);
CREATE INDEX IF NOT EXISTS idx_cmd_daily_user_id ON command_log_daily(user_id);

-- ── 집계·정리 함수 (pg_cron에서 호출) ─────────────────────────────────────
CREATE OR REPLACE FUNCTION aggregate_command_logs_daily()
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  kst_today_epoch DOUBLE PRECISION;
BEGIN
  -- 오늘 자정(KST)의 Unix timestamp
  kst_today_epoch := EXTRACT(EPOCH FROM
    DATE_TRUNC('day', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'
  );

  -- 오늘 이전 raw 로그를 요약 테이블에 upsert
  INSERT INTO command_log_daily (date, user_id, command, source, hour_of_day, weekday, count)
  SELECT
    (to_timestamp(created_at) AT TIME ZONE 'Asia/Seoul')::date                               AS date,
    user_id, command, source,
    EXTRACT(HOUR  FROM to_timestamp(created_at) AT TIME ZONE 'Asia/Seoul')::smallint         AS hour_of_day,
    (EXTRACT(ISODOW FROM to_timestamp(created_at) AT TIME ZONE 'Asia/Seoul') - 1)::smallint  AS weekday,
    COUNT(*)::integer                                                                         AS count
  FROM command_logs
  WHERE created_at < kst_today_epoch
  GROUP BY 1, 2, 3, 4, 5, 6
  ON CONFLICT (date, user_id, command, source, hour_of_day)
  DO UPDATE SET count = command_log_daily.count + EXCLUDED.count;

  -- 집계된 raw 로그 삭제 (오늘치 raw는 보존)
  DELETE FROM command_logs WHERE created_at < kst_today_epoch;
END;
$$;

-- ── pg_cron 설정 ────────────────────────────────────────────────────────────
-- 사전 조건: Supabase 대시보드 → Database → Extensions → pg_cron 활성화 후 실행.
-- 매일 KST 01:00 (UTC 16:00) 집계 실행.
-- 이미 등록된 경우 cron.unschedule('aggregate_command_logs') 로 먼저 제거.
--
-- SELECT cron.schedule(
--   'aggregate_command_logs',
--   '0 16 * * *',
--   'SELECT aggregate_command_logs_daily()'
-- );

-- ── Korean Stock Name Cache ────────────────────────────────────────────────
-- 종목명 → 종목코드 캐시. KIS API 호출 최소화 목적.
-- updated_at 기준 TTL(90일) 초과 시 KIS API 재검증 후 upsert.
-- 종목명 변경·코드 재배정 시나리오 모두 TTL로 처리.
CREATE TABLE IF NOT EXISTS kr_stock_cache (
  name       TEXT PRIMARY KEY,          -- 한글 종목명 (e.g. 삼천당제약)
  code       TEXT NOT NULL,             -- 종목코드 6자리 (e.g. 000250)
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION update_kr_stock_cache_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS kr_stock_cache_updated_at ON kr_stock_cache;
CREATE TRIGGER kr_stock_cache_updated_at
  BEFORE UPDATE ON kr_stock_cache
  FOR EACH ROW EXECUTE FUNCTION update_kr_stock_cache_updated_at();

-- ── Row Level Security ─────────────────────────────────────────────────────
ALTER TABLE users             ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders            ENABLE ROW LEVEL SECURITY;
ALTER TABLE trade_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE operational_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE nl_logs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_config     ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategy_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE command_logs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE command_log_daily  ENABLE ROW LEVEL SECURITY;
ALTER TABLE kr_stock_cache     ENABLE ROW LEVEL SECURITY;

-- ── Grants (SQL로 생성 시 자동 부여되지 않으므로 명시 필요) ────────────────
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;


-- ── Batch Tracking on Trade Logs & DCA Schedules ───────────────────────────
ALTER TABLE trade_logs ADD COLUMN IF NOT EXISTS group_no INTEGER;
CREATE INDEX IF NOT EXISTS idx_trade_logs_group_no ON trade_logs(user_id, group_no);

CREATE TABLE IF NOT EXISTS dca_schedules (
  id            TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL,
  exchange      TEXT NOT NULL,
  ticker        TEXT NOT NULL,
  side          TEXT NOT NULL DEFAULT 'bid',
  frequency     TEXT NOT NULL DEFAULT 'daily',      -- daily|weekly|days|monthly
  days_of_week  JSONB NOT NULL DEFAULT '[]'::jsonb, -- [0..6] (0=월..6=일)
  day_of_month  INTEGER,                            -- 1..31
  exec_time     TEXT NOT NULL DEFAULT '09:05',      -- HH:MM (KST)
  amount_type   TEXT NOT NULL DEFAULT 'budget',     -- budget|volume
  amount        DOUBLE PRECISION NOT NULL,
  max_runs      INTEGER,
  run_count     INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'active',     -- active|paused|completed
  group_no      INTEGER,
  next_run_at   DOUBLE PRECISION NOT NULL,
  last_run_at   DOUBLE PRECISION,
  created_at    DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dca_schedules_user ON dca_schedules(user_id);
ALTER TABLE dca_schedules ENABLE ROW LEVEL SECURITY;
GRANT ALL ON TABLE dca_schedules TO service_role;

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


-- Supabase 데이터베이스 크기(bytes) 조회 RPC 함수 (무료 티어 500MB 모니터링용)
CREATE OR REPLACE FUNCTION get_db_size_bytes()
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
AS $$
  SELECT pg_database_size(current_database());
$$;
GRANT EXECUTE ON FUNCTION get_db_size_bytes() TO service_role;

-- ── Feedbacks (사용자 피드백 / 건의사항) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS feedbacks (
  id            TEXT PRIMARY KEY,
  user_id       TEXT NOT NULL,
  user_email    TEXT NOT NULL DEFAULT '',
  category      TEXT NOT NULL DEFAULT 'feature', -- bug|feature|inquiry
  title         TEXT NOT NULL,
  content       TEXT NOT NULL,
  browser_info  TEXT,
  status        TEXT NOT NULL DEFAULT 'new',     -- new|in_progress|resolved|dismissed
  admin_note    TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedbacks_user ON feedbacks(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedbacks_status ON feedbacks(status, created_at DESC);

DROP TRIGGER IF EXISTS feedbacks_updated_at ON feedbacks;
CREATE TRIGGER feedbacks_updated_at
  BEFORE UPDATE ON feedbacks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE feedbacks ENABLE ROW LEVEL SECURITY;
GRANT ALL ON TABLE feedbacks TO service_role;

