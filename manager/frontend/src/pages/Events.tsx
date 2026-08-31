import { useEffect, useState } from 'react'
import { usePersistedState } from '../hooks/usePersistedState'
import {
  archiveEvent,
  fetchEvents,
  markEventRead,
  unarchiveEvent,
  unreadEvent,
  bulkMarkEventsRead,
  bulkArchiveEvents,
  bulkDeleteEvents,
} from '../api/events'
import type { Event } from '../types'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import ErrorBanner from '../components/ui/ErrorBanner'
import FilterBar from '../components/ui/FilterBar'
import Spinner from '../components/ui/Spinner'
import Pagination from '../components/ui/Pagination'
import { staggerDelay } from '../utils/animation'

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
  const [level, setLevel] = usePersistedState('filter:events:level', '')
  const [state, setState] = usePersistedState('filter:events:state', 'unread')
  const [expandedFilter, setExpandedFilter] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [pendingId, setPendingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 페이징 및 일괄 작업 상태
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [totalCount, setTotalCount] = useState(0)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [bulkPending, setBulkPending] = useState(false)

  function loadEvents() {
    setLoading(true)
    fetchEvents(level, state, page, pageSize)
      .then((res) => {
        setEvents(res.events)
        setTotalCount(res.total)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류가 발생했습니다.'))
      .finally(() => setLoading(false))
  }

  // 필터가 변경되면 페이지와 선택 리셋
  useEffect(() => {
    setPage(1)
    setSelectedIds([])
  }, [level, state])

  // 필터, 페이지, 페이지 크기가 변경되면 데이터 로드
  useEffect(() => {
    loadEvents()
  }, [level, state, page, pageSize])

  const toggleFilter = (name: string) => {
    setExpandedFilter((prev) => (prev === name ? null : name))
  }

  async function runAction(eventId: number, action: () => Promise<Event>) {
    setPendingId(eventId)
    setError(null)
    try {
      await action()
      setSelectedIds((prev) => prev.filter((id) => id !== eventId))
      loadEvents()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '이벤트 상태 변경에 실패했습니다.')
    } finally {
      setPendingId(null)
    }
  }

  async function runBulkAction(action: () => Promise<{ success: boolean }>) {
    if (selectedIds.length === 0) return
    setBulkPending(true)
    setError(null)
    try {
      await action()
      setSelectedIds([])
      loadEvents()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '일괄 처리에 실패했습니다.')
    } finally {
      setBulkPending(false)
    }
  }

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(events.map((e) => e.id))
    } else {
      setSelectedIds([])
    }
  }

  const handleSelectOne = (id: number, checked: boolean) => {
    if (checked) {
      setSelectedIds((prev) => [...prev, id])
    } else {
      setSelectedIds((prev) => prev.filter((item) => item !== id))
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <FilterBar collapsible isOpen={expandedFilter === 'state'} onToggle={() => toggleFilter('state')}
          options={STATE_OPTIONS} value={state} onChange={setState}
          disabled={expandedFilter !== null && expandedFilter !== 'state'} />
        <FilterBar collapsible isOpen={expandedFilter === 'level'} onToggle={() => toggleFilter('level')}
          options={LEVEL_OPTIONS} value={level} onChange={setLevel}
          disabled={expandedFilter !== null && expandedFilter !== 'level'} />
      </div>

      {error && <ErrorBanner message={error} />}

      {/* 일괄 작업 툴바 */}
      {selectedIds.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-indigo-100 bg-indigo-50/50 px-4 py-3 dark:border-indigo-950 dark:bg-indigo-950/20 text-xs">
          <span className="font-semibold text-indigo-700 dark:text-indigo-300">
            {selectedIds.length}개 선택됨
          </span>
          <div className="flex gap-2">
            <Button
              variant="success"
              size="sm"
              disabled={bulkPending}
              onClick={() => void runBulkAction(() => bulkMarkEventsRead(selectedIds))}
            >
              일괄 읽음
            </Button>
            <Button
              variant="warning"
              size="sm"
              disabled={bulkPending}
              onClick={() => void runBulkAction(() => bulkArchiveEvents(selectedIds))}
            >
              일괄 보관
            </Button>
            <Button
              variant="danger"
              size="sm"
              disabled={bulkPending}
              onClick={() => {
                if (window.confirm(`${selectedIds.length}개의 이벤트를 정말로 삭제하시겠습니까?`)) {
                  void runBulkAction(() => bulkDeleteEvents(selectedIds))
                }
              }}
            >
              일괄 삭제
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedIds([])}
            >
              선택 취소
            </Button>
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading ? (
          <Spinner />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                    <th className="whitespace-nowrap px-4 py-3 text-left font-medium w-8">
                      <input
                        type="checkbox"
                        checked={events.length > 0 && selectedIds.length === events.length}
                        onChange={(e) => handleSelectAll(e.target.checked)}
                        className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                      />
                    </th>
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
                      <td colSpan={8} className="px-4 py-10 text-center text-xs text-slate-400 dark:text-slate-500">
                        이벤트가 없습니다.
                      </td>
                    </tr>
                  ) : events.map((event, index) => (
                    <tr
                      key={event.id}
                      className={`animate-fade-in transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40 ${
                        event.level === 'error' ? 'bg-rose-50/40 dark:bg-rose-950/20' : ''
                      }`}
                      style={staggerDelay(index)}
                    >
                      <td className="px-4 py-2.5 w-8">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(event.id)}
                          onChange={(e) => handleSelectOne(event.id, e.target.checked)}
                          className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                        />
                      </td>
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
            <Pagination
              currentPage={page}
              totalPages={Math.ceil(totalCount / pageSize)}
              pageSize={pageSize}
              totalCount={totalCount}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
            />
          </>
        )}
      </div>
    </div>
  )
}

export default function Events() {
  return <EventsContent />
}
