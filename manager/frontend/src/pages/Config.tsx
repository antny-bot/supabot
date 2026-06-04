import { useEffect, useState } from 'react'
import ProfileSettingsCard from '../components/settings/ProfileSettingsCard'
import DisplaySettingsCard from '../components/settings/DisplaySettingsCard'
import MfaSettingsCard from '../components/settings/MfaSettingsCard'
import PageHeader from '../components/ui/PageHeader'
import Spinner from '../components/ui/Spinner'
import { PAGE_META } from '../config/pageMeta'
import { useAuthContext } from '../contexts/AuthContext'
import {
  DISPLAY_PREFERENCES_EVENT,
  readDisplayPreferences,
  type DisplayPreferences,
} from '../lib/displayPreferences'

const CONFIG_TABS = [
  { id: 'display', label: '화면 표시' },
  { id: 'profile', label: '프로필' },
  { id: 'security', label: '보안' },
]

export default function Config() {
  const { user } = useAuthContext()
  const [activeTab, setActiveTab] = useState('display')
  const [loading] = useState(false)
  const [mfaEnabled, setMfaEnabled] = useState(user?.mfa_enabled ?? false)
  const [displayPreferences, setDisplayPreferences] = useState<DisplayPreferences>(
    () => readDisplayPreferences(),
  )

  useEffect(() => {
    setMfaEnabled(user?.mfa_enabled ?? false)
  }, [user])

  useEffect(() => {
    function syncPreferences() {
      setDisplayPreferences(readDisplayPreferences())
    }
    syncPreferences()
    window.addEventListener(DISPLAY_PREFERENCES_EVENT, syncPreferences)
    return () => window.removeEventListener(DISPLAY_PREFERENCES_EVENT, syncPreferences)
  }, [])

  if (loading) return <Spinner />

  return (
    <div className="max-w-xl space-y-5">
      <PageHeader {...PAGE_META.config} />

      {/* Tab strip */}
      <div className="md:border-b md:border-slate-200 md:dark:border-slate-800">
        <div className="flex md:hidden overflow-x-auto gap-2 pb-2 scrollbar-none snap-x snap-mandatory">
          {CONFIG_TABS.map((tab) => (
            <button
              key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`flex-shrink-0 snap-start px-4 py-1.5 rounded-full text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === tab.id ? 'bg-indigo-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
              }`}
            >{tab.label}</button>
          ))}
        </div>
        <div className="hidden md:flex gap-1.5 pb-0">
          {CONFIG_TABS.map((tab) => (
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
        {activeTab === 'display' && (
          <DisplaySettingsCard preferences={displayPreferences} onChange={setDisplayPreferences} />
        )}
        {activeTab === 'profile' && (
          <ProfileSettingsCard initialUsername={user?.username || ''} email={user?.email || ''} />
        )}
        {activeTab === 'security' && (
          <MfaSettingsCard initialEnabled={mfaEnabled} onStatusChange={setMfaEnabled} />
        )}
      </div>
    </div>
  )
}
