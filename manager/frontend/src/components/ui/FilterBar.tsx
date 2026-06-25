import { ChevronRight } from 'lucide-react'

interface Option {
  value: string
  label: string
}

interface FilterBarProps {
  label?: string
  options: Option[]
  value: string
  onChange: (v: string) => void
  collapsible?: boolean
  isOpen?: boolean
  onToggle?: () => void
  className?: string
  disabled?: boolean
}

export default function FilterBar({
  label,
  options,
  value,
  onChange,
  collapsible = false,
  isOpen = false,
  onToggle,
  className = '',
  disabled = false,
}: FilterBarProps) {
  const btnClass = (active: boolean) =>
    `px-3 py-1.5 rounded-lg text-app-caption font-medium transition-colors ${
      active
        ? 'bg-primary-600 text-white shadow-sm'
        : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700'
    }`

  if (!collapsible) {
    return (
      <div className={`flex flex-wrap gap-1.5 ${className}`}>
        {options.map((opt) => (
          <button key={opt.value} onClick={() => onChange(opt.value)} className={btnClass(value === opt.value)}>
            {opt.label}
          </button>
        ))}
      </div>
    )
  }

  const selected = options.find((o) => o.value === value) ?? options[0]
  const summaryLabel = label ? `${label}: ${selected.label}` : selected.label
  const isActive = value !== ''

  return (
    <div className={`flex items-center transition-all duration-200 ${disabled ? 'opacity-40 pointer-events-none' : ''} ${className}`}>
      <button
        onClick={onToggle}
        disabled={disabled}
        className={`inline-flex shrink-0 items-center gap-1.5 ${btnClass(isActive)}`}
      >
        {summaryLabel}
        <ChevronRight
          size={12}
          className={`transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      <div
        className={`grid transition-all duration-200 ease-in-out ${
          isOpen ? 'grid-cols-[1fr] opacity-100 ml-1.5' : 'grid-cols-[0fr] opacity-0 ml-0'
        }`}
      >
        <div className="overflow-hidden min-w-0">
          <div className="flex flex-nowrap items-center gap-1.5 p-0.5">
            {options.map((opt) => (
              <button
                key={opt.value}
                onClick={() => {
                  onChange(opt.value)
                  onToggle?.()
                }}
                className={`whitespace-nowrap ${btnClass(value === opt.value)}`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
