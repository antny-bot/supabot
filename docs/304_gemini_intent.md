# gemini_intent.md — Gemini 자연어 Intent 및 Function Calling 에이전트

## 개요

`llm_enabled=True` 시 텍스트 메시지 룰 기반 전처리(`preprocess_natural_language_intent`)를 1차 패스트트랙으로 수행하며, 미적중된 복합 요청 및 주문/취소/전략 변경은 **Gemini Function Calling (Tool Use)** 기반의 멀티턴 에이전트 루프(`run_nl_agent_loop`)로 처리합니다.
이를 통해 단발성 스키마 파싱의 한계를 넘어, 실시간 시세·잔고·미체결 주문을 능동적으로 조회하고 최적의 실행 계획(Proposed Actions)을 사용자 승인 하에 실행합니다.

## 핵심 아키텍처

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
        FC -->|Write Tool 호출<br/>예: propose_cancel_orders, propose_manual_order| WT[실행 보류 큐에 Action 적재<br/>ProposedAction 생성 및 결과 반환]
        WT --> G
        FC -->|최종 텍스트 응답| DONE[루프 종료]
    end

    DONE --> HAS_WRITE{보류된 Write Action<br/>존재 여부?}
    HAS_WRITE -->|없음: 순수 조회/분석 답변| REPLY[최종 자연어 브리핑 전송]
    HAS_WRITE -->|있음: 주문/취소/설정/템플릿 변경| CONFIRM["실행 계획 요약 + [✅ 실행] / [❌ 취소] 버튼 전송<br/>main._pending_nl_intents[token] 저장"]
    CONFIRM -->|사용자 [✅ 실행] 클릭| EXEC[execute_confirmed_actions<br/>보류된 Action 순차 실행 및 결과 리포트]
```

## 1. 읽기 전용 도구 (Read Tools, 즉시 실행)

에이전트 루프 내에서 실계좌나 DB를 변경하지 않고 정보를 즉시 수집하여 Gemini에게 컨텍스트로 제공합니다.

1. `get_ticker_price(exchange, ticker)`: 실시간 시세, 전일 대비 변동률, 고/저가 조회.
2. `get_technical_indicators(exchange, ticker, interval)`: RSI(14), MACD, 볼린저 밴드, 스토캐스틱 등 보조지표 계산.
3. `get_account_balances(exchange)`: 거래소별 보유 현금(KRW/USD) 및 보유 종목 수량·평단가 조회.
4. `get_open_orders(exchange, ticker)`: 현재 대기/예약/미체결 중인 주문 목록 및 UUID 조회.
5. `get_recent_trades(exchange, ticker, limit)`: 최근 체결 완료된 거래 내역 조회.
6. `get_strategy_templates()`: Manager Backend 등록 전략 템플릿 목록 조회.
7. `get_budget_health(exchange)`: 필요 예산 대비 실계좌 예수금 건전성 상태 조회.
8. `get_user_settings()`: 사용자의 현재 봇 환경설정 조회.
9. `get_report_pnl(period)`: Manager REST API 종합 손익(총 실현/미실현손익, ROI, 거래 수) 리포트 조회.
10. `get_report_win_stats(period)`: Manager REST API 승률(Win Rate), 손익비(Profit Factor), 승/패 및 연승/연패 통계 조회.
11. `get_report_daily_profit(period)`: 일별 실현 손익 및 거래 횟수 추이 조회.
12. `get_report_monthly_profit()`: 월별 누적 실현 손익 및 월간 실적 추이 조회.
13. `get_report_roi_ranking(period)`: 종목별 실현 손익 및 수익률 성과 랭킹(Top/Bottom) 조회.
14. `get_report_strategy_performance(period)`: 전략별(RSI, DCA, 그리드 등) 실현 손익 및 승률 비교 조회.
15. `get_report_exchange_performance(period)`: 거래소별(업비트, 빗썸, KIS, 토스) 거래 비중 및 손익 조회.
16. `get_report_drawdown_risk(period)`: 포트폴리오 최대 낙폭(MDD) 및 고점 대비 하락 리스크 분석.
17. `get_report_asset_allocation()`: 포트폴리오 자산 배분 비중(현금 대비 코인/주식) 조회.
18. `get_report_dca_batches(period)`: DCA(분할 매수) 차수별 배치 실행 현황 및 평균 매수가 조회.

## 2. 변경 제안 도구 (Write Proposal Tools, 실행 보류 및 승인)

실거래 안전 표준([`100_project_standards.md`](file:///E:/apps/supabot/docs/100_project_standards.md))에 따라 실제 거래소 API나 DB 변경을 즉시 호출하지 않고, `session_proposed_actions` 큐에 적재한 뒤 사용자의 승인 인라인 버튼을 생성합니다.

1. `propose_manual_order(exchange, ticker, side, price, volume, amount_krw)`: 단일 지정가 매수/매도 제안.
2. `propose_cancel_orders(exchange, order_uuids, reason)`: 확인된 특정 미체결 주문 UUID 목록 취소 제안.
3. `propose_rsi_strategy(exchange, ticker, side, buy_rsi_range, sell_rsi_range, count, amount_krw, dca_mode)`: RSI 순환 매매 분할 주문 제안.
4. `propose_grid_strategy(exchange, ticker, side, start_price, end_price, count, amount_krw, volume)`: 거미줄 분할 주문 제안.
5. `propose_template_action(template_id, action, amount_krw)`: 전략 템플릿 제어 제안 (`run`, `pause`, `stop_and_cancel`, `topup`).
6. `propose_update_config(config_key, config_value)`: 환경설정 변경 제안 (사전 유효성 검증 포함).
7. `propose_watchlist_change(exchange, ticker, action)`: 관심종목 등록/해제 제안.

## 3. Manager REST API HMAC 대리 인증

텔레그램 봇이 사용자를 대리하여 Manager Backend REST API를 안전하게 호출할 수 있도록 HMAC-SHA256 헤더 인증을 지원합니다:
- `X-Bot-User-Id`: 텔레그램 `user_id`
- `X-Timestamp`: Unix Timestamp (5분 이내 유효)
- `X-Signature`: `HMAC-SHA256(MANAGER_API_KEY, f"{timestamp}:{bot_user_id}:{path}")`
- `X-Is-Admin`: 관리자 여부 (`true` / `false`)

## 4. Multi-turn 최근 대화 맥락 (Recent Context)

사용자가 연속 대화 시 이전 발화의 종목이나 의도를 승계할 수 있도록 슬라이딩 윈도우 컨텍스트를 지원합니다.
- 보관 위치: `context.user_data["_nl_recent_context"]`
- 보관 용량: 최근 4턴 슬라이딩 윈도우
- 복합 시나리오 지원:
  1. 유저: *"비트코인 미체결 주문 확인해줘"* → 봇: (주문 목록 2건 표시)
  2. 유저: *"그 중 제일 아래 거 취소해줘"* → 에이전트가 이전 맥락의 주문 목록 중 해당 UUID를 특정하여 취소 계획 제안

## 5. 미처리 자연어 로그 및 감사 추적

Gemini 호출 문장은 `append_natural_language_log()`를 통해 기록되며, Function Calling 도구 호출 trace(`llm_action: "get_open_orders, propose_cancel_orders"`)가 함께 저장됩니다.
- 마스킹 규칙 준수: 개인정보 및 보안 토큰은 `<TOKEN>`, `<STOCK>`, `<NUMBER>`로 마스킹.
- `nl_logs.confirm_status`: `auto`(조회), `pending`(승인 대기), `confirmed`(실행 완료), `rejected`(취소됨).
