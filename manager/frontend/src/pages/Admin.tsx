import { FormEvent, useEffect, useState } from 'react'
import { CheckCircle } from 'lucide-react'
import { fetchConfig, saveConfig } from '../api/config'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import Spinner from '../components/ui/Spinner'
import { PAGE_META } from '../config/pageMeta'
import type { ConfigItem } from '../types'
import { EventsContent } from './Events'
import { UsersContent } from './Users'

const ADMIN_TABS = [
  { id: 'users',      label: '유저관리' },
  { id: 'events',     label: '이벤트' },
  { id: 'monitoring', label: '주문 및 신호 주기' },
]

const MONITORING_CONFIG_KEYS = [
  'poll_active_interval',
  'poll_no_order_interval',
  'signal_analysis_interval',
] as const

type MonitoringConfigKey = (typeof MONITORING_CONFIG_KEYS)[number]
function isMonitoringKey(key: string): key is MonitoringConfigKey {
  return MONITORING_CONFIG_KEYS.includes(key as MonitoringConfigKey)
}

function ConfigNumberField({
  item, value, onChange,
}: { item: ConfigItem; value: string; onChange: (next: string) => void }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-semibold text-slate-800 dark:text-slate-200">{item.label}</label>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">{item.desc}</p>
      <div className="flex items-center gap-2">
        <input
          type="number" min={1} required value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-32 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-indigo-400"
        />
        <span className="text-sm text-slate-500 dark:text-slate-400">초</span>
      </div>
      {item.updated_at && (
        <p className="mt-2 text-xs text-slate-400 dark:text-slate-600">
          마지막 수정: {item.updated_at.slice(0, 19).replace('T', ' ')}
        </p>
      )}
    </div>
  )
}

function MonitoringTab() {
  const [config, setConfig] = useState<ConfigItem[]>([])
  const [values, setValues] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetchConfig()
      .then((items) => {
        setConfig(items)
        const init: Record<string, string> = {}
        for (const item of items) init[item.key] = item.value
        setValues(init)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류가 발생했습니다.'))
      .finally(() => setLoading(false))
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      await saveConfig(values)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '저장에 실패했습니다.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Spinner />

  const monitoringItems = config.filter((item) => isMonitoringKey(item.key))
  const otherItems = config.filter((item) => !isMonitoringKey(item.key))

  return (
    <div className="space-y-4 max-w-xl">
      {error && <ErrorBanner message={error} />}
      {saved && (
        <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400">
          <CheckCircle size={16} className="shrink-0" />
          설정이 저장되었습니다.
        </div>
      )}
      <form onSubmit={handleSubmit} className="space-y-4">
        {monitoringItems.length > 0 && (
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="mb-4">
              <h2 className="text-app-body font-semibold text-slate-900 dark:text-slate-100">주문 및 신호 주기</h2>
              <p className="mt-1 text-app-caption text-slate-500 dark:text-slate-400">
                주문 감시 간격과 신호 분석 주기를 한 곳에서 관리합니다.
              </p>
            </div>
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {monitoringItems.map((item, index) => (
                <div
                  key={item.key}
                  className={`${index === 0 ? 'pt-0' : 'pt-4'} ${index === monitoringItems.length - 1 ? 'pb-0' : 'pb-4'}`}
                >
                  <ConfigNumberField item={item} value={values[item.key] ?? ''} onChange={(next) => setValues((prev) => ({ ...prev, [item.key]: next }))} />
                </div>
              ))}
            </div>
          </section>
        )}
        {otherItems.map((item) => (
          <div key={item.key} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <ConfigNumberField item={item} value={values[item.key] ?? ''} onChange={(next) => setValues((prev) => ({ ...prev, [item.key]: next }))} />
          </div>
        ))}
        <button
          type="submit" disabled={saving}
          className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-60"
        >
          {saving ? '저장 중...' : '설정 저장'}
        </button>
      </form>
    </div>
  )
}

export default function Admin() {
  const [activeTab, setActiveTab] = useState('users')

  return (
    <div className="space-y-5">
      <PageHeader {...PAGE_META.admin} />

      {/* Tab strip */}
      <div className="md:border-b md:border-slate-200 md:dark:border-slate-800">
        <div className="flex md:hidden overflow-x-auto gap-2 pb-2 scrollbar-none snap-x snap-mandatory">
          {ADMIN_TABS.map((tab) => (
            <button
              key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`flex-shrink-0 snap-start px-4 py-1.5 rounded-full text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === tab.id ? 'bg-indigo-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
              }`}
            >{tab.label}</button>
          ))}
        </div>
        <div className="hidden md:flex gap-1.5 pb-0">
          {ADMIN_TABS.map((tab) => (
            <button
              key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`px-3.5 py-2 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
                activeTab === tab.id
                  ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                  : 'border-transparent text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
              }`}
            >{tab.label}</button>
          ))}
        </div>
      </div>

      <div>
        {activeTab === 'users'      && <UsersContent />}
        {activeTab === 'events'     && <EventsContent />}
        {activeTab === 'monitoring' && <MonitoringTab />}
      </div>
    </div>
  )
}
