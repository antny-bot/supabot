import { FormEvent, useEffect, useRef, useState } from 'react'
import { CheckCircle, ChevronLeft, ChevronRight, Download, RefreshCw, Trash2, Upload } from 'lucide-react'
import { fetchConfig, saveConfig } from '../api/config'
import {
  createStockCacheEntry,
  deleteStockCacheEntry,
  exportStockCache,
  fetchStockCache,
  refreshStockCache,
  type StockCacheRow as StockRow,
  uploadStockCache,
} from '../api/stockCache'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import ResponsiveTabs from '../components/ui/ResponsiveTabs'
import Spinner from '../components/ui/Spinner'
import { PAGE_META } from '../config/pageMeta'
import type { ConfigItem } from '../types'
import { staggerDelay } from '../utils/animation'
import { EventsContent } from './Events'
import { UsersContent } from './Users'

const ADMIN_TABS = [
  { id: 'users',       label: '유저관리' },
  { id: 'events',      label: '이벤트' },
  { id: 'monitoring',  label: '주문 및 신호 주기' },
  { id: 'stock-cache', label: '종목 캐시' },
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
          className="w-32 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-primary-400"
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
        <div className="animate-fade-in-up flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400">
          <CheckCircle size={16} className="shrink-0" />
          설정이 저장되었습니다.
        </div>
      )}
      <form onSubmit={handleSubmit} className="space-y-4">
        {monitoringItems.length > 0 && (
          <section className="animate-fade-in-up rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
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
        {otherItems.map((item, index) => (
          <div key={item.key} className="animate-fade-in-up rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900" style={staggerDelay(index + 1)}>
            <ConfigNumberField item={item} value={values[item.key] ?? ''} onChange={(next) => setValues((prev) => ({ ...prev, [item.key]: next }))} />
          </div>
        ))}
        <button
          type="submit" disabled={saving}
          className="rounded-xl bg-primary-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-700 disabled:opacity-60"
        >
          {saving ? '저장 중...' : '설정 저장'}
        </button>
      </form>
    </div>
  )
}

// ── 종목 캐시 탭 ──────────────────────────────────────────────────────────────

function StockCacheTab() {
  const [rows, setRows] = useState<StockRow[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [newCode, setNewCode] = useState('')
  const [saving, setSaving] = useState(false)
  const [overwrite, setOverwrite] = useState(true)
  const [uploadStatus, setUploadStatus] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const load = async (q = search) => {
    setLoading(true)
    setError(null)
    try {
      setRows(await fetchStockCache(q))
      setPage(1)
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleSearch = (e: FormEvent) => {
    e.preventDefault()
    load(search)
  }

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault()
    if (!newName.trim() || !newCode.trim()) return
    setSaving(true)
    try {
      await createStockCacheEntry(newName.trim(), newCode.trim())
      setNewName('')
      setNewCode('')
      await load()
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (name: string) => {
    if (!confirm(`"${name}" 삭제할까요?`)) return
    try {
      await deleteStockCacheEntry(name)
      await load()
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error))
    }
  }

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadStatus(null)
    try {
      const { added, skipped, errors } = await uploadStockCache(file, overwrite)
      setUploadStatus(`완료: 추가/수정 ${added}건, 건너뜀 ${skipped}건, 오류 ${errors}건`)
      await load()
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error))
    } finally {
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleExport = () => {
    exportStockCache()
  }

  const handleRefresh = async () => {
    if (!confirm('KRX(코스피+코스닥+코넥스) 전체 종목명/코드를 받아와 캐시에 일괄 반영합니다. 계속할까요?')) return
    setRefreshing(true)
    setUploadStatus(null)
    setError(null)
    try {
      const { added } = await refreshStockCache()
      setUploadStatus(`KRX 갱신 완료: ${added}건 반영`)
      await load()
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error))
    } finally {
      setRefreshing(false)
    }
  }

  const inputCls = 'rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100'
  const btnPrimary = 'rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50'

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize))
  const pagedRows = rows.slice((page - 1) * pageSize, page * pageSize)

  return (
    <div className="space-y-5">
      {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">{error}</div>}
      {uploadStatus && <div className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700 dark:bg-green-900/30 dark:text-green-400">{uploadStatus}</div>}

      {/* 단건 추가 */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">종목 추가 / 수정</h3>
        <form onSubmit={handleAdd} className="flex flex-wrap gap-2 items-end">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">종목명</label>
            <input className={inputCls} placeholder="삼천당제약" value={newName} onChange={e => setNewName(e.target.value)} required />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-500">종목코드</label>
            <input className={inputCls} placeholder="000250" value={newCode} onChange={e => setNewCode(e.target.value)} required maxLength={6} />
          </div>
          <button type="submit" disabled={saving} className={btnPrimary}>{saving ? '저장 중...' : '저장'}</button>
        </form>
      </div>

      {/* CSV 업로드 */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">CSV 일괄 업로드</h3>
        <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">CSV 형식: 헤더 <code className="font-mono">name,code</code> (순서 무관)</p>
        <div className="flex flex-wrap gap-3 items-center">
          <label className="flex items-center gap-1.5 text-sm text-slate-600 dark:text-slate-300 cursor-pointer">
            <input type="checkbox" checked={overwrite} onChange={e => setOverwrite(e.target.checked)} className="rounded" />
            중복 덮어쓰기
          </label>
          <label className={`${btnPrimary} flex items-center gap-1.5 cursor-pointer`}>
            <Upload size={14} />
            CSV 업로드
            <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleUpload} />
          </label>
          <button onClick={handleExport} className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
            <Download size={14} />
            CSV 내보내기
          </button>
          <button onClick={handleRefresh} disabled={refreshing} className={`${btnPrimary} flex items-center gap-1.5`}>
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'KRX 갱신 중...' : 'KRX 전체 갱신'}
          </button>
        </div>
      </div>

      {/* 검색 + 목록 */}
      <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
          <form onSubmit={handleSearch} className="flex gap-2 flex-1">
            <input className={`${inputCls} flex-1 max-w-xs`} placeholder="종목명 또는 코드 검색" value={search} onChange={e => setSearch(e.target.value)} />
            <button type="submit" className={btnPrimary}>검색</button>
          </form>
          <span className="text-xs text-slate-400">{rows.length}건</span>
          <select
            className={`${inputCls} text-xs py-1.5`}
            value={pageSize}
            onChange={e => { setPageSize(Number(e.target.value)); setPage(1) }}
          >
            {[10, 20, 50].map(n => <option key={n} value={n}>{n}개씩</option>)}
          </select>
        </div>

        {loading ? (
          <div className="flex justify-center py-10"><Spinner /></div>
        ) : rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-400">데이터 없음</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 dark:border-slate-800 text-left text-xs text-slate-500 uppercase">
                <th className="px-4 py-2">종목명</th>
                <th className="px-4 py-2">종목코드</th>
                <th className="px-4 py-2">갱신일시</th>
                <th className="px-4 py-2 text-right">삭제</th>
              </tr>
            </thead>
            <tbody>
              {pagedRows.map(r => (
                <tr key={r.name} className="border-b border-slate-50 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50">
                  <td className="px-4 py-2 font-medium text-slate-800 dark:text-slate-200">{r.name}</td>
                  <td className="px-4 py-2 font-mono text-slate-600 dark:text-slate-400">{r.code}</td>
                  <td className="px-4 py-2 text-slate-400 text-xs">{r.updated_at ? r.updated_at.slice(0, 19).replace('T', ' ') : '-'}</td>
                  <td className="px-4 py-2 text-right">
                    <button onClick={() => handleDelete(r.name)} className="text-red-400 hover:text-red-600 dark:hover:text-red-300">
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {!loading && rows.length > 0 && (
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 dark:border-slate-800">
            <div className="text-xs text-slate-500 dark:text-slate-400">
              <span className="font-semibold text-slate-900 dark:text-white">{page}</span> / {totalPages} 페이지
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="rounded-lg border border-slate-200 bg-white p-1.5 transition-colors disabled:opacity-30 dark:border-slate-700 dark:bg-slate-800"
              >
                <ChevronLeft size={16} />
              </button>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="rounded-lg border border-slate-200 bg-white p-1.5 transition-colors disabled:opacity-30 dark:border-slate-700 dark:bg-slate-800"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Admin() {
  const [activeTab, setActiveTab] = useState('users')

  return (
    <div className="space-y-5">
      <PageHeader {...PAGE_META.admin} />

      <ResponsiveTabs tabs={ADMIN_TABS} activeTab={activeTab} onChange={setActiveTab} />

      <div key={activeTab} className="animate-fade-in-up">
        {activeTab === 'users'       && <UsersContent />}
        {activeTab === 'events'      && <EventsContent />}
        {activeTab === 'monitoring'  && <MonitoringTab />}
        {activeTab === 'stock-cache' && <StockCacheTab />}
      </div>
    </div>
  )
}
