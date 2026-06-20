import { useEffect, useState } from 'react'
import { fetchReportNlLogs } from '../../api/reports'
import type { NlLogRow } from '../../types'
import Badge from '../../components/ui/Badge'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
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
    <div className="space-y-4">
      <p className="text-xs text-slate-500 dark:text-slate-400">
        총 {total.toLocaleString()}건 (최근 200건 표시) — 미처리 자연어 익명 로그
      </p>
      <div className={`${CARD} overflow-x-auto`}>
        <table className="w-full text-xs">
          <thead className="border-b border-slate-200 dark:border-slate-800 text-left text-slate-500 dark:text-slate-400">
            <tr>
              <th className={TH}>시각</th>
              <th className={TH}>유저</th>
              <th className={TH}>원문</th>
              <th className={TH}>전처리</th>
              <th className={TH}>LLM 액션</th>
              <th className={TH}>최종 액션</th>
              <th className={TH}>상태</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.length === 0 ? (
              <tr><td colSpan={7} className={`${TD} text-center text-slate-400`}>데이터 없음</td></tr>
            ) : rows.map((row) => (
              <tr key={row.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                <td className={`${TD} whitespace-nowrap font-mono text-slate-500`}>{row.logged_at_fmt}</td>
                <td className={`${TD} whitespace-nowrap text-slate-500`}>{row.user_id ?? '—'}</td>
                <td className={`${TD} max-w-[200px] truncate`} title={row.raw_text}>{row.raw_text}</td>
                <td className={`${TD} max-w-[180px] truncate text-slate-500`} title={row.preprocessed ?? ''}>{row.preprocessed ?? '—'}</td>
                <td className={`${TD} whitespace-nowrap`}>{row.llm_action ?? '—'}</td>
                <td className={`${TD} whitespace-nowrap font-medium`}>{row.final_action ?? '—'}</td>
                <td className={`${TD} whitespace-nowrap`}>{row.confirm_status ? <Badge value={row.confirm_status} /> : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
