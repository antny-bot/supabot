import { useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

interface AdvancedSectionProps {
  /** 접힌 상태에서 보이는 제목 (기본: "고급 설정") */
  title?: string
  /** 접힌 상태에서 현재 값 요약을 보여준다 (기본값 사용 여부 확인용) */
  summary?: string
  defaultOpen?: boolean
  children: ReactNode
}

/**
 * 고급 설정 아코디언. 기본 접힘 + 현재 값 요약 표시.
 * 입력 요소는 접혀 있어도 DOM에 유지되므로 폼 상태/검증에 영향을 주지 않는다.
 * 애니메이션은 DESIGN.md의 grid-template 전환(0fr → 1fr) 규칙을 따른다.
 */
export default function AdvancedSection({
  title = '고급 설정',
  summary,
  defaultOpen = false,
  children,
}: AdvancedSectionProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 rounded-xl px-3.5 py-2.5 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
      >
        <span className="min-w-0">
          <span className="block whitespace-nowrap break-keep text-app-body-sm font-semibold text-slate-700 dark:text-slate-200">
            {title}
          </span>
          {summary ? (
            <span className="mt-0.5 block truncate text-app-caption text-slate-400">{summary}</span>
          ) : null}
        </span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-slate-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      <div
        className={`grid transition-[grid-template-rows] duration-200 ease-out ${
          open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
        }`}
      >
        <div className="overflow-hidden">
          <div className="space-y-4 border-t border-slate-100 p-3.5 dark:border-slate-800">{children}</div>
        </div>
      </div>
    </div>
  )
}
