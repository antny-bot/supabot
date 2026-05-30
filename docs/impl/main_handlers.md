# main_handlers.md

**파일**: `src/main.py` (2500줄대)

## 모듈 전역 객체

```python
user_manager     = UserManager()
exchange_adapter = ExchangeAdapter(user_manager)
order_manager    = OrderManager()
signal_engine    = SignalEngine(user_manager, exchange_adapter)
_order_wake_event: asyncio.Event    # 새 주문 시 sync 루프 즉시 깨움
_pending_nl_intents: dict           # token → {user_id, intent} (Gemini 확인 대기)
NL_UNMATCHED_LOG_PATH: str          # 전처리 미처리 자연어 익명 로그
KST = timezone(timedelta(hours=9))
```

## 커맨드 맵

| 커맨드 | 핸들러 | 비고 |
|--------|--------|------|
| /start | `start_command` | 유저 등록; 관리자 승인 요청 |
| /help, /commands | `help_command` | 전체 커맨드 메뉴 |
| /info | `info_command` | build_info.py의 버전/빌드 정보 |
| /config | `config_command` (ConversationHandler) | 다단계 키 설정 |
| /nlstats | `nlstats_command` | 관리자 전용 자연어 전처리 후보 통계 |
| /asset | `asset_command` | 포트폴리오 전체 잔고 |
| /price, /p | `price_command` | 실시간 시세 |
| /history | `history_command` | 최근 체결 내역 |
| /orders | `orders_command` | 추적 중 미체결 주문 목록 |
| /status | `status_command` | 전략 대시보드 |
| /buy | `buy_command` | 단일 지정가 매수; KIS는 확인 필요 |
| /sell | `sell_command` | 단일 지정가 매도; KIS는 확인 필요 |
| /grid | `grid_command` | 가격 범위 → N개 분할 매수 |
| /sgrid | `sgrid_command` | 보유 수량 기반 분할 매도 |
| /rsitrade | `rsitrade_command` | RSI 역산 분할 전략 |
| /cancel | `cancel_command` | 종목 전체 주문 취소 |
| /watch | `watch_command` | RSI 감시 종목 추가 |
| /unwatch | `unwatch_command` | 감시 종목 제거 |
| (일반 텍스트) | `natural_language_command` | Gemini 자연어 처리 |

## ConversationHandler 상태 (/config)

```
SET_EXCHANGE (0)
    │ conf_* 버튼
    ├─→ SET_ACCESS (1) → SET_SECRET (2)            (Upbit/Bithumb)
    ├─→ SET_KIS_APP (3) → SET_KIS_SECRET (4)
    │       → SET_KIS_ACCOUNT (5) → SET_KIS_PRODUCT (6) → SET_KIS_ENV (7)
    └─→ SET_GEMINI_KEY (8)
```

API 키 포함 메시지는 캡처 즉시 삭제됨 (`delete_message`).

## 인증 미들웨어

`@check_auth` 데코레이터 (대부분의 핸들러 적용):
1. `user_manager.get_user(chat_id)` 조회
2. 없으면 미등록 안내 반환
3. `is_active=False` 이면 승인 대기 안내 반환
4. 정상이면 핸들러 호출 (`user` dict 세 번째 인자로 전달)

## 백그라운드 루프 (`post_init` 에서 시작)

### order_sync_loop
- `sync_orders(application)` 반복 호출
- 간격: 주문 있을 때 `poll_active_interval` (60초) / 없을 때 `poll_no_order_interval` (300초)
- `_order_wake_event` 로 새 주문 시 즉시 깨어남

### signal_analysis_loop
- `signal_engine.analyze_watchlist(application)` 반복 호출
- 간격: `signal_analysis_interval` (300초)
- **관리자 preferences가 두 루프 간격 결정**

### sync_orders 핵심 로직
각 추적 주문에 대해:
1. KIS 장외 → `market_closed`/`pending_reorder` + `next_check_at` 설정
2. KIS `pending_reorder` → 잔량 재주문 시도 (`replace_order_uuid`)
3. 일반 → `get_order_status` 조회; 새 체결 시 `filled_volume` 업데이트
4. rsitrade 매수 체결 → RSI 역산으로 매도가 계산, 매도 주문 생성
5. `done`/`cancel` → 추적 제거 또는 `pending_reorder` 처리 (KIS 전략)

## Gemini 자연어 흐름 (요약)

1. 일반 텍스트 → `natural_language_command` (`llm_enabled` 시)
2. `preprocess_natural_language_intent(text, user)` 로 안전한 조회 표현을 먼저 처리
   - 조회 action만 허용: `asset`, `price`, `orders`, `status`, `history`, `config_view`, `help`
   - 매수/매도/취소/설정 변경성 표현은 전처리하지 않음
   - 전처리 성공 시 Gemini를 호출하지 않고 로그도 남기지 않음
3. 전처리 실패 시 `parse_natural_language_intent(text, user)` → Gemini API → JSON intent
4. `normalize_natural_language_intent(text, intent, user)` 로 서버 후처리 보정
   - `주문대기`, `예약 주문`, `추적 중인 전략 주문` → `status`
   - `미체결`, `오픈오더`, `거래소에 걸린 주문` → `orders`
5. 전처리 실패로 Gemini까지 간 문장은 `append_natural_language_log()` 로 `data/nl_unmatched.jsonl`에 익명 기록
6. **읽기 액션** (`asset`, `price`, `orders`, `status`, `history`, `config_view`, `help`): `execute_query_intent` 즉시 실행
7. **쓰기 액션** (buy, sell, grid, rsitrade 등): 확인 버튼 표시 → 클릭 시 `execute_confirmed_intent`

관리자는 `/nlstats`로 `data/nl_unmatched.jsonl`의 상위 미처리 패턴, LLM action, 최종 action 집계를 확인할 수 있다. 로그에는 chat_id/user_id를 저장하지 않고 숫자, 6자리 주식코드, 긴 토큰을 마스킹한다.

상세 Intent 스키마 및 흐름: `docs/detail/gemini_intent.md`

## KIS 시간 헬퍼

```python
is_kis_regular_session(now=None)   → bool    # 평일 09:00–15:35 KST
next_kis_regular_session(now=None) → datetime
kis_next_check_timestamp(now=None) → float   # Unix timestamp
```

상세: `docs/detail/kis_market_policy.md`

## 유틸리티 함수 (main.py)

```python
parse_exchange_and_ticker(args, default_exchange)  # args → (exchange, ticker)
normalize_exchange(value)          # "빗썸" → "bithumb", "한투" → "kis" 등
parse_number(value)                # "100만" → 1000000.0
parse_rsi_range("25-30")           # → (25.0, 30.0)
interpolate_range(start, end, i, count)  # i번째 균등 분할값
validate_max_order(user, order_krw)      # max_order_krw 제한 확인
parse_config_value(key, raw_value)       # /config set 타입 검증·변환
validate_config_update(user, key, value) # 제약 위반 시 ValueError
preprocess_natural_language_intent(text, user) # 조회성 자연어 전처리
append_natural_language_log(text, llm_intent, final_intent) # 익명 JSONL 로그 저장
read_natural_language_log_stats(path, limit) # /nlstats 집계
```
