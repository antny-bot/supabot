import { Link } from 'react-router-dom'
import { ArrowRight, Cloud, Cpu, Lock, ShieldCheck, Zap } from 'lucide-react'
import PublicLayout from '../components/layout/PublicLayout'

export default function Home() {
  return (
    <PublicLayout>
      {/* Hero Section */}
      <section className="relative overflow-hidden py-20 sm:py-28">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(45rem_50rem_at_top,theme(colors.indigo.100),theme(colors.slate.50))] dark:bg-[radial-gradient(45rem_50rem_at_top,theme(colors.indigo.950),theme(colors.slate.950))] opacity-60" />
        
        <div className="mx-auto max-w-5xl px-4 sm:px-6 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50/80 px-3.5 py-1 text-xs font-semibold text-indigo-700 dark:border-indigo-900/60 dark:bg-indigo-950/60 dark:text-indigo-300 mb-6 backdrop-blur-sm">
            <Zap size={13} className="text-indigo-600 dark:text-indigo-400" />
            <span>차세대 퀀트 & 스마트 트레이딩 솔루션</span>
          </div>

          <h1 className="text-4xl font-extrabold tracking-tight sm:text-6xl text-slate-900 dark:text-white">
            지능형 자산 운용의 새로운 기준,<br className="hidden sm:inline" />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-violet-600 via-indigo-600 to-cyan-500 dark:from-violet-400 dark:via-indigo-300 dark:to-cyan-400">
              supabot
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-base sm:text-lg leading-relaxed text-slate-600 dark:text-slate-300">
            암호화폐와 국내/해외 주식을 단 하나의 대시보드에서 관리하세요. 
            정밀한 알고리즘 매매, 체계적인 리스크 제어, Google Drive를 통한 안전한 데이터 클라우드 백업을 지원합니다.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <Link
              to="/login"
              className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3.5 text-base font-semibold text-white shadow-lg shadow-indigo-600/30 hover:bg-indigo-500 hover:shadow-indigo-600/40 transition-all"
            >
              대시보드 시작하기
              <ArrowRight size={18} />
            </Link>
            <Link
              to="/terms"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white/70 px-6 py-3.5 text-base font-semibold text-slate-700 hover:bg-white dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200 dark:hover:bg-slate-800 backdrop-blur-sm transition-all"
            >
              이용약관 및 정책 확인
            </Link>
          </div>
        </div>
      </section>

      {/* Feature Grid */}
      <section className="py-16 sm:py-24 border-t border-slate-200/80 bg-white dark:border-slate-800/80 dark:bg-slate-900/50">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <h2 className="text-xs font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-2">Core Architecture</h2>
            <p className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-4xl">
              안전하고 투명한 자동화 플랫폼
            </p>
            <p className="mt-4 text-slate-600 dark:text-slate-400">
              사용자의 보안과 데이터 주권을 최우선으로 설계된 아키텍처를 제공합니다.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* Card 1 */}
            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-7 dark:border-slate-800 dark:bg-slate-900/40 hover:border-indigo-500/50 transition-colors">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600/10 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-400 mb-5">
                <Cpu size={24} />
              </div>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">멀티 마켓 통합 트레이딩</h3>
              <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                업비트(Upbit), 빗썸(Bithumb), 한국투자증권(KIS), 토스증권(Toss) 등 코인과 국내외 주식을 아우르는 실시간 전략 실행 엔진을 탑재했습니다.
              </p>
            </div>

            {/* Card 2 */}
            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-7 dark:border-slate-800 dark:bg-slate-900/40 hover:border-indigo-500/50 transition-colors">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-violet-600/10 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400 mb-5">
                <Cloud size={24} />
              </div>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">Google Drive 안전 백업</h3>
              <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                사용자의 거래 설정, 전략 템플릿, 거래 로그를 사용자 본인의 Google Drive 격리 앱 폴더(AppData)에 안전하게 암호화하여 백업 및 복원합니다.
              </p>
            </div>

            {/* Card 3 */}
            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-7 dark:border-slate-800 dark:bg-slate-900/40 hover:border-indigo-500/50 transition-colors">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-600/10 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400 mb-5">
                <ShieldCheck size={24} />
              </div>
              <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">철저한 보안 및 데이터 보호</h3>
              <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                API 키와 민감 정보는 Fernet AES 군사 등급 알고리즘으로 양방향 암호화 보관되며, Google 사용자 데이터는 어떠한 외부 제3자에게도 전달되지 않습니다.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Security & Google API Compliance Statement */}
      <section className="py-16 sm:py-20 bg-slate-50 dark:bg-slate-950">
        <div className="mx-auto max-w-4xl px-4 sm:px-6">
          <div className="rounded-2xl border border-indigo-200/80 bg-gradient-to-br from-indigo-50/70 to-purple-50/40 p-8 dark:border-indigo-900/60 dark:from-indigo-950/40 dark:to-slate-900/60">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white">
                <Lock size={20} />
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                  Google API 제한적 사용 정책(Limited Use) 준수 서약
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                  supabot은 Google API 서비스 사용자 데이터 정책(Limited Use 요건 포함)을 엄격히 준수합니다. 
                  OAuth 인증을 통해 획득한 Google Drive 접근 권한은 사용자가 명시적으로 요청한 시스템 데이터 백업 및 복원 파일 관리 용도로만 한정되어 사용되며, 
                  광고 목적의 활용, 제3자 제공, 또는 AI/머신러닝 모델의 학습 데이터로 일절 사용되지 않습니다.
                </p>
                <div className="mt-4 flex gap-4 text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                  <Link to="/privacy" className="hover:underline">개인정보처리방침 전문 보기 →</Link>
                  <Link to="/terms" className="hover:underline">이용약관 전문 보기 →</Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </PublicLayout>
  )
}
