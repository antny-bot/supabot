import { ShieldCheck, ChevronRight } from 'lucide-react'
import { krwFmt } from '../../utils/formatters'

export interface BudgetHealthData {
  exchange?: string
  actual_cash_krw?: number | null
  balance_available?: boolean
  health_grade?: 'HEALTHY' | 'WARNING' | 'SHORTAGE' | 'UNKNOWN' | string
  health_message?: string
  daily_required_krw?: number
  monthly_remaining_required_krw?: number
  daily_deposit_needed_krw?: number
  monthly_deposit_needed_krw?: number
  active_templates_count?: number
  holding_templates_count?: number
  [key: string]: any
}

interface BudgetHealthCardProps {
  healthData?: BudgetHealthData | null
  loading?: boolean
  showDetailLink?: boolean
  onClick?: () => void
  className?: string
}

export default function BudgetHealthCard({
  healthData,
  loading = false,
  showDetailLink = false,
  onClick,
  className = '',
}: BudgetHealthCardProps) {
  if (loading && !healthData) {
    return (
      <div className={`rounded-xl border border-slate-200 dark:border-slate-800 bg-white/60 dark:bg-slate-900/60 p-4 animate-pulse ${className}`}>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-5 h-5 rounded-full bg-slate-200 dark:bg-slate-700 shrink-0" />
            <div className="space-y-1.5">
              <div className="w-56 h-4 rounded bg-slate-200 dark:bg-slate-700" />
              <div className="w-36 h-3 rounded bg-slate-200 dark:bg-slate-700" />
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="w-16 h-7 rounded bg-slate-200 dark:bg-slate-700" />
            <div className="w-16 h-7 rounded bg-slate-200 dark:bg-slate-700" />
            <div className="w-16 h-7 rounded bg-slate-200 dark:bg-slate-700" />
          </div>
        </div>
      </div>
    )
  }

  if (!healthData) return null

  const healthGrade = healthData.health_grade || 'HEALTHY'
  const isHealthy = healthGrade === 'HEALTHY'
  const isWarning = healthGrade === 'WARNING'
  const isUnknown = healthGrade === 'UNKNOWN'

  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => (e.key === 'Enter' || e.key === ' ') && onClick() : undefined}
      className={`group rounded-xl border p-4 transition-all ${
        onClick ? 'cursor-pointer hover:shadow-md' : ''
      } ${
        isHealthy
          ? 'border-emerald-200 bg-emerald-50/70 hover:border-emerald-300 dark:border-emerald-800/50 dark:bg-emerald-950/20 dark:hover:border-emerald-700/60'
          : isWarning
          ? 'border-amber-200 bg-amber-50/70 hover:border-amber-300 dark:border-amber-800/50 dark:bg-amber-950/20 dark:hover:border-amber-700/60'
          : isUnknown
          ? 'border-slate-300 bg-slate-50/80 hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900/60 dark:hover:border-slate-600'
          : 'border-red-200 bg-red-50/70 hover:border-red-300 dark:border-red-800/50 dark:bg-red-950/20 dark:hover:border-red-700/60'
      } ${className}`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        {/* 좌측 상태 요약 */}
        <div className="flex items-center gap-2.5">
          <ShieldCheck
            size={20}
            className={`shrink-0 ${
              isHealthy ? 'text-emerald-600 dark:text-emerald-400' : isWarning ? 'text-amber-600 dark:text-amber-400' : isUnknown ? 'text-slate-500 dark:text-slate-400' : 'text-red-600 dark:text-red-400'
            }`}
          />
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-sm text-slate-800 dark:text-slate-100 break-keep">
                [{healthData.exchange || 'TOSS'}] 멀티 전략 통합 예수금 Health Check
              </span>
              <span
                className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                  isHealthy
                    ? 'bg-emerald-200 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200'
                    : isWarning
                    ? 'bg-amber-200 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200'
                    : isUnknown
                    ? 'bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-300'
                    : 'bg-red-200 text-red-800 dark:bg-red-900/60 dark:text-red-200'
                }`}
              >
                {healthGrade}
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-300 mt-0.5 break-keep">
              {healthData.health_message}
            </p>
          </div>
        </div>

        {/* 우측 수치 지표 및 상세 연결 링크 (모바일 대응 flex-wrap 및 grid) */}
        <div className="flex flex-wrap items-center justify-between sm:justify-end gap-2.5 sm:gap-4 pt-2 sm:pt-0 border-t sm:border-t-0 border-slate-200/60 dark:border-slate-800/60 min-w-0">
          <div className="grid grid-cols-3 sm:flex items-center gap-2 sm:gap-4 text-xs font-mono min-w-0 flex-1 sm:flex-initial">
            <div className="min-w-0">
              <span className="text-slate-500 block text-[10px] sm:text-[11px] truncate">예수금</span>
              <span
                className="font-bold text-slate-800 dark:text-slate-100 text-xs sm:text-sm truncate block"
                title={isUnknown || healthData.actual_cash_krw == null ? '조회 불가' : `${Number(healthData.actual_cash_krw || 0).toLocaleString()}원`}
              >
                {isUnknown || healthData.actual_cash_krw == null ? '-' : krwFmt(healthData.actual_cash_krw || 0)}
              </span>
            </div>
            <div className="min-w-0">
              <span className="text-slate-500 block text-[10px] sm:text-[11px] truncate">일 필요액</span>
              <span className="font-bold text-slate-800 dark:text-slate-100 text-xs sm:text-sm truncate block">
                {krwFmt(healthData.daily_required_krw || 0)}
              </span>
            </div>
            <div className="min-w-0">
              <span className="text-slate-500 block text-[10px] sm:text-[11px] truncate">당월 잔여</span>
              <span className="font-bold text-slate-800 dark:text-slate-100 text-xs sm:text-sm truncate block">
                {krwFmt(healthData.monthly_remaining_required_krw || 0)}
              </span>
            </div>
          </div>

          {showDetailLink && (
            <div className="flex items-center gap-1 ml-auto sm:ml-0 pl-2 sm:pl-3 border-l border-slate-300/80 dark:border-slate-700/80 text-xs font-semibold text-slate-600 dark:text-slate-300 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 shrink-0 transition-colors">
              <span className="hidden md:inline">감사 원장 보기</span>
              <span className="md:hidden">상세</span>
              <ChevronRight size={14} className="transition-transform group-hover:translate-x-0.5" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
