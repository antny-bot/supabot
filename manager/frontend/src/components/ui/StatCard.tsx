import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: number | string
  icon: ReactNode
  iconBg?: string
}

export default function StatCard({ label, value, icon, iconBg = 'bg-indigo-500' }: StatCardProps) {
  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl p-4 shadow-sm border border-slate-200 dark:border-slate-800 flex items-center gap-4">
      <div className={`${iconBg} rounded-lg p-2.5 text-white shrink-0`}>
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 leading-none">
          {typeof value === 'number' ? value.toLocaleString() : value}
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 truncate">{label}</p>
      </div>
    </div>
  )
}
