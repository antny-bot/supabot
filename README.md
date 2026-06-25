# TTBot (Telegram Trading Bot)

Oracle Cloud VM Docker 환경에서 24시간 무중단 구동되는 **멀티유저 & 멀티거래소 통합 자동매매 봇**입니다. 단순한 주문 도구를 넘어, 지능형 알고리즘과 실시간 동기화 엔진을 갖춘 전문 트레이딩 시스템입니다.

## 🧭 시스템 구성

봇과 관리 도구는 **Supabase PostgreSQL을 공유 데이터 레이어로** 사용하는 두 개의 독립 컴포넌트로 분리되어 있습니다. 봇은 manager 없이도 완전히 동작하며, manager는 확장(관리 UI)에 불과합니다.

```
   [Oracle Cloud VM]                  [Supabase]                [Synology NAS]
   supabot (Telegram Bot)  ◄────────► PostgreSQL DB ◄────────►  supabot-manager
     · 주문 실행/추적                   공유 데이터 레이어            (FastAPI + HTMX 웹)
     · 시그널 알림                      users, orders,              · 유저 승인/차단/삭제
     · /internal/notify ◄───────────── trade_logs, nl_logs,        · 주문/거래/이벤트 모니터링
          (Telegram 전송 위임)          operational_events,         · system_config 편집
                                       system_config
```

- **봇 → Supabase 직접 read/write** (DB 장애 시 `data/*.json` 파일로 폴백)
- **manager → Supabase 직접 read/write** + Telegram 알림이 필요할 때만 봇의 `/internal/notify`를 단방향 호출
- 모노레포 구조: 봇은 `src/`, 관리 UI는 `manager/`, 공유 스키마는 `shared/schema.sql`

> manager 배포·사용법은 [`manager/README.md`](manager/README.md)를 참조하세요.
> 새 사용자 등록·승인·manager 로그인 절차는 [`docs/user-onboarding.md`](docs/user-onboarding.md)를 참조하세요.

## 새 사용자 시작하기

새 사용자가 `supabot`을 쓰기 시작하는 기본 순서는 아래와 같습니다.

1. 사용자가 텔레그램에서 봇에게 `/start`를 보냅니다.
2. 봇이 사용자를 등록하고 관리자 승인 대기 상태로 넣습니다.
3. 관리자가 `supabot-manager`에서 해당 사용자를 `active`로 승인합니다.
4. 사용자가 텔레그램 봇 기능을 사용합니다.
5. 웹 대시보드도 필요하면 관리자가 `manager_email`을 연결하고 Supabase Auth 계정을 만든 뒤 manager 로그인을 열어줍니다.

상세 절차와 운영 체크리스트는 [`docs/user-onboarding.md`](docs/user-onboarding.md)에 정리되어 있습니다.

## 🚀 주요 특징

- **지능형 RSI 순환 매매:** 하단 RSI에서 매집하고 상단 RSI에서 자동 익절하는 `/rsitrade` 전략 지원.
- **실시간 주문 동기화:** 거래소 앱/웹에서 직접 조작한 주문도 1분 이내에 감지하여 봇의 추적 목록을 자동 최신화.
- **전략 대시보드:** 가동 중인 모든 트레이딩 전략을 거래소별로 그룹화하고 진행률(🔵⚪)로 시각화하여 브리핑.
- **Gemini 자연어 명령:** 텔레그램 일반 문장을 기존 명령 의도로 해석합니다. 안전한 조회 표현은 룰 기반 전처리로 즉시 처리하고, 나머지는 Gemini가 해석합니다. 주문/설정 변경은 확인 버튼을 거칩니다.
- **견고한 예외 처리:** 
  - **부분 체결 대응:** 주문이 일부만 체결되어도 즉시 물량을 파악하여 후속 대응(익절 등) 가동.
  - **자동 복구 시스템:** 봇 재시작 시 꼬인 주문 상태를 전수 조사하여 중단된 전략을 자동으로 복구.
  - **수익 보장 버퍼:** 수수료와 슬리피지를 고려한 0.1% 가격 보정을 통해 확실한 체결 유도.
- **통합 거래소 지원:** 업비트(Upbit CLI), 빗썸(Bithumb V2 API), 한국투자증권(KIS Open API), 토스증권(Toss Open API) 및 한글 명령어 지원.
- **친절한 상세 가이드:** 모든 명령어 뒤에 `-h`, `-help`, `--help`를 붙여 상세 사용법과 예시를 즉시 확인 가능.

## 📜 주요 명령어 안내

모든 명령어는 `/[명령어] -h`를 통해 상세 가이드를 볼 수 있습니다.

### 1. 기본 및 설정
- `/start` : 시스템 접속 및 메뉴 확인 (최초 접속 시 관리자 승인 필요)
- `/status` : **(NEW)** 가동 중인 트레이딩 전략 통합 대시보드 확인
- `/config` : 거래소별 API 키 설정 및 자동 유효성 검증
- `/config -v` : API 키 상태, RSI 기준, Gemini 자연어 설정 상태 확인
- `/whoami` : 내 Telegram ID, 권한, 활성 상태, 기본 거래소, 자연어 상태 확인 (`/me` alias 지원)
- `/help` : 전체 명령어 사용 설명서 출력

> 유저 승인·차단·삭제, 시스템 폴링 간격 변경, 주문/거래/이벤트 모니터링은 봇 명령이 아니라 별도 웹 대시보드 **supabot-manager**에서 수행합니다. (`manager/README.md` 참조)

봇은 시작 시 Telegram 명령어 메뉴를 자동 갱신합니다. 새 명령이 보이지 않으면 배포 후 봇 프로세스가 새 코드로 재시작되었는지 확인하세요.

### 2. 자산 및 시세 조회
- `/asset` : 통합 자산 현황 조회 (소액 자산 자동 요약 포함)
- `/price` (단축: `/p`) : 특정 종목의 실시간 시세 및 변동률 확인
- `/indicators` (단축: `/ind`) : RSI·MACD·볼린저밴드·스토캐스틱 멀티지표 한눈에 조회
- `/history` : 최근 체결 완료된 거래 내역 조회 (최근 5건)
- `/report` : 기간별 실현 손익 및 체결 요약 리포트

### 3. 거래 및 주문 관리
- `/rsitrade` : **(HOT)** RSI 구간 기반 자동 매집 및 익절 순환 전략 시작
- `/grid` : 지정 가격 범위 내 거미줄 분할 매수 셋팅
- `/sgrid` : 보유 수량 기반 거미줄 분할 매도 셋팅
- `/buy` / `/sell` : 단일 지정가 매수/매도 주문 확인 후 전송 (확인 요청 10분 만료)
- `/orders` : 현재 추적 중인 모든 미체결 주문 목록
- `/cancel` : 특정 종목의 모든 주문 일괄 취소

### 4. 시그널 및 알림
- `/watch` : RSI 매수 시그널 실시간 감시 종목 추가
- `/unwatch` : 감시 목록에서 종목 제거

### 5. 관리자 전용
- `/halt` / `/resume` : 전체 거래 즉시 중지/재개 (손절·익절 보호 매도는 계속 동작)
- `/dbsync` : DB 상태를 인메모리 주문 목록에 강제 재동기화
- `/resetuser <user_id>` : **(NEW)** 특정 유저의 주문 추적·실적을 완전 초기화. 거래소 미체결 주문을 먼저 취소 시도한 뒤 확인을 거쳐 주문/체결 내역을 모두 삭제하는 비가역 작업으로, 주문 추적이 꼬였을 때만 사용

## 🛠 설치 및 실행 방법 (Oracle Cloud VM)

Oracle Cloud에서 SSH 복구와 컨테이너 기동까지 실제로 확인한 기록은 [Oracle Cloud SSH 복구 및 컨테이너 기동 성공 기록](docs/archive/oracle-cloud-ssh-recovery-success.md)을 참고하세요 (특정 시점 인스턴스 상태 기준 기록 — archive로 보관).

### 1. 프로젝트 설정
`config/.env` 파일을 생성하고 다음 내용을 입력합니다.
```env
TELEGRAM_BOT_TOKEN=여러분의_봇_토큰
ADMIN_CHAT_ID=최고_관리자_채팅_ID
USER_SECRET_KEY=Fernet_마스터키

# Supabase 데이터 레이어 (필수)
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=service_role_키

# supabot-manager 연동 (선택 — manager 사용 시에만)
MANAGER_API_KEY=manager와_공유하는_랜덤_32자_이상_키
# INTERNAL_PORT=8765   # /internal/notify 포트 (기본 8765)
```

`SUPABASE_URL`과 `SUPABASE_SERVICE_KEY`는 Supabase 대시보드 → Settings → API에서 확인합니다. `service_role` 키는 RLS를 우회하는 마스터 키이므로 GitHub·채팅 등 공개 채널에 절대 올리지 마세요. 봇은 이 키로 Supabase의 `users`/`orders` 등 테이블을 직접 읽고 씁니다. DB 연결이 불가능하면 자동으로 `data/*.json` 파일 폴백으로 동작합니다.

`MANAGER_API_KEY`는 supabot-manager가 봇의 `/internal/notify`로 Telegram 알림 전송을 위임할 때 쓰는 인증 키입니다. 설정하지 않으면 알림 엔드포인트가 비활성(항상 401)되며 봇의 매매 기능에는 영향이 없습니다.

`TELEGRAM_BOT_TOKEN`은 텔레그램에서 `@BotFather`를 검색한 뒤 `/newbot` 명령으로 새 봇을 만들면 발급됩니다. 봇 이름과 사용자명을 입력하면 BotFather가 긴 토큰 문자열을 보내주며, 이 값을 `TELEGRAM_BOT_TOKEN=` 뒤에 붙여 넣습니다. 토큰은 봇 제어 권한과 같으므로 GitHub, 채팅방, 스크린샷 등에 공개하지 마세요.

`ADMIN_CHAT_ID`는 봇을 처음 관리할 텔레그램 계정의 숫자 ID입니다. 생성한 봇에게 먼저 `/start`를 보내고, 텔레그램에서 `@userinfobot` 또는 `@RawDataBot`을 실행해 표시되는 본인 ID를 확인한 뒤 `ADMIN_CHAT_ID=` 뒤에 입력합니다. 봇은 이 ID를 최초 최고 관리자 기준으로 사용합니다.

`USER_SECRET_KEY`는 유저별 거래소/Gemini 키를 암호화하는 마스터키입니다. 암호화된 키는 Supabase `users` 테이블(DB 폴백 시 `data/users.json`)에 `enc:v1:` 형식으로 저장됩니다. Oracle VM의 `config/.env`에만 보관하고 GitHub에 올리지 마세요. 생성 예시는 다음과 같습니다.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

이미 평문으로 저장된 키가 있더라도 `USER_SECRET_KEY`를 설정한 뒤 봇을 재시작하면 `enc:v1:<ciphertext>` 형식으로 자동 마이그레이션됩니다. `USER_SECRET_KEY`가 없거나 Fernet 형식이 아니면 기존 평문 키 읽기는 유지되지만 새 API 키 저장은 거부됩니다. 이미 암호화된 값은 반드시 암호화할 때 사용한 같은 `USER_SECRET_KEY`가 있어야 복호화됩니다. 다른 키를 넣으면 봇은 기동되지만 `/whoami`에 `보안 키: 복호화 오류`가 표시되고 거래소/Gemini 키는 사용할 수 없습니다.

### 2. 거래소 API 키 발급

업비트와 빗썸에서 각각 API Key와 Secret Key를 발급받아야 자산 조회와 주문 기능을 사용할 수 있습니다. 주문 권한이 포함된 키는 실제 매매가 가능한 권한이므로, 필요한 권한만 선택하고 가능하면 Oracle Cloud VM의 공인 IP를 허용 IP로 등록하세요.

**업비트 API 키**
1. 업비트 PC 웹에 로그인합니다.
2. `마이페이지` > `Open API` 메뉴로 이동합니다.
3. 필요한 권한을 선택합니다. 이 봇에서 주문까지 사용할 경우 자산 조회와 주문 권한이 필요합니다.
4. 주문 또는 출금 권한을 선택하는 경우 허용 IP 등록이 필요할 수 있습니다.
5. 인증을 완료한 뒤 표시되는 Access Key와 Secret Key를 안전한 곳에 보관합니다. Secret Key는 다시 확인할 수 없으므로 발급 직후 복사해 두세요.

**빗썸 API 키**
1. 빗썸 PC 웹에 로그인합니다.
2. API 관리 또는 Open API 메뉴로 이동합니다.
3. API Key를 생성하고 필요한 권한을 선택합니다. 이 봇에서 주문까지 사용할 경우 자산 조회와 주문 권한이 필요합니다.
4. 보안 인증을 완료하고, 필요한 경우 허용 IP 또는 API 사용 설정을 활성화합니다.
5. 표시되는 API Key와 Secret Key를 안전한 곳에 보관합니다. Secret Key는 외부에 공개하지 마세요.

발급한 거래소 키는 `.env`에 넣지 않고, 봇 실행 후 텔레그램에서 `/config` 명령으로 등록합니다. `/config`를 입력하면 거래소 선택 버튼이 나오며, 업비트 또는 빗썸을 선택한 뒤 Access Key와 Secret Key를 순서대로 입력하면 봇이 저장하고 유효성을 확인합니다. 입력한 키 메시지는 보안을 위해 자동 삭제됩니다.

**한국투자증권 Open API**
1. 한국투자증권 계좌를 준비하고 KIS Developers 또는 한국투자증권 Open API 메뉴에서 Open API 서비스를 신청합니다.
2. App Key와 App Secret을 발급받습니다. 모의투자와 실전투자는 별도 키를 사용할 수 있으므로 처음에는 모의투자 키를 권장합니다.
3. 계좌번호 앞 8자리와 계좌상품코드 2자리를 확인합니다. 국내주식 종합계좌는 보통 상품코드가 `01`입니다.
4. 봇에서 `/config`를 입력하고 `한국투자증권`을 선택한 뒤 App Key, App Secret, 계좌번호, 상품코드, `paper` 또는 `real` 환경을 입력합니다.
5. 지원 범위는 국내주식 시세 조회, 잔고 조회, 지정가 매수/매도, 주문 상태 확인, 일봉 RSI 감시(`/watch`), 일봉 RSI 순환전략(`/rsitrade`)입니다. 한국투자증권은 분봉 RSI를 지원하지 않으므로 RSI 기준이 분봉이면 KIS RSI 명령은 실행되지 않습니다.

**토스증권 Open API**
1. 토스증권 계좌를 준비하고 Toss Open API 포털에서 앱을 등록하여 Client ID와 Client Secret을 발급받습니다.
2. 봇에서 `/config`를 입력하고 `토스증권`을 선택한 뒤 Client ID와 Client Secret을 순서대로 입력합니다.
3. 입력 즉시 토스 API로 인증하고 계좌 번호(`account_seq`)를 자동으로 조회·저장합니다.
4. 지원 범위는 국내주식 시세 조회, 잔고 조회, 지정가/시장가 매수/매도, 주문 취소, 일봉 RSI 감시(`/watch`), 일봉 RSI 순환전략(`/rsitrade`)입니다. 토스증권은 분봉 RSI를 지원하지 않습니다.

### 3. Gemini 자연어 명령 설정

Gemini API 키는 `.env`에 넣지 않고 거래소 키처럼 텔레그램 `/config`에서 사용자별로 등록합니다.

1. Google AI Studio에서 Gemini API 키를 발급합니다.
2. 봇에서 `/config`를 입력하고 `Gemini API 키` 버튼을 누릅니다.
3. Gemini API 키를 입력하면 봇이 메시지를 삭제하고 Supabase `users` 테이블(폴백 시 `data/users.json`)에 암호화 저장합니다.
4. `/config set llm_enabled on`으로 자연어 기능을 켭니다.
5. `/config -v`로 `Gemini: 설정됨`, `llm_enabled: on`, `llm_model` 상태를 확인합니다.

자연어 기능은 기존 명령어를 대체하지 않습니다. Gemini 키가 없거나 `llm_enabled`가 꺼져 있으면 `/buy`, `/rsitrade`, `/asset` 같은 기존 명령어는 그대로 작동하고, 일반 텍스트에는 설정 안내만 표시됩니다.

### 4. GitHub Actions CI/CD 설정

이 저장소는 모노레포이며, 컴포넌트별로 분리된 워크플로가 **GitHub Container Registry(GHCR)**로 이미지를 빌드·푸시합니다. (Docker Hub를 더 이상 사용하지 않습니다.)

| 워크플로 | 트리거 | 동작 |
|----------|--------|------|
| `.github/workflows/build-bot.yml` | `src/**`·`scripts/**`·`requirements.txt`·`Dockerfile`·`docker-compose.yml` 변경이 `main`에 push, 또는 `bot-*` 태그 Release | `ghcr.io/antny-bot/supabot` 빌드·푸시. `bot-*` Release 시 Oracle VM에 SSH 자동 배포 |
| `.github/workflows/build-manager.yml` | `manager/**` 변경이 `main`에 push, 또는 `manager-*` 태그 Release | `ghcr.io/antny-bot/supabot-manager` 빌드·푸시 (Synology는 수동 pull) |
| `.github/workflows/ci-test.yml` | `main`·`claude/**` push, `main` 대상 PR | `pytest tests/ -v` 테스트 게이트 |
| `.github/workflows/cleanup-registry-and-cache.yml` | 매주 1회 스케줄 실행, 또는 수동 실행 | GHCR `supabot`·`supabot-manager` 패키지에서 최신 10개 버전 유지, Actions cache 삭제는 수동 opt-in |

GHCR는 `GITHUB_TOKEN`으로 인증하므로 별도의 레지스트리 secret이 필요 없습니다. Oracle VM 자동 배포(`build-bot.yml`)는 다음 secrets를 사용합니다: `OCI_HOST`, `OCI_USER`, `OCI_SSH_PRIVATE_KEY`, `OCI_SSH_PORT`, `OCI_DEPLOY_PATH`. 등록 위치는 저장소 `Settings` > `Secrets and variables` > `Actions`입니다.

정리 워크플로(`cleanup-registry-and-cache.yml`)도 `GITHUB_TOKEN`만 사용합니다. 기본 운영 정책은 다음과 같습니다.

1. 매주 월요일 03:25(KST)에 스케줄 실행
2. `ghcr.io/antny-bot/supabot`, `ghcr.io/antny-bot/supabot-manager` 각각 최신 10개 버전 유지
3. Actions cache 삭제는 기본 비활성화, 필요할 때만 수동 실행에서 활성화

수동 실행이 필요하면 `Actions` 탭에서 `Cleanup Registry and Cache` 워크플로를 열고 `Run workflow`를 누르면 됩니다. `keep_versions`로 남길 GHCR 버전 개수를 조정할 수 있고, `cleanup_caches`를 켜서 cache 삭제를 명시적으로 실행할 수 있습니다. 캐시를 비우면 다음 Docker Buildx 빌드는 캐시 재생성 때문에 평소보다 오래 걸릴 수 있습니다.

상세한 워크플로 설명과 운영 규칙은 [docs/github-actions-workflows.md](/E:/apps/supabot/docs/github-actions-workflows.md) 를 기준으로 관리합니다.

봇 배포 순서:
1. 변경 사항을 `main`에 push하면 `latest` 이미지가 갱신됩니다.
2. 버전 고정 배포가 필요하면 `bot-vX.Y.Z` 형식의 태그로 Release를 발행합니다.
3. `bot-*` Release는 `latest`와 버전 태그 이미지를 함께 푸시하고, 이어서 Oracle VM에 SSH로 `docker compose pull && up -d`를 실행합니다.

### 5. 도커 실행 (Oracle Cloud VM)
Oracle Cloud VM에서 Docker Compose로 컨테이너를 실행합니다. 거래소 API 직결을 위해 `network_mode: host`를 사용합니다.

```yaml
services:
  supabot:
    image: ghcr.io/antny-bot/supabot:latest
    container_name: supabot
    restart: unless-stopped
    network_mode: host
    environment:
      TZ: Asia/Seoul
    volumes:
      - ./config/.env:/app/config/.env:ro
      - ./data:/app/data
```

## 🏗 시스템 아키텍처

**봇 (`src/`)**
- `src/main.py`: 텔레그램 핸들러 및 **실시간 동기화/자동 대응 엔진**, `/internal/notify` 서버
- `src/core/db.py`: Supabase REST 클라이언트 (requests 기반 — Oracle Cloud의 HTTP/2 ALPN 차단 회피)
- `src/core/exchange_adapter.py`: 거래소 API 통합 정규화 레이어 — Upbit/Bithumb/KIS/Toss (+캔들 캐싱)
- `src/core/signal_engine.py` · `indicators.py`: **RSI 가격 역산** 및 RSI/MACD/볼린저/스토캐스틱 멀티지표
- `src/core/order_manager.py`: 전략별 주문 상태 추적 (DB 우선 + 파일 폴백)
- `src/core/user_manager.py`: 멀티유저 권한·설정 관리 (DB 우선 + 파일 폴백)
- `src/core/secret_crypto.py`: 사용자 API 키 Fernet 암복호화
- `src/core/trade_log.py` · `operational_events.py` · `metrics.py` · `bot_logger.py`: 체결/운영 로그(DB+파일 이중기록), 메트릭, 구조화 로깅
- `src/core/command_log.py`: 명령어 사용 로그 (`command_logs` DB 단방향 기록 — Analytics 집계 소스)
- `src/core/formatters.py` · `parsers.py` · `natural_language.py`: 메시지 포매팅, 입력 파싱, 자연어 전처리

**공유 데이터 (`shared/`)**
- `shared/schema.sql`: Supabase 테이블 정의 — `users`, `orders`, `trade_logs`, `operational_events`, `nl_logs`, `system_config`, `command_logs`(raw 1일), `command_log_daily`(Analytics 요약, pg_cron 집계) (RLS 활성)

**관리 UI (`manager/`)**
- FastAPI + React(TypeScript/Recharts) 웹 대시보드. Synology Docker 배포. 상세: [`manager/README.md`](manager/README.md)

### 데이터 저장 방식

봇은 Supabase PostgreSQL을 1차 저장소로 사용합니다. 핵심 모듈(`user_manager`, `order_manager`)은 `SUPABASE_URL`·`SUPABASE_SERVICE_KEY`가 설정되어 있으면 DB를 우선 읽고 쓰며, 연결 실패 시 `data/*.json` 파일로 자동 폴백합니다. 체결/운영 로그는 DB와 파일에 **이중 기록**합니다. 관리자 폴링 간격 같은 시스템 설정은 `system_config` 테이블에서 읽습니다.

## 📈 트레이딩 전략 및 상세 메커니즘

수파봇은 단순 주문 제출에 그치지 않고 가격 변동성과 기술적 지표에 실시간으로 대응하는 복합 트레이딩 전략 엔진을 탑재하고 있습니다. 전체 상세 사양은 [RSI 역산 및 전략 상세 명세](docs/detail/rsi_algorithm.md)를 참고하세요.

### 1. RSI 순환 매매 전략 (`/rsitrade`)
과매도 구간 진입 시 분할 매집을 개시하고, 매수 체결 분량에 대해 목표 과매수 구간 가격으로 즉시 익절 매도를 대기시키는 순환 매매 전략입니다.

- **RSI 가격 역산**: 사용자가 목표 RSI(예: 30)를 지정하면, 봇은 이분 탐색(Binary Search)과 가상 캔들 대입 방식을 이용해 **해당 RSI가 되는 경계 가격을 실시간 역산**합니다. 이를 통해 지표 지연 현상 없이 정확한 지정가 타점에 진입합니다.
- **실시간 분할 진입**: 입력받은 매수 RSI 구간(예: `25-30`) 내에서 분할 횟수만큼 목표 RSI를 쪼개어(예: 30, 28.75, 27.5...) 각각 가격을 역산한 뒤 다수의 매수 지정가 주문을 깔아둡니다.
- **연동 익절 매도**: 매수 주문이 부분 또는 전량 체결될 때마다, 체결된 수량만큼 즉시 연동된 익절 매도 주문(`rsitrade_sell`)을 생성하여 거래소에 제출합니다. 매도 타점 또한 목표 익절 RSI(예: `65-75` 중 65)에 맞춰 가격을 역산합니다.
- **손절(Stop-Loss) 및 트레일링 스톱**: 매수 체결 이후 가격 폭락에 대비하여 설정한 비율(`stop_loss_pct`)에 따른 손절가(`stop_price`)를 지정합니다. 현재가가 손절가 이하로 떨어지면 기존 익절 매도 주문을 즉시 취소하고 시장가 수준으로 손절합니다. 트레일링 스톱(`trailing_stop_pct`)이 켜져 있다면 가격 상승에 맞춰 손절가를 동적으로 위로 올립니다.

### 2. 거미줄 분할 매매 전략 (`/grid`, `/sgrid`)
특정 가격 범위 내에 거미줄망처럼 분할 주문을 깔아두는 그리드 트레이딩 방식입니다.

- **거미줄 매수 (`/grid`)**: 사용자가 입력한 시작가와 종료가 범위 내에서 주문 개수만큼 등간격으로 쪼개어 매수 한도 주문을 배치합니다. 총 예산을 주문 개수로 나눈 금액으로 가격별 수량을 계산합니다.
- **거미줄 매도 (`/sgrid`)**: 보유한 총수량을 설정한 시작가와 종료가 범위 내에서 주문 개수만큼 쪼개어 분할 매도 주문을 배치합니다.

### 3. 거래소별 예외 및 복구 정책 (특히 KIS·토스)
- **KIS/토스 정규장 제한**: 국내주식(KIS/토스)은 정규장(평일 09:00 - 15:35) 외에는 거래소에 신규 주문을 제출할 수 없습니다. 장외에 `/grid`, `/sgrid`, `/rsitrade`, `/sgridrsi`, `/buy`, `/sell`을 실행하면 반려되지 않고 **예약(`reserved`) 배치**로 등록되며, 다음 정규장 시작(09:00)에 자동으로 실제 주문이 제출됩니다.
- **자동 재주문 복구 (`pending_reorder`)**: KIS/토스 국내주식 주문은 장 마감 시 미체결 물량이 자동 만료되어 취소됩니다. 수파봇은 만료된 전략 주문을 감지하면 `pending_reorder` 상태로 이월해 두고, 다음 영업일 정규장 시작(09:00) 시 **"원래 설정 수량 - 이미 체결된 수량"** 만큼의 잔량에 대해 자동으로 동일 조건 재주문을 진행해 전략의 영속성을 보장합니다.
- **코인 거래소**: 업비트와 빗썸은 24시간 거래되므로 별도의 만료 및 재주문 복구 프로세스를 거치지 않고 체결 시까지 지속 추적됩니다.

## 📈 RSI 기준과 캔들 조회 로직

RSI 기간은 기본적으로 14기간이며, 캔들 기준 기본값은 일봉입니다.

```text
/config set rsi_interval day
/config set rsi_interval 60
/config -v
```

허용되는 RSI 캔들 기준은 다음과 같습니다.

- 일봉: `day`, `daily`, `d`, `1d`
- 분봉: `1`, `3`, `5`, `10`, `15`, `30`, `60`, `240`

거래소별 캔들 조회 방식은 다릅니다.

- Upbit: 일봉은 Upbit CLI `candles list-days`, 분봉은 `candles list-minutes`를 사용합니다.
- Bithumb: 일봉은 `/v1/candles/days`, 분봉은 `/v1/candles/minutes/{unit}`를 사용합니다.
- 한국투자증권: 일봉만 지원하며 KIS `inquire-daily-itemchartprice`(`FHKST03010100`)를 사용합니다.
- 토스증권: 일봉만 지원하며 Toss Open API `/api/v1/candlesticks` (국내주식)를 사용합니다.

한국투자증권과 토스증권은 분봉 RSI를 지원하지 않습니다. 사용자의 `rsi_interval`이 `60` 같은 분봉일 때 KIS/Toss 종목으로 `/watch` 또는 `/rsitrade`를 실행하면 봇은 주문을 만들지 않고 안내 메시지를 반환합니다.

## 🕘 한국투자증권 주문 추적 정책

코인 거래소는 24시간 거래되지만 한국투자증권 국내주식 주문은 정규장 중심으로 동작합니다. 불필요한 API 호출을 줄이고 만료 주문을 안전하게 다루기 위해 KIS 주문은 다음 정책을 따릅니다.

- KIS 주문 상태 조회는 평일 KST 09:00-15:35에만 수행합니다.
- 장외, 주말에는 KIS 주문 조회를 건너뛰고 다음 평일 09:00 이후로 다시 확인합니다.
- 별도 휴일 캘린더는 관리하지 않습니다. 공휴일처럼 평일이지만 휴장인 날에는 KIS API의 장외/거래불가 응답을 기준으로 다음 평일 09:00로 미룹니다.
- `/status`에서는 KIS 주문을 `대기`, `부분체결`, `장외 대기`, `다음 정규장 재주문 예정`으로 표시합니다.

국내주식 미체결 주문은 다음날 거래소에서 사라질 수 있으므로, 봇은 거래소 주문 ID와 봇의 전략 의도를 분리해 관리합니다.

- 수동 `/buy 한투`, `/sell 한투` 주문은 자동 재주문하지 않습니다. 만료 또는 외부 취소가 감지되면 알림 후 추적을 종료합니다.
- `/rsitrade 한투` 같은 전략 주문은 만료되면 `pending_reorder` 상태로 유지합니다.
- 부분 체결 후 만료된 전략 주문은 전체 수량이 아니라 `주문 수량 - 체결 수량` 잔량만 다음 정규장에 재주문합니다.
- 재주문 성공 시 기존 전략 정보는 유지하고 새 KIS 주문 ID로 교체합니다.

이 정책은 사용자가 직접 낸 수동 주문이 원치 않게 반복되는 일을 막고, 봇이 만든 전략 주문만 다음 정규장에도 의도를 이어가도록 하기 위한 것입니다.

**참고 — `reserved`와 `pending_reorder`는 다른 상황입니다.** `reserved`는 주문 *발행 시점*에 이미 장외였던 경우(거래소엔 아직 제출 안 됨, `/status`·매니저 주문 현황에 "예약" 상태로 표시), `pending_reorder`는 *이미 제출됐던* 주문이 장 마감으로 취소된 경우입니다. 둘 다 다음 정규장에 동일한 자동 제출 로직을 거칩니다.

## 🧠 Gemini 자연어 명령 로직

Gemini 자연어 기능은 텔레그램 일반 텍스트를 기존 명령어 의도로 변환하는 보조 계층입니다. LLM은 거래소 API를 직접 호출하지 않고, 봇 내부에서 검증 가능한 JSON 의도만 반환합니다.

처리 순서는 다음과 같습니다.

1. 안전한 조회 표현은 룰 기반 전처리로 먼저 처리합니다. 이 경우 Gemini를 호출하지 않고 로그에도 남기지 않습니다.
2. 전처리로 처리하지 못한 문장만 Gemini로 보내 JSON intent를 받습니다.
3. Gemini 결과는 서버 후처리 규칙으로 한 번 더 보정합니다. 예를 들어 `주문대기중인것은?`, `예약 주문 보여줘`, `추적 중인 전략 주문 있어?`는 전략 대시보드인 `/status`로 보정하고, `미체결 주문`, `오픈오더`, `거래소에 실제 걸린 주문`은 `/orders`로 둡니다.
4. 전처리로 처리하지 못해 Gemini까지 간 문장은 익명화된 형태로 `data/nl_unmatched.jsonl`과 Supabase `nl_logs` 테이블에 누적합니다. 숫자, 6자리 주식코드, 긴 토큰은 마스킹하며 파일은 최근 500줄만 유지합니다.

## 🧪 운영 모니터링

봇 운영 상태(유저, 주문, 거래, 최근 오류 이벤트)는 텔레그램 명령이 아니라 **supabot-manager 웹 대시보드**에서 확인합니다. 봇은 운영 이벤트를 `data/bot_events.jsonl`과 Supabase `operational_events` 테이블에 이중 기록하며, API 키·secret 값은 저장하지 않고 긴 토큰과 계좌성 숫자는 마스킹합니다. 메트릭(주문 성공률·API 지연·폴링 건전성)은 `src/core/metrics.py`가 인메모리로 수집합니다.

즉시 실행되는 조회 의도:

- 자산 조회: `내 자산 보여줘`
- 시세 조회: `삼성전자 현재가 보여줘`, `BTC 가격 알려줘`
- 전략 상태: `주문대기중인것은?`, `예약 주문 보여줘`, `전략 상태 알려줘`
- 미체결 주문: `미체결 주문 뭐 있어?`, `오픈오더 보여줘`
- 설정 조회: `현재 설정 보여줘`
- 체결 내역: `최근 체결 내역 보여줘`
- 애매한 조회: `비트 봐줘`처럼 의도가 불명확하면 시세/자산/전략 상태 중 무엇을 볼지 되묻습니다.

확인 버튼이 필요한 변경 의도:

- 주문: `BTC 100만원어치 RSI 25-30으로 나눠서 사줘`
- 단일 매수/매도: `한투 삼성전자 70000원에 1주 사줘`
- 설정 변경: `RSI 기준 일봉으로 바꿔줘`
- 관심 종목 변경: `삼성전자 RSI 감시해줘`
- 취소: `BTC 주문 취소해줘`

주문과 설정 변경은 Gemini가 해석했더라도 즉시 실행하지 않습니다. 봇이 해석 결과를 요약하고 `실행` 버튼을 보여준 뒤, 사용자가 버튼을 누른 경우에만 서버 측 검증과 기존 주문 로직을 통과합니다. 검증 항목에는 거래소명, 종목, 가격, 수량, RSI 범위, 예산, `max_order_krw`, KIS 일봉 제한, KIS 정규장 정책이 포함됩니다.

거래소 API 키와 Gemini API 키는 `USER_SECRET_KEY`가 설정된 경우 Supabase `users` 테이블(폴백 시 `data/users.json`)에 `enc:v1:` 형식으로 암호화 저장됩니다. 이는 저장소 단독 유출을 줄이기 위한 보호이며, `.env`의 `USER_SECRET_KEY`와 저장된 암호문을 모두 가진 운영자는 복호화할 수 있습니다. 암복호화 로직은 `src/core/secret_crypto.py`에 분리되어 있습니다.

## ⚠️ 면책 조항
본 소프트웨어는 투자 보조 도구일 뿐이며, 투자에 대한 모든 책임은 사용자 본인에게 있습니다. 매매 수수료 및 호가 단위 보정 등에 유의하여 사용하시기 바랍니다.
