import { useEffect, useState } from 'react'
import ProfileSettingsCard from '../components/settings/ProfileSettingsCard'
import DisplaySettingsCard from '../components/settings/DisplaySettingsCard'
import MfaSettingsCard from '../components/settings/MfaSettingsCard'
import PageHeader from '../components/ui/PageHeader'
import ResponsiveTabs from '../components/ui/ResponsiveTabs'
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

      <ResponsiveTabs tabs={CONFIG_TABS} activeTab={activeTab} onChange={setActiveTab} />

      <div key={activeTab} className="animate-fade-in-up">
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
