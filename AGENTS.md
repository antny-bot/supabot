# AGENTS.md — supabot 에이전트 진입점

모든 AI 에이전트(Claude Code, Codex, 기타) 공통 진입점. 작업 전 필독.

## 프로젝트
멀티유저·멀티거래소 텔레그램 자동매매 봇 (Upbit, Bithumb, KIS, Toss).
Docker on Oracle Cloud VM. 실거래 경로 포함 — 변경 전 본 문서 "안전 규칙" 필독.

**모노레포 구조**: 봇은 `src/`, 관리 웹 UI는 `manager/`, 공유 DB 스키마는 `shared/schema.sql`.
봇과 manager는 **Supabase PostgreSQL을 공유**할 뿐 서로 직접 의존하지 않는다. 봇은 manager 없이도 완전히 동작한다.

## 도메인별 빠른 진입 (불필요한 문서는 읽지 않기)

작업 도메인이 명확하면 아래 문서만 읽고 시작한다. 다른 도메인 문서는 건너뛰어도 됨.

| 도메인 | 읽을 문서 | 비고 |
|--------|-----------|------|
| 🪙 가상화폐 (Upbit/Bithumb) | `docs/impl/exchange_adapter.md` (Upbit/Bithumb 섹션) | KIS/Toss 섹션 스킵 가능 |
| 📈 국내주식 — 한국투자증권(KIS) | `docs/impl/exchange_adapter.md` (KIS 섹션) → `docs/detail/kis_market_policy.md` | 해외주문 미지원 |
| 📈 국내주식 — 토스증권 (005930 등 국내 종목코드) | `docs/impl/exchange_adapter.md` (Toss 섹션) | |
| 🌎 해외주식 — 토스증권 (AAPL 등 알파벳 티커) | `docs/detail/toss_overseas_stock.md` | 통화 분기(`is_us_stock_ticker`) 전담 문서 |
| 🔌 토스 API 엔드포인트/필드 확인 | `docs/impl/toss_api_reference.md` | 원본 OpenAPI(`docs/toss.json`, 6400+줄)는 세부 스키마 필요할 때만 |
| 🤖 RSI/거미줄 전략 (`/grid`,`/rsitrade` 등) | `docs/impl/signal_engine.md` → `docs/detail/rsi_algorithm.md` | |
| 💬 텔레그램 커맨드/핸들러 (봇 backend) | `docs/impl/main_handlers.md` | |
| 🖥️ 관리 웹 UI backend (FastAPI 라우터) | `manager/README.md` (라우터 표) | |
| 🖥️ 관리 웹 UI frontend (React/Vite) | `manager/README.md` (프론트엔드 구조) → `manager/frontend/DESIGN.md` | |

## 봇 모듈 맵 (`src/`)

| 파일 | 책임 | 관련 Tier 2 문서 |
|------|------|-----------------|
| `src/main.py` (~765줄) | 텔레그램 핸들러 등록, 폴링 루프(`sync_orders`), `/internal/notify` 서버, 공통 헬퍼(`resolve_ticker_for_command` 등) | `docs/impl/main_handlers.md` |
| `src/handlers/*.py` | 명령어 핸들러 기능별 분리 — `strategy_handlers`(grid/rsitrade), `query_handlers`(asset/orders/price/history), `manual_order_handlers`, `nl_intent_handlers`(자연어), `config_handlers`, `status_handlers`, `system_handlers`, `watch_handlers`. 거래소별 분기는 직접 안 하고 `main.exchange_adapter.get_exchange(exchange).<capability>()` 호출로 위임 | `docs/impl/main_handlers.md` |
| `src/internal_api.py` (269줄) | 매니저 백엔드 연동 webhook API (HMAC 인증) | — |
| `src/core/db.py` (106줄) | Supabase REST 클라이언트 (requests 기반, httpx ALPN 회피) | — |
| `src/core/exchange_adapter.py` (201줄) | 거래소 레지스트리/파사드 — `get_exchange(name)`로 Exchange 인스턴스 반환, 공개 메서드는 dict 기반 dispatch (세션·캔들캐시·토큰은 adapter가 단일 소유) | `docs/impl/exchange_adapter.md` |
| `src/core/exchanges/base.py` (96줄) | `BaseExchange` — capability 메서드 기본값(코인 거래소 동작): `supports_minute_candles`/`is_market_open`/`requires_numeric_ticker`/`round_volume`/`requires_integer_volume`/`format_volume`/`adjust_price_to_tick`/`env_label`/`required_credential_fields` | `docs/impl/exchange_adapter.md` |
| `src/core/exchanges/{upbit,bithumb,kis,toss}.py` | 거래소별 Mixin(저수준 HTTP/인증, adapter가 상속) + `XxxExchange(BaseExchange)`(공개 메서드 위임 + capability 오버라이드) | `docs/impl/exchange_adapter.md` |
| `src/core/exchanges/common.py` (70줄) | `CommonMixin` — 코인/KRX/해외주식 틱사이즈 static 유틸 (`adjust_price_to_tick`/`adjust_krx_price_to_tick`/`adjust_us_price_to_tick`) | — |
| `src/core/formatters.py` (761줄) | Telegram 메시지 포매팅 (CMD_HELP 등) | — |
| `src/core/user_manager.py` (~390줄) | 유저 설정·권한 (DB 우선 + 파일 폴백, `status` 문자열) | `docs/impl/user_manager.md` |
| `src/core/natural_language.py` (414줄) | NL 전처리 + `nl_logs` 기록 | `docs/detail/gemini_intent.md` |
| `src/core/parsers.py` (275줄) | 거래소명·숫자(억/만)·RSI 파싱, KIS 세션 판정 | — |
| `src/core/signal_engine.py` (207줄) | RSI 계산 + 목표가 역산 | `docs/impl/signal_engine.md` |
| `src/core/order_manager.py` (162줄) | 주문 상태 기계 (DB 우선 + 파일 폴백, `has_order` O(1) uuid 인덱스) | `docs/impl/order_manager.md` |
| `src/core/trading_gate.py` | 글로벌 거래 중지(kill-switch) + 총 노출 한도 게이트. 관리자 `/halt`·`/resume`, `system_config.trading_halt` 저장 | `docs/impl/main_handlers.md` |
| `src/core/strategy_tokens.py` | 전략(grid/RSI) confirm 버튼 단일 사용 토큰 (멱등성·중복주문 방지). `manual_order_tokens` 패턴 | `docs/impl/main_handlers.md` |
| `src/core/indicators.py` (154줄) | RSI/MACD/볼린저/스토캐스틱 계산 (`ta`) | — |
| `src/core/stock_resolver.py` | 한국 주식 종목명→코드 해석 (정적맵→DB캐시→KIS검색) | — |
| `src/core/trade_log.py` (94줄) | 체결 로그 (DB + 파일 이중기록) | — |
| `src/core/command_log.py` (22줄) | 명령어 사용 로그 (`command_logs` DB 단방향 기록, 파일 폴백 없음) | — |
| `src/core/metrics.py` (85줄) | 인메모리 운영 메트릭 | — |
| `src/core/operational_events.py` (85줄) | 운영 이벤트 (DB + 파일 이중기록, 마스킹) | — |
| `src/core/secret_crypto.py` (52줄) | 사용자 키 Fernet 암복호화 (`enc:v1:`) | — |
| `src/core/bot_logger.py` (33줄) | 구조화 JSON 로깅 (stdout) | — |
| `data/orders.json` · `users.json` | DB 폴백/캐시 (0600) | — |
| `config/.env` | BOT_TOKEN, ADMIN_CHAT_ID, SUPABASE_*, MANAGER_API_KEY | `config/.env.template` |

## 관리 UI 모듈 맵 (`manager/`)

FastAPI 백엔드 + React/TypeScript(Vite+Tailwind) SPA 프론트엔드. Synology Docker 배포 (`ghcr.io/antny-bot/supabot-manager`, 포트 8000).

| 파일 | 책임 |
|------|------|
| `manager/backend/main.py` | FastAPI 앱, 세션, 로그인/로그아웃 |
| `manager/backend/db.py` | Supabase REST 클라이언트 (= `src/core/db.py`) |
| `manager/backend/auth.py` | Supabase Auth 이메일/비번 로그인 |
| `manager/backend/bot_client.py` | 봇 `/internal/notify` 단방향 호출 |
| `manager/backend/routers/` | dashboard, users, orders, trades, events, sysconfig, reports, templates, mfa, analytics, stock_cache (11개) |

라우트: `/admin/dashboard`, `/admin/users`(+approve/deactivate/activate/block/DELETE), `/admin/orders`, `/admin/trades`, `/admin/events`, `/admin/config`, `/admin/reports`(손익·보유·승률·거래소/일별 분석), `/admin/templates`(전략 템플릿), `/analytics`(admin only), 종목 캐시 관리(`/api/stock-cache`, admin only). 상세: `manager/README.md`.

## 핵심 데이터 스키마

> **저장 방식**: 1차 저장소는 Supabase PostgreSQL (`shared/schema.sql`). `user_manager`/`order_manager`는
> `is_db_available()`(SUPABASE_URL+SERVICE_KEY)면 DB를 우선 읽고 쓰며, 실패 시 `data/*.json` 파일로 폴백.
> `trade_log`·`operational_events`는 DB+파일 이중 기록. 아래 JSON은 런타임/폴백 표현이며 DB 컬럼과 1:1 대응한다.

### Order (`orders` 테이블 / `data/orders.json` 폴백)
```jsonc
{
  "user_id": "str",
  "exchange": "upbit|bithumb|kis|toss",
  "ticker": "KRW-BTC",          // KIS/Toss 국내: "005930", Toss 해외: "AAPL" (currency 컬럼 없음, 패턴으로 추론)
  "uuid": "exchange_order_id",
  "price": 50000000.0,
  "volume": 0.001,
  "filled_volume": 0.0,
  "side": "bid|ask",
  "strategy": "manual|grid|rsitrade",
  "target_rsi": null,          // rsitrade 전략 전용
  "linked_to": null,           // 매수-매도 쌍 연결
  "status": "wait|partial|done|cancel|pending_reorder",
  "created_at": 1700000000.0,
  "next_check_at": 0.0,
  "reorder_of": null,          // 재주문 시 이전 uuid
  "stop_price": null           // rsitrade_sell 전용: 손절 기준가 (stop_loss_pct로 계산)
}
```

### User (`users` 테이블 / `data/users.json` 폴백)
```jsonc
{
  "<user_id>": {
    "username": "str",
    "is_admin": false,
    // DB는 status 문자열(pending|active|inactive|blocked|deleted)을 사용.
    // 파일 폴백 표현은 is_active bool. _db_row_to_user/_user_to_db_row가 양방향 변환.
    "is_active": false,
    "preferences": {
      "default_exchange": "upbit",
      "rsi_interval": "day",       // day | 1 | 3 | 5 | 10 | 15 | 30 | 60 | 240
      "rsi_buy_range": "25-30",
      "rsi_sell_range": "65-75",
      "rsi_order_count": 5,
      "rsi_budget_krw": null,
      "max_order_krw": null,
      "stop_loss_pct": null,   // RSITrade 손절 비율(%) — null이면 손절 비활성
      "signal_alerts": true,
      "signal_rsi_threshold": 30,
      "signal_bb_alert": false,    // 볼린저 하단 이탈 시 추가 알림 (RSI OR BB 조건)
      "asset_min_display_krw": 10000,
      "llm_enabled": false,
      "llm_model": "gemini-2.5-flash",
      "poll_active_interval": 60,        // 폐기 예정 — system_config 테이블이 우선
      "poll_no_order_interval": 300,     // 폐기 예정 — system_config 테이블이 우선
      "signal_analysis_interval": 300    // 폐기 예정 — system_config 테이블이 우선
    },
    "exchanges": {
      "upbit":   { "access_key": "", "secret_key": "", "watchlist": [] },
      "bithumb": { "access_key": "", "secret_key": "", "watchlist": [] },
      "kis":     { "app_key": "", "app_secret": "", "account_no": "", "product_code": "01", "env": "paper|real", "watchlist": [] },
      "toss":    { "client_id": "", "client_secret": "", "account_seq": null, "watchlist": [] }
    },
    "llm": { "gemini_api_key": "" }
  }
}
```

### Supabase 테이블 (`shared/schema.sql`)

| 테이블 | 용도 |
|--------|------|
| `users` | 유저 설정·권한·암호화 키 (`status` 문자열) |
| `orders` | 주문 상태 (created_at/next_check_at = Unix ts `DOUBLE PRECISION`) |
| `trade_logs` | 체결 내역 (DB+파일 이중기록) |
| `operational_events` | 운영 이벤트 로그 (DB+파일 이중기록) |
| `nl_logs` | 미처리 자연어 익명 로그 |
| `system_config` | 폴링/분석 간격 등 시스템 설정. `_get_admin_prefs()`가 우선 읽음 (key: poll_active_interval=60, poll_no_order_interval=300, signal_analysis_interval=300) |
| `command_logs` | 명령어 사용 raw 로그 (오늘치만 보관, pg_cron이 매일 집계 후 삭제) |
| `command_log_daily` | 명령어 사용 일별 요약 (date·user·command·hour·weekday·count). Analytics 분석 원본. |
| `kr_stock_cache` | 한국 주식 종목명→코드 DB 캐시 (KIS search-stock-info 결과, TTL 90일). 봇은 `src/core/stock_resolver.py`로 읽고, manager는 `manager/backend/routers/stock_cache.py`로 CRUD·CSV 입출력·KRX 일괄 갱신 |

- 모든 테이블 RLS 활성. `service_role` 키(봇/manager 서버용)는 RLS 우회.
- `src/core/db.py`는 supabase-py 대신 requests로 REST 호출 (Oracle Cloud의 HTTP/2 ALPN 차단 회피).

## 거래소별 인증 방식

| 거래소 | 방식 | 비고 |
|--------|------|------|
| Upbit | CLI subprocess (`upbit` 명령) | Node.js, async subprocess |
| Bithumb | REST + JWT (SHA512 query hash) | aiohttp 세션 재사용 |
| KIS | OAuth2 (client_credentials) | 토큰 캐시 per user/env/key |
| Toss | OAuth2 Bearer (`/api/v1/oauth2/token`) | 토큰 캐시 per user/client_id; account_seq 자동 조회 |

## 주요 제약사항

| 제약 | 상세 |
|------|------|
| KIS 정규장 | 평일 09:00-15:35 KST만 주문 조회. 장외 전략 주문 → `pending_reorder` |
| 수수료 버퍼 | 매수 `×0.999`, 매도 `×1.001` 적용 후 tick 반올림 |
| KIS/Toss 분봉 미지원 | `rsi_interval`이 분봉이면 KIS·Toss RSI 명령 거부 |
| 실거래 경로 | 모든 order 관련 코드 = 실머니. 테스트에서 live API 호출 금지 |
| 재주문 | KIS 전략 주문 만료 시 `volume - filled_volume` 잔량만 재주문 |
| 해외주식(Toss) 통화 혼재 | `trade_logs`에 currency 컬럼 없음 — KRW/USD 구분은 `is_us_stock_ticker()`로 매번 추론(`docs/detail/toss_overseas_stock.md`). KIS는 해외주문 미지원 |

## 작업별 문서 진입점

| 작업 | 읽을 문서 |
|------|-----------|
| 거래소 API 추가/수정 | `docs/impl/exchange_adapter.md` |
| 주문 상태 추적 수정 | `docs/impl/order_manager.md` |
| 유저 설정 스키마 변경 | `docs/impl/user_manager.md` |
| RSI 계산/가격 역산 | `docs/impl/signal_engine.md` → `docs/detail/rsi_algorithm.md` |
| 텔레그램 커맨드 추가 | `docs/impl/main_handlers.md` |
| KIS 장외/재주문 로직 | `docs/detail/kis_market_policy.md` |
| 토스증권 해외(미국)주식 로직 수정 | `docs/detail/toss_overseas_stock.md` |
| 토스 API 신규 엔드포인트 연동 | `docs/impl/toss_api_reference.md` → 필요 시 `docs/toss.json` |
| Gemini 자연어 흐름 | `docs/detail/gemini_intent.md` |
| Supabase 스키마 | `shared/schema.sql` |
| 관리 UI 백엔드 (라우터/API 추가·수정) | `manager/README.md` (라우터 표) |
| 관리 UI 프론트엔드 (페이지/컴포넌트 추가·수정) | `manager/README.md` (프론트엔드 구조) → `manager/frontend/DESIGN.md` |
| CI/CD 워크플로 수정 | `docs/github-actions-workflows.md` |
| 신규 사용자 온보딩 | `docs/user-onboarding.md` |
| Docker/배포 (Oracle VM) | `docs/oracle-cloud-deploy-sequence.md` (최초 VM 셋업은 `docs/oracle-cloud-vm-setup.md`) |

## 안전 규칙

1. **모든 주문 경로는 실거래.** `exchange_adapter.create_order()`, `cancel_order()`, `_create_kis_order()` 등은 실계좌에 직접 영향. 비가역적으로 취급.

2. **테스트에서 라이브 API 호출 금지.** `_run_upbit_cli`, `_request_bithumb`, `_request_kis` 반드시 mock. 실제 네트워크 도달 시 실주문/취소 발생.

3. **API 키 암호화 저장.** 거래소/Gemini 키는 `USER_SECRET_KEY`(Fernet)로 `enc:v1:` 형식 암호화되어
   Supabase `users` 테이블(폴백 시 `data/users.json`)에 저장. 암복호화는 `src/core/secret_crypto.py`.
   `get_user()`는 런타임용 복호화 copy 반환 — 로그·에러 메시지에 평문 노출 금지, 절대 commit 금지.

4. **KIS paper vs real.** `exchanges.kis.env = "real"` 이면 실계좌 매매. `env` 변경 시 극도 주의.

5. **Supabase 자격증명.** `SUPABASE_SERVICE_KEY`는 RLS를 우회하는 마스터 키 — 공개 채널/로그/commit 절대 금지.
   `MANAGER_API_KEY`(봇↔manager 공유), `SESSION_SECRET`(manager 세션 서명)도 동일하게 비밀 취급.
   `config/.env`·`manager/.env`는 git-ignore 상태 유지.

6. **UTF-8.** 소스 파일 내 한글 주석/메시지 처리 시 UTF-8 인코딩 명시.

7. **`/resetuser`(관리자 전용, `system_handlers.resetuser_command`)는 비가역적.** 거래소 미체결 주문 취소 → confirm → 대상 유저의 `orders`/`trade_logs`(DB+`trades.jsonl`) 전체 삭제. 거래소 취소 실패 시 자동 중단되지만, 삭제 자체는 백업 없이는 복구 불가 — 실행 전 Supabase 백업 확보 권장. 상세: `docs/impl/main_handlers.md`.

## 검증 절차

```bash
# 호스트에 Python 없음 → Docker 내부에서 실행
docker compose run --rm supabot python -m pytest tests/
docker compose run --rm supabot python -m py_compile src/main.py
```

주문·거래소·KIS 로직 변경 시 전체 테스트 통과 필수.
manager(`manager/`) 변경 시: `cd manager && python -m py_compile backend/**/*.py` 로 문법 확인.

**테스트 출력 토큰 절약 전략** (`pytest.ini`의 `addopts`로 적용, 테스트 240+개 → 계속 증가 예정):
- 성공한 테스트는 `.` 한 글자로만 표시 (`-q`, pytest 기본 quiet 모드).
- 실패/에러 테스트만 짧은 traceback(`--tb=short`) + 끝부분 한 줄 요약(`-ra`)으로 추적 가능하게 출력.
- `-v`를 직접 붙이면 이 설정과 충돌해 테스트명이 전부 나열되니, 토큰을 아끼려면 플래그 없이 `pytest tests/`만 실행할 것.
- 신규 테스트 추가 시 별도 설정 불필요 — `pytest.ini`에 이미 적용되어 자동으로 동일한 출력 형식을 따름.

## 백업 · 롤백 절차

### 정기 백업

1차 데이터 소스는 Supabase다. **Supabase 대시보드의 자동 백업(또는 `pg_dump`)을 우선 확보**하고,
DB 폴백/캐시인 파일도 함께 백업한다.

```bash
# 운영 서버에서 직접 실행 (Docker 호스트) — 파일 폴백 백업
./scripts/backup.sh

# 또는 cron 등록 예시 (매일 새벽 3시)
# 0 3 * * * cd /opt/supabot && ./scripts/backup.sh >> /var/log/supabot-backup.log 2>&1
```

백업 결과물은 `./backups/YYYYMMDD_HHMMSS/` 에 저장됩니다. `data/orders.json`, `data/users.json` 복사본이 생성됩니다.
DB 운영 시 이 파일들은 마지막 폴백 시점의 스냅샷일 수 있으므로, 권위 있는 복원은 Supabase 백업을 사용한다.

### 배포 롤백

```bash
# 1. 현재 컨테이너 중지
docker compose down

# 2. 이전 이미지로 되돌리기
docker tag ghcr.io/antny-bot/supabot:latest ghcr.io/antny-bot/supabot:broken
docker pull ghcr.io/antny-bot/supabot:<이전_SHA_태그>
docker tag ghcr.io/antny-bot/supabot:<이전_SHA_태그> ghcr.io/antny-bot/supabot:latest

# 3. 데이터 복원 (필요 시)
cp backups/<YYYYMMDD_HHMMSS>/orders.json data/orders.json
cp backups/<YYYYMMDD_HHMMSS>/users.json  data/users.json
chmod 600 data/orders.json data/users.json

# 4. 재기동
docker compose up -d
```

> ⚠️ DB 운영 중에는 파일 복원보다 Supabase 백업 복원이 우선입니다. 파일 복원 시 복원 시점 이후의 유저 설정 변경이 유실될 수 있습니다. 주문 복원은 거래소 실제 상태와 비교하여 불일치 여부를 확인하세요.
