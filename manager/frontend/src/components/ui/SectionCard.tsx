import type { ReactNode } from 'react'

interface SectionCardProps {
  title?: string
  subtitle?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
  contentClassName?: string
}

export default function SectionCard({
  title,
  subtitle,
  actions,
  children,
  className = '',
  contentClassName = '',
}: SectionCardProps) {
  const hasHeader = title || subtitle || actions

  return (
    <section className={`overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`.trim()}>
      {hasHeader ? (
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
          <div className="min-w-0">
            {title ? <h2 className="text-app-body font-semibold text-slate-900 dark:text-slate-100">{title}</h2> : null}
            {subtitle ? (
              <p className="mt-1 text-app-caption text-slate-500 dark:text-slate-400">{subtitle}</p>
            ) : null}
          </div>
          {actions ? <div className="shrink-0">{actions}</div> : null}
        </div>
      ) : null}
      <div className={contentClassName}>{children}</div>
    </section>
  )
}
