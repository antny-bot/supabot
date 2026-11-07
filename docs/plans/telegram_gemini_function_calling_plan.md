# 텔레그램 AI 에이전트(Gemini Function Calling) 및 Backend REST API 연동 개발 계획서

> **대상 에이전트**: Gemini 3.8 Flash (코딩 및 검수 에이전트)
> **작성 목적**: 기존 단발성 JSON 스키마(`TradeIntentModel`) 분류 방식의 한계를 넘어, **Gemini Function Calling (Tool Use)** 기반의 멀티턴 에이전트 루프(Agentic Loop)를 구축한다. 이를 통해 텔레그램 자연어 대화만으로 주문 조회·취소·신규 주문·전략 템플릿·예산 원장 등 `supabot` 코어 및 `manager/backend` REST API의 모든 기능을 조합하여 처리한다.

---

## 0. 에이전트 작업 준수 사항 (필독)

1. **실거래 안전 규칙 준수 ([`docs/100_project_standards.md`](file:///E:/apps/supabot/docs/100_project_standards.md))**
   - 모든 주문/취소/예산 변경 경로는 실계좌에 직접 영향을 미치므로 **읽기 전용 도구(Read-Only Tools)**만 에이전트 루프 내에서 즉시 자동 실행하고, **쓰기/변경 도구(Mutating Tools)**는 반드시 **실행 계획 제안(Pending Plan) → 사용자의 `[✅ 실행] / [❌ 취소]` 인라인 버튼 승인** 후에만 실제 실행되도록 설계한다.
   - 모든 단위 테스트에서 실제 거래소 네트워크 호출(`create_order`, `cancel_order`, `get_ticker`, `get_balances`)과 Manager HTTP 호출, Gemini SDK 호출(`client.models.generate_content`)은 반드시 `unittest.mock.patch` 또는 `AsyncMock`으로 모킹(Mock)한다.
2. **하위 호환성 유지**
   - 빠른 응답과 토큰 절약을 위해 기존의 규칙 기반 전처리(`preprocess_natural_language_intent`)는 1차 패스트트랙(Fast-track)으로 유지한다.
   - 기존 테스트(`pytest tests/`)가 단 하나도 깨지지 않도록 하위 호환성을 보장하며 단계별(Phase 1 → Phase 4)로 구현한다.
3. **검증 명령어**
   - 문법 검사:
     ```bash
     python -m py_compile src/core/nl_agent.py src/core/nl_tools.py src/core/manager_api_client.py src/handlers/nl_intent_handlers.py manager/backend/routers/_auth.py
     ```
   - 단위 테스트 실행:
     ```bash
     pytest tests/test_nl_agent_tools.py tests/test_natural_language.py
     ```
   - 전체 회귀 테스트:
     ```bash
     pytest tests/
     ```

---

## 1. 아키텍처 설계 (Target Architecture)

### 1.1. 기존 방식 vs Function Calling 에이전트 방식 비교

| 구분 | 기존 (`TradeIntentModel` 단발성) | 신규 (`Function Calling` 멀티턴 에이전트) |
|------|-----------------------------------|--------------------------------------------|
| **호출 구조** | `response_schema=TradeIntentModel` 1회 호출 | `tools=[...]` 등록 후 최대 `MAX_STEPS(5)` 루프 |
| **복합 요청** | 불가 (*"미체결 확인하고 가장 오래된 것 취소해줘"* 실패) | 가능 (1. 미체결 조회 도구 실행 → 2. 결과 확인 후 특정 UUID 취소 제안) |
| **Backend 연동** | 봇 내부 핸들러 일부만 고정 매핑 | Bot Core 직접 호출 + Manager REST API(`templates`, `budget`, `reports` 등) 전면 활용 |
| **안전장치** | 단일 `intent` dict를 `_pending_nl_intents`에 저장 | 단일 또는 복수의 `ProposedAction` 리스트를 `_pending_nl_intents`에 저장 후 일괄 승인/취소 |

### 1.2. 전체 데이터 및 제어 흐름

```mermaid
flowchart TD
    U[사용자 텔레그램 자연어 입력] --> P{1. 룰 기반 전처리<br/>preprocess_natural_language_intent}
    P -->|단순 조회 적중| Q[즉시 실행 및 응답<br/>Gemini 미호출 / 비용 0]
    P -->|미적중 / 복합·변경 요청| A[2. Gemini Agentic Loop 진입<br/>src/core/nl_agent.py]

    subgraph AgentLoop["멀티턴 Function Calling 루프 (최대 5 Step)"]
        A --> G[Gemini API 호출<br/>tools = Read Tools + Write Proposal Tools]
        G --> FC{Function Call 반환?}
        FC -->|Read Tool 호출<br/>예: get_open_orders, get_balances| RT[즉시 실행: Bot Core 또는<br/>Manager REST API 호출]
        RT -->|Tool 실행 결과 JSON 전달| G
        FC -->|Write Tool 호출<br/>예: propose_cancel_orders, propose_create_order| WT[실행 보류 큐에 Action 적재<br/>ProposedAction 생성 및 결과 반환]
        WT --> G
        FC -->|최종 텍스트 응답| DONE[루프 종료]
    end

    DONE --> HAS_WRITE{보류된 Write Action<br/>존재 여부?}
    HAS_WRITE -->|없음: 순수 조회/분석 답변| REPLY[최종 자연어 브리핑 전송]
    HAS_WRITE -->|있음: 주문/취소/설정/템플릿 변경| CONFIRM["실행 계획 요약 + [✅ 실행] / [❌ 취소] 버튼 전송<br/>main._pending_nl_intents[token] 저장"]
    CONFIRM -->|사용자 [✅ 실행] 클릭| EXEC[execute_confirmed_actions<br/>보류된 Action 순차 실행 및 결과 리포트]
```

---

## 2. 단계별 상세 구현 명세 (Implementation Steps)

---

### Phase 1: Bot ↔ Manager Backend 인증 확장 및 REST API 클라이언트 구축

현재 `manager/backend`의 라우터들은 웹 브라우저 세션(`request.session`)만을 통해 인증(`get_current_user`)하고 있다. 텔레그램 봇이 사용자의 대리인(Agent)으로서 Manager의 REST API(`/api/orders`, `/api/templates`, `/api/reports` 등)를 안전하게 호출할 수 있도록 **HMAC 내부 헤더 인증**을 추가한다.

#### Task 1.1: `manager/backend/routers/_auth.py` — Bot HMAC 대리 인증 지원
- **대상 파일**: [`manager/backend/routers/_auth.py`](file:///E:/apps/supabot/manager/backend/routers/_auth.py)
- **수정 내용**:
  1. `get_current_user(request: Request)` 내부에서 세션(`request.session.get("user_email")`)이 없을 경우, 다음 헤더가 존재하는지 확인한다:
     - `X-Bot-User-Id`: 텔레그램 `user_id` 문자열
     - `X-Timestamp`: Unix timestamp 문자열 (5분 이내 유효성 검증)
     - `X-Signature`: `HMAC-SHA256(MANAGER_API_KEY, f"{timestamp}:{bot_user_id}:{request.url.path}")`
     - `X-Is-Admin`: `"true"` 또는 `"false"`
  2. 서명이 유효하면 세션 없이도 아래 dict를 반환하여 모든 기존 Manager 라우터(`orders`, `templates`, `dashboard`, `trades`, `reports`)를 그대로 재사용할 수 있게 한다:
     ```python
     return {
         "email": f"bot_{bot_user_id}@telegram.local",
         "is_admin": is_admin_header,
         "bot_user_id": bot_user_id,
     }
     ```

#### Task 1.2: `src/core/manager_api_client.py` 신규 생성 — Manager REST API 호출기
- **대상 파일**: `src/core/manager_api_client.py` (신규)
- **구현 내용**:
  - 환경변수 `MANAGER_BACKEND_URL` (기본값 `http://localhost:8000`) 및 `MANAGER_API_KEY` 사용.
  - `async def request_manager_api(method: str, path: str, user_id: str, is_admin: bool = False, params: dict = None, json_body: dict = None) -> dict`:
    - `X-Bot-User-Id`, `X-Timestamp`, `X-Signature`, `X-Is-Admin` 헤더를 자동 생성하여 `aiohttp.ClientSession`으로 호출.
    - 타임아웃 10초, 네트워크 오류 시 명확한 에러 dict(`{"ok": False, "error": "..."}`) 반환 (봇 크래시 방지).

---

### Phase 2: Gemini Function Calling 도구 카탈로그(`src/core/nl_tools.py`) 구현

Gemini에게 제공할 도구(Tools)를 **읽기 전용 도구(Immediate Read Tools)**와 **변경 제안 도구(Write Proposal Tools)**로 엄격히 분리하여 정의한다.

#### Task 2.1: 읽기 전용 도구 (루프 내 즉시 실행, 결과값을 Gemini에 반환)
- **대상 파일**: `src/core/nl_tools.py` (신규)
- **도구 목록**:
  1. `get_ticker_price(exchange: str, ticker: str) -> dict`
     - 종목 코드 해석(`resolve_ticker`) 후 현재가, 전일 대비, 고가/저가 반환.
  2. `get_technical_indicators(exchange: str, ticker: str) -> dict`
     - RSI(14), MACD, 볼린저밴드, 스토캐스틱 등 보조지표 계산 결과 반환.
  3. `get_account_balances(exchange: str) -> dict`
     - 사용자의 해당 거래소 보유 현금(KRW/USD) 및 보유 종목 수량·평단가·수익률 목록 반환.
  4. `get_open_orders(exchange: Optional[str] = None, ticker: Optional[str] = None) -> dict`
     - 현재 대기/예약/부분체결 중인 주문 목록(`uuid`, `exchange`, `ticker`, `side`, `price`, `volume`, `filled_volume`, `strategy`, `status`, `created_at`) 반환.
     - AI가 *"제일 오래된 주문 취소해줘"* 또는 *"비트코인 매수 걸려있는 거 다 취소해줘"*를 수행할 때 먼저 호출하여 `uuid`를 특정하는 용도.
  5. `get_recent_trades(exchange: Optional[str] = None, ticker: Optional[str] = None, limit: int = 10) -> dict`
     - 최근 체결 내역(`trade_logs`) 반환.
  6. `get_strategy_templates() -> dict`
     - Manager API (`GET /api/templates`) 또는 DB를 조회하여 등록된 전략 템플릿 목록(ID, 이름, 거래소, 종목, 전략 타입, 활성 상태, 예산 현황) 반환.
  7. `get_budget_health(exchange: str) -> dict`
     - Manager API (`GET /api/templates/budget-health`)를 호출하여 거래소별 필요 예산 대비 실계좌 예수금 상태 반환.
  8. `get_user_settings() -> dict`
     - 사용자의 현재 설정(`preferences`) 반환.

#### Task 2.2: 변경 제안 도구 (실제 실행하지 않고 `pending_actions` 큐에 적재)
- **설계 원칙**: Gemini가 주문이나 취소를 결정했을 때 호출하는 함수들이다. 이 함수들은 **절대로 거래소 API나 DB 쓰기를 즉시 호출하지 않는다.** 대신 실행에 필요한 파라미터를 검증(틱사이즈, 최소/최대 주문금액, 종목코드 확인 등)한 뒤 `session_proposed_actions` 리스트에 추가하고, Gemini에게는 `{"status": "staged_for_user_confirmation", "summary": "..."}`를 반환한다.
- **도구 목록**:
  1. `propose_manual_order(exchange: str, ticker: str, side: str, price: float, volume: Optional[float] = None, amount_krw: Optional[float] = None) -> dict`
     - 수동 지정가 매수(`bid`)/매도(`ask`) 주문 제안. `amount_krw`만 주어진 경우 `price`로 나누어 `volume` 자동 산출 및 거래소별 `round_volume` 적용.
  2. `propose_cancel_orders(exchange: str, order_uuids: list[str], reason: Optional[str] = None) -> dict`
     - `get_open_orders`로 확인한 특정 주문 `uuid` 리스트(또는 종목 전체)를 취소 제안 큐에 등록.
  3. `propose_rsi_strategy(exchange: str, ticker: str, side: str, buy_rsi_range: Optional[str] = None, sell_rsi_range: Optional[str] = None, count: int = 5, amount_krw: Optional[float] = None, dca_mode: bool = False) -> dict`
     - `rsitrade`(매수) 또는 `sgridrsi`(매도) 전략 주문 제안 및 예상 역산 가격표 요약 생성.
  4. `propose_grid_strategy(exchange: str, ticker: str, side: str, start_price: float, end_price: float, count: int, amount_krw: Optional[float] = None, volume: Optional[float] = None) -> dict`
     - `grid`(매수) 또는 `sgrid`(매도) 거미줄 주문 제안.
  5. `propose_template_action(template_id: int, action: str, amount_krw: Optional[float] = None) -> dict`
     - Manager Backend 전략 템플릿 제어 제안 (`run`: 즉시 실행, `pause`: 일시중지, `stop_and_cancel`: 중지 및 미체결 취소, `topup`: 예산 추가 충전).
  6. `propose_update_config(config_key: str, config_value: str) -> dict`
     - 사용자 환경설정(`preferences`) 변경 제안 (`validate_config_update` 사전 검증 수행).
  7. `propose_watchlist_change(exchange: str, ticker: str, action: str) -> dict`
     - 관심종목 추가(`watch`) / 삭제(`unwatch`) 제안.

---

### Phase 3: 멀티턴 에이전트 루프(`src/core/nl_agent.py`) 구현

#### Task 3.1: `run_nl_agent_loop` 코어 엔진 작성
- **대상 파일**: `src/core/nl_agent.py` (신규)
- **구현 사양**:
  1. **시스템 프롬프트 구성 (`SYSTEM_INSTRUCTION`)**:
     - 역할: `supabot` 멀티 거래소(업비트, 빗썸, 한국투자증권, 토스증권) 트레이딩 AI 어시스턴트.
     - 지침:
       - 사용자의 요청에 답하기 위해 현재 시세, 잔고, 미체결 주문, 전략 템플릿 정보가 필요하다면 추측하지 말고 반드시 **Read Tool**을 먼저 호출할 것.
       - 예: *"내 비트코인 주문 취소해줘"* → 먼저 `get_open_orders(ticker="BTC")`를 호출해 주문 UUID와 내역을 확인한 뒤 `propose_cancel_orders`를 호출할 것.
       - 예: *"업비트 남은 원화의 절반으로 이더리움 현재가에 사줘"* → `get_account_balances("upbit")`와 `get_ticker_price("upbit", "ETH")`를 호출해 금액과 수량을 계산한 뒤 `propose_manual_order`를 호출할 것.
       - `propose_*` 도구가 호출되면 이미 사용자에게 확인 버튼이 표시될 예정이므로, 최종 텍스트 응답에서는 제안한 작업 내역을 친절하고 간결하게 한국어로 브리핑할 것.
  2. **에이전트 루프 제어**:
     - `MAX_AGENT_STEPS = 5` (무한 루프 및 과도한 API 과금 방지).
     - 각 턴마다 `client.models.generate_content`를 `asyncio.to_thread`로 호출 (`temperature=0.1`).
     - 응답의 `candidates[0].content.parts`에서 `function_call` 파트들을 추출:
       - `function_call`이 있으면 해당 파이썬 함수를 비동기 실행하고 `types.Part.from_function_response(name=..., response=...)`를 생성하여 대화 `contents`에 추가한 뒤 다음 루프 진행.
       - `function_call`이 없으면 최종 텍스트(`response.text`)를 추출하고 루프 종료.
  3. **반환 구조 (`AgentRunResult`)**:
     ```python
     @dataclass
     class AgentRunResult:
         reply_text: str                      # Gemini의 최종 한국어 설명
         proposed_actions: list[dict]         # 확인 버튼 클릭 시 실행할 변경 작업 목록
         tool_trace: list[dict]               # 호출된 도구 이력 (로깅/디버깅용)
     ```

---

### Phase 4: 텔레그램 핸들러 연동 및 일괄 승인 실행기 구현

#### Task 4.1: `src/handlers/nl_intent_handlers.py` 리팩토링
- **대상 파일**: [`src/handlers/nl_intent_handlers.py`](file:///E:/apps/supabot/src/handlers/nl_intent_handlers.py)
- **수정 내용**:
  1. `natural_language_command`:
     - **Step 1**: 기존 `preprocess_natural_language_intent(text, user)`를 먼저 실행. 단순 시세/잔고/미체결 조회는 기존과 동일하게 즉시 응답 (0초대 응답 유지).
     - **Step 2**: 전처리 미적중 시 `"🤖 AI가 요청을 분석하고 있습니다..."` 임시 상태 메시지를 전송하고 `run_nl_agent_loop(text, user, recent_context)` 호출.
     - **Step 3**:
       - `result.proposed_actions`가 비어 있으면(순수 복합 조회/분석 질문): 임시 메시지를 `result.reply_text`로 수정(`edit_text`)하고 종료.
       - `result.proposed_actions`가 존재하면(주문/취소/템플릿 제어 등):
         - `result.reply_text`와 각 `proposed_action`의 요약본을 합쳐 확인 메시지 생성.
         - `main._pending_nl_intents[token]`에 `{"user_id": chat_id, "actions": result.proposed_actions, "log_id": log_id}` 저장.
         - `[✅ 실행] / [❌ 취소]` 인라인 키보드 버튼 부착.
  2. `execute_confirmed_actions(query, context, user, actions: list[dict])`:
     - 기존 단일 `intent` 실행 함수(`execute_confirmed_intent`)를 유지하면서, 복수의 `actions` 리스트를 순차 실행할 수 있는 실행기 추가.
     - 예: `[기존 주문 2건 취소] → [신규 지정가 매수 1건 등록]`과 같은 복합 작업도 버튼 한 번 클릭으로 순차 실행 후 각각의 성공/실패 결과를 종합하여 텔레그램 메시지에 업데이트.

#### Task 4.2: 대화 맥락(`_nl_recent_context`) 고도화
- 사용자가 *"방금 조회한 주문 중에서 첫 번째 것만 취소해줘"*라고 이어 말할 수 있도록, 최근 대화 컨텍스트(`_nl_recent_context`)에 직전 턴에서 조회된 핵심 요약(종목, 주문 UUID 요약 등, 최대 500자 이내 축약본)을 함께 보관하도록 개선한다.

#### Task 4.3: 보안 로깅 (`nl_logs`) 확장
- [`src/core/natural_language.py`](file:///E:/apps/supabot/src/core/natural_language.py)의 `append_natural_language_log`에서 기존 민감정보 마스킹(`<TOKEN>`, `<STOCK>`, `<NUMBER>`) 규칙을 그대로 준수하되, 에이전트가 어떤 도구를 호출했는지(`tool_names: ["get_open_orders", "propose_cancel_orders"]`)를 `llm_action` 필드에 요약 기록한다.

---

## 3. 테스트 및 검수 계획 (Verification Plan)

코딩 완료 후 `tests/test_nl_agent_tools.py`를 신규 작성하여 다음 시나리오들을 검증한다.

1. **`test_read_only_multi_step_query`**
   - 시나리오: *"내 업비트 잔고랑 비트코인 현재가 같이 알려줘"*
   - 검증: Gemini가 `get_account_balances`와 `get_ticker_price`를 호출하고, 확인 버튼 없이 즉시 통합 브리핑 텍스트를 반환하는지 검증.
2. **`test_lookup_then_propose_cancel_orders`**
   - 시나리오: *"삼성전자 걸려있는 미체결 주문 확인해서 다 취소해줘"*
   - 검증:
     1) Step 1에서 `get_open_orders(ticker="005930")`가 호출되어 주문 UUID(`uuid-1`, `uuid-2`)를 반환.
     2) Step 2에서 Gemini가 `propose_cancel_orders(order_uuids=["uuid-1", "uuid-2"])`를 호출.
     3) 실제 `cancel_order`는 아직 호출되지 않고, `_pending_nl_intents`에 저장된 뒤 확인 버튼이 생성되는지 검증.
     4) 사용자가 `nlrun|{token}` 콜백을 눌렀을 때 비로소 2건의 주문 취소가 실행되는지 검증.
3. **`test_balance_check_then_propose_half_buy`**
   - 시나리오: *"업비트 원화 잔고 절반으로 비트코인 1억원에 지정가 매수해줘"*
   - 검증: `get_account_balances`로 원화 잔고(예: 2,000,000원) 확인 후 1,000,000원어치(`volume=0.01`) 매수 제안(`propose_manual_order`)이 정확히 생성되는지 검증.
4. **`test_manager_api_template_control_with_hmac`**
   - 시나리오: *"내 전략 템플릿 목록 확인하고 코스피 탑10 전략 일시중지해줘"*
   - 검증: `manager_api_client`가 HMAC 서명 헤더를 포함해 Manager API를 호출하고, `propose_template_action`을 통해 승인 후 중지 처리되는지 검증.
5. **`test_agent_loop_max_steps_guard`**
   - 시나리오: 비정상적으로 도구 호출이 반복되는 경우 `MAX_AGENT_STEPS(5)`에서 안전하게 루프를 종료하고 안내 메시지를 반환하는지 검증.
6. **`test_existing_nl_regression`**
   - 기존 `tests/test_natural_language.py`의 모든 테스트 케이스가 100% 통과하는지 확인.

---

## 4. 작업 체크리스트 (Gemini 3.8 Flash 실행 및 검수용)

- [x] **Phase 1**: [`manager/backend/routers/_auth.py`](file:///E:/apps/supabot/manager/backend/routers/_auth.py) HMAC 헤더 인증 추가 및 `src/core/manager_api_client.py` 구현
- [x] **Phase 2**: `src/core/nl_tools.py` 읽기 도구 8종 및 쓰기 제안 도구 7종 구현 (실거래 Mock 안전성 확인)
- [x] **Phase 3**: `src/core/nl_agent.py` 멀티턴 Function Calling 루프(`run_nl_agent_loop`) 구현
- [x] **Phase 4**: [`src/handlers/nl_intent_handlers.py`](file:///E:/apps/supabot/src/handlers/nl_intent_handlers.py) 에이전트 루프 연동 및 다중 액션 승인 콜백(`execute_confirmed_actions`) 구현
- [x] **Phase 5**: `tests/test_nl_agent_tools.py` 단위 테스트 작성 및 `pytest tests/` 전체 통과 확인
- [x] **문서 동기화**: 구현 완료 후 [`docs/304_gemini_intent.md`](file:///E:/apps/supabot/docs/304_gemini_intent.md) 및 [`docs/205a_natural_language.md`](file:///E:/apps/supabot/docs/205a_natural_language.md) 최신화
