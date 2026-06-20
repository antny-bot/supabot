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
  return (
    <div className="md:border-b md:border-slate-200 md:dark:border-slate-800">
      <div
        className="flex gap-2 overflow-x-auto pb-2 scrollbar-none snap-x snap-mandatory md:hidden"
        role="tablist"
        aria-orientation="horizontal"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => onChange(tab.id)}
            className={`shrink-0 snap-start whitespace-nowrap rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-primary-600 text-white'
                : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        className="hidden gap-1.5 pb-0 md:flex"
        role="tablist"
        aria-orientation="horizontal"
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => onChange(tab.id)}
            className={`-mb-px rounded-t-lg border-b-2 px-3.5 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'border-primary-600 text-primary-600 dark:border-primary-400 dark:text-primary-400'
                : 'border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  )
}
