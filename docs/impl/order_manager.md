# order_manager.md

**파일**: `src/core/order_manager.py` (162줄)

## 역할
전체 사용자·거래소 활성 주문 영속화. 봇이 제출했다고 믿는 주문의 단일 정보 소스.

저장은 **DB-우선 + 파일 폴백** 구조. `core.db.is_db_available()` (`SUPABASE_URL` + `SUPABASE_SERVICE_KEY` 존재)이면 `orders` 테이블에서 로드, 모든 변경을 `_db_upsert(order)` / `_db_delete(uuid)`로 즉시 DB 반영. DB 미사용/호출 실패 시 `data/orders.json` 파일로 폴백. 양방향 동기화 없음, 파일은 비상 폴백.

`replace_order_uuid(old, new)`는 UUID가 PK라 `_db_delete(old)` 후 `_db_upsert(new)` 순으로 처리(in-place UPDATE 아님).

## 상태 기계

```mermaid
stateDiagram-v2
    [*] --> wait: add_order<br/>(장중, 실거래소 호출 성공)
    [*] --> reserved: add_order<br/>(KIS/Toss 장외, supports_reserved_orders)

    reserved --> wait: 다음 정규장<br/>sync_orders가 실거래소에 제출<br/>(replace_order_uuid로 UUID 교체)

    wait --> wait: partial fill<br/>update_order_fill (exec_vol > 0)
    wait --> done: exchange state=done
    wait --> cancel: exchange state=cancel<br/>(KIS 전략 주문만)

    cancel --> pending_reorder: 장외/상태 미확인<br/>mark_reorder_pending
    pending_reorder --> wait: 다음 정규장<br/>(replace_order_uuid로 UUID 교체)

    done --> [*]
```

`market_closed`는 `sync_orders`가 KIS 장외 시간에 임시 설정하는 보류 상태(다이어그램 미포함, `wait`/`reserved` 모두에 덧씌워질 수 있음). 재주문 시도 전까지 유지.

`reserved` ≠ `pending_reorder`. `pending_reorder`: **이미 제출됐다가** 마감으로 취소된 주문. `reserved`: **처음부터 장외라 제출조차 안 한** 주문(가짜 uuid `reserved:<hex>`로만 등록). 둘 다 `sync_orders`(`src/main.py`)가 `supports_reserved_orders=True` 거래소(KIS/Toss)에 동일한 다음-정규장 제출 경로로 처리. `add_order(..., status="reserved")`는 `grid`/`rsitrade`/`sgridrsi`/`manual` 모든 전략에서 호출부가 `getattr(ex, "supports_reserved_orders", False) and not ex.is_market_open(ticker)` 체크 후 직접 설정 — `order_manager`는 이 분기 모름(호출부 책임).

## 주요 메서드

```python
manager.add_order(
    user_id, exchange, ticker, uuid, price, volume,
    side="bid",           # "bid" | "ask"
    strategy="manual",    # manual | grid | sgrid | rsitrade | rsitrade_sell | gridrsi | sgridrsi
    target_rsi=None,      # float, rsitrade/gridrsi/sgridrsi 레그 전용
    linked_to=None,       # rsitrade/gridrsi 매수 레그: 매도 목표 RSI(float). sgridrsi는 None
    status="wait"
)

manager.update_order_fill(uuid, filled_volume, status)  # 부분/전체 체결 업데이트
manager.update_order_status(uuid, status)               # 상태만 업데이트
manager.mark_reorder_pending(uuid, next_check_at)       # KIS 장외 처리
manager.replace_order_uuid(old_uuid, new_uuid)          # KIS 재주문 (전략 의도 유지)
manager.update_next_check_at(uuid, next_check_at)
manager.remove_order(uuid)
manager.get_user_orders(user_id, exchange=None)
manager.get_strategy_orders(user_id, strategy)
```

`on_order_added` 콜백: `post_init`에서 설정. 새 주문 시 `_order_wake_event` 즉시 깨움 → 폴링 대기 없이 즉시 sync.

## 스키마 핵심 필드 (동기화 로직 관련)

| 필드 | 설명 |
|------|------|
| `filled_volume` | 확인된 체결량. exchange `executed_volume`과 비교해 새 부분체결 감지 |
| `linked_to` | rsitrade/gridrsi 매수 레그: 매도 목표 RSI(float). 체결 시 `sync_orders`가 읽어 매도가 계산. sgridrsi는 None |
| `reorder_of` | `replace_order_uuid` 호출 시 이전 uuid 저장 (감사 체인) |
| `next_check_at` | Unix timestamp; sync 루프가 이 시각까지 해당 주문 건너뜀 |

전체 스키마는 `CLAUDE.md` 참조.

## 영속화 세부 사항
- DB-우선: `is_db_available()`이면 `orders` 테이블 사용. 쓰기는 `_db_upsert`/`_db_delete`, `uuid`가 PK.
- 컬럼 매핑: `created_at` / `next_check_at`는 Unix timestamp(`DOUBLE PRECISION`)로 그대로 저장 — 타입 변환 없음.
- 파일 폴백: DB 미사용/실패 시 `data/orders.json` (생성자 인자로 변경 가능), 쓰기 후 `chmod 0600` 적용
- asyncio 단일 이벤트 루프 → 잠금(lock) 불필요

## 참조
- KIS pending_reorder 상세 흐름: `docs/detail/kis_market_policy.md`
