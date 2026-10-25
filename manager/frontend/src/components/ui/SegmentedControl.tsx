import type { ReactNode } from 'react'

export interface SegmentOption<T extends string = string> {
  id: T
  label: string
  icon?: ReactNode
  badge?: string | number
}

interface SegmentedControlProps<T extends string = string> {
  options: SegmentOption<T>[]
  value: T
  onChange: (value: T) => void
  size?: 'sm' | 'md'
  className?: string
}

export default function SegmentedControl<T extends string = string>({
  options,
  value,
  onChange,
  size = 'md',
  className = '',
}: SegmentedControlProps<T>) {
  const py = size === 'sm' ? 'py-1' : 'py-1.5'
  const text = size === 'sm' ? 'text-xs' : 'text-xs sm:text-sm'

  return (
    <div
      className={`inline-flex items-center rounded-xl bg-slate-100 p-1 dark:bg-slate-800/80 ${className}`}
      role="tablist"
    >
      {options.map((option) => {
        const active = option.id === value
        return (
          <button
            key={option.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(option.id)}
            className={`flex items-center justify-center gap-1.5 rounded-lg px-3 ${py} ${text} font-medium transition-all duration-150 ${
              active
                ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-900 dark:text-white'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            {option.icon && <span className="shrink-0">{option.icon}</span>}
            <span>{option.label}</span>
            {option.badge !== undefined && (
              <span
                className={`ml-1 rounded-full px-1.5 py-0.2 text-[10px] font-bold ${
                  active
                    ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
                    : 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300'
                }`}
              >
                {option.badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
