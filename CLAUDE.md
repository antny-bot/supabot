# CLAUDE.md — supabot 에이전트 진입점

## 프로젝트
멀티유저·멀티거래소 텔레그램 자동매매 봇 (Upbit, Bithumb, KIS).
Docker on Oracle Cloud VM. 실거래 경로 포함 — 변경 전 반드시 `AGENTS.md` 확인.

## 모듈 맵

| 파일 | 책임 | 관련 Tier 2 문서 |
|------|------|-----------------|
| `src/main.py` (2124줄) | 텔레그램 핸들러, 폴링 루프, Gemini NL 라우팅 | `docs/impl/main_handlers.md` |
| `src/core/exchange_adapter.py` (730줄) | 3거래소 통합 API 추상화 | `docs/impl/exchange_adapter.md` |
| `src/core/order_manager.py` (119줄) | 주문 JSON 영속화 + 상태 기계 | `docs/impl/order_manager.md` |
| `src/core/signal_engine.py` (98줄) | RSI 계산 + 목표가 역산 | `docs/impl/signal_engine.md` |
| `src/core/user_manager.py` (193줄) | 유저 설정·권한 관리 | `docs/impl/user_manager.md` |
| `data/orders.json` | 런타임 주문 상태 (0600) | — |
| `data/users.json` | 런타임 유저 설정·키 (0600) | — |
| `config/.env` | BOT_TOKEN, ADMIN_CHAT_ID | `config/.env.template` |

## 핵심 데이터 스키마

### Order (`data/orders.json`)
```jsonc
{
  "user_id": "str",
  "exchange": "upbit|bithumb|kis",
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
  "reorder_of": null           // 재주문 시 이전 uuid
}
```

### User (`data/users.json`)
```jsonc
{
  "<user_id>": {
    "username": "str",
    "is_admin": false,
    "is_active": false,
    "preferences": {
      "default_exchange": "upbit",
      "rsi_interval": "day",       // day | 1 | 3 | 5 | 10 | 15 | 30 | 60 | 240
      "rsi_buy_range": "25-30",
      "rsi_sell_range": "65-75",
      "rsi_order_count": 5,
      "rsi_budget_krw": null,
      "max_order_krw": null,
      "signal_alerts": true,
      "signal_rsi_threshold": 30,
      "asset_min_display_krw": 10000,
      "llm_enabled": false,
      "llm_model": "gemini-2.5-flash",
      "poll_active_interval": 60,        // 관리자 전용
      "poll_no_order_interval": 300,     // 관리자 전용
      "signal_analysis_interval": 300    // 관리자 전용
    },
    "exchanges": {
      "upbit":   { "access_key": "", "secret_key": "", "watchlist": [] },
      "bithumb": { "access_key": "", "secret_key": "", "watchlist": [] },
      "kis":     { "app_key": "", "app_secret": "", "account_no": "", "product_code": "01", "env": "paper|real", "watchlist": [] }
    },
    "llm": { "gemini_api_key": "" }
  }
}
```

## 거래소별 인증 방식

| 거래소 | 방식 | 비고 |
|--------|------|------|
| Upbit | CLI subprocess (`upbit` 명령) | Node.js, async subprocess |
| Bithumb | REST + JWT (SHA512 query hash) | aiohttp 세션 재사용 |
| KIS | OAuth2 (client_credentials) | 토큰 캐시 per user/env/key |

## 주요 제약사항

| 제약 | 상세 |
|------|------|
| KIS 정규장 | 평일 09:00-15:35 KST만 주문 조회. 장외 전략 주문 → `pending_reorder` |
| 수수료 버퍼 | 매수 `×0.999`, 매도 `×1.001` 적용 후 tick 반올림 |
| KIS 분봉 미지원 | `rsi_interval`이 분봉이면 KIS RSI 명령 거부 |
| 실거래 경로 | 모든 order 관련 코드 = 실머니. 테스트에서 live API 호출 금지 |
| 재주문 | KIS 전략 주문 만료 시 `volume - filled_volume` 잔량만 재주문 |

## 테스트 실행
```bash
# Docker 내부에서 실행 (호스트 Python 미설치)
docker compose run --rm sutt-bot python -m pytest tests/ -v
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
| Docker/배포 | `docs/oracle-cloud-deploy-sequence.md` |
