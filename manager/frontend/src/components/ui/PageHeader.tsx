import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  subtitle: string
  Icon: LucideIcon
  actions?: ReactNode
}

export default function PageHeader({ title, subtitle, Icon, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div className="flex items-start gap-3">
        <div className="rounded-2xl bg-primary-50 p-3 text-primary-600 shadow-sm dark:bg-primary-900/30 dark:text-primary-400">
          <Icon size={20} />
        </div>
        <div className="space-y-1">
          <h1 className="text-app-title font-bold text-slate-900 dark:text-white">{title}</h1>
          <p className="text-app-body-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
        </div>
      </div>

      {actions ? <div className="md:shrink-0">{actions}</div> : null}
    </div>
  )
}
