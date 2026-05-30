# gemini_intent.md — Gemini 자연어 Intent 처리

## 개요

`llm_enabled=True` 이고 일반 텍스트 메시지가 오면, 봇이 Google Gemini API로 전송해 JSON intent로 변환. 사용자가 "비트코인 시세 알려줘" 처럼 자연어 입력 가능.

## 사전 조건

- `users.json → llm.gemini_api_key` 설정 필요
- `llm_enabled=True` 필요
- `validate_config_update`: `llm_enabled=True` + 빈 API 키 조합 → `ValueError`

## Gemini 프롬프트 구조

`_build_llm_prompt(user_text, user)` — zero-shot JSON 추출:

```
You parse Korean Telegram trading bot messages into one JSON object only.
Do not execute anything. Use null for unknown fields.
Supported actions: asset, price, orders, status, config_view, history,
  buy, sell, grid, sgrid, rsitrade, watch, unwatch, config_set, cancel, help, clarify.
Schema: { "action": str, "exchange": str|null, "ticker": str|null,
          "price": num|null, "volume": num|null, "amount_krw": num|null,
          "start_price": num|null, "end_price": num|null, "count": int|null,
          "buy_rsi_range": str|null, "sell_rsi_range": str|null,
          "config_key": str|null, "config_value": str|null, "question": str|null }
Exchange: upbit | bithumb | kis | null. Default: {user's default_exchange}.
User text: {text}
```

temperature=0.1, `response_mime_type="application/json"`.

## Intent 스키마

```python
{
    "action":         str,         # 지원 action 목록 또는 null
    "exchange":       str|None,    # "upbit" | "bithumb" | "kis" | null
    "ticker":         str|None,    # "BTC", "005930" 등
    "price":          float|None,
    "volume":         float|None,
    "amount_krw":     float|None,
    "start_price":    float|None,
    "end_price":      float|None,
    "count":          int|None,
    "buy_rsi_range":  str|None,    # "25-30"
    "sell_rsi_range": str|None,    # "65-75"
    "config_key":     str|None,
    "config_value":   str|None,
    "question":       str|None,    # action=="clarify" 시 Gemini의 질문
}
```

## 읽기 vs 쓰기 구분

`_is_immediate_intent(action)` 으로 즉시 실행 여부 판별:

```python
IMMEDIATE = {"asset", "price", "orders", "status", "config_view", "history"}
```

| 구분 | 액션 목록 | 처리 |
|------|-----------|------|
| **읽기 (즉시)** | asset, price, orders, status, config_view, history | `execute_query_intent` |
| **쓰기 (확인)** | buy, sell, grid, sgrid, rsitrade, watch, unwatch, config_set, cancel, help | 확인 버튼 표시 후 실행 |

## 확인 플로우

```
일반 텍스트 메시지
      │
parse_natural_language_intent() → JSON intent
      │
action == "clarify" 또는 None? → 질문/오류 응답 반환
      │
_is_immediate_intent? ──► execute_query_intent (확인 없음)
      │
_pending_nl_intents[token] = {user_id, intent} 저장
확인 버튼 표시: [실행] (nlrun|token) / [취소] (nlcancel|token)
      │
사용자 [실행] 클릭
      │
natural_language_confirm_callback():
  1. token 존재 확인 (만료/없으면 오류)
  2. user_id 일치 확인 (타인 실행 방지)
  3. execute_confirmed_intent(query, context, user, intent)
```

`execute_confirmed_intent` 는 일반 커맨드 핸들러와 동일한 내부 함수 호출 (거래소 어댑터, 검증 동일 적용).

## 오류 처리

| 상황 | 응답 |
|------|------|
| Gemini API 실패 | None 반환 → "해석할 수 없습니다" 안내 |
| token 만료 (봇 재시작 등) | "만료된 자연어 요청" |
| 다른 유저가 확인 클릭 | "다른 사용자의 요청은 실행할 수 없습니다" |
| `execute_confirmed_intent` 예외 | 에러 메시지 유저에게 전송 |

## 검증 항목 (execute_confirmed_intent 내부)

거래소명, 종목, 가격, 수량, RSI 범위, 예산, `max_order_krw`, KIS 일봉 제한, KIS 정규장 정책 — 일반 커맨드 핸들러와 동일한 검증 통과 필요.
