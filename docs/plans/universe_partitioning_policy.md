# 유니버스 분리(Universe Partitioning) 정책 설계 및 구현 문서

## 1. 개요 및 배경
단일 계좌 내에서 KOSPI/KOSDAQ 시총 상위 TOP N 전략(바스켓 모으기)과 개별 종목 전략(RSI 순환매매, 그리드, DCA 등)이 동시에 운용될 때, 동일 종목(예: 삼성전자)을 중복 매수/매도하여 포지션과 잔고가 꼬이는 문제를 원천 차단하기 위해 **방안 B: 유니버스 분리 (Universe Partitioning)** 정책을 도입한다.

---

## 2. 세부 정책 및 규칙

### 2.1. 유니버스 격리 원칙
1. **대형주(TOP N 바스켓)**:
   - 시가총액 상위 1~10위 대형주는 TOP N 모으기 전략 전담 영역으로 지정한다.
   - 개별 전략(RSI, 그리드, 정기적립 DCA)은 TOP N 유니버스에 속한 종목으로 신규 등록할 수 없다.
   - 단, 수동 긴급 매매(`manual`) 및 비상 손절(`stoploss`)은 계좌 보호를 위해 언제나 허용된다.

2. **개별 전략 운용 종목의 TOP N 바스켓 차순위 편입 (Fallback Progression)**:
   - 사용자가 이미 시총 10위권 내 종목에 대해 개별 전략을 운용 중인 상태에서 TOP N 전략이 당일 매수 바스켓을 산출할 경우:
   - 충돌하는 종목을 스킵하고 **차순위 종목(11위 등)을 자동 편입**하여 목표 바스켓 수량(N개)을 유지한다.

---

## 3. 구현 사양

### 3.1. `manager/backend/services/universe_resolver.py`
- `resolve_strategy_targets(...)` 함수에 `exclude_tickers` 옵션 추가:
  - `exclude_tickers`에 포함된 종목은 슬라이싱/선정 시 건너뛰고 차순위 순위 종목으로 채워 목표 개수(`target_count`)를 달성.

### 3.2. `src/core/trading_gate.py`
- `DEFAULT_TOP_UNIVERSE_TICKERS`: 시총 상위 10위 대형주 코드 세트 (`005930`, `000660`, `373220`, `207940`, `005380`, `000270`, `068270`, `105560`, `055550`, `012450`).
- `assert_single_strategy_per_ticker`:
  - 신규 개별 전략(`rsitrade`, `grid`, `sgrid`, `sgridrsi`, `dca`) 주문 시 해당 ticker가 TOP N 전담 유니버스에 속해 있고 탑 전략이 활성화되어 있거나 기본 정책 적용 시 차단:
  - 차단 메시지:
    > `🛑 [{ticker}] 해당 종목은 'TOP N 모으기 전략' 전담 종목입니다. 유니버스 분리 정책에 따라 개별 전략(RSI/그리드)으로 등록할 수 없습니다. (시총 11위 이하 종목을 선택해주세요)`

---

## 4. 검증 계획
- `tests/test_universe_partitioning.py`:
  1. `universe_resolver`: `exclude_tickers` 전달 시 충돌 종목 제외 및 차순위 종목 편입 검증.
  2. `trading_gate`: TOP N 전담 종목(삼성전자 등)에 개별 전략 주문 시도 시 차단 및 안내문 검증.
  3. `trading_gate`: TOP N 전담 외 종목(11위 이하 등)은 개별 전략 정상 허용 검증.
  4. 수동(`manual`) 및 손절(`stoploss`)은 TOP N 종목이라도 항상 허용 검증.
