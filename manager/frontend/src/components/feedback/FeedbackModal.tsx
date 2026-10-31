import { FormEvent, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertCircle,
  Bug,
  CheckCircle2,
  Clock,
  HelpCircle,
  Lightbulb,
  MessageSquare,
  PenLine,
  Send,
  Trash2,
  X,
} from 'lucide-react'
import {
  deleteMyFeedback,
  fetchMyFeedbacks,
  submitFeedback,
  updateMyFeedback,
} from '../../api/feedback'
import Badge from '../ui/Badge'
import Spinner from '../ui/Spinner'
import type { FeedbackCategory, FeedbackItem } from '../../types'

interface Props {
  isOpen: boolean
  onClose: () => void
}

const CATEGORY_META: Record<
  FeedbackCategory,
  { label: string; icon: React.ElementType; color: string }
> = {
  feature: { label: '기능 제안', icon: Lightbulb, color: 'text-amber-500' },
  bug: { label: '버그 신고', icon: Bug, color: 'text-rose-500' },
  inquiry: { label: '일반 문의', icon: HelpCircle, color: 'text-sky-500' },
}


export default function FeedbackModal({ isOpen, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<'send' | 'history'>('send')

  // 작성 상태
  const [category, setCategory] = useState<FeedbackCategory>('feature')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitSuccess, setSubmitSuccess] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // 내역 상태
  const [myFeedbacks, setMyFeedbacks] = useState<FeedbackItem[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [editCategory, setEditCategory] = useState<FeedbackCategory>('feature')
  const [updating, setUpdating] = useState(false)

  // ESC 키 닫기 핸들러
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  // 내역 불러오기
  const loadHistory = async () => {
    setLoadingHistory(true)
    try {
      const res = await fetchMyFeedbacks()
      setMyFeedbacks(res.reports || [])
    } catch {
      // ignore
    } finally {
      setLoadingHistory(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      loadHistory()
      setSubmitSuccess(false)
      setErrorMsg(null)
    }
  }, [isOpen])

  useEffect(() => {
    if (activeTab === 'history') {
      loadHistory()
    }
  }, [activeTab])

  if (!isOpen) return null

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!title.trim() || !content.trim()) return

    setSubmitting(true)
    setErrorMsg(null)
    try {
      await submitFeedback({
        category,
        title: title.trim(),
        content: content.trim(),
        browser_info: typeof navigator !== 'undefined' ? navigator.userAgent : '',
      })
      setSubmitSuccess(true)
      setTitle('')
      setContent('')
      setCategory('feature')
      loadHistory()
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '피드백 제출에 실패했습니다.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm('정말 이 피드백을 삭제하시겠습니까?')) return
    try {
      await deleteMyFeedback(id)
      setMyFeedbacks((prev) => prev.filter((item) => item.id !== id))
    } catch {
      alert('삭제에 실패했습니다.')
    }
  }

  const handleStartEdit = (item: FeedbackItem) => {
    setEditingId(item.id)
    setEditTitle(item.title)
    setEditContent(item.content)
    setEditCategory(item.category)
  }

  const handleSaveEdit = async (e: FormEvent) => {
    e.preventDefault()
    if (!editingId || !editTitle.trim() || !editContent.trim()) return
    setUpdating(true)
    try {
      const updated = await updateMyFeedback(editingId, {
        category: editCategory,
        title: editTitle.trim(),
        content: editContent.trim(),
      })
      setMyFeedbacks((prev) =>
        prev.map((item) => (item.id === editingId ? { ...item, ...updated } : item)),
      )
      setEditingId(null)
    } catch {
      alert('수정에 실패했습니다.')
    } finally {
      setUpdating(false)
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      {/* 백드롭 */}
      <div
        className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* 모달 본체 */}
      <div className="relative z-10 w-full max-w-xl max-h-[90vh] flex flex-col rounded-2xl bg-white shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800 break-keep overflow-hidden animate-fade-in-up">
        {/* 모달 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-slate-800 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary-50 dark:bg-primary-950/50 text-primary-600 dark:text-primary-400">
              <MessageSquare size={17} />
            </div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white">피드백 및 건의사항</h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="닫기"
          >
            <X size={18} />
          </button>
        </div>

        {/* 탭 네비게이션 */}
        <div className="flex px-6 pt-3 pb-2 border-b border-slate-100 dark:border-slate-800 gap-2 shrink-0 bg-slate-50/50 dark:bg-slate-900/50">
          <button
            type="button"
            onClick={() => {
              setActiveTab('send')
              setSubmitSuccess(false)
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'send'
                ? 'bg-white dark:bg-slate-800 text-primary-600 dark:text-primary-400 shadow-sm border border-slate-200/80 dark:border-slate-700'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            피드백 작성
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('history')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'history'
                ? 'bg-white dark:bg-slate-800 text-primary-600 dark:text-primary-400 shadow-sm border border-slate-200/80 dark:border-slate-700'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            <span>내 작성 내역</span>
            {myFeedbacks.length > 0 && (
              <span className="rounded-full bg-primary-100 dark:bg-primary-950/60 px-1.5 py-0.2 text-[10px] font-bold text-primary-600 dark:text-primary-400">
                {myFeedbacks.length}
              </span>
            )}
          </button>
        </div>

        {/* 탭 콘텐츠 영역 */}
        <div className="flex-1 overflow-y-auto p-6 min-h-[300px]">
          {activeTab === 'send' ? (
            submitSuccess ? (
              <div className="flex flex-col items-center justify-center py-10 text-center gap-3 animate-fade-in-up">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 size={28} />
                </div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  소중한 피드백이 접수되었습니다!
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm">
                  보내주신 의견은 관리자가 면밀히 검토 후 반영할 예정입니다. 진행 상황은 &lsquo;내 작성 내역&rsquo;에서 확인하실 수 있습니다.
                </p>
                <div className="flex items-center gap-2.5 mt-3">
                  <button
                    type="button"
                    onClick={() => setSubmitSuccess(false)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  >
                    추가 작성하기
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab('history')}
                    className="px-4 py-2 rounded-xl text-xs font-semibold bg-primary-600 hover:bg-primary-500 text-white shadow-sm transition-colors"
                  >
                    내 내역 확인
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                {/* 유형 선택 */}
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-2">
                    피드백 유형
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {(['feature', 'bug', 'inquiry'] as FeedbackCategory[]).map((cat) => {
                      const meta = CATEGORY_META[cat]
                      const Icon = meta.icon
                      const isSelected = category === cat
                      return (
                        <button
                          key={cat}
                          type="button"
                          onClick={() => setCategory(cat)}
                          className={`flex items-center justify-center gap-2 py-2 px-3 rounded-xl border text-xs font-medium transition-all ${
                            isSelected
                              ? 'border-primary-500 bg-primary-50/50 text-primary-700 dark:bg-primary-950/30 dark:border-primary-400 dark:text-primary-300 font-bold shadow-sm'
                              : 'border-slate-200 dark:border-slate-700 bg-transparent text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600'
                          }`}
                        >
                          <Icon size={14} className={meta.color} />
                          <span>{meta.label}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* 제목 */}
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">
                    제목
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="제목을 간결하게 입력해주세요"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-xs placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-all"
                  />
                </div>

                {/* 본문 내용 */}
                <div>
                  <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">
                    상세 내용
                  </label>
                  <textarea
                    required
                    rows={6}
                    placeholder="겪으신 문제나 원하시는 기능, 문의 내용을 자세히 적어주시면 검토에 큰 도움이 됩니다."
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white text-xs placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 resize-none transition-all"
                  />
                </div>

                {errorMsg && (
                  <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-400 text-xs">
                    <AlertCircle size={14} className="shrink-0" />
                    <span>{errorMsg}</span>
                  </div>
                )}

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 rounded-xl text-xs font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  >
                    취소
                  </button>
                  <button
                    type="submit"
                    disabled={submitting || !title.trim() || !content.trim()}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-primary-600 hover:bg-primary-500 disabled:opacity-50 text-white shadow-sm transition-all"
                  >
                    {submitting ? (
                      <>
                        <Spinner className="w-3.5 h-3.5" />
                        <span>전송 중...</span>
                      </>
                    ) : (
                      <>
                        <Send size={13} />
                        <span>피드백 전송</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            )
          ) : (
            /* 내 작성 내역 탭 */
            <div>
              {loadingHistory ? (
                <div className="py-12 flex justify-center">
                  <Spinner />
                </div>
              ) : myFeedbacks.length === 0 ? (
                <div className="py-12 text-center text-slate-400 dark:text-slate-500 text-xs flex flex-col items-center gap-2">
                  <MessageSquare size={24} className="opacity-40" />
                  <span>아직 등록한 피드백이 없습니다.</span>
                </div>
              ) : (
                <div className="space-y-3">
                  {myFeedbacks.map((item) => {
                    const isEditing = editingId === item.id
                    const catMeta = CATEGORY_META[item.category] || CATEGORY_META.feature
                                        const CatIcon = catMeta.icon

                    if (isEditing) {
                      return (
                        <form
                          key={item.id}
                          onSubmit={handleSaveEdit}
                          className="p-4 rounded-xl border border-primary-300 dark:border-primary-700 bg-primary-50/20 dark:bg-primary-950/20 space-y-3"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-primary-600 dark:text-primary-400">
                              피드백 수정
                            </span>
                            <div className="flex gap-1.5">
                              {(['feature', 'bug', 'inquiry'] as FeedbackCategory[]).map((cat) => (
                                <button
                                  key={cat}
                                  type="button"
                                  onClick={() => setEditCategory(cat)}
                                  className={`px-2 py-1 rounded text-[11px] font-medium border ${
                                    editCategory === cat
                                      ? 'border-primary-500 bg-primary-500 text-white'
                                      : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400'
                                  }`}
                                >
                                  {CATEGORY_META[cat].label}
                                </button>
                              ))}
                            </div>
                          </div>
                          <input
                            type="text"
                            required
                            value={editTitle}
                            onChange={(e) => setEditTitle(e.target.value)}
                            className="w-full px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs"
                          />
                          <textarea
                            required
                            rows={3}
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            className="w-full px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs resize-none"
                          />
                          <div className="flex justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => setEditingId(null)}
                              className="px-2.5 py-1 text-xs text-slate-500"
                            >
                              취소
                            </button>
                            <button
                              type="submit"
                              disabled={updating}
                              className="px-3 py-1 bg-primary-600 text-white rounded-lg text-xs font-semibold"
                            >
                              {updating ? '저장 중...' : '저장'}
                            </button>
                          </div>
                        </form>
                      )
                    }

                    return (
                      <div
                        key={item.id}
                        className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/60 shadow-xs space-y-2.5"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2 flex-wrap min-w-0">
                            <div className="flex items-center gap-1 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                              <CatIcon size={12} className={catMeta.color} />
                              <span>{catMeta.label}</span>
                            </div>
                            <span className="text-slate-300 dark:text-slate-700">·</span>
                            <Badge value={item.status} />
                          </div>
                          <div className="flex items-center gap-1 shrink-0 text-slate-400 text-[11px]">
                            <Clock size={11} />
                            <span>
                              {item.created_at
                                ? new Date(item.created_at).toLocaleDateString('ko-KR')
                                : ''}
                            </span>
                          </div>
                        </div>

                        <div>
                          <h4 className="text-xs font-bold text-slate-900 dark:text-white">
                            {item.title}
                          </h4>
                          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
                            {item.content}
                          </p>
                        </div>

                        {/* 관리자 답변 영역 */}
                        {item.admin_note && (
                          <div className="mt-2 p-3 rounded-lg bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-100 dark:border-emerald-900/40 text-xs">
                            <div className="flex items-center gap-1.5 font-bold text-emerald-700 dark:text-emerald-400 mb-1">
                              <CheckCircle2 size={13} />
                              <span>관리자 답변</span>
                            </div>
                            <p className="text-emerald-900 dark:text-emerald-200 whitespace-pre-wrap leading-relaxed">
                              {item.admin_note}
                            </p>
                          </div>
                        )}

                        {/* 작업 버튼 (신규 상태일 때만 수정/삭제 허용) */}
                        {item.status === 'new' && (
                          <div className="flex items-center justify-end gap-2 pt-1 border-t border-slate-100 dark:border-slate-800/80">
                            <button
                              type="button"
                              onClick={() => handleStartEdit(item)}
                              className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-primary-600 dark:text-slate-400 dark:hover:text-primary-400 transition-colors"
                            >
                              <PenLine size={11} />
                              <span>수정</span>
                            </button>
                            <span className="text-slate-300 dark:text-slate-700 text-xs">·</span>
                            <button
                              type="button"
                              onClick={() => handleDelete(item.id)}
                              className="flex items-center gap-1 text-[11px] text-rose-500 hover:text-rose-600 transition-colors"
                            >
                              <Trash2 size={11} />
                              <span>삭제</span>
                            </button>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  )
}
