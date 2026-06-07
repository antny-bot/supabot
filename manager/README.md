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
| `pages/` | 11개 페이지: Dashboard, Orders, Trades, Templates, Reports, Events, Users, Admin, Config, Login, Analytics |
| `components/layout/` | AppLayout, Sidebar, TopBar, BottomNav, AllMenuDrawer — 데스크톱/모바일 레이아웃 전환 |
| `components/settings/` | DisplaySettingsCard, MfaSettingsCard, ProfileSettingsCard |
| `components/ui/` | 공통 UI 빌딩블록: Button, Badge, Spinner, StatCard, PageHeader, ErrorBanner, FilterBar 등 |
| `api/` | 라우터별 REST 클라이언트 — 아래 백엔드 라우터 표와 1:1 대응 (예: `api/orders.ts` ↔ `routers/orders.py`) |
| `hooks/`, `contexts/` | useAuth, useTheme, usePersistedState, useRealtime / AuthContext |
| `lib/`, `config/` | displayPreferences·navPreferences (localStorage 동기화), `pageMeta.ts` (네비게이션·아이콘 단일 소스) |
| `types/`, `utils/` | 공유 TypeScript 타입, 포매터 |

## 라우터 / 라우트

`manager/backend/routers/` 10개 라우터로 구성된다.

| 라우터 | 주요 라우트 | 비고 |
|--------|------------|------|
| `dashboard` | `GET /api/dashboard` | admin: 전체 통계 / user: 개인 통계 |
| `users` | `GET /api/users`, approve/deactivate/activate/block/DELETE | admin only |
| `orders` | `GET /api/orders` | status·exchange 필터, 페이지네이션 |
| `trades` | `GET /api/trades` | 기간 필터, 거래소·전략별 집계 |
| `events` | `GET /api/events`, PATCH read/archive | admin only |
| `sysconfig` | `GET /api/sysconfig`, `POST /api/sysconfig` | admin only |
| `reports` | `GET /api/reports/{pnl,strategy,roi-ranking,monthly,holdings,pairs,win-stats}` | PnL·보유자산·승률 분석 |
| `templates` | `GET/POST/PATCH/DELETE /api/templates`, execute | 전략 템플릿 CRUD·실행 |
| `mfa` | MFA 설정·검증 | — |
| `analytics` | `GET /api/analytics/{overview,activity,commands,users,heatmap}` | admin only, 사용 분석 |

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

Supabase 대시보드 → Authentication → Users → Add user 로 이메일+비밀번호 계정 생성
(Auto Confirm 체크). 이 계정으로 manager에 로그인한다.

## 로컬 테스트

```bash
cd manager
pip install -r requirements.txt
cp .env.template .env   # 값 채우기
uvicorn backend.main:app --reload --port 8000
```
