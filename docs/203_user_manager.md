# user_manager.md

**파일**: `src/core/user_manager.py` (~390줄)

## 역할
유저 설정 로드·영속화·기본값 적용.

저장: **DB-우선 + 파일 폴백**. `core.db.is_db_available()` (`SUPABASE_URL` + `SUPABASE_SERVICE_KEY` 존재) 시 `users` 테이블 로드 및 즉시 upsert. DB 미사용/실패 시 `data/users.json` 폴백. 자동 동기화 없음 — manager UI `users` 테이블 직접 변경은 봇 인메모리 미반영. `reload_from_db()` (관리자 `/dbsync` 호출) 유일 풀(pull) 경로, 재시작 없이 DB 상태 인메모리 반영.

## 유저 스키마

```python
{
    "username":  str,
    "is_admin":  bool,    # True면 status="active"로 즉시 활성화
    "is_active": bool,    # status == "active" 와 동치 (런타임 편의 필드)
    "status":    str,     # pending | active | inactive | blocked | deleted
    "preferences": { ... },
    "exchanges":  { ... },
    "llm": { "gemini_api_key": str }
}
```

`status` 문자열 단일 소스(과거 `is_active` 대체). DB 변환 `_db_row_to_user()` / `_user_to_db_row()`:
- `_db_row_to_user`: DB `status` → `is_active = (status == "active")`, `status` 보존
- `_user_to_db_row`: 명시적 `status` 우선, 없으면 `is_active`에서 (`active`/`pending`) 유도

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
    "poll_active_interval":    60,       # ↓ system_config 테이블로 이관
    "poll_no_order_interval":  300,
    "signal_analysis_interval":300,
}
```

`poll_active_interval` / `poll_no_order_interval` / `signal_analysis_interval` 키 유저 preferences 미반영. `is_db_available()` 시 main.py `_get_admin_prefs()`가 `system_config` 테이블 **먼저** 읽어 간격 결정, DB 미사용 시 관리자 preferences 폴백. (DEFAULT_PREFERENCES 폴백용 기본값 보존.)

`_ensure_user_defaults()` `get_user()` 호출마다 실행 → 누락 키 자동 추가/저장. 스키마 추가: additive migration.

## 거래소 서브스키마

```python
"upbit":   { "access_key": str, "secret_key": str, "watchlist": [str] }
"bithumb": { "access_key": str, "secret_key": str, "watchlist": [str] }
"kis":     { "app_key": str, "app_secret": str, "account_no": str,
             "product_code": "01", "env": "paper|real", "watchlist": [str] }
"toss":    { "client_id": str, "client_secret": str,
             "account_seq": int|None, "watchlist": [str] }
```

`account_seq`: `validate_api_keys()` 호출 시 Toss API 자동 조회/저장. 키 입력 후 검증, 사용자 입력 수동 불필요.

## 관리자 vs 일반 유저

| 항목 | 관리자 | 일반 유저 |
|------|--------|-----------|
| `/start` 시 즉시 활성화 | O (`status="active"`) | X (`status="pending"`, 관리자 승인 필요) |
| 거래 명령 사용 | O | O (활성화 후) |

폴링 간격 세 키: `system_config` 테이블 관리 (DEFAULT_PREFERENCES 참조).

관리자: `ADMIN_CHAT_ID` 환경변수 기반, 시작 시 `initialize_admin()` 등록.

## 주요 메서드

```python
manager.add_user(user_id, username, is_admin=False)
manager.get_user(user_id)                      # 기본값 자동 적용, 저장될 수 있음
manager.update_preference(user_id, key, value)
manager.update_exchange_keys(user_id, exchange, access_key, secret_key)
manager.update_kis_keys(user_id, app_key, app_secret, account_no, product_code, env)
manager.update_toss_keys(user_id, client_id, client_secret)   # account_seq를 None으로 초기화
manager.update_toss_account_seq(user_id, account_seq)         # validate 후 자동 저장
manager.update_gemini_api_key(user_id, api_key)
manager.set_active(user_id, status=True)   # True → status="active", False → status="inactive"
manager.add_watchlist(user_id, exchange, ticker)
manager.remove_watchlist(user_id, exchange, ticker)
manager.initialize_admin(admin_chat_id)
manager.reload_from_db()                       # DB 상태를 인메모리에 즉시 반영(/dbsync), DB 미사용 시 no-op
```

## 영속화 세부 사항
- DB-우선: `is_db_available()` 시 `users` 테이블 사용. 단건 쓰기 `_upsert_user(user_id)`, 전체 업서트 `save_users()`.
- 파일 폴백: DB 미사용/실패 시 `data/users.json` (생성자 인자 변경 가능), 쓰기 후 `chmod 0600` 적용.
- API 키 암호화: `USER_SECRET_KEY` 설정 시 `enc:v1:` 형식 저장. 암호화/복호화 `core.secret_crypto` 분리 (`encrypt_secret`/`decrypt_secret`). 보안: `AGENTS.md` 참조.
