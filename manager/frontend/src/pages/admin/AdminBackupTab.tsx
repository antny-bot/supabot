import { FormEvent, useEffect, useState } from 'react'
import {
  Archive,
  CheckCircle,
  Clock,
  Cloud,
  Download,
  HardDrive,
  KeyRound,
  Link,
  Play,
  RefreshCw,
  Save,
  ShieldCheck,
  Unlink,
} from 'lucide-react'
import {
  BackupConfig,
  BackupLocalFile,
  BackupState,
  connectGDrive,
  disconnectGDrive,
  fetchBackupConfig,
  fetchBackupStatus,
  getBackupDownloadUrl,
  saveBackupConfig,
  saveGDriveSettings,
  triggerBackup,
} from '../../api/backup'
import { requestGoogleDriveAuthCode } from '../../utils/googleAuth'
import Badge from '../../components/ui/Badge'
import ErrorBanner from '../../components/ui/ErrorBanner'

const DAYS_MAP = [
  { val: 0, label: '월' },
  { val: 1, label: '화' },
  { val: 2, label: '수' },
  { val: 3, label: '목' },
  { val: 4, label: '금' },
  { val: 5, label: '토' },
  { val: 6, label: '일' },
]

export default function AdminBackupTab() {
  const [config, setConfig] = useState<BackupConfig | null>(null)
  const [state, setState] = useState<BackupState | null>(null)
  const [localFiles, setLocalFiles] = useState<BackupLocalFile[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [triggering, setTriggering] = useState(false)
  const [connectingGDrive, setConnectingGDrive] = useState(false)
  const [disconnectingGDrive, setDisconnectingGDrive] = useState(false)
  const [showGDriveSettings, setShowGDriveSettings] = useState(false)
  const [gdriveClientIdInput, setGdriveClientIdInput] = useState('')
  const [gdriveClientSecretInput, setGdriveClientSecretInput] = useState('')
  const [gdriveFolderInput, setGdriveFolderInput] = useState('')
  const [savingGDriveSettings, setSavingGDriveSettings] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const loadData = async () => {
    try {
      setLoading(true)
      setError(null)
      const [cfgRes, statusRes] = await Promise.all([
        fetchBackupConfig(),
        fetchBackupStatus(),
      ])
      setConfig(cfgRes)
      if (cfgRes.gdrive_client_id) {
        setGdriveClientIdInput(cfgRes.gdrive_client_id)
      }
      if (cfgRes.gdrive_folder) {
        setGdriveFolderInput(cfgRes.gdrive_folder)
      }
      setState(statusRes.state)
      setLocalFiles(statusRes.local_files)
    } catch (err: any) {
      setError(err.message || '데이터를 불러오는 데 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleConnectGDrive = async () => {
    try {
      const clientId = (gdriveClientIdInput.trim() || config?.gdrive_client_id?.trim() || '')
      if (!clientId) {
        setShowGDriveSettings(true)
        setError('Google Client ID가 설정되지 않았습니다. 아래 [Google OAuth 설정]에서 발급받은 Client ID와 Client Secret을 먼저 저장해 주세요.')
        return
      }

      setConnectingGDrive(true)
      setError(null)
      setSuccessMsg(null)

      // Google Identity Services 팝업 실행
      const code = await requestGoogleDriveAuthCode(clientId)

      // 백엔드로 code 전달하여 토큰 교환 및 DB 저장
      const res = await connectGDrive({
        code,
        client_id: clientId,
        client_secret: gdriveClientSecretInput.trim() || undefined,
      })

      setSuccessMsg(`Google Drive 연동 성공: ${res.user_email || 'Google 계정 연결됨'}`)
      await loadData()
    } catch (err: any) {
      setError(err.message || 'Google Drive 연동 중 오류가 발생했습니다.')
    } finally {
      setConnectingGDrive(false)
    }
  }

  const handleDisconnectGDrive = async () => {
    if (!confirm('Google Drive 연동을 해제하시겠습니까?\n해제 시 정기 백업 시 클라우드 자동 업로드가 중단됩니다.')) return
    try {
      setDisconnectingGDrive(true)
      setError(null)
      setSuccessMsg(null)
      await disconnectGDrive()
      setSuccessMsg('Google Drive 연동이 해제되었습니다.')
      await loadData()
    } catch (err: any) {
      setError(err.message || 'Google Drive 연동 해제 중 오류가 발생했습니다.')
    } finally {
      setDisconnectingGDrive(false)
    }
  }

  const handleSaveGDriveSettings = async (e: FormEvent) => {
    e.preventDefault()
    try {
      setSavingGDriveSettings(true)
      setError(null)
      setSuccessMsg(null)
      await saveGDriveSettings({
        client_id: gdriveClientIdInput.trim(),
        client_secret: gdriveClientSecretInput.trim() || undefined,
        folder: gdriveFolderInput.trim() || undefined,
      })
      setSuccessMsg('Google Drive 설정이 저장되었습니다. 이제 [Google 계정으로 연동하기]를 클릭하세요.')
      await loadData()
    } catch (err: any) {
      setError(err.message || 'Google Drive 설정 저장 실패')
    } finally {
      setSavingGDriveSettings(false)
    }
  }

  const handleSaveConfig = async (e: FormEvent) => {
    e.preventDefault()
    if (!config) return
    try {
      setSaving(true)
      setError(null)
      setSuccessMsg(null)
      await saveBackupConfig(config)
      setSuccessMsg('백업 설정이 성공적으로 저장되었습니다.')
      setTimeout(() => setSuccessMsg(null), 3000)
    } catch (err: any) {
      setError(err.message || '설정 저장 중 오류가 발생했습니다.')
    } finally {
      setSaving(false)
    }
  }

  const handleTriggerBackup = async () => {
    if (!confirm('지금 Supabase 전체 백업을 실행하시겠습니까?')) return
    try {
      setTriggering(true)
      setError(null)
      setSuccessMsg(null)
      const res = await triggerBackup()
      setSuccessMsg(`백업 성공: ${res.file || '완료'} (${res.total_rows || 0}행)`)
      await loadData()
    } catch (err: any) {
      setError(err.message || '백업 실행 중 오류가 발생했습니다.')
    } finally {
      setTriggering(false)
    }
  }

  const toggleDay = (dayVal: number) => {
    if (!config) return
    const current = new Set(config.days_of_week)
    if (current.has(dayVal)) {
      if (current.size > 1) {
        current.delete(dayVal)
      }
    } else {
      current.add(dayVal)
    }
    setConfig({
      ...config,
      days_of_week: Array.from(current).sort(),
    })
  }

  const formatFileSize = (bytes: number) => {
    if (!bytes) return '0 B'
    const k = 1024
    if (bytes < k) return `${bytes} B`
    if (bytes < k * k) return `${(bytes / k).toFixed(1)} KB`
    return `${(bytes / (k * k)).toFixed(1)} MB`
  }

  const formatDate = (isoOrTs: string | number | null) => {
    if (!isoOrTs) return '-'
    const d = typeof isoOrTs === 'number' ? new Date(isoOrTs * 1000) : new Date(isoOrTs)
    return d.toLocaleString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 text-sm text-slate-500 dark:text-slate-400 whitespace-nowrap break-keep">
        <RefreshCw className="w-5 h-5 animate-spin mr-2" />
        백업 상태를 불러오는 중입니다...
      </div>
    )
  }

  const inputCls =
    'rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800 outline-none transition-colors hover:border-slate-300 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:border-slate-600 [color-scheme:light] dark:[color-scheme:dark]'

  return (
    <div className="space-y-6 break-keep">
      {error && <ErrorBanner message={error} />}
      {successMsg && (
        <div className="flex items-center gap-2 p-3 bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300 rounded-lg text-sm break-keep">
          <CheckCircle className="w-4 h-4 shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* 상태 요약 카드 4종 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap">
              최근 성공 시각
            </span>
            <Clock className="w-4 h-4 text-primary-500" />
          </div>
          <div className="text-base font-semibold text-slate-900 dark:text-white truncate">
            {formatDate(state?.last_success_at || null)}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
            <Badge
              value={
                state?.last_status === 'success'
                  ? 'active'
                  : state?.last_status === 'error'
                    ? 'error'
                    : state?.last_status === 'partial_error'
                      ? 'warning'
                      : 'pending'
              }
              label={
                state?.last_status === 'success'
                  ? '정상'
                  : state?.last_status === 'error'
                    ? '실패'
                    : state?.last_status === 'partial_error'
                      ? '일부실패(GDrive)'
                      : '대기'
              }
            />
            <span>총 {state?.total_rows || 0} 행 백업</span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap">
              최근 백업 파일
            </span>
            <Archive className="w-4 h-4 text-violet-500" />
          </div>
          <div className="text-sm font-semibold text-slate-900 dark:text-white truncate" title={state?.last_backup_file || '-'}>
            {state?.last_backup_file || '-'}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            크기: {formatFileSize(state?.last_backup_size || 0)}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap">
              Google Drive 상태
            </span>
            <Cloud className="w-4 h-4 text-blue-500" />
          </div>
          <div className="text-base font-semibold text-slate-900 dark:text-white flex items-center gap-2">
            {config?.gdrive_enabled ? (
              <Badge
                value="active"
                label={config.gdrive_source === 'db' ? '웹 연동 완료' : '연동 완료 (.env)'}
              />
            ) : (
              <Badge value="warning" label="미연동" />
            )}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400 truncate" title={config?.gdrive_user_email || config?.gdrive_folder}>
            {config?.gdrive_user_email ? (
              <span className="text-primary-600 dark:text-primary-400 font-medium truncate block">{config.gdrive_user_email}</span>
            ) : (
              `폴더: ${config?.gdrive_folder || 'supabot-backups'}`
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap">
              로컬 스냅샷
            </span>
            <HardDrive className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-base font-semibold text-slate-900 dark:text-white">
            {localFiles.length}개 보관 중
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            최대 유지: {config?.local_max_keep || 7}개
          </div>
        </div>
      </div>

      {/* Google Drive 클라우드 연동 섹션 (웹 인증 관리) */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-950/40 flex items-center justify-center text-blue-600 dark:text-blue-400 shrink-0">
              <Cloud className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white whitespace-nowrap break-keep">
                Google Drive 클라우드 백업 연동
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 break-keep">
                웹에서 Google 계정을 1회 인증하면, 백업 생성 시 지정된 구글 드라이브 폴더에 암호화 보관됩니다.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowGDriveSettings(!showGDriveSettings)}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 flex items-center gap-1.5 whitespace-nowrap break-keep transition-colors"
            >
              <KeyRound className="w-3.5 h-3.5" />
              <span>OAuth 키/폴더 설정</span>
            </button>

            {config?.gdrive_enabled ? (
              <button
                type="button"
                onClick={handleDisconnectGDrive}
                disabled={disconnectingGDrive}
                className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100 disabled:opacity-50 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-400 dark:hover:bg-rose-900/40 flex items-center gap-1.5 whitespace-nowrap break-keep transition-colors"
              >
                {disconnectingGDrive ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Unlink className="w-3.5 h-3.5" />
                )}
                <span>연동 해제</span>
              </button>
            ) : null}

            <button
              type="button"
              onClick={handleConnectGDrive}
              disabled={connectingGDrive}
              className="rounded-lg bg-blue-600 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1.5 whitespace-nowrap break-keep transition-colors shadow-sm"
            >
              {connectingGDrive ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Link className="w-3.5 h-3.5" />
              )}
              <span>{config?.gdrive_enabled ? '계정 재인증 / 변경' : 'Google 계정으로 연동하기'}</span>
            </button>
          </div>
        </div>

        {/* 연동 상태 요약 바 */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-50 dark:bg-slate-800/40 rounded-lg text-xs">
          <div className="flex items-center gap-3">
            <span className="text-slate-500 dark:text-slate-400 whitespace-nowrap">연동 계정:</span>
            {config?.gdrive_user_email ? (
              <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                {config.gdrive_user_email}
              </span>
            ) : (
              <span className="text-slate-400 italic">미연동 상태입니다.</span>
            )}
          </div>
          <div className="flex items-center gap-4 text-slate-500 dark:text-slate-400">
            <span>
              보관 폴더: <code className="px-1 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-200 text-[11px]">{config?.gdrive_folder || 'supabot-backups'}</code>
            </span>
            <span>
              인증 방식: <span className="font-medium text-slate-700 dark:text-slate-300">{config?.gdrive_source === 'db' ? '웹 DB 인증' : config?.gdrive_source === 'env' ? '서버 .env 인증' : '미연동'}</span>
            </span>
          </div>
        </div>

        {/* Google OAuth 키 및 폴더 설정 (접이식) */}
        {showGDriveSettings && (
          <form onSubmit={handleSaveGDriveSettings} className="p-4 bg-slate-50/70 dark:bg-slate-800/20 rounded-lg border border-slate-200 dark:border-slate-800 space-y-3 pt-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                <KeyRound className="w-3.5 h-3.5 text-primary-500" />
                Google Cloud Console OAuth 클라이언트 정보
              </span>
              <span className="text-[11px] text-slate-400">
                .env에 등록되어 있으면 자동으로 불러옵니다.
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
                  Google Client ID <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  placeholder="예: xxxxx.apps.googleusercontent.com"
                  value={gdriveClientIdInput}
                  onChange={(e) => setGdriveClientIdInput(e.target.value)}
                  className={`${inputCls} w-full text-xs`}
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
                  Google Client Secret {config?.gdrive_has_secret && <span className="text-emerald-500 text-[10px] ml-1">(등록됨)</span>}
                </label>
                <input
                  type="password"
                  placeholder={config?.gdrive_has_secret ? '기존 Secret 유지 중 (변경 시에만 입력)' : '예: GOCSPX-xxxx...'}
                  value={gdriveClientSecretInput}
                  onChange={(e) => setGdriveClientSecretInput(e.target.value)}
                  className={`${inputCls} w-full text-xs`}
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-[11px] font-medium text-slate-600 dark:text-slate-400 mb-1">
                  Google Drive 백업 저장 폴더명
                </label>
                <input
                  type="text"
                  placeholder="supabot-backups"
                  value={gdriveFolderInput}
                  onChange={(e) => setGdriveFolderInput(e.target.value)}
                  className={`${inputCls} w-full text-xs`}
                />
                <p className="mt-1 text-[11px] text-slate-400">
                  Google Drive 루트에 해당 이름의 폴더가 없을 경우 백업 시 자동으로 생성됩니다.
                </p>
              </div>
            </div>

            <div className="p-3 bg-blue-50/70 dark:bg-blue-950/20 rounded-lg text-[11px] text-blue-800 dark:text-blue-300 space-y-1">
              <div className="font-semibold flex items-center gap-1">
                <span>Google Cloud Console 설정 안내:</span>
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-blue-700 dark:text-blue-400 pl-1">
                <li>
                  <strong>승인된 자바스크립트 원본(Origin):</strong>{' '}
                  <code className="px-1 py-0.5 rounded bg-blue-100 dark:bg-blue-900/40">
                    {typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5173'}
                  </code>
                </li>
                <li>
                  <strong>사용 API:</strong> Google Drive API v3 활성화 필수
                </li>
              </ul>
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setShowGDriveSettings(false)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
              >
                닫기
              </button>
              <button
                type="submit"
                disabled={savingGDriveSettings}
                className="rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-700 disabled:opacity-50 flex items-center gap-1"
              >
                {savingGDriveSettings ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                <span>설정 저장</span>
              </button>
            </div>
          </form>
        )}
      </div>

      {/* 액션 바: 즉시 백업 버튼 */}
      <div className="flex items-center justify-between p-4 bg-slate-50/70 dark:bg-slate-900/60 rounded-xl border border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-primary-500" />
          <div>
            <div className="text-sm font-semibold text-slate-900 dark:text-white break-keep">
              Supabase 14개 전체 테이블 덤프 및 Fallback SQLite 동기화
            </div>
            <div className="text-xs text-slate-500 dark:text-slate-400 break-keep">
              클릭 시 즉시 스냅샷을 생성하고 ZIP 패키징 및 Google Drive로 전송합니다.
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={handleTriggerBackup}
          disabled={triggering}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 flex items-center gap-1.5 whitespace-nowrap break-keep transition-colors"
        >
          {triggering ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4 fill-current" />
          )}
          <span>{triggering ? '백업 진행 중...' : '즉시 백업 실행'}</span>
        </button>
      </div>

      {/* 백업 설정 폼 */}
      {config && (
        <form onSubmit={handleSaveConfig} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 space-y-5">
          <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2 whitespace-nowrap break-keep">
              <Clock className="w-4 h-4 text-primary-500" />
              백업 주기 및 보존 정책 설정
            </h3>
            <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={config.enabled}
                onChange={(e) => setConfig({ ...config, enabled: e.target.checked })}
                className="rounded border-slate-300 text-primary-600 focus:ring-primary-500 dark:border-slate-600 dark:bg-slate-800"
              />
              <span className="whitespace-nowrap break-keep">정기 자동 백업 활성화</span>
            </label>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* 스케줄 방식 */}
            <div className="space-y-3">
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 whitespace-nowrap break-keep">
                스케줄 방식
              </label>
              <div className="flex gap-4">
                <label className="flex items-center gap-1.5 text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="schedule_type"
                    value="interval"
                    checked={config.schedule_type === 'interval'}
                    onChange={() => setConfig({ ...config, schedule_type: 'interval' })}
                    className="text-primary-600 focus:ring-primary-500 dark:border-slate-600 dark:bg-slate-800"
                  />
                  <span className="whitespace-nowrap break-keep">시간 간격 (기본 24시간 제안)</span>
                </label>
                <label className="flex items-center gap-1.5 text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="schedule_type"
                    value="weekly"
                    checked={config.schedule_type === 'weekly'}
                    onChange={() => setConfig({ ...config, schedule_type: 'weekly' })}
                    className="text-primary-600 focus:ring-primary-500 dark:border-slate-600 dark:bg-slate-800"
                  />
                  <span className="whitespace-nowrap break-keep">요일 선택 매일 실행</span>
                </label>
              </div>

              {config.schedule_type === 'interval' ? (
                <div className="pt-2">
                  <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1 whitespace-nowrap break-keep">
                    실행 주기 (시간)
                  </label>
                  <div className="flex items-center gap-2">
                    <select
                      value={config.interval_hours}
                      onChange={(e) => setConfig({ ...config, interval_hours: Number(e.target.value) })}
                      className={`${inputCls} w-32`}
                    >
                      <option value={6} className="bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100">6시간</option>
                      <option value={12} className="bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100">12시간</option>
                      <option value={24} className="bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100">24시간 (권장)</option>
                      <option value={48} className="bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100">48시간</option>
                      <option value={72} className="bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100">72시간</option>
                    </select>
                    <span className="text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap break-keep">
                      마지막 백업 성공 시점 기준
                    </span>
                  </div>
                </div>
              ) : (
                <div className="space-y-3 pt-2">
                  <div>
                    <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1.5 whitespace-nowrap break-keep">
                      실행 요일 선택 (다중 선택 가능)
                    </label>
                    <div className="flex gap-1.5">
                      {DAYS_MAP.map((d) => {
                        const isSelected = config.days_of_week.includes(d.val)
                        return (
                          <button
                            key={d.val}
                            type="button"
                            onClick={() => toggleDay(d.val)}
                            className={`w-8 h-8 rounded-lg text-xs font-semibold transition-colors ${
                              isSelected
                                ? 'bg-primary-500 text-white shadow-sm'
                                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
                            }`}
                          >
                            {d.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1 whitespace-nowrap break-keep">
                      실행 시각 (KST)
                    </label>
                    <input
                      type="time"
                      value={config.time_of_day}
                      onChange={(e) => setConfig({ ...config, time_of_day: e.target.value })}
                      className={`${inputCls} w-32`}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* 보존 정책 */}
            <div className="space-y-3">
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 whitespace-nowrap break-keep">
                백업 파일 보존 정책 (초과 시 자동 삭제)
              </label>

              <div className="grid grid-cols-2 gap-4 pt-1">
                <div>
                  <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1 whitespace-nowrap break-keep">
                    로컬 최대 보관 개수
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={config.local_max_keep}
                    onChange={(e) => setConfig({ ...config, local_max_keep: Number(e.target.value) })}
                    className={`${inputCls} w-full`}
                  />
                  <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500 whitespace-nowrap break-keep">기본값: 7개</p>
                </div>
                <div>
                  <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1 whitespace-nowrap break-keep">
                    Google Drive 최대 보관 개수
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={200}
                    value={config.gdrive_max_keep}
                    onChange={(e) => setConfig({ ...config, gdrive_max_keep: Number(e.target.value) })}
                    className={`${inputCls} w-full`}
                  />
                  <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500 whitespace-nowrap break-keep">기본값: 14개</p>
                </div>
              </div>

              <div className="p-3 bg-blue-50/70 dark:bg-blue-950/30 rounded-lg text-xs text-blue-800 dark:text-blue-300 flex items-start gap-2 break-keep leading-relaxed">
                <Cloud className="w-4 h-4 shrink-0 mt-0.5 text-blue-500" />
                <span>
                  Google Drive 연동 시 상단의 <strong>[Google 계정으로 연동하기]</strong> 버튼을 통해 브라우저에서 원클릭으로 간편하게 인증하거나, 서버 <code>.env</code> 파일의 토큰을 사용할 수 있습니다.
                </span>
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-2 border-t border-slate-200 dark:border-slate-800">
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-primary-600 px-4 py-2 text-xs font-medium text-white hover:bg-primary-700 disabled:opacity-50 flex items-center gap-1.5 whitespace-nowrap break-keep transition-colors"
            >
              {saving ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              <span>{saving ? '저장 중...' : '설정 저장'}</span>
            </button>
          </div>
        </form>
      )}

      {/* 로컬 백업 파일 목록 */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white flex items-center gap-2 whitespace-nowrap break-keep">
            <Archive className="w-4 h-4 text-violet-500" />
            보관 중인 로컬 백업 파일 ({localFiles.length}개)
          </h3>
          <button
            type="button"
            onClick={loadData}
            className="text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 flex items-center gap-1 whitespace-nowrap break-keep transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            새로고침
          </button>
        </div>

        {localFiles.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500 dark:text-slate-400 whitespace-nowrap break-keep">
            보관 중인 백업 파일이 없습니다. 상단의 '즉시 백업 실행'을 눌러 첫 백업을 생성하세요.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 font-medium border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="py-2.5 px-4 whitespace-nowrap break-keep">파일명</th>
                  <th className="py-2.5 px-4 whitespace-nowrap break-keep">생성 일시</th>
                  <th className="py-2.5 px-4 whitespace-nowrap break-keep">파일 용량</th>
                  <th className="py-2.5 px-4 text-right whitespace-nowrap break-keep">다운로드</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {localFiles.map((f) => (
                  <tr key={f.filename} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="py-2.5 px-4 font-medium text-slate-900 dark:text-white whitespace-nowrap">
                      {f.filename}
                    </td>
                    <td className="py-2.5 px-4 text-slate-600 dark:text-slate-300 whitespace-nowrap">
                      {formatDate(f.createdAt)}
                    </td>
                    <td className="py-2.5 px-4 text-slate-600 dark:text-slate-300 whitespace-nowrap">
                      {formatFileSize(f.sizeBytes)}
                    </td>
                    <td className="py-2.5 px-4 text-right whitespace-nowrap">
                      <a
                        href={getBackupDownloadUrl(f.filename)}
                        download={f.filename}
                        className="inline-flex items-center gap-1 text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 font-medium transition-colors"
                      >
                        <Download className="w-3.5 h-3.5" />
                        <span>다운로드</span>
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
