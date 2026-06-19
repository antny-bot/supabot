# CLAUDE.md — supabot 에이전트 진입점

## 프로젝트
멀티유저·멀티거래소 텔레그램 자동매매 봇 (Upbit, Bithumb, KIS, Toss).
Docker on Oracle Cloud VM. 실거래 경로 포함 — 변경 전 반드시 `AGENTS.md` 확인.

**모노레포 구조**: 봇은 `src/`, 관리 웹 UI는 `manager/`, 공유 DB 스키마는 `shared/schema.sql`.
봇과 manager는 **Supabase PostgreSQL을 공유**할 뿐 서로 직접 의존하지 않는다. 봇은 manager 없이도 완전히 동작한다.

## 봇 모듈 맵 (`src/`)

| 파일 | 책임 | 관련 Tier 2 문서 |
|------|------|-----------------|
| `src/main.py` (~2134줄) | 텔레그램 핸들러, 폴링 루프, Gemini NL 라우팅, `/internal/notify` 서버 | `docs/impl/main_handlers.md` |
| `src/core/db.py` (106줄) | Supabase REST 클라이언트 (requests 기반, httpx ALPN 회피) | — |
| `src/core/exchange_adapter.py` (1128줄) | 4거래소 통합 API 추상화 — Upbit/Bithumb/KIS/Toss (+캔들 캐싱) | `docs/impl/exchange_adapter.md` |
| `src/core/formatters.py` (631줄) | Telegram 메시지 포매팅 (CMD_HELP 등) | — |
| `src/core/user_manager.py` (~390줄) | 유저 설정·권한 (DB 우선 + 파일 폴백, `status` 문자열) | `docs/impl/user_manager.md` |
| `src/core/natural_language.py` (414줄) | NL 전처리 + `nl_logs` 기록 | `docs/detail/gemini_intent.md` |
| `src/core/parsers.py` (275줄) | 거래소명·숫자(억/만)·RSI 파싱, KIS 세션 판정 | — |
| `src/core/signal_engine.py` (207줄) | RSI 계산 + 목표가 역산 | `docs/impl/signal_engine.md` |
| `src/core/order_manager.py` (162줄) | 주문 상태 기계 (DB 우선 + 파일 폴백) | `docs/impl/order_manager.md` |
| `src/core/indicators.py` (154줄) | RSI/MACD/볼린저/스토캐스틱 계산 (`ta`) | — |
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
| `manager/backend/routers/` | dashboard, users, orders, trades, events, sysconfig, reports, templates, mfa, analytics |

라우트: `/admin/dashboard`, `/admin/users`(+approve/deactivate/activate/block/DELETE), `/admin/orders`, `/admin/trades`, `/admin/events`, `/admin/config`, `/analytics`(admin only). 상세: `manager/README.md`.

## 핵심 데이터 스키마

> **저장 방식**: 1차 저장소는 Supabase PostgreSQL (`shared/schema.sql`). `user_manager`/`order_manager`는
> `is_db_available()`(SUPABASE_URL+SERVICE_KEY)면 DB를 우선 읽고 쓰며, 실패 시 `data/*.json` 파일로 폴백.
> `trade_log`·`operational_events`는 DB+파일 이중 기록. 아래 JSON은 런타임/폴백 표현이며 DB 컬럼과 1:1 대응한다.

### Order (`orders` 테이블 / `data/orders.json` 폴백)
```jsonc
{
  "user_id": "str",
  "exchange": "upbit|bithumb|kis|toss",
  "ticker": "KRW-BTC",
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

## 테스트 실행
```bash
# Docker 내부에서 실행 (호스트 Python 미설치)
docker compose run --rm supabot python -m pytest tests/ -v
```

## 작업별 문서 진입점

| 작업 | 읽을 문서 |
|------|-----------|
| 거래소 API 추가/수정 | `docs/impl/exchange_adapter.md` |
| 주문 상태 추적 수정 | `docs/impl/order_manager.md` |
| 유저 설정 스키마 변경 | `docs/impl/user_manager.md` |
| RSI 계산/가격 역산 | `docs/impl/signal_engine.md` → `docs/detail/rsi_algorithm.md` |
| 텔레그램 커맨드 추가 | `docs/impl/main_handlers.md` |
| KIS 장외/재주문 로직 | `docs/detail/kis_market_policy.md` |
| Gemini 자연어 흐름 | `docs/detail/gemini_intent.md` |
| Supabase 스키마 | `shared/schema.sql` |
| 관리 UI 백엔드 (라우터/API 추가·수정) | `manager/README.md` (라우터 표) |
| 관리 UI 프론트엔드 (페이지/컴포넌트 추가·수정) | `manager/README.md` (프론트엔드 구조) → `manager/frontend/DESIGN.md` |
| CI/CD 워크플로 수정 | `docs/github-actions-workflows.md` |
| 신규 사용자 온보딩 | `docs/user-onboarding.md` |
| Docker/배포 (Oracle VM) | `docs/oracle-cloud-deploy-sequence.md` (최초 VM 셋업은 `docs/oracle-cloud-vm-setup.md`) |
