# AGENTS.md — 에이전트 안전 규칙

프로젝트 구조·스키마·작업별 진입점은 **CLAUDE.md** 참조.

## 안전 규칙

1. **모든 주문 경로는 실거래.** `exchange_adapter.create_order()`, `cancel_order()`, `_create_kis_order()` 등은 실계좌에 직접 영향. 비가역적으로 취급.

2. **테스트에서 라이브 API 호출 금지.** `_run_upbit_cli`, `_request_bithumb`, `_request_kis` 를 반드시 mock. 실제 네트워크에 도달하면 실주문/취소가 발생.

3. **API 키는 런타임 평문.** `data/users.json` 에 거래소 키 평문 저장. 로그·에러 메시지에 노출 금지, 절대 commit 금지.

4. **KIS paper vs real.** `users.json → exchanges.kis.env = "real"` 이면 실계좌 매매. `env` 변경 시 극도 주의.

5. **UTF-8.** 소스 파일 내 한글 주석/메시지 처리 시 UTF-8 인코딩 명시.

## 검증 절차

```bash
# 호스트에 Python 없음 → Docker 내부에서 실행
docker compose run --rm supabot python -m pytest tests/ -v
docker compose run --rm supabot python -m py_compile src/main.py
```

주문·거래소·KIS 로직 변경 시 전체 테스트 통과 필수.
