import { Check, Monitor, Palette, RotateCcw, Type } from 'lucide-react'
import {
  DISPLAY_ACCENT_OPTIONS,
  DISPLAY_FONT_OPTIONS,
  type DisplayPreferences,
  resetDisplayPreferences,
  saveDisplayPreferences,
} from '../../lib/displayPreferences'

interface DisplaySettingsCardProps {
  preferences: DisplayPreferences
  onChange: (preferences: DisplayPreferences) => void
}

export default function DisplaySettingsCard({
  preferences,
  onChange,
}: DisplaySettingsCardProps) {
  function update(next: Partial<DisplayPreferences>) {
    onChange(saveDisplayPreferences(next))
  }

  function handleReset() {
    onChange(resetDisplayPreferences())
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-4 flex items-start gap-3">
        <div className="rounded-lg bg-primary-50 p-2.5 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400">
          <Monitor size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-app-body font-semibold text-slate-900 dark:text-slate-100">표시</h2>
              <p className="mt-1 text-app-caption text-slate-500 dark:text-slate-400">
                관리자 전체 화면의 글꼴과 글자 크기를 조절합니다.
              </p>
            </div>
            <button
              type="button"
              onClick={handleReset}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-app-caption font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            >
              <RotateCcw size={14} />
              기본값
            </button>
          </div>
        </div>
      </div>

      <div className="space-y-5">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-app-label font-semibold text-slate-800 dark:text-slate-200">
            <Type size={16} />
            글꼴
          </div>
          <div className="flex flex-wrap gap-2">
            {DISPLAY_FONT_OPTIONS.map((option) => {
              const active = preferences.fontFamily === option.value
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => update({ fontFamily: option.value })}
                  className={`rounded-lg border px-3.5 py-2 text-app-body-sm font-medium transition-colors ${
                    active
                      ? 'border-primary-600 bg-primary-50 text-primary-700 dark:border-primary-400 dark:bg-primary-900/30 dark:text-primary-300'
                      : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-slate-100'
                  }`}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-2 text-app-label font-semibold text-slate-800 dark:text-slate-200">
            <Palette size={16} />
            강조 색상
          </div>
          <div className="flex flex-wrap gap-2">
            {DISPLAY_ACCENT_OPTIONS.map((option) => {
              const active = preferences.accentColor === option.value
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => update({ accentColor: option.value })}
                  aria-label={option.label}
                  className={`flex h-9 w-9 items-center justify-center rounded-full border-2 transition-colors ${
                    active
                      ? 'border-slate-900 dark:border-slate-100'
                      : 'border-transparent hover:border-slate-300 dark:hover:border-slate-600'
                  }`}
                >
                  <span
                    className="flex h-7 w-7 items-center justify-center rounded-full"
                    style={{ backgroundColor: option.swatch }}
                  >
                    {active && <Check size={14} className="text-white" />}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <label
              htmlFor="displayFontSize"
              className="text-app-label font-semibold text-slate-800 dark:text-slate-200"
            >
              글자 크기
            </label>
            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-app-caption font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
              {preferences.fontSizePx}px
            </span>
          </div>
          <input
            id="displayFontSize"
            type="range"
            min={12}
            max={22}
            step={1}
            value={preferences.fontSizePx}
            onChange={(e) => update({ fontSizePx: Number(e.target.value) })}
            className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-primary-600 dark:bg-slate-700 dark:accent-primary-400"
          />
          <div className="flex justify-between text-app-caption text-slate-400 dark:text-slate-500">
            <span>12px</span>
            <span>22px</span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
          <p className="text-app-caption font-medium text-slate-500 dark:text-slate-400">미리보기</p>
          <p className="mt-2 text-app-body text-slate-800 dark:text-slate-100">
            주문 현황, 거래 내역, 관리자 설정 화면의 본문 크기가 이렇게 표시됩니다.
          </p>
          <p className="mt-2 text-app-label text-slate-500 dark:text-slate-400">
            숫자 컬럼의 고정폭 글꼴은 유지되고, 전체 위계만 함께 조절됩니다.
          </p>
        </div>
      </div>
    </section>
  )
}
