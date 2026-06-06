import { ChevronRight } from 'lucide-react'

export interface DateRangeValue {
  mode: '1d' | '7d' | '30d' | 'all' | 'custom'
  from: string
  to: string
}

const PRESETS: { value: DateRangeValue['mode']; label: string }[] = [
  { value: '1d',     label: '1일'      },
  { value: '7d',     label: '7일'      },
  { value: '30d',    label: '30일'     },
  { value: 'all',    label: '전체 기간' },
  { value: 'custom', label: '커스텀'   },
]

function toDateStr(d: Date) {
  return d.toISOString().slice(0, 10)
}

function getThisMonth() {
  const now = new Date()
  return {
    from: toDateStr(new Date(now.getFullYear(), now.getMonth(), 1)),
    to:   toDateStr(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
  }
}

function getLastMonth() {
  const now = new Date()
  return {
    from: toDateStr(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
    to:   toDateStr(new Date(now.getFullYear(), now.getMonth(), 0)),
  }
}

function getThisYear() {
  const now = new Date()
  return {
    from: toDateStr(new Date(now.getFullYear(), 0, 1)),
    to:   toDateStr(new Date(now.getFullYear(), 11, 31)),
  }
}

interface Props {
  value: DateRangeValue
  onChange: (v: DateRangeValue) => void
  collapsible?: boolean
  isOpen?: boolean
  onToggle?: () => void
  className?: string
}

export default function DateRangePicker({
  value,
  onChange,
  collapsible = false,
  isOpen = false,
  onToggle,
  className = '',
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

  const handleDate = (field: 'from' | 'to', v: string) => {
    onChange({ ...value, [field]: v })
  }

  if (!collapsible) {
    return (
      <div className={`space-y-2 ${className}`}>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p.value}
              onClick={() => handlePreset(p.value)}
              className={`px-3 py-1.5 rounded-lg text-app-caption font-medium transition-colors ${
                value.mode === p.value
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700'
              }`}
            >
              {p.label}
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
                className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300"
              />
              <span className="text-xs text-slate-400">~</span>
              <input
                type="date"
                value={value.to}
                onChange={(e) => handleDate('to', e.target.value)}
                className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300"
              />
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="text-[10px] text-slate-400 self-center">빠른 선택:</span>
              {[
                { label: '이번달', fn: getThisMonth },
                { label: '지난달', fn: getLastMonth },
                { label: '올해',   fn: getThisYear  },
              ].map(({ label, fn }) => (
                <button
                  key={label}
                  onClick={() => handleQuick(fn())}
                  className="rounded px-2 py-0.5 text-[10px] font-medium border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600 transition-colors"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  const modeLabel = PRESETS.find((p) => p.value === value.mode)?.label ?? value.mode

  return (
    <div className={`flex items-center ${className}`}>
      <button
        onClick={onToggle}
        className={`inline-flex shrink-0 items-center gap-1 px-3 py-1.5 rounded-lg text-app-caption font-medium transition-colors ${
          value.mode !== 'all'
            ? 'bg-indigo-600 text-white shadow-sm'
            : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700'
        }`}
      >
        {modeLabel}
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
          <div className="flex items-center gap-2">
            <div className="flex flex-nowrap gap-1.5">
              {PRESETS.map((p) => (
                <button
                  key={p.value}
                  onClick={() => {
                    handlePreset(p.value)
                    if (p.value !== 'custom') onToggle?.()
                  }}
                  className={`whitespace-nowrap px-3 py-1.5 rounded-lg text-app-caption font-medium transition-colors ${
                    value.mode === p.value
                      ? 'bg-indigo-600 text-white shadow-sm'
                      : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>

            {value.mode === 'custom' && (
              <div className="flex shrink-0 items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-1.5 dark:border-slate-700 dark:bg-slate-800/50">
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
                <div className="flex gap-1 border-l border-slate-200 ml-1 pl-1 dark:border-slate-700">
                  {[
                    { label: '이번달', fn: getThisMonth },
                    { label: '지난달', fn: getLastMonth },
                  ].map(({ label, fn }) => (
                    <button
                      key={label}
                      onClick={() => handleQuick(fn())}
                      className="rounded px-1 py-0.5 text-[10px] text-slate-500 hover:bg-white dark:hover:bg-slate-700 transition-colors whitespace-nowrap"
                    >
                      {label}
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
