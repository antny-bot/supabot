import { Fragment, useEffect, useState, useMemo } from 'react'
import { fetchReportNlLogs } from '../../api/reports'
import type { NlLogRow, NlLogsStats } from '../../types'
import Badge from '../../components/ui/Badge'
import { TableRowSkeleton } from '../../components/ui/Skeleton'
import ErrorBanner from '../../components/ui/ErrorBanner'
import Pagination from '../../components/ui/Pagination'
import { staggerDelay } from '../../utils/animation'

export default function NlLogsSection() {
  const [rows, setRows] = useState<NlLogRow[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<NlLogsStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [expandedId, setExpandedId] = useState<number | string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportNlLogs(200)
      .then((data) => {
        setRows(data.rows)
        setTotal(data.total)
        if (data.stats) {
          setStats(data.stats)
        }
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [])

  // 프론트엔드 자체 폴백 통계 계산 (백엔드 stats가 없을 때도 보장)
  const computedStats = useMemo(() => {
    if (stats) return stats
    if (!rows.length) return null

    let toolCalls = 0
    let multiTurn = 0
    let confirmed = 0
    let rejected = 0
    let pending = 0
    const toolFreq: Record<string, number> = {}

    for (const r of rows) {
      const tools = r.tool_chain || (r.llm_action ? r.llm_action.split(',').map(s => s.trim()) : [])
      if (tools.length > 0 && r.llm_action !== 'chat' && r.llm_action !== 'unmatched') {
        toolCalls++
        for (const t of tools) {
          if (t) toolFreq[t] = (toolFreq[t] || 0) + 1
        }
      }
      if (tools.length > 1) multiTurn++
      if (r.confirm_status === 'confirmed') confirmed++
      if (r.confirm_status === 'rejected') rejected++
      if (r.confirm_status === 'pending') pending++
    }

    const decided = confirmed + rejected
    return {
      total_queries: total || rows.length,
      tool_call_count: toolCalls,
      tool_call_rate: Math.round((toolCalls / rows.length) * 100),
      multi_turn_count: multiTurn,
      confirmed_count: confirmed,
      rejected_count: rejected,
      pending_count: pending,
      approval_rate: decided > 0 ? Math.round((confirmed / decided) * 100) : 0,
      top_tools: Object.entries(toolFreq).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([tool, count]) => ({ tool, count })),
      final_actions: [],
    }
  }, [stats, rows, total])

  if (error) return <ErrorBanner message={error} />

  const toggleExpand = (id: number | string) => {
    setExpandedId((prev) => (prev === id ? null : id))
  }

  return (
    <div className="space-y-5">
      {/* 1. 상단 멀티턴 AI 에이전트 핵심 지표 카드 */}
      {computedStats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 break-keep">총 자연어 요청</p>
            <p className="mt-1 text-2xl font-bold tracking-tight text-slate-800 dark:text-slate-100">
              {computedStats.total_queries.toLocaleString()}
              <span className="text-xs font-normal text-slate-400 ml-1">건</span>
            </p>
            <p className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">최근 대화 분석 포함</p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 break-keep">도구 사용(에이전트) 비율</p>
            <p className="mt-1 text-2xl font-bold tracking-tight text-blue-600 dark:text-blue-400">
              {computedStats.tool_call_rate}%
            </p>
            <p className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">
              {computedStats.tool_call_count}건 도구 활용
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 break-keep">멀티턴 복합 체인</p>
            <p className="mt-1 text-2xl font-bold tracking-tight text-purple-600 dark:text-purple-400">
              {computedStats.multi_turn_count}
              <span className="text-xs font-normal text-slate-400 ml-1">건</span>
            </p>
            <p className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">2단계 이상 연쇄 실행</p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400 break-keep">실행 승인율</p>
            <p className="mt-1 text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400">
              {computedStats.approval_rate}%
            </p>
            <p className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">
              승인 {computedStats.confirmed_count} / 거절 {computedStats.rejected_count}
            </p>
          </div>
        </div>
      )}

      {/* 2. 최다 호출 도구 랭킹 바 */}
      {computedStats && computedStats.top_tools.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-400">
          <span className="font-semibold text-slate-700 dark:text-slate-300 mr-1">🔥 주요 호출 도구:</span>
          {computedStats.top_tools.map((item) => (
            <span
              key={item.tool}
              className="inline-flex items-center gap-1 rounded-md bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700 shadow-2xs border border-slate-200 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200"
            >
              <span>{item.tool}</span>
              <span className="rounded-full bg-blue-100 px-1.5 py-0.2 text-[10px] text-blue-700 dark:bg-blue-900/60 dark:text-blue-300">
                {item.count}
              </span>
            </span>
          ))}
        </div>
      )}

      {/* 3. 메인 로그 테이블 */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                  <th className="px-4 py-3 text-left font-medium">시각</th>
                  <th className="px-4 py-3 text-left font-medium">유저</th>
                  <th className="px-4 py-3 text-left font-medium">질문 원문</th>
                  <th className="px-4 py-3 text-left font-medium">에이전트 도구 체인 (Tool Chain)</th>
                  <th className="px-4 py-3 text-left font-medium">최종 조치</th>
                  <th className="px-4 py-3 text-left font-medium">상태</th>
                  <th className="px-3 py-3 text-center font-medium">상세</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {Array.from({ length: 8 }).map((_, i) => (
                  <TableRowSkeleton key={i} cols={7} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                  <th className="px-4 py-3 text-left font-medium whitespace-nowrap">시각</th>
                  <th className="px-4 py-3 text-left font-medium whitespace-nowrap">유저</th>
                  <th className="px-4 py-3 text-left font-medium min-w-[200px]">질문 원문</th>
                  <th className="px-4 py-3 text-left font-medium min-w-[240px]">에이전트 도구 체인 (Tool Chain)</th>
                  <th className="px-4 py-3 text-left font-medium whitespace-nowrap">최종 조치</th>
                  <th className="px-4 py-3 text-left font-medium whitespace-nowrap">상태</th>
                  <th className="px-3 py-3 text-center font-medium whitespace-nowrap">상세</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {(() => {
                  const pagedRows = rows.slice((page - 1) * pageSize, page * pageSize)
                  if (rows.length === 0) {
                    return (
                      <tr>
                        <td colSpan={7} className="px-4 py-10 text-center text-xs text-slate-400 dark:text-slate-500">
                          기록된 자연어 에이전트 로그가 없습니다.
                        </td>
                      </tr>
                    )
                  }
                  return pagedRows.map((row, i) => {
                    const isExpanded = expandedId === row.id
                    const tools = row.tool_chain || (row.llm_action ? row.llm_action.split(',').map(s => s.trim()) : [])
                    const isMulti = tools.length > 1
                    const hasDetails = (row.tool_trace && row.tool_trace.length > 0) || (row.proposed_actions && row.proposed_actions.length > 0) || Boolean(row.raw_text)

                    return (
                      <Fragment key={row.id}>
                        <tr
                          onClick={() => toggleExpand(row.id)}
                          className={`cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40 ${
                            isExpanded ? 'bg-slate-50/80 dark:bg-slate-800/60' : ''
                          }`}
                          style={staggerDelay(i)}
                        >
                          <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-500 dark:text-slate-400">
                            {row.logged_at_fmt}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-600 dark:text-slate-400">
                            {row.user_id ? String(row.user_id).slice(-6) : '—'}
                          </td>
                          <td className="px-4 py-3 text-xs text-slate-800 dark:text-slate-200 font-medium break-keep">
                            {row.raw_text}
                          </td>
                          <td className="px-4 py-3 text-xs">
                            {tools.length > 0 && row.llm_action !== 'chat' && row.llm_action !== 'unmatched' ? (
                              <div className="flex flex-wrap items-center gap-1.5">
                                {tools.map((t, idx) => {
                                  const isWrite = t.startsWith('propose_')
                                  return (
                                    <span key={idx} className="inline-flex items-center gap-1">
                                      <span
                                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium border ${
                                          isWrite
                                            ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800/50'
                                            : 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800/50'
                                        }`}
                                      >
                                        {t}
                                      </span>
                                      {idx < tools.length - 1 && (
                                        <span className="text-[10px] text-slate-400 dark:text-slate-600 font-bold">➔</span>
                                      )}
                                    </span>
                                  )
                                })}
                                {isMulti && (
                                  <span className="rounded-full bg-purple-100 px-1.5 py-0.2 text-[9px] font-semibold text-purple-700 dark:bg-purple-950/50 dark:text-purple-300">
                                    멀티턴
                                  </span>
                                )}
                              </div>
                            ) : row.preprocessed ? (
                              <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                                ⚡ 패스트트랙 ({row.preprocessed})
                              </span>
                            ) : (
                              <span className="text-xs text-slate-400">일반 대화</span>
                            )}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-xs font-semibold text-slate-700 dark:text-slate-300">
                            {row.final_action ?? '—'}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {row.confirm_status ? <Badge value={row.confirm_status} /> : '—'}
                          </td>
                          <td className="px-3 py-3 text-center whitespace-nowrap">
                            <button
                              type="button"
                              className="text-xs font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                            >
                              {isExpanded ? '닫기 ▲' : (hasDetails ? '상세 ▼' : '보기 ▼')}
                            </button>
                          </td>
                        </tr>

                        {/* 확장된 상세 정보 서브 패널 */}
                        {isExpanded && (
                          <tr className="bg-slate-50/50 dark:bg-slate-800/30">
                            <td colSpan={7} className="px-6 py-4">
                              <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-xs dark:border-slate-700 dark:bg-slate-900">
                                <div>
                                  <p className="font-semibold text-slate-600 dark:text-slate-400 mb-1">💬 사용자 발화 원문:</p>
                                  <p className="rounded bg-slate-50 p-2 font-medium text-slate-800 dark:bg-slate-800 dark:text-slate-200">
                                    {row.raw_text}
                                  </p>
                                </div>

                                {row.tool_trace && row.tool_trace.length > 0 && (
                                  <div>
                                    <p className="font-semibold text-slate-600 dark:text-slate-400 mb-1">🛠️ 에이전트 단계별 도구 실행 내역 (Tool Trace):</p>
                                    <div className="space-y-1.5">
                                      {row.tool_trace.map((item, idx) => (
                                        <div key={idx} className="rounded border border-slate-100 bg-slate-50 p-2 text-[11px] dark:border-slate-800 dark:bg-slate-800/60">
                                          <div className="flex items-center justify-between text-blue-600 dark:text-blue-400 font-bold mb-1">
                                            <span>Step {item.step || idx + 1}: {item.tool}</span>
                                          </div>
                                          {item.args && Object.keys(item.args).length > 0 && (
                                            <div className="text-slate-600 dark:text-slate-400">
                                              <span className="font-semibold">Args:</span> {JSON.stringify(item.args)}
                                            </div>
                                          )}
                                          {item.result && (
                                            <div className="text-slate-500 dark:text-slate-400 truncate mt-0.5">
                                              <span className="font-semibold">Result:</span> {JSON.stringify(item.result)}
                                            </div>
                                          )}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {row.proposed_actions && row.proposed_actions.length > 0 && (
                                  <div>
                                    <p className="font-semibold text-amber-600 dark:text-amber-400 mb-1">📋 사용자 승인 제안 작업 (Proposed Actions):</p>
                                    <div className="rounded border border-amber-100 bg-amber-50/50 p-2 text-[11px] text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
                                      {row.proposed_actions.map((act, idx) => (
                                        <div key={idx} className="py-0.5">
                                          #{idx + 1}: {JSON.stringify(act)}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-100 dark:border-slate-800">
                                  <span>Log ID: {row.id}</span>
                                  <span>유저 ID: {row.user_id || '알 수 없음'}</span>
                                  <span>승인 상태: {row.confirm_status || '미지정'}</span>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })
                })()}
              </tbody>
            </table>
          </div>
        )}

        {/* 4. 자연어 로그 페이징 */}
        {!loading && rows.length > 0 && (
          <Pagination
            currentPage={page}
            totalPages={Math.max(1, Math.ceil(rows.length / pageSize))}
            pageSize={pageSize}
            totalCount={rows.length}
            onPageChange={setPage}
            onPageSizeChange={(sz) => {
              setPageSize(sz)
              setPage(1)
            }}
            pageSizeOptions={[10, 20, 50, 100]}
          />
        )}
      </div>

      <p className="text-right text-xs text-slate-400 dark:text-slate-600">
        총 {total.toLocaleString()}건 기록됨 (최근 200건 분석 기준)
      </p>
    </div>
  )
}
