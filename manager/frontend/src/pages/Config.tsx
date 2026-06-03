import { useEffect, useState, FormEvent } from 'react'
import { CheckCircle } from 'lucide-react'
import { fetchConfig, saveConfig } from '../api/config'
import type { ConfigItem } from '../types'
import { useAuthContext } from '../contexts/AuthContext'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import MfaSettingsCard from '../components/settings/MfaSettingsCard'

export default function Config() {
  const { user } = useAuthContext()
  const [config, setConfig] = useState<ConfigItem[]>([])
  const [values, setValues] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [mfaEnabled, setMfaEnabled] = useState(user?.mfa_enabled ?? false)

  useEffect(() => {
    setMfaEnabled(user?.mfa_enabled ?? false)
  }, [user])

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

  return (
    <div className="space-y-5 max-w-xl">
      <h1 className="text-xl font-bold text-slate-900 dark:text-white">시스템 설정</h1>

      {error && <ErrorBanner message={error} />}

      {saved && (
        <div className="flex items-center gap-2 p-4 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-xl text-emerald-700 dark:text-emerald-400 text-sm">
          <CheckCircle size={16} className="shrink-0" />
          설정이 저장되었습니다.
        </div>
      )}

      <MfaSettingsCard initialEnabled={mfaEnabled} onStatusChange={setMfaEnabled} />

      <form onSubmit={handleSubmit} className="space-y-4">
        {config.map((item) => (
          <div key={item.key} className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-5">
            <label className="block text-sm font-semibold text-slate-800 dark:text-slate-200 mb-1">
              {item.label}
            </label>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{item.desc}</p>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={1}
                required
                value={values[item.key] ?? ''}
                onChange={(e) => setValues((prev) => ({ ...prev, [item.key]: e.target.value }))}
                className="w-32 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400"
              />
              <span className="text-sm text-slate-500 dark:text-slate-400">초</span>
            </div>
            {item.updated_at && (
              <p className="text-xs text-slate-400 dark:text-slate-600 mt-2">
                마지막 수정: {item.updated_at.slice(0, 19).replace('T', ' ')}
              </p>
            )}
          </div>
        ))}

        <button
          type="submit"
          disabled={saving}
          className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white rounded-xl text-sm font-medium transition-colors"
        >
          {saving ? '저장 중…' : '설정 저장'}
        </button>
      </form>
    </div>
  )
}
