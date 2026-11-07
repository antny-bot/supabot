import PublicLayout from '../components/layout/PublicLayout'
import { AlertTriangle } from 'lucide-react'

export default function Terms() {
  return (
    <PublicLayout>
      <div className="py-12 sm:py-16">
        <div className="mx-auto max-w-4xl px-4 sm:px-6">
          {/* Header */}
          <div className="border-b border-slate-200 pb-8 dark:border-slate-800">
            <span className="text-xs font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
              Legal & Terms
            </span>
            <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white sm:text-4xl">
              서비스 이용약관 (Terms of Service)
            </h1>
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
              최종 수정일: 2026년 11월 7일 | 시행일: 2026년 11월 7일
            </p>
          </div>

          {/* Content */}
          <div className="prose prose-slate dark:prose-invert mt-8 max-w-none text-slate-700 dark:text-slate-300 space-y-8 text-sm sm:text-base leading-relaxed">
            {/* Disclaimer Alert */}
            <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-6 dark:border-amber-900/60 dark:bg-amber-950/40">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-6 w-6 shrink-0 text-amber-600 dark:text-amber-400 mt-0.5" />
                <div>
                  <h2 className="text-base font-bold text-amber-950 dark:text-amber-200 m-0">
                    투자 위험 고지 및 금융 면책 조항 (Investment Risk Disclaimer)
                  </h2>
                  <p className="mt-2 text-sm text-amber-900 dark:text-amber-300 leading-relaxed">
                    supabot은 사용자가 직접 설정한 전략에 따라 거래를 보조하는 소프트웨어 도구이며, 
                    어떠한 경우에도 투자 권유나 재정적 조언을 제공하지 않습니다. 
                    암호화폐 및 주식 거래는 높은 시장 변동성으로 인해 원금 손실 위험이 수반되며, 
                    모든 투자 판단과 그에 따른 손익 책임은 전적으로 이용자 본인에게 귀속됩니다.
                  </p>
                </div>
              </div>
            </section>

            {/* 제1조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제1조 (목적)</h2>
              <p>
                본 약관은 supabot(이하 &quot;서비스&quot;)이 제공하는 통합 퀀트 트레이딩 관리 대시보드 및 자동화 보조 소프트웨어의 
                이용 조건, 절차, 권리 및 의무, 책임 사항을 규정함을 목적으로 합니다.
              </p>
            </section>

            {/* 제2조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제2조 (용어의 정의)</h2>
              <ol className="list-decimal pl-5 space-y-1.5 text-sm sm:text-base">
                <li>&quot;서비스&quot;라 함은 supabot이 제공하는 웹 대시보드, 주문 체결 자동화 엔진, 포트폴리오 모니터링 시스템 일체를 의미합니다.</li>
                <li>&quot;이용자&quot;라 함은 본 약관에 동의하고 서비스를 이용하는 회원을 의미합니다.</li>
                <li>&quot;외부 거래소&quot;라 함은 이용자가 연동하여 주문을 집행하는 암호화폐 거래소(업비트, 빗썸 등) 및 증권사(한국투자증권, 토스증권 등)를 의미합니다.</li>
              </ol>
            </section>

            {/* 제3조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제3조 (약관의 효력 및 변경)</h2>
              <p>
                1. 본 약관은 서비스 화면에 게시함으로써 효력이 발생합니다.<br />
                2. 서비스는 관계 법령을 위배하지 않는 범위에서 약관을 개정할 수 있으며, 개정된 약관은 적용일 최소 7일 전 서비스 내 공지합니다.
              </p>
            </section>

            {/* 제4조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제4조 (계정 및 외부 연동 관리)</h2>
              <p>
                1. 이용자는 본인의 Google OAuth 계정, 거래소 API Key, Secret Key를 안전하게 관리할 책임이 있습니다.<br />
                2. 거래소 API Key 발급 시에는 반드시 출금 권한을 제외한 &quot;조회 및 주문(매수/매도)&quot; 권한만을 부여하여 등록하여야 합니다.<br />
                3. 이용자의 관리 소홀이나 제3자의 부정 사용으로 인하여 발생하는 결과에 대하여 당사는 고의 또는 중과실이 없는 한 책임을 지지 않습니다.
              </p>
            </section>

            {/* 제5조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제5조 (Google 서비스 연동)</h2>
              <p>
                1. 서비스는 이용자의 편의를 위하여 Google OAuth 인증 및 Google Drive 백업 연동 기능을 제공합니다.<br />
                2. 이용자는 Google 연동 시 Google의 서비스 약관 및 정책을 준수해야 하며, 당사는 Google API 서비스 정책을 철저히 준수합니다.<br />
                3. 구글 계정 보안 관리 페이지를 통해 이용자는 언제든 서비스 연동을 해제할 수 있습니다.
              </p>
            </section>

            {/* 제6조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제6조 (면책 조항 및 책임의 한계)</h2>
              <p>
                1. 당사는 천재지변, 기간통신사업자의 회선 장애, 외부 거래소의 전산 장애 또는 API 호출 제한(Rate Limit), 
                시장 유동성 부족으로 인한 체결 지연(슬리피지) 등으로 인한 손해에 대하여 책임을 지지 않습니다.<br />
                2. 이용자가 설정한 자동매매 전략 수치(진입 조건, 분할 매수/매도 비율, 손절선 등)에 대한 판단과 그로 인해 발생하는 모든 재정적 손실은 
                전적으로 이용자 자신의 책임입니다.<br />
                3. 서비스는 과거의 수익률이나 특정 전략의 성공을 보장하지 않습니다.
              </p>
            </section>

            {/* 제7조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제7조 (서비스의 변경 및 중단)</h2>
              <p>
                당사는 시스템 정기 점검, 하드웨어 교체, 긴급 보안 패치 등 불가피한 사유가 있는 경우 서비스의 일부 또는 전부를 일시적으로 중단할 수 있습니다.
              </p>
            </section>

            {/* 제8조 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">제8조 (준거법 및 분쟁 해결)</h2>
              <p>
                본 약관의 해석 및 당사와 이용자 간의 분쟁에 대하여는 대한민국 법률을 준거법으로 하며, 
                분쟁 발생 시 관할 법원은 민사소송법에 따른 법원으로 합니다.
              </p>
            </section>

            {/* 문의처 */}
            <section className="space-y-3">
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">문의 및 고객 지원</h2>
              <p>
                서비스 이용 및 약관 관련 문의는 <a href="mailto:support@supabot.app" className="text-indigo-600 underline dark:text-indigo-400">support@supabot.app</a>으로 연락주시기 바랍니다.
              </p>
            </section>
          </div>
        </div>
      </div>
    </PublicLayout>
  )
}
