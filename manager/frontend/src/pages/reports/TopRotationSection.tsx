import { useEffect, useState } from 'react'
import { RotateCw, TrendingUp, DollarSign, Clock, Layers, ArrowUpRight, ArrowDownRight, CheckCircle2 } from 'lucide-react'
import { fetchTemplates, type Template } from '../../api/templates'
import { fetchTopRotationReport, type TopRotationReport } from '../../api/reports'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { krwFmt, CARD, TH, TD } from './ReportsShared'

export default function TopRotationSection() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [report, setReport] = useState<TopRotationReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedGroupNo, setSelectedGroupNo] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [exchangeFilter, setExchangeFilter] = useState<string>('all')

  useEffect(() => {
    fetchTemplates()
      .then((tpls) => {
        const topTpls = tpls.filter((t) => t.strategy_type === 'kospi_top_dca' || t.name.includes('TOP'))
        setTemplates(topTpls)
        if (topTpls.length > 0) {
          setSelectedTemplateId(topTpls[0].id)
        } else if (tpls.length > 0) {
          setSelectedTemplateId(tpls[0].id)
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : '템플릿 목록 로드 실패'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedTemplateId) return
    setLoading(true)
    setError(null)
    fetchTopRotationReport(selectedTemplateId, selectedGroupNo)
      .then(setReport)
      .catch((e) => setError(e instanceof Error ? e.message : '리포트 데이터 로드 실패'))
      .finally(() => setLoading(false))
  }, [selectedTemplateId, selectedGroupNo])

  if (loading && !report) return <Spinner />
  if (error) return <ErrorBanner message={error} />

  const filteredTemplates = templates.filter((t) => {
    if (exchangeFilter !== 'all' && t.exchange.toLowerCase() !== exchangeFilter.toLowerCase()) {
      return false
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase()
      const matchName = t.name.toLowerCase().includes(q)
      const matchId = String(t.id).includes(q)
      const matchEx = t.exchange.toLowerCase().includes(q)
      return matchName || matchId || matchEx
    }
    return true
  })

  const params = report?.template?.params || {}
  const nextTarget = params.next_target_ticker
  const cycleNo = params.cycle_no || 1
  const carryover = params.carryover_budget || 0
  const monthlySpent = params.monthly_spent || 0
  const monthlyBudget = params.monthly_budget || report?.template?.budget || 3000000
  const lastStatus = params.last_status_message || '정상 대기 중'

  return (
    <div className="space-y-4">
      {/* 템플릿 선택 및 상단 컨트롤 바 (검색 / 거래소 필터 탑재) */}
      <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm space-y-3">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          {/* 전략 선택, 거래소 필터, 검색 인풋 */}
          <div className="flex flex-1 flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5 font-semibold text-sm text-slate-700 dark:text-slate-200">
              <Layers size={18} className="text-indigo-600 dark:text-indigo-400" />
              <span>전략:</span>
            </div>

            {/* 거래소 필터 칩 */}
            <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-700/60 p-0.5 rounded-lg text-xs">
              {['all', 'toss', 'kis', 'upbit', 'bithumb'].map((ex) => (
                <button
                  key={ex}
                  onClick={() => setExchangeFilter(ex)}
                  className={`px-2 py-0.5 rounded-md font-medium transition-colors ${
                    exchangeFilter === ex
                      ? 'bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm'
                      : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                  }`}
                >
                  {ex === 'all' ? '전체' : ex.toUpperCase()}
                </button>
              ))}
            </div>

            {/* 빠른 검색 인풋 */}
            <div className="relative">
              <input
                type="text"
                placeholder="전략명/#ID 검색..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-32 sm:w-40 pl-2.5 pr-6 py-1 text-xs rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs"
                >
                  ✕
                </button>
              )}
            </div>

            {/* 템플릿 드롭다운 */}
            <select
              value={selectedTemplateId || ''}
              onChange={(e) => setSelectedTemplateId(Number(e.target.value))}
              className="max-w-[220px] sm:max-w-[300px] truncate rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-1 text-xs sm:text-sm font-medium text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {filteredTemplates.length === 0 ? (
                <option value="" disabled>검색 결과 없음</option>
              ) : (
                filteredTemplates.map((t) => (
                  <option key={t.id} value={t.id}>
                    #{t.id} {t.name} [{t.exchange.toUpperCase()}]
                  </option>
                ))
              )}
            </select>
            <span className="text-[11px] text-slate-400">
              ({filteredTemplates.length}/{templates.length}개)
            </span>
          </div>

          {/* 우측 배치 필터 및 새로고침 */}
          <div className="flex items-center gap-2 self-end lg:self-auto">
            <span className="text-xs text-slate-500 dark:text-slate-400">배치 필터:</span>
            <select
              value={selectedGroupNo === null ? '' : selectedGroupNo}
              onChange={(e) => setSelectedGroupNo(e.target.value === '' ? null : Number(e.target.value))}
              className="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-2 py-1 text-xs text-slate-700 dark:text-slate-200"
            >
              <option value="">전체 배치</option>
              {(params.history || []).map((h: any) => (
                <option key={h.group_no} value={h.group_no}>
                  Batch #{h.group_no} ({h.date})
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                if (selectedTemplateId) {
                  setLoading(true)
                  fetchTopRotationReport(selectedTemplateId, selectedGroupNo)
                    .then(setReport)
                    .finally(() => setLoading(false))
                }
              }}
              className="flex items-center gap-1 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 px-2.5 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200"
            >
              <RotateCw size={13} />
              새로고침
            </button>
          </div>
        </div>
      </div>

      {/* 핵심 상태 KPI 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs">
            <span>이월 잔여 가용 예산</span>
            <DollarSign size={15} className="text-emerald-500" />
          </div>
          <div className="mt-2 text-xl font-bold text-slate-800 dark:text-slate-100">
            {krwFmt(carryover)}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            당월 누적 소진: {krwFmt(monthlySpent)} / 월 {krwFmt(monthlyBudget)}
          </div>
        </div>

        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs">
            <span>현재 회전 사이클</span>
            <RotateCw size={15} className="text-indigo-500" />
          </div>
          <div className="mt-2 text-xl font-bold text-slate-800 dark:text-slate-100">
            Cycle #{cycleNo}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            사이클 매수 완료: {(params.current_cycle_bought || []).length}개 종목
          </div>
        </div>

        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs">
            <span>다음 매수 차례 (Head-of-Line)</span>
            <Clock size={15} className="text-amber-500" />
          </div>
          <div className="mt-2 text-base font-bold text-slate-800 dark:text-slate-100 truncate">
            {nextTarget ? `${nextTarget.rank}위 ${nextTarget.name}` : '전 종목 완료 / 대기'}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            {nextTarget ? `부족액: ${krwFmt(nextTarget.shortfall || 0)} (필요 ${krwFmt(nextTarget.required_krw || 0)})` : '다음 사이클 준비'}
          </div>
        </div>

        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs">
            <span>전략 운용 상태</span>
            <CheckCircle2 size={15} className="text-blue-500" />
          </div>
          <div className="mt-2 text-base font-bold text-slate-800 dark:text-slate-100">
            {params.strategy_status === 'active' ? '🟢 가동중 (Active)' : '⏸️ 일시보류 (Holding)'}
          </div>
          <div className="mt-1 text-[11px] text-slate-400 truncate" title={lastStatus}>
            {lastStatus}
          </div>
        </div>
      </div>

      {/* 보유 및 이탈 관리 종목 테이블 */}
      <div className={`${CARD} overflow-hidden`}>
        <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp size={16} className="text-indigo-600 dark:text-indigo-400" />
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">
              전략 전용 포지션 및 이탈 분할매도 현황
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            관리 종목: {(report?.holdings_status || []).length}개
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/60">
                <th className={TH}>종목명 (코드)</th>
                <th className={TH}>순위</th>
                <th className={TH}>관리 상태</th>
                <th className={`${TH} text-right`}>보유수량</th>
                <th className={`${TH} text-right`}>평균단가</th>
                <th className={`${TH} text-right`}>현재가</th>
                <th className={`${TH} text-right`}>평가금액</th>
                <th className={`${TH} text-right`}>평가손익 (수익률)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {(report?.holdings_status || []).length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-slate-400">
                    현재 전략으로 보유 중인 포지션이 없습니다. (배치 실행 대기)
                  </td>
                </tr>
              ) : (
                report?.holdings_status.map((item, idx) => {
                  const isUp = item.pnl >= 0
                  return (
                    <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                      <td className={`${TD} font-semibold text-slate-800 dark:text-slate-200`}>
                        {item.name} <span className="text-slate-400 font-normal">({item.ticker})</span>
                      </td>
                      <td className={TD}>{item.rank}</td>
                      <td className={TD}>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${
                          item.status_code === 'exiting'
                            ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
                            : item.status_code === 'holding_top'
                            ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
                            : 'bg-slate-100 text-slate-800 dark:bg-slate-700 dark:text-slate-300'
                        }`}>
                          {item.status_badge}
                        </span>
                      </td>
                      <td className={`${TD} text-right font-mono`}>{item.qty}주</td>
                      <td className={`${TD} text-right font-mono`}>{krwFmt(item.avg_price)}</td>
                      <td className={`${TD} text-right font-mono`}>{krwFmt(item.current_price)}</td>
                      <td className={`${TD} text-right font-mono font-semibold`}>{krwFmt(item.eval_value)}</td>
                      <td className={`${TD} text-right font-mono ${isUp ? 'text-red-500' : 'text-blue-500'}`}>
                        <div className="flex items-center justify-end gap-1">
                          {isUp ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
                          <span>{krwFmt(item.pnl)} ({item.pnl_pct > 0 ? `+${item.pnl_pct}` : item.pnl_pct}%)</span>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 최근 배치별 예산 흐름 타임라인 */}
      <div className={`${CARD} overflow-hidden`}>
        <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
          <Clock size={16} className="text-indigo-600 dark:text-indigo-400" />
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">
            배치별 예산 소진 및 실행 타임라인
          </h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/60">
                <th className={TH}>영업일자</th>
                <th className={TH}>배치</th>
                <th className={TH}>회차</th>
                <th className={`${TH} text-right`}>전일 이월금</th>
                <th className={`${TH} text-right`}>당일 충전액</th>
                <th className={`${TH} text-right`}>당일 집행액</th>
                <th className={`${TH} text-right`}>익일 이월금</th>
                <th className={TH}>실행 요약</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {(report?.batch_budget_logs || []).length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-slate-400">
                    배치 실행 이력이 없습니다.
                  </td>
                </tr>
              ) : (
                report?.batch_budget_logs.slice().reverse().map((b: any, idx: number) => (
                  <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                    <td className={`${TD} font-mono`}>{b.date}</td>
                    <td className={`${TD} font-semibold`}>#{b.group_no}</td>
                    <td className={TD}>Cycle #{b.cycle_no}</td>
                    <td className={`${TD} text-right font-mono text-slate-500`}>{krwFmt(b.prev_carryover || 0)}</td>
                    <td className={`${TD} text-right font-mono text-emerald-600 dark:text-emerald-400 font-semibold`}>
                      +{krwFmt(b.daily_allowance || 0)}
                    </td>
                    <td className={`${TD} text-right font-mono text-red-600 dark:text-red-400`}>
                      -{krwFmt(b.spent_today || 0)}
                    </td>
                    <td className={`${TD} text-right font-mono font-semibold`}>{krwFmt(b.end_carryover || 0)}</td>
                    <td className={`${TD} text-slate-600 dark:text-slate-300 max-w-xs truncate`} title={b.status_summary}>
                      {b.status_summary}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
