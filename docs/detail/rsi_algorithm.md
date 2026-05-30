# rsi_algorithm.md — RSI 역산 수식

## 표준 RSI (참고)

```
RSI = 100 - 100 / (1 + RS)
RS  = AvgGain / AvgLoss  (period 기간)
```

순방향 RSI는 `ta.momentum.RSIIndicator` 사용.

## 역산 방식

`signal_engine.get_price_by_rsi()` 는 현재 RSI를 계산할 때와 동일하게
`ta.momentum.RSIIndicator` 를 사용한다.

역산은 닫힌 수식을 쓰지 않고, 다음 캔들의 종가를 가정한 뒤
`close_series + [next_close]` 에 대해 RSI를 다시 계산하는 방식이다.

- 매수(`bid`): 후보 가격을 낮춰 가며 목표 RSI 이하가 되는 지점을 탐색
- 매도(`ask`): 후보 가격을 높여 가며 목표 RSI 이상이 되는 지점을 탐색

이 방식은 현재 RSI 표시값과 주문 미리보기 계산이 같은 모델을 쓰도록 맞춰,
`현재 RSI > 목표 RSI` 인데도 목표 매수가가 현재가보다 높게 나오는 불일치를 방지한다.

## 탐색 개요

```python
candidate_rsi = RSIIndicator(close=close_series + [next_close], window=period).rsi().iloc[-1]
```

- `bid`: `next_close` 를 현재가 아래에서 이분 탐색
- `ask`: `next_close` 를 현재가 위에서 이분 탐색

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
