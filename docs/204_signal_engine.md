# signal_engine.md

**파일**: `src/core/signal_engine.py` (207줄)

## 역할
1. RSI 계산 (`ta.momentum.RSIIndicator`)
2. 목표 RSI 대응 다음 캔들 예상가 계산 (`/rsitrade`)
3. 관심 종목 RSI/볼린저 감시 및 알림 발송
4. RSI/MACD/BB/Stoch 멀티지표 조회 (`get_indicators()`, `/indicators` 노출)

지표 계산(RSI/MACD/BB/Stoch)은 `core.indicators`(`ta` 래퍼) 분리, `signal_engine`이 import 사용.

## 공개 인터페이스

```python
engine = SignalEngine(user_manager, exchange_adapter)

rsi, df = await engine.get_rsi(
    exchange, ticker, interval="day", period=14, user_id=None
)

price = await engine.get_price_by_rsi(
    exchange, ticker, target_rsi, side="bid",
    interval="day", period=14, user_id=None
)

indicators = await engine.get_indicators(
    exchange, ticker, interval="day", user_id=None
)   # RSI/MACD/BB/Stoch dict; /indicators 명령이 노출

await engine.analyze_watchlist(application)
```

## RSI 계산

- 캔들 조회: `exchange_adapter.get_candles()`
- 조회 개수: `period + 50`
- 정렬 기준: `candle_date_time_kst`
- 계산기: `ta.momentum.RSIIndicator(close=df["close"], window=period).rsi()`

## 목표 RSI 가격 계산

RSI 표시 및 주문 미리보기 동일 모델 사용 위해 역산도 `ta.momentum.RSIIndicator` 기반 처리.

방식:
- 과거 종가 배열 준비
- `가상의 다음 종가 1개` 붙여 RSI 재계산
- 매수(`bid`): 현재가 아래 목표 RSI 이하 가격 탐색
- 매도(`ask`): 현재가 위 목표 RSI 이상 가격 탐색
- 수수료 버퍼 및 거래소 호가 단위 적용

## 감시 루프

`analyze_watchlist(application)` 활성 사용자 및 관심 종목 감시:
1. 사용자 `rsi_interval` 기준 RSI 조회
2. `rsi <= signal_rsi_threshold` 시 텔레그램 알림 발송
3. 빠른 진입 버튼 `grid_quick_{exchange}_{ticker}` 포함
4. 종목별 `0.5초` 대기

## 참고

- 수식/탐색 설명: `docs/301_rsi_algorithm.md`
