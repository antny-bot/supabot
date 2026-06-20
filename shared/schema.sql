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
  trailing_stop_pct DOUBLE PRECISION
);

-- 기존 DB 호환성 유지용 ALTER TABLE 구문
ALTER TABLE orders ADD COLUMN IF NOT EXISTS trailing_stop_pct DOUBLE PRECISION;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS group_no INTEGER;

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
