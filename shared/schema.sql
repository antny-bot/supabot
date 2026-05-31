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
  stop_price    DOUBLE PRECISION
);

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
  executed_at DOUBLE PRECISION NOT NULL  -- Unix timestamp
);

-- ── Operational Events ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS operational_events (
  id         BIGSERIAL PRIMARY KEY,
  level      TEXT NOT NULL DEFAULT 'info',
  source     TEXT NOT NULL DEFAULT '',
  message    TEXT NOT NULL DEFAULT '',
  details    TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL  -- ISO timestamp string (KST)
);

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

-- ── Row Level Security ─────────────────────────────────────────────────────
ALTER TABLE users             ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders            ENABLE ROW LEVEL SECURITY;
ALTER TABLE trade_logs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE operational_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE nl_logs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_config     ENABLE ROW LEVEL SECURITY;
