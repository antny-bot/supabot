import { type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Monitor, Moon, Shield, Sun, Zap } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'

interface PublicLayoutProps {
  children: ReactNode
}

export default function PublicLayout({ children }: PublicLayoutProps) {
  const { theme, toggle } = useTheme()

  return (
    <div className="font-app-ui min-h-screen bg-slate-50 text-slate-800 dark:bg-slate-950 dark:text-slate-100 flex flex-col selection:bg-indigo-500 selection:text-white">
      {/* Navigation Header */}
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/80 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-900/80">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/home" className="flex items-center gap-2.5 transition-opacity hover:opacity-90">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-violet-600 to-indigo-600 shadow-md shadow-violet-500/25">
              <Zap size={20} className="text-white" />
            </div>
            <span className="text-lg font-bold tracking-tight text-slate-900 dark:text-white">
              supabot
            </span>
          </Link>

          <nav className="flex items-center gap-1 sm:gap-4 text-sm font-medium">
            <Link
              to="/home"
              className="rounded-lg px-2.5 py-1.5 text-slate-600 hover:text-indigo-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:text-indigo-400 dark:hover:bg-slate-800/60 transition-colors"
            >
              소개
            </Link>
            <Link
              to="/terms"
              className="rounded-lg px-2.5 py-1.5 text-slate-600 hover:text-indigo-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:text-indigo-400 dark:hover:bg-slate-800/60 transition-colors"
            >
              이용약관
            </Link>
            <Link
              to="/privacy"
              className="rounded-lg px-2.5 py-1.5 text-slate-600 hover:text-indigo-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:text-indigo-400 dark:hover:bg-slate-800/60 transition-colors"
            >
              개인정보처리방침
            </Link>

            <button
              type="button"
              onClick={toggle}
              aria-label="화면 모드 전환"
              className="ml-1 rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 transition-colors"
            >
              {theme === 'light' && <Sun size={17} />}
              {theme === 'dark' && <Moon size={17} />}
              {theme === 'system' && <Monitor size={17} />}
            </button>

            <Link
              to="/login"
              className="ml-2 inline-flex items-center justify-center rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 transition-colors"
            >
              대시보드 로그인
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1">
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-10 dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="flex flex-col items-center justify-between gap-6 sm:flex-row">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-indigo-600">
                <Zap size={14} className="text-white" />
              </div>
              <span className="font-semibold text-slate-800 dark:text-slate-200">supabot</span>
              <span className="text-xs text-slate-400 dark:text-slate-500">| 스마트 퀀트 트레이딩 및 자산 관리 플랫폼</span>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-6 text-xs text-slate-500 dark:text-slate-400">
              <Link to="/home" className="hover:text-indigo-600 dark:hover:text-indigo-400">서비스 소개</Link>
              <Link to="/terms" className="hover:text-indigo-600 dark:hover:text-indigo-400">서비스 이용약관</Link>
              <Link to="/privacy" className="hover:text-indigo-600 dark:hover:text-indigo-400 font-semibold text-slate-700 dark:text-slate-300">개인정보처리방침</Link>
              <a href="mailto:support@supabot.app" className="hover:text-indigo-600 dark:hover:text-indigo-400">문의: support@supabot.app</a>
            </div>
          </div>

          <div className="mt-8 border-t border-slate-100 pt-6 text-center text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
            <p className="flex items-center justify-center gap-1.5 mb-2">
              <Shield size={14} className="text-indigo-500" />
              <span>Google API 사용자 데이터 정책 및 제한적 사용 요건(Limited Use)을 엄격히 준수합니다.</span>
            </p>
            <p>© {new Date().getFullYear()} supabot. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
