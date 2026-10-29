# F4. 멀티지표 조합 신호 설계 문서

## 1. 개요
현재 RSI 감시 목록(`analyze_watchlist`)은 RSI 과매도 조건 또는 볼린저 밴드(BB) 하단 터치 조건 중 하나라도 만족하면 알림을 발송(OR 모드)합니다. 시장 변동성이 클 때 가짜 신호(Whipsaw)로 인한 잦은 알림을 필터링하기 위해, 두 지표를 동시에 만족할 때만 알림을 발송하는 AND 조합 모드를 지원합니다.

## 2. 세부 설계
1. **사용자 설정 추가**:
   - `UserManager.DEFAULT_PREFERENCES`: `"signal_combine_mode": "or"` (기본값 "or", 선택 가능: "or" | "and")
2. **신호 판정 로직 (`SignalEngine.analyze_watchlist`)**:
   - `combine_mode = user.get("preferences", {}).get("signal_combine_mode", "or")`
   - RSI 조건: `rsi_val <= threshold`
   - BB 조건: `bb_alert and current_price <= bb_lower`
   - 판정:
     - `combine_mode == "and"`: `rsi_alert and bb_triggered` 만족 시 알림
     - `combine_mode == "or"`: `rsi_alert or bb_triggered` 만족 시 알림
3. **수용 기준 (Acceptance Criteria)**:
   - `combine_mode == "or"`: RSI 단독 만족 시 알림 발생, BB 단독 만족 시 알림 발생.
   - `combine_mode == "and"`: RSI 단독 또는 BB 단독 시 알림 미발생, 둘 다 만족할 때만 알림 발생.
