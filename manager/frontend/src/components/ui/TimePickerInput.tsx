import React, { useRef, useId } from 'react'
import { Clock } from 'lucide-react'
import { normalizeTimeInput, isValidTimeInput } from '../strategy/strategyTypes'

export interface TimePickerInputProps {
  value: string
  onChange: (val: string) => void
  placeholder?: string
  className?: string
  disabled?: boolean
  required?: boolean
  presets?: Array<{ label: string; time: string }>
  'aria-label'?: string
}

const DEFAULT_PRESETS: Array<{ label: string; time: string }> = [
  { label: '09:05 (장시작 직후)', time: '09:05' },
  { label: '09:10', time: '09:10' },
  { label: '09:30', time: '09:30' },
  { label: '14:30 (오후 매수)', time: '14:30' },
  { label: '15:00 (장마감 전)', time: '15:00' },
]

function formatKoreanTime(timeStr: string): string | null {
  const norm = normalizeTimeInput(timeStr)
  if (!isValidTimeInput(norm)) return null
  const [hStr, mStr] = norm.split(':')
  const h = parseInt(hStr, 10)
  const m = parseInt(mStr, 10)
  const period = h >= 12 ? '오후' : '오전'
  const displayHour = h % 12 === 0 ? 12 : h % 12
  return `${period} ${String(displayHour).padStart(2, '0')}:${String(m).padStart(2, '0')} KST`
}

export default function TimePickerInput({
  value,
  onChange,
  placeholder = '09:05',
  className = '',
  disabled = false,
  required = false,
  presets = DEFAULT_PRESETS,
  'aria-label': ariaLabel = '실행 시각 (HH:MM)',
}: TimePickerInputProps) {
  const nativePickerRef = useRef<HTMLInputElement>(null)
  const pickerId = useId()

  const normalized = normalizeTimeInput(value)
  const hasValue = Boolean(value && value.trim())
  const isInvalid = hasValue && !isValidTimeInput(normalized)
  const timeDesc = formatKoreanTime(value)

  const handleBlur = () => {
    if (!value) return
    const autoCorrected = normalizeTimeInput(value)
    if (isValidTimeInput(autoCorrected) && autoCorrected !== value) {
      onChange(autoCorrected)
    }
  }

  const handleNativePickerChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.value) {
      onChange(e.target.value)
    }
  }

  const openNativePicker = () => {
    if (disabled || !nativePickerRef.current) return
    const el = nativePickerRef.current
    try {
      if (typeof (el as any).showPicker === 'function') {
        (el as any).showPicker()
      } else {
        el.focus()
        el.click()
      }
    } catch {
      el.focus()
    }
  }

  return (
    <div className="space-y-1.5">
      <div className="relative">
        <input
          type="text"
          aria-label={ariaLabel}
          disabled={disabled}
          required={required}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={handleBlur}
          placeholder={placeholder}
          className={`w-full rounded-xl border bg-white dark:bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-900 dark:text-white focus:outline-hidden focus:ring-2 focus:ring-indigo-500 pr-10 transition-colors ${
            isInvalid
              ? 'border-rose-400 dark:border-rose-500 bg-rose-50/30 dark:bg-rose-950/20 text-rose-700 dark:text-rose-300'
              : 'border-slate-200 dark:border-slate-700'
          } ${className}`}
        />

        {/* 숨겨진 네이티브 시간 피커 및 시계 아이콘 트리거 */}
        <input
          ref={nativePickerRef}
          type="time"
          id={pickerId}
          tabIndex={-1}
          disabled={disabled}
          value={isValidTimeInput(normalized) ? normalized : ''}
          onChange={handleNativePickerChange}
          className="sr-only"
          aria-hidden="true"
        />

        <button
          type="button"
          disabled={disabled}
          onClick={openNativePicker}
          title="시간 선택기 열기"
          aria-label="시간 선택기 열기"
          className="absolute inset-y-0 right-0 flex items-center pr-2.5 text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors cursor-pointer disabled:cursor-not-allowed"
        >
          <Clock size={15} />
        </button>
      </div>

      {/* 상태 안내 및 퀵 프리셋 버튼 */}
      <div className="flex flex-wrap items-center justify-between gap-1.5 text-[11px]">
        <div>
          {isInvalid ? (
            <span className="font-semibold text-rose-500 dark:text-rose-400 flex items-center gap-1">
              ⚠️ HH:MM 형식(00:00~23:59)으로 입력하세요 (예: 14:30, 09:05)
            </span>
          ) : timeDesc ? (
            <span className="text-indigo-600 dark:text-indigo-400 font-medium">
              ≈ {timeDesc}
            </span>
          ) : (
            <span className="text-slate-400 dark:text-slate-500">
              HH:MM 형식 또는 숫자 4자리(예: 1430) 입력
            </span>
          )}
        </div>

        {presets && presets.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {presets.map((preset) => {
              const isSelected = normalized === preset.time
              return (
                <button
                  key={preset.time}
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange(preset.time)}
                  className={`rounded-lg px-2 py-0.5 text-[10px] font-semibold transition-colors cursor-pointer ${
                    isSelected
                      ? 'bg-indigo-600 text-white shadow-2xs dark:bg-indigo-500'
                      : 'bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300'
                  }`}
                >
                  {preset.label}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
