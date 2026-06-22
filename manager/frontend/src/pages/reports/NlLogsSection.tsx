import { useEffect, useState } from 'react'
import { fetchReportNlLogs } from '../../api/reports'
import type { NlLogRow } from '../../types'
import Badge from '../../components/ui/Badge'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay } from '../../utils/animation'
import { CARD, TH, TD } from './ReportsShared'

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

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />

  return (
    <div className={`${CARD} overflow-hidden`}>
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">NL 로그</h3>
        <p className="text-xs text-slate-400 mt-0.5">
          총 {total.toLocaleString()}건 (최근 200건 표시) — 미처리 자연어 익명 로그
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
              <th className={`${TH} text-left`}>시각</th>
              <th className={`${TH} text-left`}>유저</th>
              <th className={`${TH} text-left`}>원문</th>
              <th className={`${TH} text-left`}>전처리</th>
              <th className={`${TH} text-left`}>LLM 액션</th>
              <th className={`${TH} text-left`}>최종 액션</th>
              <th className={`${TH} text-left`}>상태</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-400 text-xs">데이터 없음</td></tr>
            ) : rows.map((row, i) => (
              <tr key={row.id} className="animate-fade-in hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" style={staggerDelay(i)}>
                <td className={`${TD} whitespace-nowrap font-mono text-xs text-slate-500`}>{row.logged_at_fmt}</td>
                <td className={`${TD} whitespace-nowrap text-xs text-slate-500`}>{row.user_id ?? '—'}</td>
                <td className={`${TD} max-w-[200px] truncate text-xs text-slate-800 dark:text-slate-200`} title={row.raw_text}>{row.raw_text}</td>
                <td className={`${TD} max-w-[180px] truncate text-xs text-slate-500 dark:text-slate-400`} title={row.preprocessed ?? ''}>{row.preprocessed ?? '—'}</td>
                <td className={`${TD} whitespace-nowrap text-xs text-slate-600 dark:text-slate-400`}>{row.llm_action ?? '—'}</td>
                <td className={`${TD} whitespace-nowrap text-xs font-medium text-slate-800 dark:text-slate-200`}>{row.final_action ?? '—'}</td>
                <td className={`${TD} whitespace-nowrap`}>{row.confirm_status ? <Badge value={row.confirm_status} /> : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
