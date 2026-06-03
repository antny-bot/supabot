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

-- ── System Config ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_config (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO system_config (key, value) VALUES
  ('poll_active_interval',    '60'),
  ('poll_no_order_interval',  '300'),
  ('signal_analysis_interval','300')
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


-- ── Row Level Security ─────────────────────────────────────────────────────
ALTER TABLE users             ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders            ENABLE ROW LEVEL SECURITY;
ALTER TABLE trade_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE operational_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE nl_logs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_config     ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategy_templates ENABLE ROW LEVEL SECURITY;

-- ── Grants (SQL로 생성 시 자동 부여되지 않으므로 명시 필요) ────────────────
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
