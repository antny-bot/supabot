// -*- coding: utf-8 -*-
declare global {
  interface Window {
    google?: any
  }
}

let gsiScriptLoadingPromise: Promise<void> | null = null

export function loadGoogleGsiScript(): Promise<void> {
  if (typeof window === 'undefined') return Promise.resolve()
  if (window.google?.accounts?.oauth2) return Promise.resolve()
  if (gsiScriptLoadingPromise) return gsiScriptLoadingPromise

  gsiScriptLoadingPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[src="https://accounts.google.com/gsi/client"]')
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', (e) => reject(e))
      return
    }
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Google Identity Services 스크립트 로드에 실패했습니다.'))
    document.head.appendChild(script)
  })

  return gsiScriptLoadingPromise
}

export async function requestGoogleDriveAuthCode(clientId: string): Promise<string> {
  if (!clientId || !clientId.trim()) {
    throw new Error('Google Client ID가 설정되어 있지 않습니다. Google Cloud 콘솔에서 발급한 Client ID를 먼저 입력해주세요.')
  }

  await loadGoogleGsiScript()
  if (!window.google?.accounts?.oauth2) {
    throw new Error('Google OAuth 서비스를 초기화할 수 없습니다.')
  }

  return new Promise((resolve, reject) => {
    try {
      const client = window.google.accounts.oauth2.initCodeClient({
        client_id: clientId.trim(),
        scope: 'https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/userinfo.email',
        ux_mode: 'popup',
        callback: (response: { code?: string; error?: string; error_description?: string }) => {
          if (response.error) {
            reject(new Error(response.error_description || response.error || 'Google 계정 인증이 취소되었습니다.'))
          } else if (response.code) {
            resolve(response.code)
          } else {
            reject(new Error('Google 인증 코드를 수신하지 못했습니다.'))
          }
        },
      })
      client.requestCode()
    } catch (err: any) {
      reject(err)
    }
  })
}
