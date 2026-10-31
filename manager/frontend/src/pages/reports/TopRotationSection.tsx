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

  const params = report?.template?.params || {}
  const nextTarget = params.next_target_ticker
  const cycleNo = params.cycle_no || 1
  const carryover = params.carryover_budget || 0
  const monthlySpent = params.monthly_spent || 0
  const monthlyBudget = params.monthly_budget || report?.template?.budget || 3000000
  const lastStatus = params.last_status_message || '정상 대기 중'

  return (
    <div className="space-y-4">
      {/* 템플릿 선택 및 상단 컨트롤 바 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="flex items-center gap-2">
          <Layers size={18} className="text-indigo-600 dark:text-indigo-400" />
          <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">대상 전략 템플릿:</span>
          <select
            value={selectedTemplateId || ''}
            onChange={(e) => setSelectedTemplateId(Number(e.target.value))}
            className="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-1.5 text-sm font-medium text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                #{t.id} {t.name} ({t.exchange.toUpperCase()})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 dark:text-slate-400">배치(#Group) 필터:</span>
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

      {/* 핵심 상태 KPI 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className={CARD}>
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

        <div className={CARD}>
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

        <div className={CARD}>
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

        <div className={CARD}>
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
      <div className={CARD}>
        <div className="flex items-center justify-between mb-3">
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
      <div className={CARD}>
        <div className="flex items-center gap-2 mb-3">
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
