# order_manager.md

**파일**: `src/core/order_manager.py` (162줄)

## 역할
전체 사용자·거래소의 활성 주문을 영속화. 봇이 제출했다고 믿는 주문의 단일 정보 소스.

저장은 **DB-우선 + 파일 폴백** 구조다. `core.db.is_db_available()` (`SUPABASE_URL` + `SUPABASE_SERVICE_KEY` 존재)이면 `orders` 테이블에서 로드하고, 모든 변경을 `_db_upsert(order)` / `_db_delete(uuid)`로 즉시 DB에 반영한다. DB 미사용이거나 DB 호출 실패 시 `data/orders.json` 파일로 폴백한다. 양방향 동기화는 없으며 파일은 비상 폴백이다.

`replace_order_uuid(old, new)`는 UUID가 PK이므로 `_db_delete(old)` 후 `_db_upsert(new)` 순으로 처리한다(in-place UPDATE 아님).

## 상태 기계

```
                                  add_order (장중/실거래소 호출 성공)
                    (없음) ────────────────────────────► wait
                       │                                   │
   add_order (KIS/Toss │                      partial fill │ exchange exec_vol > 0
   장외, supports_      │                      update_fill ◄┤
   reserved_orders)     ▼                                   │
                    reserved                     done    ◄──┤ exchange state=done
                       │                                     │
                       │ 다음 정규장(sync_orders가          cancel    ◄──┤ exchange state=cancel
                       │  실거래소에 제출)                                 │  (KIS 전략 주문만)
                       ▼                              pending_reorder ◄──┘ 장외/상태 미확인
                  wait (replace_order_uuid로 UUID 교체)         │
                                                                │ 다음 정규장
                                                                ▼
                                                      wait (replace_order_uuid로 UUID 교체)
```

`market_closed`는 `sync_orders`가 KIS 장외 시간에 임시 설정. 재주문 시도 전까지 유지.

`reserved`는 `pending_reorder`와 다르다 — `pending_reorder`는 **이미 거래소에 제출됐다가** 마감으로 취소된 주문, `reserved`는 **처음부터 장외라 거래소에 제출조차 안 한** 주문이다(가짜 uuid `reserved:<hex>`로만 등록). 둘 다 `sync_orders`(`src/main.py`)가 `supports_reserved_orders=True`인 거래소(KIS/Toss)에 대해 동일한 다음-정규장 제출 경로로 처리한다. `add_order(..., status="reserved")`는 `grid`/`rsitrade`/`sgridrsi`/`manual` 모든 전략에서 호출부가 `getattr(ex, "supports_reserved_orders", False) and not ex.is_market_open(ticker)` 체크 후 직접 설정한다 — `order_manager` 자체는 이 분기를 모른다(호출부 책임).

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
| `filled_volume` | 확인된 체결량. exchange의 `executed_volume`과 비교해 새 부분체결 감지 |
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
