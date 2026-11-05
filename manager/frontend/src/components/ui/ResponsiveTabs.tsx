import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface ResponsiveTabItem {
  id: string
  label: string
}

interface ResponsiveTabsProps {
  tabs: ResponsiveTabItem[]
  activeTab: string
  onChange: (tabId: string) => void
}

export default function ResponsiveTabs({
  tabs,
  activeTab,
  onChange,
}: ResponsiveTabsProps) {
  const desktopScrollRef = useRef<HTMLDivElement>(null)
  const mobileScrollRef = useRef<HTMLDivElement>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)
  const [isOverflowing, setIsOverflowing] = useState(false)

  // Drag state for desktop
  const isDraggingRef = useRef(false)
  const startXRef = useRef(0)
  const scrollLeftRef = useRef(0)
  const dragDistanceRef = useRef(0)
  const [isMouseDown, setIsMouseDown] = useState(false)

  const checkScroll = useCallback(() => {
    const el = desktopScrollRef.current
    if (!el) return
    const { scrollLeft, scrollWidth, clientWidth } = el
    const hasOverflow = scrollWidth > clientWidth + 2
    setIsOverflowing(hasOverflow)
    setCanScrollLeft(scrollLeft > 4)
    setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 4)
  }, [])

  useEffect(() => {
    checkScroll()
    const el = desktopScrollRef.current
    if (!el) return

    const handleResize = () => checkScroll()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [checkScroll, tabs])

  // Active tab scroll-into-view
  useEffect(() => {
    const el = desktopScrollRef.current
    if (!el) return
    const activeEl = el.querySelector<HTMLElement>(`[data-tab-id="${activeTab}"]`)
    if (activeEl && typeof activeEl.scrollIntoView === 'function') {
      activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
    }
    // Also mobile
    const mEl = mobileScrollRef.current
    if (mEl) {
      const mActiveEl = mEl.querySelector<HTMLElement>(`[data-tab-id="${activeTab}"]`)
      if (mActiveEl && typeof mActiveEl.scrollIntoView === 'function') {
        mActiveEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
      }
    }
  }, [activeTab])

  // Wheel horizontal scrolling on desktop
  const handleWheel = (e: React.WheelEvent) => {
    const el = desktopScrollRef.current
    if (!el || !isOverflowing) return
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
      el.scrollLeft += e.deltaY
      checkScroll()
    }
  }

  // Mouse drag handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0 || !desktopScrollRef.current) return
    isDraggingRef.current = true
    setIsMouseDown(true)
    startXRef.current = e.pageX - desktopScrollRef.current.offsetLeft
    scrollLeftRef.current = desktopScrollRef.current.scrollLeft
    dragDistanceRef.current = 0
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDraggingRef.current || !desktopScrollRef.current) return
    e.preventDefault()
    const x = e.pageX - desktopScrollRef.current.offsetLeft
    const walk = x - startXRef.current
    dragDistanceRef.current = Math.abs(walk)
    desktopScrollRef.current.scrollLeft = scrollLeftRef.current - walk
    checkScroll()
  }

  const handleMouseUp = () => {
    isDraggingRef.current = false
    setIsMouseDown(false)
  }

  const handleTabClick = (tabId: string, e: React.MouseEvent) => {
    // If user dragged more than 5px, treat as scroll, don't trigger click
    if (dragDistanceRef.current > 5) {
      e.preventDefault()
      e.stopPropagation()
      return
    }
    onChange(tabId)
  }

  const scrollBy = (offset: number) => {
    const el = desktopScrollRef.current
    if (!el) return
    if (typeof el.scrollBy === 'function') {
      el.scrollBy({ left: offset, behavior: 'smooth' })
    } else {
      el.scrollLeft += offset
    }
    setTimeout(checkScroll, 300)
  }

  return (
    <div className="relative md:border-b md:border-slate-200 md:dark:border-slate-800 select-none">
      {/* Mobile Tab List */}
      <div
        ref={mobileScrollRef}
        className="flex gap-2 overflow-x-auto pb-2 scrollbar-none snap-x snap-mandatory md:hidden"
        role="tablist"
        aria-orientation="horizontal"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            data-tab-id={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => onChange(tab.id)}
            className={`shrink-0 snap-start whitespace-nowrap break-keep rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-primary-600 text-white'
                : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Desktop Tab List with Dial / Drag UI */}
      <div className="hidden md:flex items-center relative group">
        {/* Left Dial / Scroll Button */}
        {isOverflowing && (
          <button
            type="button"
            onClick={() => scrollBy(-240)}
            disabled={!canScrollLeft}
            aria-label="왼쪽 탭으로 이동"
            className={`shrink-0 p-1 mr-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white/95 dark:bg-slate-800/95 text-slate-600 dark:text-slate-300 shadow-sm transition-all hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-20 disabled:pointer-events-none z-10 ${
              canScrollLeft ? 'opacity-100' : 'opacity-0 pointer-events-none'
            }`}
          >
            <ChevronLeft size={16} />
          </button>
        )}

        {/* Scrollable / Draggable Area */}
        <div
          ref={desktopScrollRef}
          onScroll={checkScroll}
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          role="tablist"
          aria-orientation="horizontal"
          className={`flex-1 flex gap-1.5 pb-0 overflow-x-auto scrollbar-none scroll-smooth ${
            isOverflowing ? (isMouseDown ? 'cursor-grabbing' : 'cursor-grab') : ''
          }`}
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              data-tab-id={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={(e) => handleTabClick(tab.id, e)}
              className={`-mb-px shrink-0 whitespace-nowrap break-keep rounded-t-lg border-b-2 px-3.5 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'border-primary-600 text-primary-600 dark:border-primary-400 dark:text-primary-400'
                  : 'border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Right Dial / Scroll Button */}
        {isOverflowing && (
          <button
            type="button"
            onClick={() => scrollBy(240)}
            disabled={!canScrollRight}
            aria-label="오른쪽 탭으로 이동"
            className={`shrink-0 p-1 ml-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white/95 dark:bg-slate-800/95 text-slate-600 dark:text-slate-300 shadow-sm transition-all hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-20 disabled:pointer-events-none z-10 ${
              canScrollRight ? 'opacity-100' : 'opacity-0 pointer-events-none'
            }`}
          >
            <ChevronRight size={16} />
          </button>
        )}
      </div>
    </div>
  )
}
