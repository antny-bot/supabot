# rsi_algorithm.md — RSI 역산 수식

## 표준 RSI (참고)

```
RSI = 100 - 100 / (1 + RS)
RS  = AvgGain / AvgLoss  (period 기간)
```

순방향 RSI는 `ta.momentum.RSIIndicator` 사용.

## 역산에서 사용하는 Wilder's Smoothing 근사

`signal_engine.get_price_by_rsi()` 는 EMA 대신 **단순 rolling mean** 근사 사용:

```python
diff     = pd.Series(close_prices).diff()
gain     = diff.where(diff > 0, 0)
loss     = -diff.where(diff < 0, 0)
avg_gain = gain.rolling(window=period).mean().iloc[-1]
avg_loss = loss.rolling(window=period).mean().iloc[-1]
```

이 근사는 의도적 선택: closed-form 역산을 단순화. 결과 가격은 정확한 EMA Wilder RSI 예측과 약간 다르지만 지정가 선주문 용도로는 충분히 근접.

## 매수 역산 (bid — 가격 하락 가정)

다음 캔들을 하락 캔들로 가정 (currentGain=0, currentLoss>0).

```
target_rs = target_rsi / (100 - target_rsi)

# period-step 업데이트 규칙 (단순 평균 근사):
# new_avg_gain = (avg_gain * (period-1) + 0) / period
# new_avg_loss = (avg_loss * (period-1) + needed_loss) / period
#
# new_avg_gain / new_avg_loss = target_rs 로 놓고 needed_loss 해석:

needed_loss = (avg_gain * (period - 1) / target_rs) - (avg_loss * (period - 1))
target_price = prev_close - needed_loss
```

**엣지 케이스**: `avg_loss == 0` (모두 상승, RSI≈100) → `avg_loss = 1e-9` 으로 대체.

## 매도 역산 (ask — 가격 상승 가정)

다음 캔들을 상승 캔들로 가정 (currentLoss=0, currentGain>0).

```
needed_gain = (target_rs * avg_loss * (period - 1)) - (avg_gain * (period - 1))
target_price = prev_close + needed_gain
```

## 수수료 버퍼 적용

```python
buffer = 0.001   # 0.1%
if side == "bid":
    target_price *= (1 - buffer)   # RSI 트리거보다 낮게 매수
else:
    target_price *= (1 + buffer)   # RSI 트리거보다 높게 매도
```

## 틱 조정

`exchange_adapter.adjust_price_to_tick(target_price)` 로 유효 틱 단위로 내림 (floor).

## 호출 위치

| 위치 | 용도 |
|------|------|
| `signal_engine.get_price_by_rsi()` | 직접 RSI→가격 계산 |
| `rsitrade_command` (main.py) | 각 레그별 매수가 계산 |
| `sync_orders` (main.py) | rsitrade 매수 체결 시 매도가 계산 |
