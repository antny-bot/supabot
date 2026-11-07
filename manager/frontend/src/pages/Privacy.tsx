import PublicLayout from '../components/layout/PublicLayout'
import { ShieldCheck } from 'lucide-react'

export default function Privacy() {
  return (
    <PublicLayout>
      <div className="py-12 sm:py-16">
        <div className="mx-auto max-w-4xl px-4 sm:px-6">
          {/* Header */}
          <div className="border-b border-slate-200 pb-8 dark:border-slate-800">
            <span className="text-xs font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
              Legal & Privacy
            </span>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white sm:text-4xl">
              개인정보처리방침 (Privacy Policy)
            </h1>
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
              최종 수정일: 2026년 11월 7일 | 시행일: 2026년 11월 7일
            </p>
          </div>

          {/* Content */}
          <div className="prose prose-slate dark:prose-invert mt-8 max-w-none text-slate-700 dark:text-slate-300 space-y-8 text-sm sm:text-base leading-relaxed">
            <section>
              <p>
                <strong>supabot</strong>(이하 &quot;서비스&quot; 또는 &quot;당사&quot;)은 이용자의 개인정보를 소중하게 생각하며, 
                「개인정보 보호법」 및 관련 법령, 그리고 Google API 서비스 사용자 데이터 정책(Google API Services User Data Policy)을 
                준수하여 이용자의 권익을 보호하고 개인정보와 관련된 고충을 원활하게 처리할 수 있도록 다음과 같은 처리방침을 두고 있습니다.
              </p>
            </section>

            {/* Google API Limited Use Policy Highlight */}
            <section className="rounded-2xl border border-indigo-200 bg-indigo-50/60 p-6 dark:border-indigo-900/60 dark:bg-indigo-950/40">
              <div className="flex items-start gap-3">
                <ShieldCheck className="h-6 w-6 shrink-0 text-indigo-600 dark:text-indigo-400 mt-0.5" />
                <div>
                  <h2 className="text-base font-bold text-slate-900 dark:text-white m-0">
                    Google API 사용자 데이터 정책 및 제한적 사용 요건(Limited Use) 공지
                  </h2>
                  <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">
                    supabot의 Google API 수신 정보 사용 및 다른 앱으로의 전송은 제한적 사용(Limited Use) 요건을 포함한{' '}
                    <a
                      href="https://developers.google.com/terms/api-services-user-data-policy"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-indigo-600 underline dark:text-indigo-400 font-semibold"
                    >
                      Google API 서비스 사용자 데이터 정책
                    </a>
                    을 준수합니다.
                  </p>
                  <p className="mt-2 text-xs font-mono bg-white/70 dark:bg-slate-900/60 p-3 rounded-lg border border-slate-200/80 dark:border-slate-800">
                    &quot;supabot&apos;s use and transfer to any other app of information received from Google APIs will adhere to the Google API Services User Data Policy, including the Limited Use requirements.&quot;
                  </p>
                </div>
              </div>
            </section>

            {/* 제1조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제1조 (수집하는 개인정보 항목 및 수집 방법)</h2>
              <p>당사는 서비스 제공을 위해 최소한의 개인정보를 수집하며, 구체적인 항목은 다음과 같습니다:</p>
              <ul className="list-disc pl-5 space-y-1.5 text-sm sm:text-base">
                <li>
                  <strong>Google OAuth 연동 시:</strong> 이메일 주소(Email), 프로필 식별자(ID), 이름/닉네임
                </li>
                <li>
                  <strong>Google Drive 연동 시:</strong> 사용자의 Google Drive 애플리케이션 전용 폴더(AppData) 내 백업 파일 접근 권한 (서비스 내 설정 파일, 템플릿, 거래 로그 백업 용도)
                </li>
                <li>
                  <strong>서비스 설정 시 (사용자 직접 입력):</strong> 거래소 API 키(Access Key/Secret Key - 서버 내 AES 암호화 보관), 텔레그램 연동 Chat ID
                </li>
                <li>
                  <strong>자동 생성 정보:</strong> 접속 로그, IP 주소, 서비스 이용 기록, 세션 쿠키
                </li>
              </ul>
            </section>

            {/* 제2조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제2조 (개인정보의 이용 목적)</h2>
              <p>수집된 정보는 다음 목적에 한해서만 이용됩니다:</p>
              <ol className="list-decimal pl-5 space-y-1.5 text-sm sm:text-base">
                <li><strong>사용자 식별 및 대시보드 로그인 인증:</strong> Google OAuth 및 관리자 인증을 통한 안전한 대시보드 접근 통제</li>
                <li><strong>데이터 백업 및 복원:</strong> 사용자가 요청한 자동매매 전략 템플릿 및 시스템 구성의 사용자 개인 Google Drive 저장 및 복원</li>
                <li><strong>거래 및 알림 서비스 제공:</strong> 사용자가 설정한 전략 실행 상태 모니터링 및 비정상 거래 알림 발송</li>
                <li><strong>보안 및 시스템 안정성 확보:</strong> 부정 이용 방지, 비인가 접속 감지 및 보안 감사 로그 보관</li>
              </ol>
            </section>

            {/* 제3조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제3조 (개인정보의 보유 및 파기)</h2>
              <p>
                당사는 원칙적으로 개인정보의 수집 및 이용 목적이 달성되면 해당 정보를 지체 없이 파기합니다.
              </p>
              <ul className="list-disc pl-5 space-y-1.5 text-sm sm:text-base">
                <li><strong>보유 기간:</strong> 이용자의 서비스 이용 해지(탈퇴) 또는 Google 연동 해제 시까지 보관하며, 요청 즉시 시스템 및 데이터베이스에서 완전 삭제합니다.</li>
                <li><strong>파기 절차:</strong> 전자적 파일 형태의 정보는 기록을 재생할 수 없는 기술적 방법을 사용하여 영구 삭제합니다.</li>
              </ul>
            </section>

            {/* 제4조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제4조 (개인정보의 제3자 제공 및 위탁 금지)</h2>
              <p>
                당사는 이용자의 사전 동의 없이 개인정보를 외부에 제공하거나 판매하지 않습니다.
              </p>
              <ul className="list-disc pl-5 space-y-1.5 text-sm sm:text-base">
                <li>이용자의 개인 데이터 및 Google 사용자 데이터를 제3자 광고 플랫폼, 데이터 브로커 등에 일절 판매하거나 제공하지 않습니다.</li>
                <li>Google Drive를 통해 동기화되는 백업 데이터는 인공지능(AI)이나 대규모 언어 모델(LLM)의 일반 학습용 데이터로 사용되지 않습니다.</li>
              </ul>
            </section>

            {/* 제5조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제5조 (개인정보의 기술적·관리적 보호 조치)</h2>
              <p>당사는 이용자의 개인정보를 안전하게 보호하기 위해 다음과 같은 조치를 취하고 있습니다:</p>
              <ul className="list-disc pl-5 space-y-1.5 text-sm sm:text-base">
                <li><strong>암호화:</strong> 거래소 API 키 및 민감한 토큰 정보는 Fernet AES 기반 군사 등급 알고리즘으로 양방향 암호화되어 안전하게 데이터베이스에 격리 저장됩니다.</li>
                <li><strong>보안 통신:</strong> 모든 네트워크 통신은 최신 TLS/HTTPS 암호화 프로토콜을 적용하여 데이터 전송 중 가로채기를 방지합니다.</li>
                <li><strong>2차 인증(MFA):</strong> 무단 침입을 방지하기 위한 OTP 기반 2단계 인증 체계를 갖추고 있습니다.</li>
              </ul>
            </section>

            {/* 제6조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제6조 (이용자의 권리와 행사 방법)</h2>
              <p>
                이용자는 언제든지 자신의 개인정보를 조회, 수정, 삭제 요청할 수 있으며, 
                Google 계정 보안 설정(<a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener noreferrer" className="text-indigo-600 underline dark:text-indigo-400">구글 계정 권한 관리</a>)에서 언제든지 supabot에 부여한 접근 권한을 즉시 취소할 수 있습니다.
              </p>
            </section>

            {/* 제7조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제7조 (개인정보 보호책임자 및 문의처)</h2>
              <p>서비스 이용 중 발생하는 개인정보 보호 관련 민원은 아래의 보호책임자에게 문의하실 수 있습니다:</p>
              <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
                <p className="font-semibold text-slate-900 dark:text-white">supabot 개인정보 보호 담당 부서</p>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                  이메일: <a href="mailto:privacy@supabot.app" className="text-indigo-600 underline dark:text-indigo-400">privacy@supabot.app</a> / <a href="mailto:support@supabot.app" className="text-indigo-600 underline dark:text-indigo-400">support@supabot.app</a>
                </p>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                  응답 가능 시간: 평일 10:00 ~ 18:00 (KST)
                </p>
              </div>
            </section>
          </div>
        </div>
      </div>
    </PublicLayout>
  )
}
