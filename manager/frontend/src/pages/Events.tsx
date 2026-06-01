import { useEffect, useState } from 'react'
import { fetchEvents } from '../api/events'
import type { Event } from '../types'
import Badge from '../components/ui/Badge'
import FilterBar from '../components/ui/FilterBar'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'

const LEVEL_OPTIONS = [
  { value: '',        label: '전체' },
  { value: 'error',   label: '오류' },
  { value: 'warning', label: '경고' },
  { value: 'info',    label: '정보' },
]

function fmtTime(s: string) {
  return s ? s.slice(0, 19).replace('T', ' ') : '—'
}

export default function Events() {
  const [events, setEvents] = useState<Event[]>([])
  const [level, setLevel] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchEvents(level)
      .then(setEvents)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [level])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">이벤트 로그</h1>
        <FilterBar options={LEVEL_OPTIONS} value={level} onChange={setLevel} />
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        {loading ? (
          <Spinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800">
                  <th className="px-4 py-3 text-left font-medium whitespace-nowrap">시간</th>
                  <th className="px-4 py-3 text-left font-medium">레벨</th>
                  <th className="px-4 py-3 text-left font-medium">소스</th>
                  <th className="px-4 py-3 text-left font-medium">메시지</th>
                  <th className="px-4 py-3 text-left font-medium">상세</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {events.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-10 text-center text-slate-400 dark:text-slate-500 text-xs">
                      이벤트 없음
                    </td>
                  </tr>
                ) : events.map((ev) => (
                  <tr key={ev.id} className={`hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors ${ev.level === 'error' ? 'bg-rose-50/40 dark:bg-rose-950/20' : ''}`}>
                    <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 font-mono text-xs whitespace-nowrap">
                      {fmtTime(String(ev.created_at))}
                    </td>
                    <td className="px-4 py-2.5"><Badge value={ev.level} /></td>
                    <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300 text-xs">{ev.source}</td>
                    <td className="px-4 py-2.5 text-slate-700 dark:text-slate-200 text-xs max-w-xs truncate">
                      {ev.message}
                    </td>
                    <td className="px-4 py-2.5 text-slate-400 dark:text-slate-600 text-xs max-w-xs truncate">
                      {ev.details ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-400 dark:text-slate-600 text-right">
        최근 {events.length}건
      </p>
    </div>
  )
}
