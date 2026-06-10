interface ProgressBarProps {
  value: number
  className?: string
}

export default function ProgressBar({ value, className = '' }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, value))
  const color =
    pct >= 100 ? 'bg-emerald-500' :
    pct >= 50  ? 'bg-primary-500' :
                 'bg-amber-500'
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="flex-1 bg-slate-200 dark:bg-slate-700 rounded-full h-1.5 overflow-hidden">
        <div
          className={`${color} h-full rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-9 shrink-0 text-right text-app-caption text-slate-500 dark:text-slate-400">
        {pct}%
      </span>
    </div>
  )
}
