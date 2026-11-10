import { useEffect, useState, useCallback } from 'react'
import {
  RotateCw,
  TrendingUp,
  DollarSign,
  Activity,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { fetchStrategyDetail, type StrategyDetailReport } from '../../api/reports'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { krwFmt, pctFmt, pctColor, CARD, TH, TD } from './ReportsShared'

interface SingleStrategySectionProps {
  templateId: number
}

export default function SingleStrategySection({ templateId }: SingleStrategySectionProps) {
  const [data, setData] = useState<StrategyDetailReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [historyTab, setHistoryTab] = useState<'orders' | 'trades'>('orders')
  const [showRules, setShowRules] = useState(false)
  const [showHistory, setShowHistory] = useState(true)

  const loadData = useCallback(async () => {
    if (!templateId) return
    try {
      setLoading(true)
      setError(null)
      const res = await fetchStrategyDetail(templateId)
      setData(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : '전략 상세 정보 로드 실패')
    } finally {
      setLoading(false)
    }
  }, [templateId])

  useEffect(() => {
    loadData()
  }, [loadData])

  if (loading && !data) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    )
  }

  if (error && !data) {
    return <ErrorBanner message={error} />
  }

  if (!data) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-xs text-slate-400 dark:border-slate-700">
        전략 상세 정보를 불러올 수 없습니다.
      </div>
    )
  }

  const { template, ticker, holding, orders, trades } = data
  const params = template.params || {}
  const stype = template.strategy_type || 'grid'
  const isRsi = stype === 'rsitrade' || stype === 'rsi'
  const isGrid = stype === 'grid' || stype === 'sgrid'
  const isDca = stype === 'dca' || stype === 'sdca'

  return (
    <div className="space-y-4 break-keep animate-fade-in">
      {error && <ErrorBanner message={error} />}

      {/* [1] 핵심 포지션 및 손익 지표 카드 그리드 (필수 표시) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>보유 수량 / 원금</span>
            <Layers size={15} className="text-indigo-500" />
          </div>
          <div className="mt-1.5 text-lg sm:text-xl font-bold text-slate-800 dark:text-slate-100">
            {holding.qty > 0 ? `${holding.qty.toLocaleString()} ${ticker}` : '0 (미보유)'}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            원금: {krwFmt(holding.total_cost)}원
          </div>
        </div>

        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>평균단가 / 현재가</span>
            <TrendingUp size={15} className="text-emerald-500" />
          </div>
          <div className="mt-1.5 text-lg sm:text-xl font-bold text-slate-800 dark:text-slate-100">
            {holding.avg_price > 0 ? `${krwFmt(holding.avg_price)}원` : '—'}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            현재가: {holding.current_price > 0 ? `${krwFmt(holding.current_price)}원` : '조회 중'}
          </div>
        </div>

        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>평가 손익 (수익률)</span>
            {holding.pnl >= 0 ? (
              <ArrowUpRight size={15} className="text-rose-500" />
            ) : (
              <ArrowDownRight size={15} className="text-blue-500" />
            )}
          </div>
          <div className={`mt-1.5 text-lg sm:text-xl font-bold ${pctColor(holding.pnl)}`}>
            {holding.total_cost > 0 ? `${holding.pnl >= 0 ? '+' : ''}${krwFmt(holding.pnl)}원` : '0원'}
          </div>
          <div className={`mt-1 text-[11px] font-bold ${pctColor(holding.pnl_pct)}`}>
            수익률: {holding.total_cost > 0 ? pctFmt(holding.pnl_pct) : '0.00%'}
          </div>
        </div>

        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>
              {isDca && params.amount_type === 'volume'
                ? '정기 매수 설정'
                : stype === 'sgrid'
                ? '총 매도 수량'
                : '가용 예산 / 플랜'}
            </span>
            <DollarSign size={15} className="text-amber-500" />
          </div>
          <div className="mt-1.5 text-lg sm:text-xl font-bold text-slate-800 dark:text-slate-100">
            {isDca && params.amount_type === 'volume'
              ? `${params.schedule || '매일'} ${template.budget}주씩`
              : stype === 'sgrid'
              ? `${template.budget.toLocaleString()}주`
              : `${krwFmt(params.carryover_budget ?? template.budget)}원`}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            {isDca && params.amount_type === 'volume' ? (
              `총 ${template.count > 0 ? `${template.count}회` : '무기한'} 예정`
            ) : stype === 'sgrid' ? (
              `진행률: ${template.budget > 0 ? `${((holding.qty / template.budget) * 100).toFixed(1)}%` : '0%'}`
            ) : (
              `총예산 ${krwFmt(params.monthly_budget ?? template.budget)}원 · 소진 ${krwFmt(params.monthly_spent ?? holding.total_cost)}원`
            )}
          </div>
        </div>
      </div>

      {/* [2] 전략 운용 규칙 및 조건 설정 (아코디언으로 기본 접힘 처리) */}
      <div className={`${CARD} overflow-hidden`}>
        <button
          type="button"
          onClick={() => setShowRules((v) => !v)}
          className="flex w-full items-center justify-between p-4 text-xs font-bold text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800/50 transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <Activity size={14} className="text-indigo-600 dark:text-indigo-400" />
            <span>전략 세부 운용 규칙 및 파라미터 조건</span>
          </span>
          <span className="inline-flex items-center gap-1 text-slate-400 font-normal">
            <span>{showRules ? '접기' : '펼쳐보기'}</span>
            {showRules ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </span>
        </button>

        {showRules && (
          <div className="border-t border-slate-100 dark:border-slate-800 p-4 pt-3">
            {isRsi && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <span className="text-[11px] text-slate-400 block">RSI 매수 조건</span>
                  <p className="mt-1 font-bold text-sm text-emerald-600 dark:text-emerald-400">
                    RSI {params.buy_rsi_range || '25-30'} 이하 진입
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <span className="text-[11px] text-slate-400 block">RSI 매도 조건</span>
                  <p className="mt-1 font-bold text-sm text-rose-600 dark:text-rose-400">
                    RSI {params.sell_rsi_range || '65-75'} 이상 청산
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <span className="text-[11px] text-slate-400 block">DCA 가중치 설정</span>
                  <p className="mt-1 font-bold text-sm text-slate-800 dark:text-slate-200">
                    {params.weighted ? '가중 매수 (RSI 하락 시 증액)' : '균등 분할 매수'}
                  </p>
                </div>
              </div>
            )}

            {isGrid && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <span className="text-[11px] text-slate-400 block">거미줄 가격 범위</span>
                  <p className="mt-1 font-bold text-sm text-slate-800 dark:text-slate-200">
                    {template.start_price ? `${template.start_price.toLocaleString()}원` : '—'} ~{' '}
                    {template.end_price ? `${template.end_price.toLocaleString()}원` : '—'}
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <span className="text-[11px] text-slate-400 block">분할 그리드 수</span>
                  <p className="mt-1 font-bold text-sm text-indigo-600 dark:text-indigo-400">
                    총 {template.count}개 분할 구간 (구간당 약{' '}
                    {template.count > 0 ? krwFmt(Math.round(template.budget / template.count)) : '0'}
                    원)
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <span className="text-[11px] text-slate-400 block">주문 유형</span>
                  <p className="mt-1 font-bold text-sm text-slate-800 dark:text-slate-200">
                    {stype === 'sgrid' ? '거미줄 분할 매도' : '거미줄 분할 매수'}
                  </p>
                </div>
              </div>
            )}

            {isDca && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <span className="text-[11px] text-slate-400 block">정기 실행 주기</span>
                  <p className="mt-1 font-bold text-sm text-indigo-600 dark:text-indigo-400">
                    {params.schedule || '매일'} · {params.exec_time || '09:05'} KST
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <span className="text-[11px] text-slate-400 block">1회 주문 규모</span>
                  <p className="mt-1 font-bold text-sm text-slate-800 dark:text-slate-200">
                    {params.amount_type === 'volume'
                      ? `${template.budget} 수량`
                      : `${krwFmt(template.budget)}원`}
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                  <span className="text-[11px] text-slate-400 block">반복 횟수</span>
                  <p className="mt-1 font-bold text-sm text-slate-800 dark:text-slate-200">
                    {template.count > 0 ? `총 ${template.count}회 분할` : '무기한 반복 실행'}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* [3] 최근 주문 및 체결 내역 (접기/펼치기 가능) */}
      <div className={`${CARD} overflow-hidden`}>
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                setHistoryTab('orders')
                setShowHistory(true)
              }}
              className={`text-xs font-bold transition-colors pb-1 border-b-2 ${
                historyTab === 'orders'
                  ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                  : 'border-transparent text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
              }`}
            >
              최근 주문 ({orders.length}건)
            </button>
            <button
              type="button"
              onClick={() => {
                setHistoryTab('trades')
                setShowHistory(true)
              }}
              className={`text-xs font-bold transition-colors pb-1 border-b-2 ${
                historyTab === 'trades'
                  ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                  : 'border-transparent text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
              }`}
            >
              체결 기록 ({trades.length}건)
            </button>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={loadData}
              disabled={loading}
              className="flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <RotateCw size={11} className={loading ? 'animate-spin' : ''} />
              <span>새로고침</span>
            </button>
            <button
              type="button"
              onClick={() => setShowHistory((v) => !v)}
              className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              <span>{showHistory ? '접기' : '펼치기'}</span>
              {showHistory ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>
        </div>

        {showHistory && (
          <div className="p-4">
            {historyTab === 'orders' ? (
              orders.length === 0 ? (
                <div className="py-6 text-center text-xs text-slate-400">
                  해당 전략으로 접수된 주문 내역이 없습니다.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-100 text-slate-400 dark:border-slate-800">
                        <th className={TH}>주문시각</th>
                        <th className={TH}>구분</th>
                        <th className={TH}>주문가격</th>
                        <th className={TH}>주문수량</th>
                        <th className={TH}>체결수량</th>
                        <th className={TH}>상태</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                      {orders.map((o, idx) => (
                        <tr
                          key={o.uuid || idx}
                          className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40"
                        >
                          <td className={`${TD} text-slate-500`}>{o.created_fmt || o.created_at}</td>
                          <td className={TD}>
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                o.side === 'bid'
                                  ? 'bg-rose-50 text-rose-600 dark:bg-rose-950 dark:text-rose-400'
                                  : 'bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400'
                              }`}
                            >
                              {o.side === 'bid' ? '매수' : '매도'}
                            </span>
                          </td>
                          <td className={`${TD} font-medium text-slate-800 dark:text-slate-200`}>
                            {o.price ? `${Number(o.price).toLocaleString()}원` : '시장가'}
                          </td>
                          <td className={`${TD} text-slate-700 dark:text-slate-300`}>
                            {Number(o.volume).toLocaleString()}
                          </td>
                          <td className={`${TD} text-slate-700 dark:text-slate-300`}>
                            {Number(o.filled_volume || 0).toLocaleString()}
                          </td>
                          <td className={TD}>
                            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                              {o.status || '대기'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            ) : trades.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-400">
                해당 전략으로 체결된 거래 내역이 없습니다.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-100 text-slate-400 dark:border-slate-800">
                      <th className={TH}>체결시각</th>
                      <th className={TH}>구분</th>
                      <th className={TH}>체결단가</th>
                      <th className={TH}>체결수량</th>
                      <th className={TH}>체결금액</th>
                      <th className={TH}>수수료</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {trades.map((tr, idx) => {
                      const p = Number(tr.price || 0)
                      const v = Number(tr.volume || 0)
                      return (
                        <tr
                          key={tr.id || idx}
                          className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40"
                        >
                          <td className={`${TD} text-slate-500`}>{tr.executed_fmt || tr.executed_at}</td>
                          <td className={TD}>
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                tr.side === 'bid'
                                  ? 'bg-rose-50 text-rose-600 dark:bg-rose-950 dark:text-rose-400'
                                  : 'bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400'
                              }`}
                            >
                              {tr.side === 'bid' ? '매수' : '매도'}
                            </span>
                          </td>
                          <td className={`${TD} font-medium text-slate-800 dark:text-slate-200`}>
                            {p.toLocaleString()}원
                          </td>
                          <td className={`${TD} text-slate-700 dark:text-slate-300`}>
                            {v.toLocaleString()}
                          </td>
                          <td className={`${TD} font-bold text-slate-800 dark:text-slate-200`}>
                            {krwFmt(Math.round(p * v))}원
                          </td>
                          <td className={`${TD} text-slate-400 text-[11px]`}>
                            {tr.fee_amount ? `${Number(tr.fee_amount).toLocaleString()}원` : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
