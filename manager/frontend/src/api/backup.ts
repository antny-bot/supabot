export interface BackupConfig {
  enabled: boolean
  schedule_type: 'interval' | 'weekly'
  interval_hours: number
  days_of_week: number[] // 0=월..6=일
  time_of_day: string    // HH:MM
  local_max_keep: number
  gdrive_max_keep: number
  gdrive_enabled: boolean
  gdrive_folder: string
  gdrive_user_email?: string
  gdrive_client_id?: string
  gdrive_has_secret?: boolean
  gdrive_source?: 'db' | 'env' | 'none'
}

export interface GDriveStatusResponse {
  connected: boolean
  user_email: string
  folder: string
  client_id: string
  has_client_secret: boolean
  connected_at: string | null
  source: 'db' | 'env' | 'none'
}

export interface BackupState {
  last_attempt_at: string | null
  last_success_at: string | null
  last_status: 'none' | 'success' | 'error' | string
  last_error: string | null
  last_backup_file: string | null
  last_backup_size: number
  last_gdrive_file_id: string | null
  table_counts: Record<string, number>
  total_rows: number
}

export interface BackupLocalFile {
  filename: string
  sizeBytes: number
  createdAt: number
}

export interface BackupStatusResponse {
  state: BackupState
  local_files: BackupLocalFile[]
}

export async function fetchBackupConfig(): Promise<BackupConfig> {
  const res = await fetch('/api/backup/config')
  if (!res.ok) {
    throw new Error('백업 설정을 불러오는 데 실패했습니다.')
  }
  return res.json()
}

export async function saveBackupConfig(config: Partial<BackupConfig>): Promise<void> {
  const res = await fetch('/api/backup/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error || '백업 설정을 저장하는 데 실패했습니다.')
  }
}

export async function fetchBackupStatus(): Promise<BackupStatusResponse> {
  const res = await fetch('/api/backup/status')
  if (!res.ok) {
    throw new Error('백업 상태를 불러오는 데 실패했습니다.')
  }
  return res.json()
}

export async function triggerBackup(): Promise<any> {
  const res = await fetch('/api/backup/trigger', {
    method: 'POST',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error || '즉시 백업 실행에 실패했습니다.')
  }
  return res.json()
}

export function getBackupDownloadUrl(filename: string): string {
  return `/api/backup/download/${encodeURIComponent(filename)}`
}

export async function fetchBackupHealth(): Promise<any> {
  const res = await fetch('/api/backup/health')
  if (!res.ok) {
    throw new Error('백업 헬스 정보를 불러오는 데 실패했습니다.')
  }
  return res.json()
}

export async function fetchGDriveStatus(): Promise<GDriveStatusResponse> {
  const res = await fetch('/api/backup/gdrive/status')
  if (!res.ok) {
    throw new Error('Google Drive 연동 상태를 불러오는 데 실패했습니다.')
  }
  return res.json()
}

export async function connectGDrive(params: {
  code: string
  redirect_uri?: string
  client_id?: string
  client_secret?: string
}): Promise<{ ok: boolean; status: string; user_email: string }> {
  const res = await fetch('/api/backup/gdrive/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || err.error || 'Google Drive 연동에 실패했습니다.')
  }
  return res.json()
}

export async function disconnectGDrive(): Promise<{ ok: boolean; status: string }> {
  const res = await fetch('/api/backup/gdrive/disconnect', {
    method: 'POST',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || err.error || 'Google Drive 연동 해제에 실패했습니다.')
  }
  return res.json()
}

export async function saveGDriveSettings(settings: {
  client_id?: string
  client_secret?: string
  folder?: string
}): Promise<void> {
  const res = await fetch('/api/backup/gdrive/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || err.error || 'Google Drive 설정 저장에 실패했습니다.')
  }
}
