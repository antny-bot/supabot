import { useEffect, useState } from 'react'
import { fetchReportNlLogs } from '../../api/reports'
import type { NlLogRow } from '../../types'
import Badge from '../../components/ui/Badge'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay } from '../../utils/animation'

export default function NlLogsSection() {
  const [rows, setRows] = useState<NlLogRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportNlLogs(200)
      .then((data) => { setRows(data.rows); setTotal(data.total) })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [])

  if (error) return <ErrorBanner message={error} />

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading ? (
          <Spinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                  <th className="px-4 py-3 text-left font-medium">시각</th>
                  <th className="px-4 py-3 text-left font-medium">유저</th>
                  <th className="px-4 py-3 text-left font-medium">원문</th>
                  <th className="px-4 py-3 text-left font-medium">전처리</th>
                  <th className="px-4 py-3 text-left font-medium">LLM 액션</th>
                  <th className="px-4 py-3 text-left font-medium">최종 액션</th>
                  <th className="px-4 py-3 text-left font-medium">상태</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-10 text-center text-xs text-slate-400 dark:text-slate-500">
                      데이터 없습니다.
                    </td>
                  </tr>
                ) : rows.map((row, i) => (
                  <tr key={row.id} className="animate-fade-in transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40" style={staggerDelay(i)}>
                    <td className="px-4 py-2.5 whitespace-nowrap font-mono text-xs text-slate-500 dark:text-slate-400">{row.logged_at_fmt}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-xs text-slate-500 dark:text-slate-400">{row.user_id ?? '—'}</td>
                    <td className="px-4 py-2.5 max-w-[200px] truncate text-xs text-slate-800 dark:text-slate-200" title={row.raw_text}>{row.raw_text}</td>
                    <td className="px-4 py-2.5 max-w-[180px] truncate text-xs text-slate-500 dark:text-slate-400" title={row.preprocessed ?? ''}>{row.preprocessed ?? '—'}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-xs text-slate-600 dark:text-slate-400">{row.llm_action ?? '—'}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-xs font-medium text-slate-800 dark:text-slate-200">{row.final_action ?? '—'}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap">{row.confirm_status ? <Badge value={row.confirm_status} /> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-right text-xs text-slate-400 dark:text-slate-600">
        총 {total.toLocaleString()}건 (최근 200건 표시)
      </p>
    </div>
  )
}
