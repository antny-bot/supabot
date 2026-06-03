import { useEffect, useState } from 'react'
import { archiveEvent, fetchEvents, markEventRead, unarchiveEvent, unreadEvent } from '../api/events'
import type { Event } from '../types'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import ErrorBanner from '../components/ui/ErrorBanner'
import FilterBar from '../components/ui/FilterBar'
import Spinner from '../components/ui/Spinner'

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

function fmtTime(value: string) {
  return value ? value.slice(0, 19).replace('T', ' ') : '--'
}

export function EventsContent() {
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
      <div className="flex flex-wrap items-center gap-2">
        <FilterBar options={STATE_OPTIONS} value={state} onChange={setState} />
        <FilterBar options={LEVEL_OPTIONS} value={level} onChange={setLevel} />
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading ? (
          <Spinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                  <th className="whitespace-nowrap px-4 py-3 text-left font-medium">시간</th>
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
                    <td colSpan={7} className="px-4 py-10 text-center text-xs text-slate-400 dark:text-slate-500">
                      이벤트가 없습니다.
                    </td>
                  </tr>
                ) : events.map((event) => (
                  <tr
                    key={event.id}
                    className={`transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40 ${
                      event.level === 'error' ? 'bg-rose-50/40 dark:bg-rose-950/20' : ''
                    }`}
                  >
                    <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-slate-500 dark:text-slate-400">
                      {fmtTime(String(event.created_at))}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge value={event.level} />
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-600 dark:text-slate-300">{event.source}</td>
                    <td className="max-w-xs truncate px-4 py-2.5 text-xs text-slate-700 dark:text-slate-200">
                      {event.message}
                    </td>
                    <td className="max-w-xs truncate px-4 py-2.5 text-xs text-slate-400 dark:text-slate-600">
                      {event.details ?? '--'}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-xs text-slate-500 dark:text-slate-400">
                      {event.archived_at ? '보관됨' : event.read_at ? '읽음' : '미확인'}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap gap-2">
                        {!event.read_at ? (
                          <Button variant="success" size="sm" disabled={pendingId === event.id} onClick={() => void runAction(event.id, () => markEventRead(event.id))}>
                            읽음
                          </Button>
                        ) : (
                          <Button variant="ghost" size="sm" disabled={pendingId === event.id} onClick={() => void runAction(event.id, () => unreadEvent(event.id))}>
                            읽음 취소
                          </Button>
                        )}
                        {!event.archived_at ? (
                          <Button variant="warning" size="sm" disabled={pendingId === event.id} onClick={() => void runAction(event.id, () => archiveEvent(event.id))}>
                            보관
                          </Button>
                        ) : (
                          <Button variant="ghost" size="sm" disabled={pendingId === event.id} onClick={() => void runAction(event.id, () => unarchiveEvent(event.id))}>
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

      <p className="text-right text-xs text-slate-400 dark:text-slate-600">최근 {events.length}건</p>
    </div>
  )
}

export default function Events() {
  return <EventsContent />
}
