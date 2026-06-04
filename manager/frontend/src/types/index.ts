export interface AuthUser {
  email: string
  is_admin: boolean
  bot_user_id: string | null
  mfa_enabled?: boolean
  username?: string
}

export interface User {
  user_id: string
  username: string
  status: 'pending' | 'active' | 'inactive' | 'blocked' | 'deleted'
  is_admin: boolean
  manager_email: string | null
  created_at: string
  status_label: string
}

export interface Order {
  id?: number
  user_id: string
  exchange: string
  ticker: string
  side: 'bid' | 'ask'
  strategy: string
  price: number
  volume: number
  filled_volume: number
  order_value: number
  status: string
  status_label: string
  created_at: number
  created_fmt: string
  fill_pct: number
}

export interface Trade {
  id?: number
  user_id: string
  exchange: string
  ticker: string
  side: 'bid' | 'ask'
  strategy: string
  price: number
  volume: number
  krw: number
  fee_amount?: number
  executed_at: number
  executed_fmt: string
}

export interface Event {
  id: number
  level: 'error' | 'warning' | 'info'
  source: string
  message: string
  details?: string
  created_at: string
  read_at: string | null
  archived_at: string | null
}

export interface ConfigItem {
  key: string
  value: string
  updated_at: string
  label: string
  desc: string
}

export interface AnalyticsOverview {
  dau: number
  wau: number
  mau: number
  total_commands_30d: number
}

export interface ActivityItem {
  date: string
  count: number
}

export interface AnalyticsActivity {
  activity: ActivityItem[]
}

export interface CommandItem {
  command: string
  count: number
}

export interface AnalyticsCommands {
  commands: CommandItem[]
  total: number
}

export interface AnalyticsUserItem {
  user_id: string
  username: string
  count: number
  last_active: string
  last_active_ts: number
}

export interface AnalyticsUsers {
  users: AnalyticsUserItem[]
}

export interface AnalyticsHeatmap {
  matrix: number[][]
  max: number
}

export interface DashboardStats {
  orders_open: number
  trades_24h: number
  // 어드민 전용 (일반 유저 응답에는 없음)
  users_total?: number
  users_active?: number
  users_pending?: number
  errors_24h?: number
}

export interface DashboardData {
  stats: DashboardStats
  recent_events: Event[]
  mfa_enabled?: boolean
}

export interface TradeSummary {
  total: number
  buy: number
  sell: number
  volume_krw: number
}

export interface AggRow {
  name: string
  count: number
  krw: number
}

export interface PaginatedResponse {
  total: number
  page: number
  page_size: number
}

export interface TradesData extends PaginatedResponse {
  trades: Trade[]
  summary: TradeSummary
  by_exchange: AggRow[]
  by_strategy: AggRow[]
}

export interface OrdersData extends PaginatedResponse {
  orders: Order[]
}

// ── Reports ────────────────────────────────────────────────────────────────

export interface PnlRow {
  exchange: string
  ticker: string
  bid_krw: number
  ask_krw: number
  fee_amount: number
  pnl: number
  roi_pct: number
  bid_count: number
  ask_count: number
}

export interface PnlReport {
  rows: PnlRow[]
  summary: { total_bid: number; total_ask: number; total_fee: number; total_pnl: number }
}

export interface StrategyRow {
  strategy: string
  bid_krw: number
  ask_krw: number
  fee_amount: number
  pnl: number
  roi_pct: number
  trade_count: number
  win_rate: number
}

export interface StrategyReport {
  rows: StrategyRow[]
}

export interface RoiRankRow extends PnlRow {
  rank: number
}

export interface RoiRankingReport {
  rows: RoiRankRow[]
}

export interface MonthlyRow {
  month: string
  bid_krw: number
  ask_krw: number
  fee_amount: number
  pnl: number
  bar_pct: number
}

export interface MonthlyReport {
  rows: MonthlyRow[]
}

export interface HoldingRow {
  exchange: string
  ticker: string
  quantity: number
  avg_price: number
  cost_krw: number
  current_price: number
  value_krw: number
  pnl: number
  roi_pct: number
  oversold: boolean
}

export interface HoldingsReport {
  rows: HoldingRow[]
  summary: {
    total_cost: number
    total_value: number
    total_pnl: number
    total_roi_pct: number
    asset_count: number
    oversold_count: number
  }
}

export interface PairRow {
  ticker: string
  exchange: string
  strategy: string
  buy_price: number
  sell_price: number
  volume: number
  bid_krw: number
  ask_krw: number
  fee_amount: number
  pnl: number
  roi_pct: number
  hold_time_s: number
  hold_time_fmt: string
  buy_at_fmt: string
  sell_at_fmt: string
}

export interface PairsReport {
  pairs: PairRow[]
}

export interface WinStats {
  total_pairs: number
  win_count: number
  loss_count: number
  win_rate: number
  avg_win_pct: number
  avg_loss_pct: number
  rr_ratio: number
}

export interface WinStatsReport {
  stats: WinStats
}
