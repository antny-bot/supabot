# F5. 백테스트 엔진 설계 문서

## 1. 개요
과거 시세 데이터를 기반으로 RSI 분할 매매 전략(rsitrade)을 가상 시뮬레이션하여 승률, 최대 낙폭(MDD), 누적 수익률, 총 거래 횟수 등의 전략 성과를 사전에 검증할 수 있는 백테스트 엔진을 구축합니다.

## 2. 안전 원칙
- **어떤 경우에도 실제 거래소 주문 API(`create_order`)를 호출하지 않습니다.** 가상 주문 체결 시뮬레이터(`simulate_order_fill`)를 사용합니다.
- 수수료율(`fee_rate`, 기본 0.05%) 및 슬리피지(`slippage_pct`, 기본 0.05%)를 파라미터로 반영하여 현실적인 성과를 측정합니다.

## 3. 핵심 인터페이스
- `run_backtest(candles_df, buy_rsi_range, sell_rsi_range, count, budget, fee_rate=0.0005, slippage_pct=0.0005)`:
  - 입력: 과거 캔들 DataFrame(open, high, low, close, time), 전략 파라미터.
  - 출력:
    - `total_trades`: 총 매매 횟수
    - `win_rate`: 승률 (%)
    - `total_pnl_krw`: 총 실현 손익 (KRW)
    - `total_return_pct`: 누적 수익률 (%)
    - `mdd_pct`: 최대 낙폭 (MDD, %)
    - `trades`: 개별 체결 내역 리스트

## 4. 수용 기준 (Acceptance Criteria)
- 고정 합성 캔들 데이터로 결정론적인 결과 산출.
- 거래소 실주문 API(`create_order`) 호출 횟수가 0건임을 검증.
