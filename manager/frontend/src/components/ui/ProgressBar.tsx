interface ProgressBarProps {
  value: number
  color?: string
  className?: string
  showLabel?: boolean
}

export default function ProgressBar({
  value,
  color,
  className = '',
  showLabel = true,
}: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, value))
  const barColor =
    color ||
    (pct >= 100 ? 'bg-emerald-500' :
     pct >= 50  ? 'bg-primary-500' :
                  'bg-amber-500')

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="flex-1 bg-slate-200 dark:bg-slate-700 rounded-full h-2 overflow-hidden">
        <div
          className={`${barColor} h-full rounded-full transition-all duration-300`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className="w-10 shrink-0 text-right text-app-caption font-mono font-medium text-slate-600 dark:text-slate-300">
          {pct}%
        </span>
      )}
    </div>
  )
}
