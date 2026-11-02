import { useEffect, useState, useCallback } from 'react'
import {
  RotateCw,
  TrendingUp,
  DollarSign,
  Activity,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react'
import { fetchStrategyDetail, type StrategyDetailReport } from '../../api/reports'
import Badge from '../../components/ui/Badge'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { krwFmt, pctFmt, pctColor, CARD, TH, TD } from './ReportsShared'

interface SingleStrategySectionProps {
  templateId: number
}

const STRATEGY_TYPE_LABELS: Record<string, string> = {
  grid: '거미줄 분할 매수 (GRID)',
  sgrid: '거미줄 분할 매도 (SGRID)',
  rsitrade: 'RSI 순환 매매',
  rsi: 'RSI 순환 매매',
  dca: '정기 적립식 매수 (DCA)',
  sdca: '정기 분할 매도 (SDCA)',
}

export default function SingleStrategySection({ templateId }: SingleStrategySectionProps) {
  const [data, setData] = useState<StrategyDetailReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [historyTab, setHistoryTab] = useState<'orders' | 'trades'>('orders')

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

  const { template, ticker, name, exchange, holding, orders, trades } = data
  const params = template.params || {}
  const stype = template.strategy_type || 'grid'
  const isRsi = stype === 'rsitrade' || stype === 'rsi'
  const isGrid = stype === 'grid' || stype === 'sgrid'
  const isDca = stype === 'dca' || stype === 'sdca'

  return (
    <div className="space-y-5 break-keep animate-fade-in">
      {/* 상단 전략 정보 바 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2.5 flex-wrap">
          <Badge value={exchange} label={exchange.toUpperCase()} />
          <span className="text-base font-extrabold text-slate-900 dark:text-white">
            {name} ({ticker})
          </span>
          <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-bold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
            {STRATEGY_TYPE_LABELS[stype] || stype.toUpperCase()}
          </span>
          <span className="text-xs font-mono text-slate-400">#{template.id}</span>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
          >
            <RotateCw size={13} className={loading ? 'animate-spin' : ''} />
            <span>새로고침</span>
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      {/* [1] 핵심 포지션 및 손익 지표 카드 그리드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* 보유 수량 및 투자 원금 */}
        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>보유 수량 / 투자 원금</span>
            <Layers size={15} className="text-indigo-500" />
          </div>
          <div className="mt-2 text-xl font-bold font-mono text-slate-800 dark:text-slate-100">
            {holding.qty > 0 ? `${holding.qty.toLocaleString()} ${ticker}` : '0 (미보유)'}
          </div>
          <div className="mt-1 text-[11px] text-slate-400 font-mono">
            원금: {krwFmt(holding.total_cost)}원
          </div>
        </div>

        {/* 평균 매입가 vs 현재가 */}
        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>평균 매입단가 / 현재가</span>
            <TrendingUp size={15} className="text-emerald-500" />
          </div>
          <div className="mt-2 text-xl font-bold font-mono text-slate-800 dark:text-slate-100">
            {holding.avg_price > 0 ? `${krwFmt(holding.avg_price)}원` : '—'}
          </div>
          <div className="mt-1 text-[11px] text-slate-400 font-mono">
            현재가: {holding.current_price > 0 ? `${krwFmt(holding.current_price)}원` : '조회 중'}
          </div>
        </div>

        {/* 평가 손익 & 수익률 */}
        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>평가 손익 (수익률)</span>
            {holding.pnl >= 0 ? (
              <ArrowUpRight size={15} className="text-rose-500" />
            ) : (
              <ArrowDownRight size={15} className="text-blue-500" />
            )}
          </div>
          <div className={`mt-2 text-xl font-bold font-mono ${pctColor(holding.pnl)}`}>
            {holding.total_cost > 0 ? `${holding.pnl >= 0 ? '+' : ''}${krwFmt(holding.pnl)}원` : '0원'}
          </div>
          <div className={`mt-1 text-[11px] font-bold font-mono ${pctColor(holding.pnl_pct)}`}>
            수익률: {holding.total_cost > 0 ? pctFmt(holding.pnl_pct) : '0.00%'}
          </div>
        </div>

        {/* 전략 설정 총예산 */}
        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>전략 설정 예산</span>
            <DollarSign size={15} className="text-amber-500" />
          </div>
          <div className="mt-2 text-xl font-bold font-mono text-slate-800 dark:text-slate-100">
            {krwFmt(template.budget)}원
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            소진율: {template.budget > 0 ? `${((holding.total_cost / template.budget) * 100).toFixed(1)}%` : '0%'}
          </div>
        </div>
      </div>

      {/* [2] 전략별 특화 파라미터 및 로직 상세 카드 */}
      <div className={`${CARD} p-5 space-y-3`}>
        <h4 className="text-xs font-bold text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
          <Activity size={14} className="text-indigo-600 dark:text-indigo-400" />
          <span>전략 운용 규칙 및 조건 설정</span>
        </h4>

        {isRsi && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
            <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
              <span className="text-[11px] text-slate-400 block">RSI 매수 조건</span>
              <p className="mt-1 font-mono font-bold text-sm text-emerald-600 dark:text-emerald-400">
                RSI {params.buy_rsi_range || '25-30'} 이하 진입
              </p>
              <span className="text-[10px] text-slate-400 mt-0.5 block">과매도 구간에서 분할 매수</span>
            </div>
            <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
              <span className="text-[11px] text-slate-400 block">RSI 매도 조건</span>
              <p className="mt-1 font-mono font-bold text-sm text-rose-600 dark:text-rose-400">
                RSI {params.sell_rsi_range || '65-75'} 이상 청산
              </p>
              <span className="text-[10px] text-slate-400 mt-0.5 block">과매수 구간에서 익절 분할매도</span>
            </div>
            <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
              <span className="text-[11px] text-slate-400 block">DCA 가중치 설정</span>
              <p className="mt-1 font-mono font-bold text-sm text-slate-800 dark:text-slate-200">
                {params.weighted ? '가중 매수 (RSI 하락 시 증액)' : '균등 분할 매수'}
              </p>
              <span className="text-[10px] text-slate-400 mt-0.5 block">시그널 발생 시 자동 집행</span>
            </div>
          </div>
        )}

        {isGrid && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
            <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
              <span className="text-[11px] text-slate-400 block">거미줄 가격 범위</span>
              <p className="mt-1 font-mono font-bold text-sm text-slate-800 dark:text-slate-200">
                {template.start_price ? `${template.start_price.toLocaleString()}원` : '—'} ~{' '}
                {template.end_price ? `${template.end_price.toLocaleString()}원` : '—'}
              </p>
              <span className="text-[10px] text-slate-400 mt-0.5 block">설정된 밴드 내에서 분할 주문</span>
            </div>
            <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
              <span className="text-[11px] text-slate-400 block">분할 그리드 수</span>
              <p className="mt-1 font-mono font-bold text-sm text-indigo-600 dark:text-indigo-400">
                총 {template.count}개 분할 구간
              </p>
              <span className="text-[10px] text-slate-400 mt-0.5 block">
                구간당 약 {template.count > 0 ? krwFmt(Math.round(template.budget / template.count)) : '0'}원
              </span>
            </div>
            <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
              <span className="text-[11px] text-slate-400 block">주문 유형</span>
              <p className="mt-1 font-mono font-bold text-sm text-slate-800 dark:text-slate-200">
                {stype === 'sgrid' ? '거미줄 분할 매도' : '거미줄 분할 매수'}
              </p>
              <span className="text-[10px] text-slate-400 mt-0.5 block">지정가 호가 스프레드 분할</span>
            </div>
          </div>
        )}

        {isDca && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
            <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
              <span className="text-[11px] text-slate-400 block">정기 실행 주기</span>
              <p className="mt-1 font-mono font-bold text-sm text-indigo-600 dark:text-indigo-400">
                {params.schedule || '매일'} · {params.exec_time || '09:05'} KST
              </p>
              <span className="text-[10px] text-slate-400 mt-0.5 block">지정 시각 자동 주문 집행</span>
            </div>
            <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
              <span className="text-[11px] text-slate-400 block">1회 주문 규모</span>
              <p className="mt-1 font-mono font-bold text-sm text-slate-800 dark:text-slate-200">
                {params.amount_type === 'volume' ? `${template.budget} 수량` : `${krwFmt(template.budget)}원`}
              </p>
              <span className="text-[10px] text-slate-400 mt-0.5 block">정기 분할 집행 단위</span>
            </div>
            <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
              <span className="text-[11px] text-slate-400 block">반복 횟수</span>
              <p className="mt-1 font-mono font-bold text-sm text-slate-800 dark:text-slate-200">
                {template.count > 0 ? `총 ${template.count}회 분할` : '무기한 반복 실행'}
              </p>
              <span className="text-[10px] text-slate-400 mt-0.5 block">적립 완료 시 자동 종료</span>
            </div>
          </div>
        )}
      </div>

      {/* [3] 최근 주문 및 체결 내역 */}
      <div className={`${CARD} p-5 space-y-4`}>
        <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setHistoryTab('orders')}
              className={`text-xs font-bold transition-colors pb-1 border-b-2 ${
                historyTab === 'orders'
                  ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                  : 'border-transparent text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
              }`}
            >
              전략 주문 내역 ({orders.length}건)
            </button>
            <button
              onClick={() => setHistoryTab('trades')}
              className={`text-xs font-bold transition-colors pb-1 border-b-2 ${
                historyTab === 'trades'
                  ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                  : 'border-transparent text-slate-400 hover:text-slate-600 dark:hover:text-slate-200'
              }`}
            >
              체결 기록 ({trades.length}건)
            </button>
          </div>
          <span className="text-[11px] text-slate-400">최근 최대 50건 표시</span>
        </div>

        {historyTab === 'orders' ? (
          orders.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400">
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
                    <tr key={o.uuid || idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40">
                      <td className={`${TD} font-mono text-slate-500`}>{o.created_fmt || o.created_at}</td>
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
                      <td className={`${TD} font-mono font-medium text-slate-800 dark:text-slate-200`}>
                        {o.price ? `${Number(o.price).toLocaleString()}원` : '시장가'}
                      </td>
                      <td className={`${TD} font-mono text-slate-700 dark:text-slate-300`}>
                        {Number(o.volume).toLocaleString()}
                      </td>
                      <td className={`${TD} font-mono text-slate-700 dark:text-slate-300`}>
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
          <div className="py-8 text-center text-xs text-slate-400">
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
                    <tr key={tr.id || idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40">
                      <td className={`${TD} font-mono text-slate-500`}>{tr.executed_fmt || tr.executed_at}</td>
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
                      <td className={`${TD} font-mono font-medium text-slate-800 dark:text-slate-200`}>
                        {p.toLocaleString()}원
                      </td>
                      <td className={`${TD} font-mono text-slate-700 dark:text-slate-300`}>
                        {v.toLocaleString()}
                      </td>
                      <td className={`${TD} font-mono font-bold text-slate-800 dark:text-slate-200`}>
                        {krwFmt(Math.round(p * v))}원
                      </td>
                      <td className={`${TD} font-mono text-slate-400 text-[11px]`}>
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
    </div>
  )
}
