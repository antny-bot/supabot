import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'

interface SyncIndicatorProps {
  lastUpdated: Date | null
  loading?: boolean
  error?: string | null
}

export default function SyncIndicator({ lastUpdated, loading, error }: SyncIndicatorProps) {
  const [timeAgo, setTimeAgo] = useState<string>('대기 중')

  useEffect(() => {
    if (!lastUpdated) {
      setTimeAgo('대기 중')
      return
    }

    const updateText = () => {
      const now = new Date()
      const diffMs = now.getTime() - lastUpdated.getTime()
      const diffSec = Math.floor(diffMs / 1000)

      if (diffSec < 5) {
        setTimeAgo('방금 전')
      } else if (diffSec < 60) {
        setTimeAgo(`${diffSec}초 전`)
      } else {
        const diffMin = Math.floor(diffSec / 60)
        setTimeAgo(`${diffMin}분 전`)
      }
    }

    updateText()
    const timer = setInterval(updateText, 5000) // update every 5 seconds
    return () => clearInterval(timer)
  }, [lastUpdated])

  let statusColor = 'bg-slate-300 dark:bg-slate-600'
  let label = '비활성'

  if (error) {
    statusColor = 'bg-red-500 animate-pulse'
    label = '오류'
  } else if (loading) {
    statusColor = 'bg-amber-500 animate-pulse'
    label = '동기화 중'
  } else if (lastUpdated) {
    statusColor = 'bg-emerald-500'
    label = `실시간 동기화됨 (${timeAgo})`
  }

  return (
    <div className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 dark:border-slate-700 dark:bg-slate-800 shadow-sm text-[11px] font-medium text-slate-500 dark:text-slate-400 select-none">
      <span className="relative flex h-2 w-2">
        {loading || lastUpdated ? (
          <span
            className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
              loading ? 'bg-amber-400 animate-ping' : 'bg-emerald-400 animate-ping'
            }`}
          ></span>
        ) : null}
        <span className={`relative inline-flex rounded-full h-2 w-2 ${statusColor}`}></span>
      </span>
      <span>{label}</span>
      {loading && <RefreshCw size={10} className="animate-spin text-slate-400 ml-0.5" />}
    </div>
  )
}
