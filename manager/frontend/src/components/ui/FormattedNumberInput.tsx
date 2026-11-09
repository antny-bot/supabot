import React from 'react'

interface FormattedNumberInputProps {
  value: number
  onChange: (val: number) => void
  min?: number
  step?: number
  placeholder?: string
  className?: string
  quickAmounts?: number[]
  unitLabel?: string
  disabled?: boolean
}

function toKoreanWords(num: number): string {
  if (!num || num <= 0) return '0원'
  const eok = Math.floor(num / 100000000)
  const man = Math.floor((num % 100000000) / 10000)
  const won = num % 10000

  const parts = []
  if (eok > 0) parts.push(`${eok.toLocaleString()}억`)
  if (man > 0) parts.push(`${man.toLocaleString()}만`)
  if (won > 0) parts.push(`${won.toLocaleString()}`)
  return `${parts.join(' ')}원`
}

export default function FormattedNumberInput({
  value,
  onChange,
  min = 0,
  step = 10000,
  placeholder = '0',
  className = '',
  quickAmounts = [100000, 300000, 500000, 1000000],
  unitLabel = 'KRW',
  disabled = false,
}: FormattedNumberInputProps) {
  const displayVal = value ? value.toLocaleString() : ''

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value.replace(/[^0-9]/g, '')
    const num = raw ? parseInt(raw, 10) : 0
    onChange(num)
  }

  const handleQuickAdd = (amt: number) => {
    onChange((value || 0) + amt)
  }

  return (
    <div className="space-y-1.5">
      <div className="relative">
        <input
          type="text"
          inputMode="numeric"
          disabled={disabled}
          value={displayVal}
          onChange={handleInputChange}
          placeholder={placeholder}
          className={`w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2.5 text-sm font-bold text-slate-900 dark:text-white focus:outline-hidden focus:ring-2 focus:ring-indigo-500 pr-14 ${className}`}
        />
        <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-xs font-semibold text-slate-400">
          {unitLabel}
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-slate-500">
        <span className="font-medium text-[11px] text-indigo-600 dark:text-indigo-400">
          {value > 0 ? `≈ ${toKoreanWords(value)}` : '금액을 입력하세요'}
        </span>
        {quickAmounts && quickAmounts.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {quickAmounts.map((amt) => (
              <button
                key={amt}
                type="button"
                disabled={disabled}
                onClick={() => handleQuickAdd(amt)}
                className="rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 px-2 py-0.5 text-[10px] font-semibold text-slate-700 dark:text-slate-300 transition-colors"
              >
                +{amt >= 10000 ? `${(amt / 10000).toLocaleString()}만` : `${amt.toLocaleString()}`}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
