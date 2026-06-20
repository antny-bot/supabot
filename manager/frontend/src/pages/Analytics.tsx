import { useEffect, useRef, useState } from 'react'
import { usePersistedState } from '../hooks/usePersistedState'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  fetchAnalyticsOverview,
  fetchAnalyticsActivity,
  fetchAnalyticsCommands,
  fetchAnalyticsUsers,
  fetchAnalyticsHeatmap,
} from '../api/analytics'
import type {
  AnalyticsOverview,
  ActivityItem,
  CommandItem,
  AnalyticsUserItem,
} from '../types'
import StatCard from '../components/ui/StatCard'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import FilterBar from '../components/ui/FilterBar'
import { PAGE_META } from '../config/pageMeta'
import { staggerDelay, staggerDelayMs } from '../utils/animation'
import { Users, Activity, BarChart2, Clock } from 'lucide-react'

const PERIOD_OPTIONS = [
  { value: '1d',  label: '1일' },
  { value: '7d',  label: '7일' },
  { value: '30d', label: '30일' },
  { value: 'all', label: '전체' },
]

const WEEKDAY_LABELS = ['월', '화', '수', '목', '금', '토', '일']

function periodToDays(period: string): number {
  if (period === '30d') return 30
  if (period === 'all') return 90
  return 7
}

const CARD = 'bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm'

function heatColor(val: number, max: number): string {
  if (max === 0 || val === 0) return 'bg-slate-100 dark:bg-slate-800'
  const ratio = val / max
  if (ratio > 0.75) return 'bg-primary-600'
  if (ratio > 0.5)  return 'bg-primary-400'
  if (ratio > 0.25) return 'bg-primary-200 dark:bg-primary-700'
  return 'bg-primary-100 dark:bg-primary-900'
}

// ── Overview ─────────────────────────────────────────────────────────────

function OverviewSection() {
  const [data, setData] = useState<AnalyticsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchAnalyticsOverview()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />
  if (error)   return <ErrorBanner message={error} />
  if (!data)   return null

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <div className="animate-fade-in-up" style={staggerDelay(0)}>
        <StatCard label="DAU (오늘)"   value={data.dau}                 icon={<Users size={18} />}    iconBg="bg-primary-500" />
      </div>
      <div className="animate-fade-in-up" style={staggerDelay(1)}>
        <StatCard label="WAU (7일)"    value={data.wau}                 icon={<Activity size={18} />} iconBg="bg-emerald-500" />
      </div>
      <div className="animate-fade-in-up" style={staggerDelay(2)}>
        <StatCard label="MAU (30일)"   value={data.mau}                 icon={<Users size={18} />}    iconBg="bg-sky-500" />
      </div>
      <div className="animate-fade-in-up" style={staggerDelay(3)}>
        <StatCard label="30일 명령 수" value={data.total_commands_30d}  icon={<BarChart2 size={18} />} iconBg="bg-amber-500" />
      </div>
    </div>
  )
}

// ── Activity Chart ────────────────────────────────────────────────────────

interface ActivitySectionProps {
  days: number
  onDaysChange: (days: number) => void
}

function ActivitySection({ days, onDaysChange }: ActivitySectionProps) {
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchAnalyticsActivity(days)
      .then((d) => setActivity(d.activity))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [days])

  const dayOptions = [
    { value: '7',  label: '7일' },
    { value: '30', label: '30일' },
    { value: '90', label: '90일' },
  ]

  const displayData = activity.map((item) => ({
    ...item,
    label: item.date.slice(5), // MM-DD
  }))
  const tickInterval = days <= 7 ? 0 : days <= 30 ? 4 : 9

  return (
    <div className={`${CARD} animate-fade-in-up p-5`} style={staggerDelay(4)}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">일별 명령 건수</h2>
        <FilterBar
          options={dayOptions}
          value={String(days)}
          onChange={(v) => onDaysChange(Number(v))}
        />
      </div>
      {loading ? <div className="h-48 flex items-center justify-center"><Spinner /></div>
       : error  ? <ErrorBanner message={error} />
       : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={displayData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--tw-border-opacity, #e2e8f0)" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={tickInterval} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip formatter={(v: number) => [`${v}건`, '명령']} />
            <Bar dataKey="count" fill="#6366f1" radius={[2, 2, 0, 0]} animationBegin={staggerDelayMs(4)} animationDuration={600} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Commands Chart ────────────────────────────────────────────────────────

function CommandsSection({ period }: { period: string }) {
  const [commands, setCommands] = useState<CommandItem[]>([])
  const [total, setTotal]       = useState(0)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchAnalyticsCommands(period)
      .then((d) => { setCommands(d.commands); setTotal(d.total) })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [period])

  return (
    <div className={`${CARD} animate-fade-in-up p-5`} style={staggerDelay(6)}>
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">명령어 빈도 (상위 15)</h2>
        <span className="text-xs text-slate-400">총 {total.toLocaleString()}건</span>
      </div>
      {loading ? <div className="h-48 flex items-center justify-center"><Spinner /></div>
       : error  ? <ErrorBanner message={error} />
       : commands.length === 0 ? (
        <p className="text-sm text-slate-400 py-8 text-center">데이터 없음</p>
       ) : (
        <ResponsiveContainer width="100%" height={Math.max(180, commands.length * 28)}>
          <BarChart data={commands} layout="vertical" margin={{ top: 4, right: 32, left: 40, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
            <YAxis type="category" dataKey="command" tick={{ fontSize: 12 }} width={60} />
            <Tooltip formatter={(v: number) => [`${v}건`, '횟수']} />
            <Bar dataKey="count" fill="#6366f1" radius={[0, 2, 2, 0]} animationBegin={staggerDelayMs(6)} animationDuration={600} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Heatmap ───────────────────────────────────────────────────────────────

function HeatmapSection() {
  const [matrix, setMatrix] = useState<number[][] | null>(null)
  const [maxVal, setMaxVal]  = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [tooltip, setTooltip] = useState<{ label: string; h: number; val: number } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const drag = useRef({ isDragging: false, startX: 0, scrollLeft: 0 })

  useEffect(() => {
    fetchAnalyticsHeatmap()
      .then((d) => { setMatrix(d.matrix); setMaxVal(d.max || 1) })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const onMouseDown = (e: React.MouseEvent) => {
    drag.current = {
      isDragging: true,
      startX: e.pageX - (scrollRef.current?.offsetLeft ?? 0),
      scrollLeft: scrollRef.current?.scrollLeft ?? 0,
    }
    if (scrollRef.current) scrollRef.current.style.cursor = 'grabbing'
  }
  const stopDrag = () => {
    drag.current.isDragging = false
    if (scrollRef.current) scrollRef.current.style.cursor = 'grab'
  }
  const onMouseMove = (e: React.MouseEvent) => {
    if (!drag.current.isDragging || !scrollRef.current) return
    e.preventDefault()
    const x = e.pageX - scrollRef.current.offsetLeft
    scrollRef.current.scrollLeft = drag.current.scrollLeft - (x - drag.current.startX)
  }

  return (
    <div className={`${CARD} animate-fade-in-up p-5 relative`} style={staggerDelay(5)}>
      <div className="flex items-center gap-2 mb-4">
        <Clock size={16} className="text-slate-400" />
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">시간대별 사용 히트맵 (최근 90일, KST)</h2>
      </div>
      {tooltip && (
        <div className="pointer-events-none absolute top-4 right-4 rounded-md bg-slate-900 dark:bg-slate-700 px-2.5 py-1.5 text-xs text-white shadow-lg z-10">
          {tooltip.label} {tooltip.h}시: <span className="font-semibold">{tooltip.val}건</span>
        </div>
      )}
      {loading ? <div className="h-32 flex items-center justify-center"><Spinner /></div>
       : error  ? <ErrorBanner message={error} />
       : !matrix ? null
       : (
        <div
          ref={scrollRef}
          className="overflow-x-auto scrollbar-none select-none cursor-grab"
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={stopDrag}
          onMouseLeave={stopDrag}
        >
          <div className="min-w-max">
            {/* Hour header */}
            <div className="flex items-center mb-1">
              <div className="w-8 shrink-0" />
              {Array.from({ length: 24 }, (_, h) => (
                <div key={h} className="w-6 text-center text-[10px] text-slate-400 leading-none">
                  {h % 4 === 0 ? `${h}시` : ''}
                </div>
              ))}
            </div>
            {/* Rows */}
            {WEEKDAY_LABELS.map((label, d) => (
              <div key={d} className="flex items-center mb-0.5">
                <div className="w-8 shrink-0 text-xs text-slate-500 dark:text-slate-400 font-medium">{label}</div>
                {Array.from({ length: 24 }, (_, h) => {
                  const val = matrix[d][h]
                  return (
                    <div
                      key={h}
                      className={`w-6 h-5 rounded-sm mr-0.5 ${heatColor(val, maxVal)}`}
                      onMouseEnter={() => setTooltip({ label, h, val })}
                      onMouseLeave={() => setTooltip(null)}
                    />
                  )
                })}
              </div>
            ))}
            {/* Legend */}
            <div className="flex items-center gap-1 mt-3">
              <span className="text-[10px] text-slate-400 mr-1">적음</span>
              {['bg-slate-100 dark:bg-slate-800', 'bg-primary-100 dark:bg-primary-900', 'bg-primary-200 dark:bg-primary-700', 'bg-primary-400', 'bg-primary-600'].map((c, i) => (
                <div key={i} className={`w-5 h-4 rounded-sm ${c}`} />
              ))}
              <span className="text-[10px] text-slate-400 ml-1">많음</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Users Table ───────────────────────────────────────────────────────────

function UsersSection({ period }: { period: string }) {
  const [users, setUsers]   = useState<AnalyticsUserItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchAnalyticsUsers(period)
      .then((d) => setUsers(d.users))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [period])

  const TH = 'px-4 py-2.5 font-medium text-left text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide'
  const TD = 'px-4 py-2.5 text-sm text-slate-700 dark:text-slate-200'

  return (
    <div className={`${CARD} animate-fade-in-up overflow-hidden`} style={staggerDelay(7)}>
      <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">사용자별 활동</h2>
      </div>
      {loading ? <div className="p-8 flex justify-center"><Spinner /></div>
       : error  ? <div className="p-4"><ErrorBanner message={error} /></div>
       : users.length === 0 ? (
        <p className="text-sm text-slate-400 py-8 text-center">데이터 없음</p>
       ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50">
                <th className={TH}>#</th>
                <th className={TH}>사용자 ID</th>
                <th className={TH}>이름</th>
                <th className={`${TH} text-right`}>명령 수</th>
                <th className={`${TH} text-right`}>마지막 활동</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u, i) => (
                <tr key={u.user_id} className="animate-fade-in border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" style={staggerDelay(i)}>
                  <td className={`${TD} text-slate-400`}>{i + 1}</td>
                  <td className={TD}>
                    <code className="text-xs bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">{u.user_id}</code>
                  </td>
                  <td className={TD}>{u.username || <span className="text-slate-400">-</span>}</td>
                  <td className={`${TD} text-right font-medium tabular-nums`}>{u.count.toLocaleString()}</td>
                  <td className={`${TD} text-right text-slate-500 tabular-nums`}>{u.last_active}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────

export default function Analytics({ hideHeader = false }: { hideHeader?: boolean } = {}) {
  const [period, setPeriod] = usePersistedState('filter:analytics:period', '7d')
  const [days, setDays] = usePersistedState('filter:analytics:days', 30)
  const meta = PAGE_META.analytics

  const handlePeriodChange = (newPeriod: string) => {
    setPeriod(newPeriod)
    setDays(periodToDays(newPeriod))
  }

  return (
    <div className="space-y-6 pb-12">
      {!hideHeader ? (
        <PageHeader
          title={meta.title}
          subtitle={meta.subtitle}
          Icon={meta.Icon}
          actions={
            <FilterBar
              options={PERIOD_OPTIONS}
              value={period}
              onChange={handlePeriodChange}
            />
          }
        />
      ) : (
        <div className="flex justify-end">
          <FilterBar
            options={PERIOD_OPTIONS}
            value={period}
            onChange={handlePeriodChange}
          />
        </div>
      )}

      <OverviewSection />

      <ActivitySection days={days} onDaysChange={setDays} />

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(680px,2fr)_minmax(280px,1fr)] gap-6">
        <HeatmapSection />
        <CommandsSection period={period} />
      </div>

      <UsersSection period={period} />
    </div>
  )
}
