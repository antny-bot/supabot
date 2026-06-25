import { ChevronRight } from 'lucide-react'

export interface DateRangeValue {
  mode: '1d' | '7d' | '30d' | 'all' | 'custom'
  from: string
  to: string
}

const PRESETS: { value: DateRangeValue['mode']; label: string }[] = [
  { value: '1d', label: '1일' },
  { value: '7d', label: '7일' },
  { value: '30d', label: '30일' },
  { value: 'all', label: '전체 기간' },
  { value: 'custom', label: '직접 선택' },
]

function toDateStr(d: Date) {
  return d.toISOString().slice(0, 10)
}

function getThisMonth() {
  const now = new Date()
  return {
    from: toDateStr(new Date(now.getFullYear(), now.getMonth(), 1)),
    to: toDateStr(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
  }
}

function getLastMonth() {
  const now = new Date()
  return {
    from: toDateStr(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
    to: toDateStr(new Date(now.getFullYear(), now.getMonth(), 0)),
  }
}

function getThisYear() {
  const now = new Date()
  return {
    from: toDateStr(new Date(now.getFullYear(), 0, 1)),
    to: toDateStr(new Date(now.getFullYear(), 11, 31)),
  }
}

function getSummaryLabel(value: DateRangeValue) {
  if (value.mode === 'custom' && value.from && value.to) {
    return `${value.from} ~ ${value.to}`
  }

  return PRESETS.find((preset) => preset.value === value.mode)?.label ?? value.mode
}

interface Props {
  value: DateRangeValue
  onChange: (v: DateRangeValue) => void
  collapsible?: boolean
  isOpen?: boolean
  onToggle?: () => void
  className?: string
  label?: string
  disabled?: boolean
}

export default function DateRangePicker({
  value,
  onChange,
  collapsible = false,
  isOpen = false,
  onToggle,
  className = '',
  label,
  disabled = false,
}: Props) {
  const handlePreset = (mode: DateRangeValue['mode']) => {
    if (mode === 'custom') {
      const today = toDateStr(new Date())
      onChange({ mode: 'custom', from: value.from || today, to: value.to || today })
    } else {
      onChange({ mode, from: '', to: '' })
    }
  }

  const handleQuick = (range: { from: string; to: string }) => {
    onChange({ mode: 'custom', ...range })
  }

  const handleDate = (field: 'from' | 'to', nextValue: string) => {
    onChange({ ...value, [field]: nextValue })
  }

  if (!collapsible) {
    return (
      <div className={`space-y-2 ${className}`}>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((preset) => (
            <button
              key={preset.value}
              onClick={() => handlePreset(preset.value)}
              className={`px-3 py-1.5 rounded-lg text-app-caption font-medium transition-colors ${
                value.mode === preset.value
                  ? 'bg-primary-600 text-white shadow-sm'
                  : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700'
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>

        {value.mode === 'custom' && (
          <div className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/50">
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="date"
                value={value.from}
                onChange={(e) => handleDate('from', e.target.value)}
                className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300"
              />
              <span className="text-xs text-slate-400">~</span>
              <input
                type="date"
                value={value.to}
                onChange={(e) => handleDate('to', e.target.value)}
                className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300"
              />
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="self-center text-[10px] text-slate-400">빠른 선택:</span>
              {[
                { label: '이번 달', fn: getThisMonth },
                { label: '지난달', fn: getLastMonth },
                { label: '올해', fn: getThisYear },
              ].map(({ label: quickLabel, fn }) => (
                <button
                  key={quickLabel}
                  onClick={() => handleQuick(fn())}
                  className="rounded border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-medium text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600"
                >
                  {quickLabel}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  const summaryLabel = label ? `${label}: ${getSummaryLabel(value)}` : getSummaryLabel(value)

  return (
    <div className={`flex items-center transition-all duration-200 ${disabled ? 'opacity-40 pointer-events-none' : ''} ${className}`}>
      <button
        onClick={onToggle}
        disabled={disabled}
        className={`inline-flex shrink-0 items-center gap-1.5 px-3 py-1.5 rounded-lg text-app-caption font-medium transition-colors ${
          value.mode !== 'all'
            ? 'bg-primary-600 text-white shadow-sm'
            : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700'
        }`}
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
          <div className="flex items-center gap-1.5 p-0.5">
            <div className="flex flex-nowrap gap-1.5">
              {PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  onClick={() => {
                    handlePreset(preset.value)
                    if (preset.value !== 'custom') onToggle?.()
                  }}
                  className={`whitespace-nowrap px-3 py-1.5 rounded-lg text-app-caption font-medium transition-colors ${
                    value.mode === preset.value
                      ? 'bg-primary-600 text-white shadow-sm'
                      : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700'
                  }`}
                >
                  {preset.label}
                </button>
              ))}
            </div>

            {value.mode === 'custom' && (
              <div className="flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50/50 p-1 dark:border-slate-700 dark:bg-slate-800/20">
                <input
                  type="date"
                  value={value.from}
                  onChange={(e) => handleDate('from', e.target.value)}
                  className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-xs text-slate-700 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300"
                />
                <span className="text-[10px] text-slate-400">~</span>
                <input
                  type="date"
                  value={value.to}
                  onChange={(e) => handleDate('to', e.target.value)}
                  className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-xs text-slate-700 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300"
                />
                <div className="ml-1 flex gap-1 border-l border-slate-200 pl-1 dark:border-slate-700">
                  {[
                    { label: '이번 달', fn: getThisMonth },
                    { label: '지난달', fn: getLastMonth },
                  ].map(({ label: quickLabel, fn }) => (
                    <button
                      key={quickLabel}
                      onClick={() => handleQuick(fn())}
                      className="whitespace-nowrap rounded px-1 py-0.5 text-[10px] text-slate-500 transition-colors hover:bg-white dark:hover:bg-slate-700"
                    >
                      {quickLabel}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
