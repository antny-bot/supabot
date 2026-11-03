# 종목 독점 원칙 및 외부 매도 포지션 정합성(Reconciliation) 설계 문서

## 1. 개요 및 배경
단일 거래소 계좌(토스증권, KIS 등)에서 복수 전략(RSI, Grid, DCA 등)을 운영할 때 동일 종목(예: 삼성전자)을 각각 매수하면, 실제 거래소 계좌에는 단일 잔고로 합산되어 봇 내부 장부(전략별 포지션)와 거래소 실제 상태 간의 식별 분리가 불가능해집니다.
특히 사용자가 MTS(토스증권 앱 등)에서 직접 1주를 임의 매도하는 등 외부 수동 개입이 발생하면 잔고 부족 및 연쇄 주문 오류가 발생할 수 있습니다.

본 설계는 이를 방지하기 위한 2단계 안전장치를 구축합니다:
1. **1차 방어 (사전 차단)**: 동일 종목 독점 원칙 (Single Strategy per Ticker Gate)
2. **2차 방어 (사후 대사)**: 외부 매도 감지 시 FIFO 장부 차감 및 텔레그램 알림

---

## 2. 세부 설계

### 2.1. 1차 방어: 종목 독점 원칙 (Single Strategy per Ticker Gate)
- **위치**: `src/core/trading_gate.py`
- **검증 규칙**:
  - `strategy`가 `"manual"`, `"stoploss"`인 경우는 제외 (수동 매매 및 비상 손절은 항상 허용).
  - 전략 패밀리 그룹화:
    - RSI 그룹: `{"rsitrade", "rsitrade_sell"}`
    - GRID 그룹: `{"grid", "sgrid"}`
    - SGRIDRSI 그룹: `{"sgridrsi"}`
    - DCA 그룹: `{"dca"}`
  - 신규 전략 주문 또는 DCA 스케줄 등록 시:
    - 현재 오픈 주문(`open_orders`) 중 해당 `ticker`에 이미 다른 전략 패밀리의 주문이 존재하는지 검증.
    - 해당 `ticker`에 활성 DCA 스케줄이 존재하는지 상호 검증.
    - 이미 다른 전략이 실행 중인 경우 신규 주문을 차단하고 명확한 사유를 반환:
      > `🛑 [{ticker}] 이미 '{existing_strategy}' 전략이 운용 중입니다. 포지션 충돌을 방지하기 위해 동일 종목의 복수 전략 동시 운용은 제한됩니다.`

### 2.2. 2차 방어: 외부 매도 감지 시 FIFO 차감 및 텔레그램 알림
- **위치**: `src/main.py` (`_create_linked_sell_order`, `sync_orders`)
- **검증 및 대응 로직**:
  1. **매수 체결 후 익절 매도 생성 시 잔고 부족 (External Fill / Sold)**:
     - `_create_linked_sell_order`에서 잔고 부족(거래소 create_order 거부 또는 0주 반환) 발생 시 무한 재시도로 봇이 멈추지 않도록 처리.
     - 외부 매도로 감지하여 해당 매수 주문의 추적을 정상 완료 처리하고, 텔레그램 알림 발송:
       > `⚠️ [{exchange.upper()}] {ticker} 잔고 부족: 외부에서 수동 매도된 것으로 확인되어 익절 주문 생성을 생략하고 추적을 정리합니다.`
  2. **오픈 매도 주문의 FIFO 정합성 대사 (Active Ask Reconciliation)**:
     - 거래소 실제 보유 가능 잔고 < 봇의 오픈 매도 주문 합계 수량인 경우:
     - `created_at` 기준 FIFO(오래된 주문 우선 보존, 최근 주문 우선 취소/정리) 정책 적용.
     - 초과된 최근 매도 주문을 취소/제거하고 사용자에게 알림 발송.

---

## 3. 검증 계획 (Acceptance Criteria)
1. **단위 테스트 (`tests/test_single_strategy_ticker.py`)**:
   - 동일 종목에 다른 전략 주문 등록 시 `check_can_place_order` 차단 확인.
   - 동일 종목에 동일 전략 패밀리(예: rsitrade와 rsitrade_sell)는 허용 확인.
   - 수동 주문(`manual`)과 손절(`stoploss`)은 종목 독점 제한 없이 허용 확인.
   - 잔고 부족 시 외부 매도 감지 및 정리 로직 검증.
2. **문법 및 기존 회귀 검증**:
   - `python -m py_compile` 전수 통과.
