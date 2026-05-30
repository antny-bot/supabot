# user_manager.md

**파일**: `src/core/user_manager.py` (193줄)

## 역할
`data/users.json` 에 저장된 유저별 설정을 로드·영속화·기본값 적용. 이 파일만 `users.json` 에 씀.

## 유저 스키마

```python
{
    "username":  str,
    "is_admin":  bool,   # True면 즉시 is_active=True
    "is_active": bool,   # False = 관리자 승인 대기
    "preferences": { ... },
    "exchanges":  { ... },
    "llm": { "gemini_api_key": str }
}
```

## DEFAULT_PREFERENCES

```python
{
    "default_exchange":        "upbit",
    "asset_min_display_krw":   10000,
    "rsi_buy_range":           "25-30",
    "rsi_sell_range":          "65-75",
    "rsi_order_count":         5,
    "rsi_budget_krw":          None,
    "signal_alerts":           True,
    "signal_rsi_threshold":    30,
    "rsi_interval":            "day",    # day | 1 | 3 | 5 | 10 | 15 | 30 | 60 | 240
    "max_order_krw":           None,
    "llm_enabled":             False,
    "llm_model":               "gemini-2.5-flash-lite",
    "poll_active_interval":    60,       # 관리자 설정만 실제 반영
    "poll_no_order_interval":  300,
    "signal_analysis_interval":300,
}
```

`_ensure_user_defaults()` 가 `get_user()` 호출마다 실행 → 누락 키 자동 추가 후 저장. 스키마 추가는 additive migration.

## 거래소 서브스키마

```python
"upbit":   { "access_key": str, "secret_key": str, "watchlist": [str] }
"bithumb": { "access_key": str, "secret_key": str, "watchlist": [str] }
"kis":     { "app_key": str, "app_secret": str, "account_no": str,
             "product_code": "01", "env": "paper|real", "watchlist": [str] }
```

## 관리자 vs 일반 유저

| 항목 | 관리자 | 일반 유저 |
|------|--------|-----------|
| `/start` 시 즉시 활성화 | O | X (관리자 승인 필요) |
| 폴링 간격 설정 실제 반영 | O (전체 봇에 적용) | X (무시됨) |
| 거래 명령 사용 | O | O (활성화 후) |

관리자는 `ADMIN_CHAT_ID` 환경변수 기반, 시작 시 `initialize_admin()` 으로 등록.

## 주요 메서드

```python
manager.add_user(user_id, username, is_admin=False)
manager.get_user(user_id)                      # 기본값 자동 적용, 저장될 수 있음
manager.update_preference(user_id, key, value)
manager.update_exchange_keys(user_id, exchange, access_key, secret_key)
manager.update_kis_keys(user_id, app_key, app_secret, account_no, product_code, env)
manager.update_gemini_api_key(user_id, api_key)
manager.set_active(user_id, status=True)
manager.add_watchlist(user_id, exchange, ticker)
manager.remove_watchlist(user_id, exchange, ticker)
manager.initialize_admin(admin_chat_id)
```

## 영속화 세부 사항
- 파일: `data/users.json` (생성자 인자로 변경 가능)
- 모든 쓰기 후 `chmod 0600` 적용
- API 키 평문 저장 → 보안 주의사항: `AGENTS.md` 참조
