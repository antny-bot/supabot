# main_handlers.md

**파일**: `src/main.py` (약 765줄, 핸들러는 `src/handlers/*.py`로 분리)

## 모듈 전역 객체

```python
user_manager     = UserManager()
exchange_adapter = ExchangeAdapter(user_manager)
order_manager    = OrderManager()
signal_engine    = SignalEngine(user_manager, exchange_adapter)
metrics          # core.metrics — 인메모리 운영 지표 (주문 성공률, 레이턴시, 루프 타임스탬프)
_order_wake_event: asyncio.Event    # 새 주문 시 sync 루프 즉시 깨움
_pending_nl_intents: dict           # token → {user_id, intent} (Gemini 확인 대기)
KST = timezone(timedelta(hours=9))
```

데이터 영속화는 `core.db`(Supabase REST 클라이언트)를 통한 DB-우선 + `data/*.json` 파일 폴백 구조다. `user_manager`/`order_manager`는 DB-우선, `trade_log`/`operational_events`는 DB + 파일 이중 쓰기를 한다.

## 커맨드 맵

| 커맨드 | 핸들러 | 비고 |
|--------|--------|------|
| /start | `start_command` | 유저 등록; 관리자 승인 요청 |
| /help, /commands | `help_command` | 전체 커맨드 메뉴 |
| /info | `info_command` | build_info.py의 버전/빌드 정보 |
| /config, /cfg | `config_command` (ConversationHandler) | 다단계 키 설정 |
| /whomai, /me | `whoami_command` | 내 ID, 권한, 활성 상태 확인 |
| /asset | `asset_command` | 포트폴리오 전체 잔고 |
| /price, /p | `price_command` | 실시간 시세 |
| /indicators, /ind | `indicators_command` | RSI/MACD/BB/Stoch 멀티지표 |
| /history | `history_command` | 최근 체결 내역 |
| /report | `report_command` | 기간별 수익률 리포트 |
| /orders | `orders_command` | 추적 중 미체결 주문 목록 |
| /status | `status_command` | 전략 대시보드 |
| /buy | `buy_command` | 단일 지정가 매수 확인 후 전송; 확인 요청 10분 만료 |
| /sell | `sell_command` | 단일 지정가 매도 확인 후 전송; 확인 요청 10분 만료 |
| /grid | `grid_command` | 가격 범위 → N개 분할 매수 |
| /sgrid | `sgrid_command` | 보유 수량 기반 분할 매도 |
| /rsitrade, /gridrsi | `rsitrade_command` | RSI 역산 분할 매수 전략 (gridrsi는 alias) |
| /sgridrsi | `sgridrsi_command` | RSI 목표가 분할 매도 전략 (보유 코인 직접 매도) |
| /cancel | `cancel_command` | 종목 전체 주문 취소 (확인 버튼 후 실행) |
| /cancelno | `cancelno_command` | 배치 번호(#N)로 주문 묶음 취소 (확인 버튼 후 실행) |
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
- 간격은 `_get_admin_prefs()`로 결정 — `is_db_available()`이면 `system_config` 테이블의 `poll_active_interval`/`poll_no_order_interval`/`signal_analysis_interval`을 **먼저** 읽고, 실패 시 관리자 유저 preferences로 폴백한다.
- `_order_wake_event` 로 새 주문 시 즉시 깨어남
- `metrics.record_poll_ok()`로 루프 성공 타임스탬프 기록

### Telegram 명령어 메뉴
- `post_init`에서 `application.bot.set_my_commands(DEFAULT_BOT_COMMANDS, BotCommandScopeDefault())`를 호출해 일반 Telegram slash command 메뉴를 갱신한다.
- 관리자 chat에도 `BotCommandScopeChat`으로 동일 목록을 등록한다 — `ADMIN_BOT_COMMANDS == DEFAULT_BOT_COMMANDS`이며 관리자 전용 메뉴 항목은 더 이상 없다.
- `/me`, `/p`, `/ind`, `/cfg`, `/rsigrid` 등은 숨은 alias라 메뉴에는 표시하지 않고 `CommandHandler`로만 등록한다.
- 메뉴 갱신 실패는 봇 시작 실패로 처리하지 않고 경고 로그를 남기고 `append_operational_event`로 기록한다.

### signal_analysis_loop
- `signal_engine.analyze_watchlist(application)` 반복 호출
- 간격: `signal_analysis_interval` (300초), `_get_admin_prefs()` 사용
- **`system_config` 테이블이 세 루프 간격을 우선 결정**하고, DB 미사용 시 관리자 preferences로 폴백

### sync_orders 핵심 로직
각 추적 주문에 대해:
1. KIS 장외 → `market_closed`/`pending_reorder` + `next_check_at` 설정
2. KIS `pending_reorder` → 잔량 재주문 시도 (`replace_order_uuid`)
3. 일반 → `get_order_status` 조회; 새 체결 시 `filled_volume` 업데이트
4. rsitrade/gridrsi 매수 체결 + `linked_to` 있을 때 → RSI 역산으로 매도가 계산, 매도 주문 생성 (`rsitrade_sell`)
5. `done`/`cancel` → 추적 제거 또는 `pending_reorder` 처리 (KIS 전략)

## Gemini 자연어 흐름 (요약)

1. 일반 텍스트 → `natural_language_command` (`llm_enabled` 시)
2. `preprocess_natural_language_intent(text, user)` 로 안전한 조회 표현을 먼저 처리
   - 조회 action만 허용: `asset`, `price`, `orders`, `status`, `history`, `config_view`, `help`
   - 매수/매도/취소/설정 변경성 표현은 전처리하지 않음
   - 전처리 성공 시 Gemini를 호출하지 않고 원문 로그도 남기지 않음
3. 전처리 실패 시 `parse_natural_language_intent(text, user)` → Gemini API → JSON intent
4. `normalize_natural_language_intent(text, intent, user)` 로 서버 후처리 보정
   - `주문대기`, `예약 주문`, `추적 중인 전략 주문` → `status`
   - `미체결`, `오픈오더`, `거래소에 걸린 주문` → `orders`
5. 전처리 성공은 `data/nl_preprocess_hits.json`에 action 카운트만 기록하고, 원문은 저장하지 않음
6. 전처리 실패로 Gemini까지 간 문장은 `append_natural_language_log()` 로 `data/nl_unmatched.jsonl`에 익명 기록
7. **읽기 액션** (`asset`, `price`, `orders`, `status`, `history`, `config_view`, `help`): `execute_query_intent` 즉시 실행
8. **쓰기 액션** (buy, sell, grid, rsitrade, gridrsi, sgridrsi 등): 확인 버튼 표시 → 클릭 시 `execute_confirmed_intent`

자연어 전처리/미처리 로그는 `core.natural_language`가 관리하며 `nl_logs` 테이블(및 파일 폴백)에 기록한다. 로그에는 chat_id/user_id를 저장하지 않고 숫자, 6자리 주식코드, 긴 토큰을 마스킹한다. (`/nlstats` 명령은 제거됨.)

## 사용자 Secret 암호화

`UserManager`는 `USER_SECRET_KEY`가 설정되어 있으면 거래소/Gemini 키를 `enc:v1:<ciphertext>` 형식으로 `data/users.json`에 저장한다.

- 암호화 대상: Upbit/Bithumb `access_key`, `secret_key`; KIS `app_key`, `app_secret`, `account_no`; Gemini `gemini_api_key`
- `get_user()`는 런타임 사용을 위해 복호화된 copy를 반환한다.
- 내부 `user_manager.users`와 파일에는 암호문을 유지한다.
- 기존 평문 secret은 봇 시작 시 자동 마이그레이션한다.
- `USER_SECRET_KEY`가 없거나 Fernet 형식이 아니면 기존 평문 읽기는 유지하지만 새 secret 저장은 실패한다.
- 이미 암호화된 값은 같은 `USER_SECRET_KEY`로만 복호화된다. 다른 키가 들어오면 `get_user()`는 secret 필드를 빈 값으로 반환하고 `_secret_error`를 표시해서 `/start` 같은 기본 명령이 죽지 않게 한다.
- 거래소 API 키 저장 직후 검증 결과는 `api_validation`에 캐시하며, `/config -v`에서 마지막 성공/실패 시각을 표시한다. 조회 시점에 라이브 API를 새로 호출하지 않는다.
- 암호화/복호화 로직은 `core.secret_crypto`로 분리됨 (`encrypt_secret`/`decrypt_secret`, `enc:v1:` 포맷).

## 이벤트 로그

운영 이벤트는 `core.operational_events`가 `operational_events` 테이블 + 파일 이중 쓰기(DB + file dual write)로 기록한다.

- 기록 대상: 백그라운드 루프 예외, Telegram 메뉴/시작 알림 실패, secret key 이상, API 검증 실패, 주문 실패, 주문 확인 만료
- API 키, secret, 긴 토큰, 계좌성 숫자는 마스킹

수동 `/buy`, `/sell`은 callback_data에 주문값을 넣지 않고 `_pending_manual_orders` 서버 측 토큰을 사용한다. 토큰은 10분 후 만료되며 실행 직전 `max_order_krw`를 다시 검증한다.

전략 `/grid`,`/sgrid`,`/rsitrade`,`/sgridrsi`도 동일한 패턴으로 `core.strategy_tokens`(`create_strategy_token`/`pop_valid_strategy_token`, 10분 만료) 단일 사용 토큰을 쓴다. confirm 콜백 데이터는 `gridrun|<token>` 등 토큰만 싣고 payload는 서버 메모리에 보관한다 — 텔레그램 callback_data 64바이트 한도 회피 + 더블탭 시 두 번째 클릭은 만료 처리(중복 주문 방지).

`/cancel`, `/cancelno`도 동일한 패턴(`_pending_cancel_orders`, `create_cancel_token`/`pop_valid_cancel_token`, 10분 만료)으로 취소 대상 주문 목록을 먼저 보여주고, `cancelrun|<token>`(확정) / `cancelabort|<token>`(취소) 콜백으로 실제 취소를 실행한다 (`query_handlers.cancel_confirm_callback`).

## 거래 안전장치 (kill-switch · 노출 한도)

- **글로벌 거래 중지**: 관리자 `/halt`(중지)/`/resume`(재개). 상태는 `system_config.trading_halt`(`'1'`/`'0'`, DB 미사용 시 `data/trading_halt.flag` 파일 폴백)에 저장. `core.trading_gate.assert_can_trade()`가 수동/전략 주문 confirm 및 KIS 재주문(`sync_orders`) 직전에 차단한다. **손절·익절 등 보호성 매도는 차단하지 않는다**(포지션 방치 방지).
- **총 노출 한도**: 유저 preference `max_open_exposure_krw`. 미체결 원화 주문 잔여 노출(`core.parsers.compute_open_exposure_krw`) + 신규 주문 합이 한도를 넘으면 매수 주문을 거부(`validate_total_exposure`). USD(토스 해외주식) 주문은 통화가 달라 제외.

상세 Intent 스키마 및 흐름: `docs/detail/gemini_intent.md`

## KIS 시간 헬퍼

```python
is_kis_regular_session(now=None)   → bool    # 평일 09:00–15:35 KST
next_kis_regular_session(now=None) → datetime
kis_next_check_timestamp(now=None) → float   # Unix timestamp
```

상세: `docs/detail/kis_market_policy.md`

## 주요 유틸리티 함수

대부분의 파싱·검증 유틸은 `core.parsers`, 메시지 포맷팅 유틸은 `core.formatters`로 분리되어 main.py가 import 한다.

```python
# core.parsers
parse_exchange_and_ticker(args, default_exchange)  # args → (exchange, ticker)
normalize_exchange(value)          # "빗썸" → "bithumb", "한투" → "kis" 등
parse_number(value)                # "100만" → 1000000.0
parse_rsi_range("25-30")           # → (25.0, 30.0)
interpolate_range(start, end, i, count)  # i번째 균등 분할값
validate_max_order(user, order_krw)      # max_order_krw 제한 확인
parse_config_value(key, raw_value)       # /config set 타입 검증·변환
validate_config_update(user, key, value) # 제약 위반 시 ValueError
is_kis_regular_session/next_kis_regular_session/kis_next_check_timestamp  # KIS 정규장 판정

# core.natural_language
preprocess_natural_language_intent(text, user)  # 조회성 자연어 전처리
append_natural_language_log(text, llm_intent, final_intent)  # 익명 로그 저장 (nl_logs)

# core.formatters
build_account_summary(user_id, user)  # /whomai 응답 생성
```
