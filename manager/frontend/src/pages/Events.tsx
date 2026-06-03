import { useEffect, useState } from 'react'
import { archiveEvent, fetchEvents, markEventRead, unarchiveEvent, unreadEvent } from '../api/events'
import type { Event } from '../types'
import Badge from '../components/ui/Badge'
import FilterBar from '../components/ui/FilterBar'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import Button from '../components/ui/Button'

const LEVEL_OPTIONS = [
  { value: '', label: '전체' },
  { value: 'error', label: '오류' },
  { value: 'warning', label: '경고' },
  { value: 'info', label: '정보' },
]

const STATE_OPTIONS = [
  { value: 'unread', label: '미확인' },
  { value: 'read', label: '읽음' },
  { value: 'archived', label: '보관됨' },
  { value: 'all', label: '전체' },
]

function fmtTime(s: string) {
  return s ? s.slice(0, 19).replace('T', ' ') : '--'
}

export default function Events() {
  const [events, setEvents] = useState<Event[]>([])
  const [level, setLevel] = useState('')
  const [state, setState] = useState('unread')
  const [loading, setLoading] = useState(true)
  const [pendingId, setPendingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  function loadEvents() {
    setLoading(true)
    fetchEvents(level, state)
      .then(setEvents)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류가 발생했습니다.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadEvents()
  }, [level, state])

  async function runAction(eventId: number, action: () => Promise<Event>) {
    setPendingId(eventId)
    setError(null)
    try {
      await action()
      loadEvents()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '이벤트 상태 변경에 실패했습니다.')
    } finally {
      setPendingId(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">이벤트 로그</h1>
        <div className="flex flex-wrap items-center gap-2">
          <FilterBar options={STATE_OPTIONS} value={state} onChange={setState} />
          <FilterBar options={LEVEL_OPTIONS} value={level} onChange={setLevel} />
        </div>
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
                  <th className="px-4 py-3 text-left font-medium">상태</th>
                  <th className="px-4 py-3 text-left font-medium">작업</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {events.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-10 text-center text-slate-400 dark:text-slate-500 text-xs">
                      이벤트가 없습니다.
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
                      {ev.details ?? '--'}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                      {ev.archived_at ? '보관됨' : ev.read_at ? '읽음' : '미확인'}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap gap-2">
                        {!ev.read_at ? (
                          <Button variant="success" size="sm" disabled={pendingId === ev.id} onClick={() => void runAction(ev.id, () => markEventRead(ev.id))}>
                            읽음
                          </Button>
                        ) : (
                          <Button variant="ghost" size="sm" disabled={pendingId === ev.id} onClick={() => void runAction(ev.id, () => unreadEvent(ev.id))}>
                            읽음 취소
                          </Button>
                        )}
                        {!ev.archived_at ? (
                          <Button variant="warning" size="sm" disabled={pendingId === ev.id} onClick={() => void runAction(ev.id, () => archiveEvent(ev.id))}>
                            보관
                          </Button>
                        ) : (
                          <Button variant="ghost" size="sm" disabled={pendingId === ev.id} onClick={() => void runAction(ev.id, () => unarchiveEvent(ev.id))}>
                            보관 해제
                          </Button>
                        )}
                      </div>
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
