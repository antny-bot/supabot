import { useEffect, useState } from 'react'
import {
  Bug,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  HelpCircle,
  Lightbulb,
  MessageSquare,
  RefreshCw,
  Search,
  Trash2,
  User,
} from 'lucide-react'
import {
  deleteAdminFeedback,
  fetchAdminFeedbacks,
  updateAdminFeedback,
} from '../../api/feedback'
import Badge from '../../components/ui/Badge'
import Spinner from '../../components/ui/Spinner'
import type { FeedbackCategory, FeedbackItem, FeedbackStatus } from '../../types'

const CATEGORY_META: Record<
  FeedbackCategory,
  { label: string; icon: React.ElementType; color: string }
> = {
  feature: { label: '기능 제안', icon: Lightbulb, color: 'text-amber-500' },
  bug: { label: '버그 신고', icon: Bug, color: 'text-rose-500' },
  inquiry: { label: '일반 문의', icon: HelpCircle, color: 'text-sky-500' },
}

const STATUS_OPTIONS: { id: FeedbackStatus; label: string; variant: 'primary' | 'warning' | 'success' | 'slate' }[] = [
  { id: 'new', label: '접수 대기', variant: 'primary' },
  { id: 'in_progress', label: '검토/처리중', variant: 'warning' },
  { id: 'resolved', label: '반영 완료', variant: 'success' },
  { id: 'dismissed', label: '보류/반려', variant: 'slate' },
]

export default function AdminFeedbacksTab() {
  const [feedbacks, setFeedbacks] = useState<FeedbackItem[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [daysFilter, setDaysFilter] = useState<number | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(15)
  const [totalPages, setTotalPages] = useState(1)
  const [totalItems, setTotalItems] = useState(0)

  // 답변 작성 중인 항목 state: { [id]: string }
  const [editingNotes, setEditingNotes] = useState<Record<string, string>>({})
  const [savingNoteId, setSavingNoteId] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')

  const loadData = async () => {
    setLoading(true)
    try {
      const res = await fetchAdminFeedbacks({
        status: statusFilter,
        category: categoryFilter,
        days: daysFilter || undefined,
        page,
        page_size: pageSize,
      })
      setFeedbacks(res.reports || [])
      setTotalPages(res.pagination.totalPages || 1)
      setTotalItems(res.pagination.totalItems || 0)

      // note 상태 초기화
      const notesMap: Record<string, string> = {}
      ;(res.reports || []).forEach((r) => {
        notesMap[r.id] = r.admin_note || ''
      })
      setEditingNotes(notesMap)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [statusFilter, categoryFilter, daysFilter, page])

  const handleStatusChange = async (id: string, newStatus: FeedbackStatus) => {
    try {
      await updateAdminFeedback(id, { status: newStatus })
      setFeedbacks((prev) =>
        prev.map((item) => (item.id === id ? { ...item, status: newStatus } : item)),
      )
    } catch {
      alert('상태 변경에 실패했습니다.')
    }
  }

  const handleSaveNote = async (id: string) => {
    const note = editingNotes[id] ?? ''
    setSavingNoteId(id)
    try {
      await updateAdminFeedback(id, { admin_note: note })
      setFeedbacks((prev) =>
        prev.map((item) => (item.id === id ? { ...item, admin_note: note } : item)),
      )
      alert('관리자 답변이 저장되었습니다.')
    } catch {
      alert('답변 저장에 실패했습니다.')
    } finally {
      setSavingNoteId(null)
    }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm('정말 이 피드백을 삭제하시겠습니까?')) return
    try {
      await deleteAdminFeedback(id)
      setFeedbacks((prev) => prev.filter((item) => item.id !== id))
      setTotalItems((prev) => Math.max(0, prev - 1))
    } catch {
      alert('삭제에 실패했습니다.')
    }
  }

  const handleCopy = (item: FeedbackItem) => {
    const text = `[${CATEGORY_META[item.category]?.label || item.category}] ${item.title}\n작성자: ${item.username || item.user_email}\n내용:\n${item.content}`
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(item.id)
      setTimeout(() => setCopiedId(null), 2000)
    })
  }

  const filteredFeedbacks = searchTerm.trim()
    ? feedbacks.filter(
        (f) =>
          f.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
          f.content.toLowerCase().includes(searchTerm.toLowerCase()) ||
          (f.username && f.username.toLowerCase().includes(searchTerm.toLowerCase())) ||
          (f.user_email && f.user_email.toLowerCase().includes(searchTerm.toLowerCase())),
      )
    : feedbacks

  return (
    <div className="space-y-5 break-keep">
      {/* 상단 필터 바 */}
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3 shadow-xs">
        {/* 상태 필터 칩 */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-semibold text-slate-500 mr-1">상태:</span>
            <button
              onClick={() => {
                setStatusFilter('all')
                setPage(1)
              }}
              className={`px-3 py-1 rounded-xl text-xs font-semibold transition-all ${
                statusFilter === 'all'
                  ? 'bg-primary-600 text-white shadow-xs'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200'
              }`}
            >
              전체
            </button>
            {STATUS_OPTIONS.map((st) => (
              <button
                key={st.id}
                onClick={() => {
                  setStatusFilter(st.id)
                  setPage(1)
                }}
                className={`px-3 py-1 rounded-xl text-xs font-semibold transition-all ${
                  statusFilter === st.id
                    ? 'bg-primary-600 text-white shadow-xs'
                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200'
                }`}
              >
                {st.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={loadData}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              <span>새로고침</span>
            </button>
          </div>
        </div>

        {/* 보조 필터 & 검색 */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100 dark:border-slate-800">
          <div className="flex flex-wrap items-center gap-3">
            {/* 유형 필터 */}
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <span>유형:</span>
              <select
                value={categoryFilter}
                onChange={(e) => {
                  setCategoryFilter(e.target.value)
                  setPage(1)
                }}
                className="px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 text-xs focus:outline-none"
              >
                <option value="all">전체</option>
                <option value="bug">버그 신고</option>
                <option value="feature">기능 제안</option>
                <option value="inquiry">일반 문의</option>
              </select>
            </div>

            {/* 기간 필터 */}
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <span>기간:</span>
              <select
                value={daysFilter === null ? 'all' : String(daysFilter)}
                onChange={(e) => {
                  setDaysFilter(e.target.value === 'all' ? null : Number(e.target.value))
                  setPage(1)
                }}
                className="px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 text-xs focus:outline-none"
              >
                <option value="all">전체</option>
                <option value="7">최근 7일</option>
                <option value="30">최근 30일</option>
              </select>
            </div>
          </div>

          {/* 검색창 */}
          <div className="relative w-full sm:w-60">
            <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="제목, 내용, 유저 검색..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-xs placeholder:text-slate-400 focus:outline-none focus:border-primary-500"
            />
          </div>
        </div>
      </div>

      {/* 목록 리스트 */}
      {loading ? (
        <div className="py-20 flex justify-center">
          <Spinner />
        </div>
      ) : filteredFeedbacks.length === 0 ? (
        <div className="py-20 text-center text-slate-400 dark:text-slate-500 text-xs flex flex-col items-center gap-2">
          <MessageSquare size={32} className="opacity-40" />
          <span>등록된 피드백이 없습니다.</span>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredFeedbacks.map((item) => {
            const catMeta = CATEGORY_META[item.category] || CATEGORY_META.feature
            const CatIcon = catMeta.icon
                        const isSaving = savingNoteId === item.id
            const isCopied = copiedId === item.id

            return (
              <div
                key={item.id}
                className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-xs space-y-4 transition-all hover:border-slate-300 dark:hover:border-slate-700"
              >
                {/* 상단 메타 헤더 */}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <span className="flex items-center gap-1 text-xs font-bold text-slate-700 dark:text-slate-300">
                      <CatIcon size={14} className={catMeta.color} />
                      <span>{catMeta.label}</span>
                    </span>
                    <span className="text-slate-300 dark:text-slate-700">·</span>
                    <Badge value={item.status} />
                    <span className="text-slate-300 dark:text-slate-700">·</span>
                    <div className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                      <User size={12} />
                      <span className="font-medium text-slate-700 dark:text-slate-200">
                        {item.username || item.user_email || item.user_id}
                      </span>
                      {item.user_email && item.username && item.user_email !== item.username && (
                        <span className="text-[11px] text-slate-400">({item.user_email})</span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => handleCopy(item)}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                      title="피드백 내용 복사"
                    >
                      {isCopied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
                      <span>{isCopied ? '복사됨' : '복사'}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(item.id)}
                      className="p-1 rounded-lg text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors"
                      title="피드백 삭제"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {/* 제목 및 본문 */}
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    {item.title}
                  </h3>
                  <p className="mt-2 text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed bg-slate-50/60 dark:bg-slate-800/40 p-3.5 rounded-xl border border-slate-100 dark:border-slate-800/80">
                    {item.content}
                  </p>
                </div>

                {/* 환경 정보 (있을 때만) */}
                {item.browser_info && (
                  <div className="text-[11px] text-slate-400 truncate" title={item.browser_info}>
                    <span className="font-semibold text-slate-500">환경: </span>
                    {item.browser_info}
                  </div>
                )}

                {/* 관리자 컨트롤 바 (상태 변경 및 관리자 답변 작성) */}
                <div className="pt-3 border-t border-slate-100 dark:border-slate-800 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-500">상태 변경:</span>
                      <div className="flex gap-1">
                        {STATUS_OPTIONS.map((st) => (
                          <button
                            key={st.id}
                            type="button"
                            onClick={() => handleStatusChange(item.id, st.id)}
                            className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-all ${
                              item.status === st.id
                                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900 border-transparent shadow-xs'
                                : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                            }`}
                          >
                            {st.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="flex items-center gap-1 text-[11px] text-slate-400">
                      <Clock size={11} />
                      <span>
                        접수: {new Date(item.created_at).toLocaleString('ko-KR')}
                      </span>
                    </div>
                  </div>

                  {/* 관리자 답변 입력 폼 */}
                  <div className="rounded-xl border border-emerald-100 dark:border-emerald-950/60 bg-emerald-50/30 dark:bg-emerald-950/10 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-emerald-800 dark:text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 size={13} />
                        <span>관리자 답변 및 처리 사유</span>
                      </span>
                      <button
                        type="button"
                        disabled={isSaving}
                        onClick={() => handleSaveNote(item.id)}
                        className="px-3 py-1 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white shadow-xs transition-colors"
                      >
                        {isSaving ? '저장 중...' : '답변 저장'}
                      </button>
                    </div>
                    <textarea
                      rows={2}
                      placeholder="사용자에게 보여질 검토 의견이나 처리 결과를 작성하세요..."
                      value={editingNotes[item.id] ?? ''}
                      onChange={(e) =>
                        setEditingNotes((prev) => ({ ...prev, [item.id]: e.target.value }))
                      }
                      className="w-full px-3 py-2 rounded-lg border border-emerald-200/80 dark:border-emerald-900/60 bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-xs placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-emerald-500 resize-none"
                    />
                  </div>
                </div>
              </div>
            )
          })}

          {/* 페이지네이션 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-4">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold disabled:opacity-40"
              >
                이전
              </button>
              <span className="text-xs text-slate-500">
                {page} / {totalPages} (총 {totalItems}건)
              </span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold disabled:opacity-40"
              >
                다음
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
