import React, { useRef, useId, useState } from 'react'
import { Clock, TrendingUp, TrendingDown } from 'lucide-react'
import {
  normalizeTimeInput,
  isValidTimeInput,
  BUY_RECOMMENDED_TIME_PRESETS,
  SELL_RECOMMENDED_TIME_PRESETS,
  TradingTimePreset,
} from '../strategy/strategyTypes'

export interface TimePickerPresetItem {
  label: string
  time: string
  description?: string
  rank?: number
}

export interface TimePickerInputProps {
  value: string
  onChange: (val: string) => void
  placeholder?: string
  className?: string
  disabled?: boolean
  required?: boolean
  presets?: TimePickerPresetItem[]
  presetCategory?: 'all' | 'buy' | 'sell' | 'none'
  showTabSelector?: boolean
  'aria-label'?: string
}

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

function isTradingTimePreset(p: TimePickerPresetItem | TradingTimePreset): p is TradingTimePreset {
  return 'timeRange' in p && 'reason' in p
}

export default function TimePickerInput({
  value,
  onChange,
  placeholder = '15:10',
  className = '',
  disabled = false,
  required = false,
  presets,
  presetCategory = 'all',
  showTabSelector = true,
  'aria-label': ariaLabel = '실행 시각 (HH:MM)',
}: TimePickerInputProps) {
  const nativePickerRef = useRef<HTMLInputElement>(null)
  const pickerId = useId()

  const [activeTab, setActiveTab] = useState<'buy' | 'sell'>(
    presetCategory === 'sell' ? 'sell' : 'buy'
  )

  const normalized = normalizeTimeInput(value)
  const hasValue = Boolean(value && value.trim())
  const isInvalid = hasValue && !isValidTimeInput(normalized)
  const timeDesc = formatKoreanTime(value)

  // 매수/매도 추천 시각 정보 매칭
  const matchedBuy = BUY_RECOMMENDED_TIME_PRESETS.find((p) => p.time === normalized)
  const matchedSell = SELL_RECOMMENDED_TIME_PRESETS.find((p) => p.time === normalized)

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

  // 표시할 프리셋 결정
  let displayPresets: Array<TimePickerPresetItem | TradingTimePreset> = []
  if (presets && presets.length > 0) {
    displayPresets = presets
  } else if (presetCategory === 'buy') {
    displayPresets = BUY_RECOMMENDED_TIME_PRESETS
  } else if (presetCategory === 'sell') {
    displayPresets = SELL_RECOMMENDED_TIME_PRESETS
  } else if (presetCategory === 'all') {
    displayPresets = activeTab === 'buy' ? BUY_RECOMMENDED_TIME_PRESETS : SELL_RECOMMENDED_TIME_PRESETS
  }

  const showTabs = !presets && presetCategory === 'all' && showTabSelector

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

      {/* 상태 안내 및 추천 시각 배지 */}
      <div className="flex flex-wrap items-center justify-between gap-1.5 text-[11px]">
        <div>
          {isInvalid ? (
            <span className="font-semibold text-rose-500 dark:text-rose-400 flex items-center gap-1">
              ⚠️ HH:MM 형식(00:00~23:59)으로 입력하세요 (예: 15:10, 09:20)
            </span>
          ) : matchedBuy ? (
            <span className="text-emerald-600 dark:text-emerald-400 font-medium inline-flex items-center gap-1">
              <TrendingUp size={12} className="inline" />
              <span>
                매수 {matchedBuy.rank}순위 추천: {matchedBuy.reason} ({matchedBuy.timeRange})
              </span>
            </span>
          ) : matchedSell ? (
            <span className="text-rose-600 dark:text-rose-400 font-medium inline-flex items-center gap-1">
              <TrendingDown size={12} className="inline" />
              <span>
                매도 {matchedSell.rank}순위 추천: {matchedSell.reason} ({matchedSell.timeRange})
              </span>
            </span>
          ) : timeDesc ? (
            <span className="text-indigo-600 dark:text-indigo-400 font-medium">
              ≈ {timeDesc}
            </span>
          ) : (
            <span className="text-slate-400 dark:text-slate-500">
              HH:MM 형식 또는 숫자 4자리(예: 1510) 입력
            </span>
          )}
        </div>

        {/* 매수/매도 추천 시각 탭 전환 버튼 */}
        {showTabs && (
          <div className="flex items-center rounded-lg bg-slate-100 p-0.5 dark:bg-slate-800">
            <button
              type="button"
              onClick={() => setActiveTab('buy')}
              className={`flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold transition-colors cursor-pointer ${
                activeTab === 'buy'
                  ? 'bg-emerald-500 text-white shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
              }`}
            >
              <TrendingUp size={10} />
              매수 추천
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('sell')}
              className={`flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold transition-colors cursor-pointer ${
                activeTab === 'sell'
                  ? 'bg-rose-500 text-white shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
              }`}
            >
              <TrendingDown size={10} />
              매도 추천
            </button>
          </div>
        )}
      </div>

      {/* 프리셋 버튼 칩 목록 */}
      {displayPresets && displayPresets.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 pt-0.5">
          {displayPresets.map((preset) => {
            const isSelected = normalized === preset.time
            const isBuy = 'type' in preset ? preset.type === 'buy' : activeTab === 'buy'
            const tooltip = isTradingTimePreset(preset)
              ? `${preset.reason} (${preset.timeRange}): ${preset.description}`
              : preset.description || preset.label

            return (
              <button
                key={`${preset.time}-${preset.label}`}
                type="button"
                disabled={disabled}
                onClick={() => onChange(preset.time)}
                title={tooltip}
                className={`rounded-lg px-2 py-0.5 text-[10px] font-semibold transition-colors cursor-pointer flex items-center gap-1 ${
                  isSelected
                    ? isBuy
                      ? 'bg-emerald-600 text-white shadow-2xs dark:bg-emerald-500'
                      : 'bg-rose-600 text-white shadow-2xs dark:bg-rose-500'
                    : 'bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300'
                }`}
              >
                {'rank' in preset && (
                  <span
                    className={`rounded-xs px-1 text-[9px] ${
                      isSelected
                        ? 'bg-black/20 text-white'
                        : isBuy
                        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                        : 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300'
                    }`}
                  >
                    {preset.rank}순위
                  </span>
                )}
                <span>{preset.label}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
