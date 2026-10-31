import DonutChart from '../../components/ui/DonutChart'
import { useEffect, useState } from 'react'
import { PieChart as PieIcon, Layers, Download } from 'lucide-react'
import { fetchReportAllocation } from '../../api/reports'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import type { AllocationReport } from '../../types'
import { krwFmt } from '../../utils/formatters'
import { exportToCsv } from '../../utils/csv'

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#06b6d4', '#3b82f6']

export default function AllocationSection() {
  const [data, setData] = useState<AllocationReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchReportAllocation()
      .then((res) => {
        setData(res)
        setError(null)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '자산 배분 데이터 조회 실패'))
      .finally(() => setLoading(false))
  }, [])

  if (loading && !data) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data || data.asset_count === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-xs text-slate-400 dark:border-slate-800 dark:bg-slate-900">
        현재 보유 중인 자산이 없습니다.
      </div>
    )
  }

  const handleExport = () => {
    if (!data) return
    const exportRows = [
      ...data.by_category.map((c) => ({ type: '자산군', name: c.name, value: c.value, pct: `${c.pct}%` })),
      ...data.by_exchange.map((e) => ({ type: '거래소', name: e.name, value: e.value, pct: `${e.pct}%` })),
    ]
    exportToCsv(
      'asset_allocation',
      [
        { label: '구분', key: 'type' },
        { label: '항목명', key: 'name' },
        { label: '평가금액(KRW)', key: 'value', format: (v) => krwFmt(v) },
        { label: '비중', key: 'pct' },
      ],
      exportRows,
    )
  }

  return (
    <div className="space-y-6">
      {/* 상단 요약 & CSV 내보내기 */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-white dark:bg-slate-900 p-4 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div>
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">포트폴리오 자산 배분</h3>
          <p className="mt-0.5 text-app-caption text-slate-400">
            총 평가자산: <strong className="text-slate-900 dark:text-white font-bold">{krwFmt(data.total_value)}</strong> (총 {data.asset_count}개 종목)
          </p>
        </div>
        <button
          onClick={handleExport}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-lg transition-colors"
        >
          <Download size={14} />
          <span>CSV 내보내기</span>
        </button>
      </div>

      {/* 2열 도넛 차트 (자산군별 & 거래소별) */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* 자산군별 비중 */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
            <h4 className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
              <Layers size={14} /> 자산군별 비중
            </h4>
          </div>

          <div className="mt-4 h-64 w-full">
            <DonutChart
              data={data.by_category}
              colors={COLORS}
              innerRadius={50}
              outerRadius={75}
              paddingAngle={3}
              tooltipFormatter={(val: number) => [`${krwFmt(val)}`, '평가금액']}
            />
          </div>

          <div className="mt-4 divide-y divide-slate-100 dark:divide-slate-800 border-t border-slate-100 dark:border-slate-800">
            {data.by_category.map((cat, idx) => (
              <div key={cat.name} className="flex items-center justify-between py-2 text-xs">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                  />
                  <span className="font-medium text-slate-700 dark:text-slate-200">{cat.name}</span>
                </div>
                <div className="flex items-center gap-3 font-mono">
                  <span className="text-slate-600 dark:text-slate-400">{krwFmt(cat.value)}</span>
                  <span className="font-bold text-slate-900 dark:text-white w-12 text-right">{cat.pct}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 거래소별 비중 */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
            <h4 className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
              <PieIcon size={14} /> 거래소별 비중
            </h4>
          </div>

          <div className="mt-4 h-64 w-full">
            <DonutChart
              data={data.by_exchange}
              colors={COLORS.map((_, i) => COLORS[(i + 2) % COLORS.length])}
              innerRadius={50}
              outerRadius={75}
              paddingAngle={3}
              tooltipFormatter={(val: number) => [`${krwFmt(val)}`, '평가금액']}
            />
          </div>

          <div className="mt-4 divide-y divide-slate-100 dark:divide-slate-800 border-t border-slate-100 dark:border-slate-800">
            {data.by_exchange.map((exch, idx) => (
              <div key={exch.name} className="flex items-center justify-between py-2 text-xs">
                <div className="flex items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: COLORS[(idx + 2) % COLORS.length] }}
                  />
                  <span className="font-medium text-slate-700 dark:text-slate-200">{exch.name}</span>
                </div>
                <div className="flex items-center gap-3 font-mono">
                  <span className="text-slate-600 dark:text-slate-400">{krwFmt(exch.value)}</span>
                  <span className="font-bold text-slate-900 dark:text-white w-12 text-right">{exch.pct}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
