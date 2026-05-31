# user_manager.md

**파일**: `src/core/user_manager.py` (370줄)

## 역할
유저별 설정을 로드·영속화·기본값 적용.

저장은 **DB-우선 + 파일 폴백** 구조다. `core.db.is_db_available()` (`SUPABASE_URL` + `SUPABASE_SERVICE_KEY` 존재)이면 `users` 테이블에서 로드하고, 변경을 즉시 DB로 upsert 한다. DB 미사용이거나 DB 호출 실패 시 `data/users.json` 파일로 폴백한다. 양방향 동기화는 없으며 파일은 비상 폴백이다.

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

상태는 `status` 문자열이 단일 소스다(과거 `is_active` bool 대체). DB 행과의 변환은 `_db_row_to_user()` / `_user_to_db_row()`가 처리한다:
- `_db_row_to_user`: DB의 `status` → `is_active = (status == "active")`, `status` 그대로 보존
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

`poll_active_interval` / `poll_no_order_interval` / `signal_analysis_interval` 세 키는 더 이상 관리자 유저 preferences로 실제 반영되지 않는다. `is_db_available()`이면 main.py `_get_admin_prefs()`가 `system_config` 테이블을 **먼저** 읽어 루프 간격을 결정하고, DB 미사용 시에만 관리자 preferences로 폴백한다. (DEFAULT_PREFERENCES에는 폴백용 기본값으로만 남아 있다.)

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
| `/start` 시 즉시 활성화 | O (`status="active"`) | X (`status="pending"`, 관리자 승인 필요) |
| 거래 명령 사용 | O | O (활성화 후) |

폴링 간격 세 키는 유저 preferences가 아니라 `system_config` 테이블이 관리한다(위 DEFAULT_PREFERENCES 절 참조).

관리자는 `ADMIN_CHAT_ID` 환경변수 기반, 시작 시 `initialize_admin()` 으로 등록.

## 주요 메서드

```python
manager.add_user(user_id, username, is_admin=False)
manager.get_user(user_id)                      # 기본값 자동 적용, 저장될 수 있음
manager.update_preference(user_id, key, value)
manager.update_exchange_keys(user_id, exchange, access_key, secret_key)
manager.update_kis_keys(user_id, app_key, app_secret, account_no, product_code, env)
manager.update_gemini_api_key(user_id, api_key)
manager.set_active(user_id, status=True)   # True → status="active", False → status="inactive"
manager.add_watchlist(user_id, exchange, ticker)
manager.remove_watchlist(user_id, exchange, ticker)
manager.initialize_admin(admin_chat_id)
```

## 영속화 세부 사항
- DB-우선: `is_db_available()`이면 `users` 테이블 사용. 단건 쓰기는 `_upsert_user(user_id)`, 시작 시 전체 업서트는 `save_users()`.
- 파일 폴백: DB 미사용/실패 시 `data/users.json` (생성자 인자로 변경 가능), 쓰기 후 `chmod 0600` 적용
- API 키 암호화: `USER_SECRET_KEY` 설정 시 `enc:v1:` 형식으로 저장. 암호화/복호화 로직은 `core.secret_crypto`로 분리됨 (`encrypt_secret`/`decrypt_secret`). 보안 주의사항: `AGENTS.md` 참조
