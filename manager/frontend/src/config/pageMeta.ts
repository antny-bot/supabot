import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  ArrowLeftRight,
  BarChart2,
  ClipboardList,
  LayoutDashboard,
  LayoutTemplate,
  Settings,
  Users,
} from 'lucide-react'

export type PageMetaKey =
  | 'dashboard'
  | 'orders'
  | 'trades'
  | 'templates'
  | 'reports'
  | 'events'
  | 'users'
  | 'config'

export interface PageMeta {
  title: string
  subtitle: string
  Icon: LucideIcon
}

export interface NavItem {
  key: Exclude<PageMetaKey, 'config'>
  to: string
  label: string
  compactLabel: string
  adminOnly: boolean
  Icon: LucideIcon
}

export const PAGE_META: Record<PageMetaKey, PageMeta> = {
  dashboard: {
    title: '대시보드',
    subtitle: '서비스 운영 현황과 거래 상태를 한눈에 확인합니다.',
    Icon: LayoutDashboard,
  },
  orders: {
    title: '주문 현황',
    subtitle: '전체 주문의 상태와 진행률을 빠르게 확인합니다.',
    Icon: ClipboardList,
  },
  trades: {
    title: '거래 내역',
    subtitle: '최근 체결 현황과 거래 규모를 검토합니다.',
    Icon: ArrowLeftRight,
  },
  templates: {
    title: '전략 템플릿',
    subtitle: '반복 사용하는 전략 설정을 저장하고 즉시 실행합니다.',
    Icon: LayoutTemplate,
  },
  reports: {
    title: '리포트',
    subtitle: '손익, 전략 성과, 승률 지표를 기간별로 분석합니다.',
    Icon: BarChart2,
  },
  events: {
    title: '이벤트 로그',
    subtitle: '운영 이벤트를 읽음, 보관 상태와 함께 관리합니다.',
    Icon: Activity,
  },
  users: {
    title: '유저 관리',
    subtitle: '사용자 상태, 관리자 연결, 접근 권한을 운영합니다.',
    Icon: Users,
  },
  config: {
    title: '설정',
    subtitle: '보안 설정과 운영용 시스템 값을 관리합니다.',
    Icon: Settings,
  },
}

export const APP_NAV_ITEMS: NavItem[] = [
  { key: 'dashboard', to: '/dashboard', label: '대시보드', compactLabel: '대시보드', adminOnly: false, Icon: LayoutDashboard },
  { key: 'orders', to: '/orders', label: '주문 현황', compactLabel: '주문', adminOnly: false, Icon: ClipboardList },
  { key: 'trades', to: '/trades', label: '거래 내역', compactLabel: '거래', adminOnly: false, Icon: ArrowLeftRight },
  { key: 'templates', to: '/templates', label: '전략 템플릿', compactLabel: '템플릿', adminOnly: false, Icon: LayoutTemplate },
  { key: 'reports', to: '/reports', label: '리포트', compactLabel: '리포트', adminOnly: false, Icon: BarChart2 },
  { key: 'events', to: '/events', label: '이벤트', compactLabel: '이벤트', adminOnly: true, Icon: Activity },
  { key: 'users', to: '/users', label: '유저 관리', compactLabel: '유저', adminOnly: true, Icon: Users },
]
