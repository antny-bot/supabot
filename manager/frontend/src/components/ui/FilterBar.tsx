import { ChevronDown } from 'lucide-react'

interface Option {
  value: string
  label: string
}

interface FilterBarProps {
  options: Option[]
  value: string
  onChange: (v: string) => void
  collapsible?: boolean
  isOpen?: boolean
  onToggle?: () => void
  className?: string
}

export default function FilterBar({
  options,
  value,
  onChange,
  collapsible = false,
  isOpen = false,
  onToggle,
  className = '',
}: FilterBarProps) {
  const btnClass = (active: boolean) =>
    `px-3 py-1.5 rounded-lg text-app-caption font-medium transition-colors ${
      active
        ? 'bg-indigo-600 text-white shadow-sm'
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

  return (
    <div className={className}>
      <button
        onClick={onToggle}
        className={`inline-flex items-center gap-1 ${btnClass(value !== '')}`}
      >
        {selected.label}
        <ChevronDown
          size={12}
          className={`transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      <div
        className={`grid transition-all duration-200 ease-in-out ${
          isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
        }`}
      >
        <div className="overflow-hidden min-h-0">
          <div className="flex flex-wrap gap-1.5 pt-2">
            {options.map((opt) => (
              <button
                key={opt.value}
                onClick={() => {
                  onChange(opt.value)
                  onToggle?.()
                }}
                className={btnClass(value === opt.value)}
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
