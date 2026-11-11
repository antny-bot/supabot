# supabot-manager

봇과 Supabase DB를 공유하는 관리 웹 대시보드 (FastAPI + React/TypeScript).
Synology Docker에 배포한다. 봇과 직접 의존하지 않으며, Telegram 알림이 필요할 때만
봇의 `/internal/notify`(포트 8765)를 단방향 호출한다.

프론트엔드는 `manager/frontend/`의 React SPA(Vite + Tailwind + Recharts)이며,
`npm run build`로 빌드한 `dist/`를 FastAPI가 정적 파일로 서빙한다.
(`manager/frontend/templates/*.html`은 과거 Jinja2/HTMX 시절의 잔재로 더 이상 렌더링되지 않는 죽은 코드다.)

## 프론트엔드 구조 (`manager/frontend/src/`)

페이지·컴포넌트 작업 전 **`manager/frontend/DESIGN.md`**(페이지 헤더·아이콘·공통 컴포넌트·반응형 레이아웃 규칙) 필독.

| 디렉터리 | 내용 |
|---|---|
| `pages/` | 공개 페이지(Home, Terms, Privacy, Login) 및 대시보드 페이지(Dashboard, Operations, Orders, Trades, Templates, Reports, Admin, Config) + `admin/`(`AdminBackupTab`, `AdminFeedbacksTab`), `reports/`(`DailySnapshotSection`, `TopRotationSection`, `BudgetPlanSection`, `NlLogsSection` 등) |
| `components/layout/` | AppLayout(인증), PublicLayout(공개 헤더/푸터), Sidebar, TopBar, BottomNav, AllMenuDrawer — 공개/인증 및 데스크톱/모바일 레이아웃 전환 |
| `components/backup/` | BackupHealthCard — 대시보드 및 관리자 화면용 백업 스케줄러 상태 카드 |
| `components/settings/` | DisplaySettingsCard, MfaSettingsCard, ProfileSettingsCard (닉네임·표시 시간대 설정) |
| `components/ui/` | 공통 UI 빌딩블록: Button, Badge, Spinner, StatCard, PageHeader, ErrorBanner, FilterBar, FormattedNumberInput, TimePickerInput 등 |
| `api/` | 라우터별 REST 클라이언트 — 아래 백엔드 라우터 표와 1:1 대응 (예: `api/orders.ts` ↔ `routers/orders.py`) |
| `hooks/`, `contexts/` | useAuth, useTheme, usePersistedState, useRealtime / AuthContext |
| `lib/`, `config/` | displayPreferences·navPreferences (localStorage 동기화), `dateUtils.ts` (전역 타임존 포맷팅), `pageMeta.ts` (네비게이션·아이콘 단일 소스) |
| `types/`, `utils/` | 공유 TypeScript 타입, 포매터 |

### 프론트엔드 라우트 구성

#### 공개 페이지 (Public Pages — `PublicLayout`)
로그인 여부와 무관하게 접근 가능한 공개 페이지:
- **랜딩페이지 (`/home`)**: 서비스 소개, 핵심 기능(차세대 퀀트 & 스마트 트레이딩, 리스크 제어, Google Drive 클라우드 백업 등) 안내 및 시작하기 링크
- **이용약관 (`/terms`)**: 서비스 이용 조건 및 권리·의무, 투자 위험 고지 및 금융 면책 조항(Investment Risk Disclaimer) 명시 (`/terms-of-service` 리다이렉트 지원)
- **개인정보처리방침 (`/privacy`)**: 개인정보 수집/이용/보관 방침 및 Google API 서비스 사용자 데이터 정책(Limited Use 요건 준수) 명시 (`/privacy-policy` 리다이렉트 지원)
- **로그인 (`/login`)**: Supabase 이메일/비밀번호 로그인, Google OAuth 소셜 로그인, 2단계 인증(MFA) 지원

#### 보호된 페이지 (Protected Pages — `AppLayout`)
로그인 인증(Supabase Auth)이 필요한 대시보드 및 운영 페이지:
- `/dashboard`: 종합 자산 및 포트폴리오 요약 (백업 스케줄러 Health Card 포함)
- `/operations`: 운용 현황 및 전략 실시간 모니터링 (TOP N 순환 운용 현황, 일단위 스냅샷 차트 `DailySnapshotSection`, 예산·감사원장, 체결 타임라인; `/strategy-monitor` 리다이렉트 지원)
- `/orders`: 주문 목록 조회 및 취소/동기화/배치 묶음 관리
- `/trades`: 체결 내역 조회 및 통계
- `/templates`: 매매 전략 템플릿 관리(생성/복제/실행)
- `/reports`: 손익(PnL), 승률, 보유 자산 등 정밀 분석 보고서 (12개 시트 탭)
- `/admin`: 관리자 전용 대시보드 (대시보드, 사용 분석/Analytics, 유저관리, 피드백, 이벤트, 주문 및 신호 주기, 종목 캐시, NL 로그, 데이터 백업/Google Drive OAuth)
- `/config`: 사용자 설정(화면 표시, 프로필[닉네임·표시 시간대], 보안[MFA])

## 라우터 / 라우트

`manager/backend/routers/` 13개 라우터로 구성된다.

| 라우터 | 주요 라우트 | 비고 |
|--------|------------|------|
| `dashboard` | `GET /api/dashboard`, `GET /admin/dashboard` | admin: 전체 통계 / user: 개인 통계 + 백업 헬스 지표(`backup_health`) |
| `users` | `GET /api/users`, approve/deactivate/activate/block/DELETE, `PATCH .../email`, `POST .../invite-auth-account`, `POST .../reset-auth-password` | admin only |
| `orders` | `GET /api/orders`, `POST .../{uuid}/cancel`·`/sync`·`/force-update` | status·exchange 필터, 페이지네이션. cancel은 거래소 취소(실거래) |
| `trades` | `GET /api/trades` | 기간 필터, 거래소·전략별 집계 |
| `events` | `GET /api/events`, PATCH `read`/`unread`/`archive`/`unarchive` | admin only |
| `sysconfig` | `GET /api/sysconfig`, `POST /api/sysconfig` | admin only |
| `reports` | `GET /api/reports/{pnl,daily,monthly,strategy,exchange,roi-ranking,holdings,pairs,win-stats,drawdown,allocation,batches,top-rotation,strategy-detail,nl-logs}`, `POST /api/reports/top-rotation/backtest-compare`, `GET /api/nl-logs` | PnL·보유자산·승률·TOP N 일단위 스냅샷·NL 로그 멀티턴 도구 체인 분석. nl-logs는 admin only |
| `templates` | `GET/POST/PATCH/DELETE /api/templates`, `duplicate`, `execute`, `holding`, `stop`, `topup`, `budget-plan`, `budget-reset`, `budget-ledger` | 전략 템플릿 CRUD·복제·실행·예산 플랜/원장 |
| `mfa` | `POST /api/login/mfa`, `/api/mfa/{setup,enable,disable}` | MFA 설정·검증 |
| `analytics` | `GET /api/analytics/{overview,activity,commands,users,heatmap}` | admin only, 사용 분석 |
| `stock_cache` | `GET/POST /api/stock-cache`, `DELETE .../{name}`, `POST .../upload`·`/refresh`, `GET .../export` | admin only. KRX 종목명↔코드 캐시(`kr_stock_cache`) CRUD·CSV 입출력·FinanceDataReader 일괄 갱신 |
| `feedbacks` | `POST /api/feedbacks`, `GET/PATCH/DELETE /api/feedbacks/my`, `GET/PATCH/DELETE /api/admin/feedbacks` | 사용자 피드백/오류 보고 및 관리자 처리 |
| `backup` | `GET/POST /api/backup/{config,status,trigger,health}`, `GET /api/backup/download/{filename}`, `GET/POST /api/backup/gdrive/{status,connect,disconnect,settings}` | 백업 스케줄·보존 설정, 즉시 백업, 로컬/원격 ZIP 다운로드, Google Drive 웹 OAuth 연동 (`health` 외 admin only) |

### Analytics 엔드포인트 상세

| 엔드포인트 | 반환 | 데이터 소스 |
|-----------|------|------------|
| `GET /api/analytics/overview` | DAU / WAU / MAU / 30일 명령 수 | daily + today raw |
| `GET /api/analytics/activity?days=30` | 날짜별 명령 건수 배열 | daily + today raw |
| `GET /api/analytics/commands?period=7d` | 명령어별 빈도 상위 15 | daily + today raw |
| `GET /api/analytics/users?period=7d` | 유저별 명령 수·마지막 활동 | daily + today raw |
| `GET /api/analytics/heatmap` | 7×24 요일×시간 matrix (최근 90일) | daily + today raw |

Analytics는 `command_log_daily`(집계 요약)와 `command_logs`(오늘 raw)를 union해 항상 오늘 데이터까지 포함한다.

### Analytics 데이터 파이프라인

```
[봇 command_logs]  ──→  Supabase pg_cron (매일 01:00 KST)
  raw 로그 1일 보관        aggregate_command_logs_daily()
                                    │
                                    ▼
                         [command_log_daily]  ← Analytics 읽기
                           영구 집계 보관
```

pg_cron 활성화 및 스케줄 등록은 `shared/schema.sql` 하단 주석 참조.

## Synology 배포 순서

1. **이미지 빌드** — `manager/**` 변경이 `main`에 머지되면 GitHub Actions가
   `ghcr.io/antny-bot/supabot-manager:latest` 를 빌드·push 한다.

2. **GHCR 접근** — 패키지를 Public으로 전환하거나, private 유지 시 PAT(`read:packages`)로 로그인:
   ```bash
   echo "<GITHUB_PAT>" | docker login ghcr.io -u <github_user> --password-stdin
   ```

3. **배포 폴더 + `.env`** — 예: `/volume1/docker/supabot-manager/` 에 `.env.template`을
   복사해 `.env` 작성:
   ```
   SUPABASE_URL=https://<project>.supabase.co
   SUPABASE_SERVICE_KEY=<service_role 키>
   SUPABASE_ANON_KEY=<anon public 키>
   SESSION_SECRET=<python3 -c "import secrets; print(secrets.token_hex(32))">
   BOT_NOTIFY_URL=http://<Oracle VM 공인 IP>:8765
   MANAGER_API_KEY=<봇 config/.env의 MANAGER_API_KEY와 동일>
   ```

4. **실행** — 같은 폴더에 `docker-compose.yml`을 두고:
   ```bash
   docker compose up -d
   ```
   (DSM GUI 사용 시: 이미지 pull → 포트 `8000:8000` 매핑 → 환경변수 입력 → 실행)

5. **방화벽** — Oracle VCN Security List에서 Synology 공인 IP만 8765 Ingress 허용.

6. **확인** — `http://<Synology IP>:8000` → Supabase Auth 계정으로 로그인 → 유저 목록.

## 관리자 계정

최초 관리자 계정은 Supabase 대시보드 → Authentication → Users → Add user 로
이메일+비밀번호 계정 생성 후 (Auto Confirm 체크) `users.is_admin=true`, `manager_email`을
연결해 만든다. 이 계정으로 manager에 로그인한다.

이후 추가 사용자의 로그인 계정은 `/admin/users` 화면에서 `manager_email` 연결 후
`초대 메일 발송` 버튼으로 만들 수 있다 (`POST /api/users/{user_id}/invite-auth-account`,
Supabase Auth invite API 호출 → 사용자에게 비밀번호 설정 메일 발송, 성공 시 `manager_invited_at`
기록). SMTP/이메일 템플릿이 설정되어 있어야 메일이 실제로 발송된다.

초대를 이미 보낸 사용자(= `manager_invited_at` 존재)는 같은 자리의 버튼이
`비밀번호 재설정`으로 바뀌며, `POST /api/users/{user_id}/reset-auth-password`
(Supabase Auth recover API 호출)로 비밀번호 재설정 메일을 다시 보낼 수 있다.
중복 초대 메일 발송은 백엔드에서 차단된다.

## 로컬 테스트

```bash
cd manager
pip install -r requirements.txt
cp .env.template .env   # 값 채우기
uvicorn backend.main:app --reload --port 8000
```
