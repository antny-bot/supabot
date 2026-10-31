import { useEffect, useState, useCallback } from 'react'
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Layers,
  RefreshCw,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { fetchOrderBatches } from '../../api/orders'
import Badge from '../../components/ui/Badge'
import ProgressBar from '../../components/ui/ProgressBar'
import Spinner from '../../components/ui/Spinner'
import type { OrderBatchItem } from '../../types'
import { krwFmt } from '../../utils/formatters'

interface Props {
  onSelectGroupNo: (groupNo: number) => void
  initialGroupNo?: number
}

export default function OrderBatchesSection({ onSelectGroupNo, initialGroupNo }: Props) {
  const [batches, setBatches] = useState<OrderBatchItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)

  // 펼쳐진 배치 목록 상태
  const [expandedBatches, setExpandedBatches] = useState<Set<number>>(new Set())

  const loadBatches = useCallback(
    async (showSpinner = false) => {
      if (showSpinner) setLoading(true)
      try {
        const res = await fetchOrderBatches(undefined, undefined, page, pageSize)
        setBatches(res.batches || [])
        setTotalPages(res.total_pages || 1)
        setTotalCount(res.total || 0)
        setError(null)

        // initialGroupNo가 있으면 자동 펼침
        if (initialGroupNo && !expandedBatches.has(initialGroupNo)) {
          setExpandedBatches((prev) => new Set([...prev, initialGroupNo]))
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : '배치 목록을 불러오지 못했습니다.')
      } finally {
        if (showSpinner) setLoading(false)
      }
    },
    [page, pageSize, initialGroupNo],
  )

  useEffect(() => {
    loadBatches(true)
  }, [loadBatches])

  const toggleExpand = (groupNo: number) => {
    setExpandedBatches((prev) => {
      const next = new Set(prev)
      if (next.has(groupNo)) {
        next.delete(groupNo)
      } else {
        next.add(groupNo)
      }
      return next
    })
  }

  return (
    <div className="space-y-4 break-keep animate-fade-in-up">
      {/* 상단 컨트롤 바 */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400">
            <Layers size={16} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              전략 배치 실행 주문 묶음
            </h3>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              전략 템플릿에서 발행된 일괄 주문들을 회차(배치) 단위로 한눈에 추적합니다. (총 {totalCount}개 회차)
            </p>
          </div>
        </div>

        <button
          onClick={() => loadBatches(true)}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          <span>새로고침</span>
        </button>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-50 p-4 text-xs font-medium text-rose-600 dark:bg-rose-950/30 dark:text-rose-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : batches.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center text-slate-400 dark:text-slate-500 text-xs gap-2">
          <Layers size={36} className="opacity-30" />
          <span>아직 발행된 전략 배치 주문 내역이 없습니다.</span>
          <span className="text-[11px] text-slate-400">
            전략 템플릿에서 '즉시 실행'하거나 스케줄러가 가동되면 여기에 회차별로 등록됩니다.
          </span>
        </div>
      ) : (
        <div className="space-y-3.5">
          {batches.map((batch) => {
            const isExpanded = expandedBatches.has(batch.group_no)
            const isFullyDone = batch.total_orders > 0 && batch.done_count === batch.total_orders

            return (
              <div
                key={batch.group_no}
                className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xs transition-all dark:border-slate-800 dark:bg-slate-900"
              >
                {/* 배치 카드 헤더 */}
                <div className="p-4 sm:p-5 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2.5">
                    {/* 좌측: 배치 번호 & 템플릿명 & 거래소 */}
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <span className="rounded-lg bg-indigo-100 px-2.5 py-1 text-xs font-extrabold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                        배치 #{batch.group_no}
                      </span>
                      <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                        {batch.template_name}
                      </h4>
                      <Badge value={batch.exchange} label={batch.exchange.toUpperCase()} />
                      <span className="text-xs text-slate-400">· {batch.created_fmt}</span>
                    </div>

                    {/* 우측 액션: 개별 주문 필터링 버튼 & 펼치기 토글 */}
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => onSelectGroupNo(batch.group_no)}
                        className="flex items-center gap-1 rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 transition-colors"
                        title="이 배치의 개별 주문 목록으로 전환하여 조회/관리"
                      >
                        <span>개별 주문 보기</span>
                        <ExternalLink size={12} />
                      </button>

                      <button
                        type="button"
                        onClick={() => toggleExpand(batch.group_no)}
                        className="flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                      >
                        <span>{isExpanded ? '접기' : '상세 목록'}</span>
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    </div>
                  </div>

                  {/* 지표 요약 그리드 */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1 text-xs">
                    <div className="rounded-xl bg-slate-50 p-2.5 dark:bg-slate-800/50">
                      <span className="text-[11px] text-slate-500">주문 구성</span>
                      <div className="mt-0.5 flex items-center gap-1.5 font-bold text-slate-800 dark:text-slate-200">
                        <span>총 {batch.total_orders}건</span>
                        <span className="text-[11px] font-normal text-slate-400">
                          (매수 {batch.buy_count} / 매도 {batch.sell_count})
                        </span>
                      </div>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-2.5 dark:bg-slate-800/50">
                      <span className="text-[11px] text-slate-500">체결 상태</span>
                      <div className="mt-0.5 flex items-center gap-1.5 flex-wrap font-semibold">
                        <span className="text-emerald-600 dark:text-emerald-400">
                          완료 {batch.done_count}
                        </span>
                        {batch.wait_count > 0 && (
                          <span className="text-blue-600 dark:text-blue-400">
                            · 대기 {batch.wait_count}
                          </span>
                        )}
                        {batch.reserved_count > 0 && (
                          <span className="text-violet-600 dark:text-violet-400">
                            · 예약 {batch.reserved_count}
                          </span>
                        )}
                        {batch.cancel_count > 0 && (
                          <span className="text-rose-500">
                            · 취소 {batch.cancel_count}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-2.5 dark:bg-slate-800/50">
                      <span className="text-[11px] text-slate-500">총 주문 규모</span>
                      <div className="mt-0.5 font-bold text-slate-800 dark:text-slate-200">
                        {krwFmt(batch.total_order_value)}
                      </div>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-2.5 dark:bg-slate-800/50">
                      <span className="text-[11px] text-slate-500">체결 진행률</span>
                      <div className="mt-0.5 font-bold text-slate-800 dark:text-slate-200">
                        {batch.fill_pct}%{' '}
                        <span className="text-[11px] font-normal text-slate-400">
                          ({krwFmt(batch.total_filled_value)})
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* 프로그레스 바 */}
                  <div className="space-y-1">
                    <ProgressBar
                      value={batch.fill_pct}
                      color={isFullyDone ? 'bg-emerald-500' : 'bg-primary-600'}
                    />
                  </div>
                </div>

                {/* 아코디언 상세 주문 목록 */}
                {isExpanded && (
                  <div className="border-t border-slate-100 bg-slate-50/50 dark:border-slate-800 dark:bg-slate-900/60 p-4">
                    <div className="mb-2 text-xs font-bold text-slate-700 dark:text-slate-300">
                      소속 주문 목록 ({batch.orders.length}건)
                    </div>
                    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-slate-200 bg-slate-50/80 text-slate-500 dark:border-slate-800 dark:bg-slate-800/60 font-semibold">
                            <th className="px-3.5 py-2">종목명</th>
                            <th className="px-3.5 py-2">구분</th>
                            <th className="px-3.5 py-2 text-right">주문가</th>
                            <th className="px-3.5 py-2 text-right">주문수량</th>
                            <th className="px-3.5 py-2 text-right">체결수량</th>
                            <th className="px-3.5 py-2 text-right">체결률</th>
                            <th className="px-3.5 py-2">상태</th>
                            <th className="px-3.5 py-2">시간</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
                          {batch.orders.map((ord) => (
                            <tr
                              key={ord.uuid}
                              className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                            >
                              <td className="px-3.5 py-2 font-bold text-slate-900 dark:text-white">
                                {ord.ticker}
                              </td>
                              <td className="px-3.5 py-2">
                                <span
                                  className={`inline-flex items-center gap-1 font-bold ${
                                    ord.side === 'bid'
                                      ? 'text-rose-600 dark:text-rose-400'
                                      : 'text-blue-600 dark:text-blue-400'
                                  }`}
                                >
                                  {ord.side === 'bid' ? (
                                    <>
                                      <TrendingUp size={12} />
                                      <span>매수</span>
                                    </>
                                  ) : (
                                    <>
                                      <TrendingDown size={12} />
                                      <span>매도</span>
                                    </>
                                  )}
                                </span>
                              </td>
                              <td className="px-3.5 py-2 text-right font-mono text-slate-700 dark:text-slate-300">
                                {ord.price.toLocaleString()}원
                              </td>
                              <td className="px-3.5 py-2 text-right font-mono text-slate-700 dark:text-slate-300">
                                {ord.volume.toLocaleString()}
                              </td>
                              <td className="px-3.5 py-2 text-right font-mono text-slate-700 dark:text-slate-300">
                                {ord.filled_volume.toLocaleString()}
                              </td>
                              <td className="px-3.5 py-2 text-right font-mono text-slate-500">
                                {ord.fill_pct}%
                              </td>
                              <td className="px-3.5 py-2">
                                <Badge value={ord.status} />
                              </td>
                              <td className="px-3.5 py-2 text-slate-400 text-[11px]">
                                {ord.created_fmt}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          {/* 페이지네이션 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-3">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 text-xs font-semibold disabled:opacity-40"
              >
                이전
              </button>
              <span className="text-xs text-slate-500">
                {page} / {totalPages}
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
