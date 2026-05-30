# signal_engine.md

**파일**: `src/core/signal_engine.py` (98줄)

## 역할
1. RSI 계산 (pandas-ta 사용)
2. 목표 RSI → 목표가 역산 (Wilder's Smoothing 근사, `/rsitrade` 전략용)
3. 감시 목록 백그라운드 스캔

## 공개 인터페이스

```python
engine = SignalEngine(user_manager, exchange_adapter)

rsi, df = await engine.get_rsi(
    exchange, ticker, interval="day", period=14, user_id=None
)
# rsi: float (최신 RSI) | None
# df:  pandas DataFrame, 컬럼: close, open, high, low, candle_date_time_kst

price = await engine.get_price_by_rsi(
    exchange, ticker, target_rsi, side="bid",
    interval="day", period=14, user_id=None
)
# price: 틱 반올림된 float | None

await engine.analyze_watchlist(application)
# 모든 활성 유저의 감시 종목 스캔, 시그널 시 텔레그램 알림
```

## RSI 계산 상세

- 라이브러리: `ta.momentum.RSIIndicator(close=df['close'], window=period).rsi()`
- 캔들: `exchange_adapter.get_candles()` 로 `count = period + 50` 조회
- 정렬: `candle_date_time_kst` 기준 오름차순 정렬 후 계산

## 역산 알고리즘 요약

목표 RSI에 도달하는 가격을 역산:
- Wilder's Smoothing을 단순 이동평균으로 근사 (`rolling(period).mean()`)
- 매수(`bid`): 다음 캔들이 하락 가정 (currentGain=0)
- 매도(`ask`): 다음 캔들이 상승 가정 (currentLoss=0)
- 수수료 버퍼: bid → `×0.999`, ask → `×1.001`
- 틱 조정: `exchange_adapter.adjust_price_to_tick()` 최종 적용

**수학 공식 전체**: `docs/detail/rsi_algorithm.md`

## 감시 목록 스캔 루프

`analyze_watchlist(application)` — `signal_analysis_loop()` 에서 `signal_analysis_interval` (기본 300초) 마다 호출.

각 활성 유저 × 각 거래소 × 각 감시 종목:
1. `rsi_interval` 기준 RSI 조회
2. `rsi <= signal_rsi_threshold` (기본 30) 이면 텔레그램 알림 발송
3. 알림에 "거미줄 셋팅하기" 인라인 버튼 포함 (`grid_quick_{exchange}_{ticker}`)
4. 종목 간 0.5초 대기 (API Rate Limit 보호)

## 참조
- 역산 수식 상세: `docs/detail/rsi_algorithm.md`
