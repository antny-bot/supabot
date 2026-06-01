export interface AuthUser {
  email: string
  is_admin: boolean
  bot_user_id: string | null
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
}

export interface ConfigItem {
  key: string
  value: string
  updated_at: string
  label: string
  desc: string
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

export interface TradesData {
  trades: Trade[]
  summary: TradeSummary
  by_exchange: AggRow[]
  by_strategy: AggRow[]
}
