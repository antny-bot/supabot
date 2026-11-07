# 200_system_architecture.md — 시스템 아키텍처 및 데이터 스키마

supabot 봇 백엔드·관리 UI 모듈 구성, 핵심 데이터 스키마(PostgreSQL/JSON 폴백), 인증, 연동 제약사항 설명입니다.

---

## 🤖 봇 모듈 맵 (`src/`)

| 파일 | 책임 | 관련 개발 문서 |
|------|------|-----------------|
| `src/main.py` | 텔레그램 핸들러 등록, 스케줄러 등록 및 봇 실행 루프 진입점 | [205_main_handlers.md](file:///E:/apps/supabot/docs/205_main_handlers.md) |
| `src/internal_api.py` | 매니저 백엔드 연동 webhook API (HMAC 인증, `/internal/notify`, `/internal/order-events`) | — |
| `src/handlers/strategy_handlers.py` | 자동매매 전략 명령 처리 (`/rsitrade`, `/grid`, `/sgrid`, `/sgridrsi`) | [301_rsi_algorithm.md](file:///E:/apps/supabot/docs/301_rsi_algorithm.md) |
| `src/handlers/dca_handlers.py` | 분할 적립식 매수 명령 처리 (`/dca`) | [205_main_handlers.md](file:///E:/apps/supabot/docs/205_main_handlers.md) |
| `src/handlers/manual_order_handlers.py` | 수동 주문 명령 처리 (`/buy`, `/sell`, `/cancel`) | [205_main_handlers.md](file:///E:/apps/supabot/docs/205_main_handlers.md) |
| `src/handlers/query_handlers.py` | 시세/자산/지표 및 도움말 조회 (`/asset`, `/price`, `/indicators`, `/help`) | [205_main_handlers.md](file:///E:/apps/supabot/docs/205_main_handlers.md) |
| `src/handlers/list_view_handlers.py` | 목록 및 페이징 핸들러 (`/orders`, `/history`, `/report`) | [205_main_handlers.md](file:///E:/apps/supabot/docs/205_main_handlers.md) |
| `src/handlers/status_handlers.py` | 통합 전략 대시보드 명령 처리 (`/status`) | [205_main_handlers.md](file:///E:/apps/supabot/docs/205_main_handlers.md) |
| `src/handlers/config_handlers.py` | API 키 및 환경설정 핸들러 (`/config`, `/whoami`) | [103_exchange_api_setup.md](file:///E:/apps/supabot/docs/103_exchange_api_setup.md) |
| `src/handlers/watch_handlers.py` | 실시간 시그널 감시 핸들러 (`/watch`, `/unwatch`) | [204_signal_engine.md](file:///E:/apps/supabot/docs/204_signal_engine.md) |
| `src/handlers/system_handlers.py` | 시스템 관리 명령 처리 (`/start`, `/halt`, `/resume`, `/dbsync`, `/resetuser`) | [205_main_handlers.md](file:///E:/apps/supabot/docs/205_main_handlers.md) |
| `src/handlers/nl_intent_handlers.py` | Gemini 자연어 인텐트 실행 및 콜백 핸들러 | [304_gemini_intent.md](file:///E:/apps/supabot/docs/304_gemini_intent.md) |
| `src/core/order_sync.py` | 거래소 실시간 주문 동기화 엔진 (체결/취소/만료 감지, 사후 액션 유발, KIS 재주문 및 예약주문 정규장 처리) | [202_order_manager.md](file:///E:/apps/supabot/docs/202_order_manager.md) |
| `src/core/order_execution.py` | 주문 생성 및 체결 사후 연동 처리 | [202_order_manager.md](file:///E:/apps/supabot/docs/202_order_manager.md) |
| `src/core/order_manager.py` | 주문 상태 관리 (DB 우선 + 파일 폴백) | [202_order_manager.md](file:///E:/apps/supabot/docs/202_order_manager.md) |
| `src/core/dca_manager.py` | DCA 적립식/분할 매매 스케줄러 (시장가/지정가 주문, 휴장일/서킷브레이커 이월 관리) | [205_main_handlers.md](file:///E:/apps/supabot/docs/205_main_handlers.md) |
| `src/core/exchange_adapter.py` | 거래소 레지스트리/파사드 | [201_exchange_adapter.md](file:///E:/apps/supabot/docs/201_exchange_adapter.md) |
| `src/core/exchanges/base.py` | `BaseExchange` — 거래소 capability 기본값 정의 | [201_exchange_adapter.md](file:///E:/apps/supabot/docs/201_exchange_adapter.md) |
| `src/core/exchanges/{upbit,bithumb,kis,toss}.py` | 거래소별 HTTP/인증 구현 및 capability 오버라이드 | [201_exchange_adapter.md](file:///E:/apps/supabot/docs/201_exchange_adapter.md) |
| `src/core/exchanges/common.py` | `CommonMixin` — 틱사이즈 static 유틸 | — |
| `src/core/signal_engine.py` | RSI 계산 + 목표가 역산 알고리즘 | [204_signal_engine.md](file:///E:/apps/supabot/docs/204_signal_engine.md) |
| `src/core/indicators.py` | RSI/MACD/볼린저/스토캐스틱 계산 (`ta`) | — |
| `src/core/user_manager.py` | 유저 설정·권한 (DB 우선 + 파일 폴백) | [203_user_manager.md](file:///E:/apps/supabot/docs/203_user_manager.md) |
| `src/core/trading_gate.py` | 글로벌 거래 중지(kill-switch) + 총 노출 한도 게이트 | [205_main_handlers.md](file:///E:/apps/supabot/docs/205_main_handlers.md) |
| `src/core/db.py` & `db_sync.py` | Supabase REST 클라이언트 (requests 기반, ALPN 회피) 및 동기화 | — |
| `src/core/secret_crypto.py` | 사용자 키 Fernet 암복호화 (`enc:v1:`) | [205b_security_logging.md](file:///E:/apps/supabot/docs/205b_security_logging.md) |
| `src/core/natural_language.py` | NL 전처리 + Gemini 인텐트 처리 + `nl_logs` 기록 | [304_gemini_intent.md](file:///E:/apps/supabot/docs/304_gemini_intent.md) |
| `src/core/formatters.py` | Telegram 메시지 포매팅 | — |
| `src/core/parsers.py` | 거래소명·숫자(억/만)·RSI 파싱, KIS 세션 판정 | [205c_utility_parsers.md](file:///E:/apps/supabot/docs/205c_utility_parsers.md) |
| `src/core/stock_resolver.py` | 한국 주식 종목명→코드 해석 (DB 캐시 연동) | — |
| `src/core/trade_log.py` | 체결 로그 (DB + 파일 이중기록) | — |
| `src/core/command_log.py` | 명령어 사용 로그 | — |
| `src/core/metrics.py` | 인메모리 운영 메트릭 | — |
| `src/core/operational_events.py` | 운영 이벤트 (DB + 파일 이중기록, 마스킹) | [205b_security_logging.md](file:///E:/apps/supabot/docs/205b_security_logging.md) |
| `src/core/bot_logger.py` | 구조화 JSON 로깅 (stdout) | — |
| `data/orders.json` · `users.json` | DB 폴백/로컬 캐시 (0600) | — |
| `config/.env` | BOT_TOKEN, ADMIN_CHAT_ID, SUPABASE_*, MANAGER_API_KEY | — |

---

## 🖥️ 관리 UI 모듈 맵 (`manager/`)

FastAPI 백엔드 + React/TypeScript(Vite+Tailwind) SPA. Synology Docker 배포 (`ghcr.io/antny-bot/supabot-manager`, 포트 8000).

| 파일 | 책임 |
|------|------|
| `manager/backend/main.py` | FastAPI 앱, 세션, 로그인/로그아웃 |
| `manager/backend/db.py` | Supabase REST 클라이언트 (= `src/core/db.py`) |
| `manager/backend/auth.py` | Supabase Auth 이메일/비번 로그인 |
| `manager/backend/bot_client.py` | 봇 `/internal/notify`, `/internal/execute_dca`, `/internal/order-events` 연동 |
| `manager/backend/routers/` | dashboard, users, orders, trades, events, sysconfig, reports, templates, mfa, analytics, stock_cache (11개 라우터) |
| `manager/backend/services/budget_manager.py` | 예산 플랜 관리, 감사 원장(budget_ledger) 및 예수금 Health Check 전담 엔진 |
| `manager/backend/services/progression_manager.py` | 전략 일단위 실행 흐름, 진행 상태 및 대사(Reconciliation), 주문 취소/이월 처리 |
| `manager/backend/services/order_planner.py` | 목표 비중/수량 기반 주문 생성 및 슬리피지/호가 플래너 |
| `manager/backend/services/universe_resolver.py` | 시장 시가총액 TOP 50 동적 유니버스 및 일별 스냅샷 리졸버 |

상세 구조: [manager/README.md](file:///E:/apps/supabot/manager/README.md), [manager/frontend/DESIGN.md](file:///E:/apps/supabot/manager/frontend/DESIGN.md) 참고.

---

## 🗄️ 핵심 데이터 스키마

> **저장 방식**: 1차 저장소 Supabase PostgreSQL (`shared/schema.sql`). `user_manager`/`order_manager`는 `is_db_available()`(SUPABASE_URL+SERVICE_KEY)면 DB 우선, 실패 시 `data/*.json` 폴백. `trade_log`·`operational_events` DB+파일 이중 기록.

### 1. Order (`orders` 테이블 / `data/orders.json` 폴백)
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
  "strategy": "manual|grid|rsitrade|dca",
  "target_rsi": null,          // rsitrade 전략 전용
  "linked_to": null,           // 매수-매도 쌍 연결
  "status": "wait|partial|done|cancel|pending_reorder|cancel_requested",
  "created_at": 1700000000.0,
  "next_check_at": 0.0,
  "reorder_of": null,          // 재주문 시 이전 uuid
  "stop_price": null,          // rsitrade_sell 전용: 손절 기준가 (stop_loss_pct로 계산)
  "template_id": null          // 전략 템플릿 ID (예산 플랜 및 감사 추적 연결)
}
```

### 2. User (`users` 테이블 / `data/users.json` 폴백)
```jsonc
{
  "<user_id>": {
    "username": "str",
    "is_admin": false,
    "is_active": false, // DB는 status 문자열 사용, 파일 폴백 표현은 is_active bool
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
      "signal_bb_alert": false,    // 볼린저 하단 이탈 시 추가 알림
      "asset_min_display_krw": 10000,
      "llm_enabled": false,
      "llm_model": "gemini-2.5-flash",
      "poll_active_interval": 60,
      "poll_no_order_interval": 300,
      "signal_analysis_interval": 300
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

### 3. Supabase 테이블 (`shared/schema.sql` 정의)

| 테이블 | 용도 |
|--------|------|
| `users` | 유저 설정·권한·암호화 키 |
| `orders` | 주문 상태 (Unix timestamp `DOUBLE PRECISION`) |
| `trade_logs` | 체결 내역 |
| `operational_events` | 운영 이벤트 로그 |
| `nl_logs` | 미처리 자연어 익명 로그 |
| `system_config` | 시스템 전체 설정 (폴링 및 분석 간격 등) |
| `command_logs` | 명령어 사용 raw 로그 (매일 집계 후 삭제) |
| `command_log_daily` | 명령어 사용 일별 요약 (Analytics 분석용) |
| `kr_stock_cache` | 한국 주식 종목명→코드 DB 캐시 (TTL 90일) |
| `strategy_templates` | 사용자별 전략 템플릿 (매개변수 params JSONB, 예산 플랜, 실행 설정) |
| `dca_schedules` | 정기 분할/적립식 매매 스케줄러 (주기, 요일, 실행시각, 주문방식(market/limit), 이월모드) |
| `budget_ledger` | 전략별 예산 감사 원장 (5대 불변식 보장, 일일충전/주문차감/환원/수수료정산 내역) |
| `market_top_snapshots` | KOSPI/KOSDAQ/코인 시장별 마스터 시가총액 TOP 50 프리징 일별 스냅샷 |
| `feedbacks` | 사용자 피드백 및 오류 보고 접수 |

---

## 🔑 거래소별 인증 방식

| 거래소 | 방식 | 비고 |
|--------|------|------|
| **Upbit** | CLI subprocess (`upbit` 명령) | Node.js, async subprocess |
| **Bithumb** | REST + JWT (SHA512 query hash) | aiohttp 세션 재사용 |
| **KIS** | OAuth2 (client_credentials) | 토큰 캐시 per user/env/key |
| **Toss** | OAuth2 Bearer (`/api/v1/oauth2/token`) | 토큰 캐시 per user/client_id, account_seq 자동 조회 |

---

## ⚠️ 주요 제약사항

* **KIS 정규장**: 평일 09:00-15:35 KST 주문 조회. 장외 전략 주문 → `pending_reorder` 상태 대기.
* **수수료 버퍼**: 매수 `×0.999`, 매도 `×1.001` 적용 후 틱사이즈 반올림.
* **분봉 미지원**: KIS/Toss `rsi_interval` 분봉 시 RSI 명령어 거부.
* **실거래 경로**: 실제 네트워크 도달 시 실계좌 매매 발생. 테스트 시 mock 필수.
* **재주문**: KIS 전략 주문 만료 시 미체결 잔량(`volume - filled_volume`)만 재주문.
* **해외주식 통화 혼재**: `trade_logs` currency 컬럼 없음. KRW/USD 구분 `is_us_stock_ticker()` 패턴 검사로 추론.
* **DCA 주문 방식 & 이월 모드**: DCA 주문은 지정가(`limit`, 현재가 기준 호가) 또는 시장가(`market`, 즉시 체결)를 지원하며, 업비트/빗썸 시장가 매수는 `ord_type="price"` 총액 매수로 발행. 휴장일/임시공휴일 또는 사이드카·서킷브레이커 발동 시 설정된 이월 정책(`next_day`: 다음 거래일 정규장 개장, `delay_20m`: 20분 후 재시도, `skip`: 건너뛰기)으로 안전하게 자동 처리.
* **통합 예산 플랜 & 감사 원장(Budget Audit Ledger)**: 전략별 예산은 `strategy_templates`의 `budget_mode`(`total` | `monthly`)와 `budget_ledger`를 통해 관리되며, 일일 충전(`DAILY_CREDIT`), 주문 집행(`BUY_ORDER_SPEND`), 취소 환원(`ORDER_CANCEL_REFUND`), 매도 대금 재투입(`SELL_PROCEEDS_RECYCLE`)이 1원 단위 감사 원장으로 기록되어 원장-잔액 항등식 및 일일 충전 멱등성 보장.
