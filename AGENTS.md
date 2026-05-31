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

## 백업 · 롤백 절차

### 정기 백업

```bash
# 운영 서버에서 직접 실행 (Docker 호스트)
./scripts/backup.sh

# 또는 cron 등록 예시 (매일 새벽 3시)
# 0 3 * * * cd /opt/supabot && ./scripts/backup.sh >> /var/log/supabot-backup.log 2>&1
```

백업 결과물은 `./backups/YYYYMMDD_HHMMSS/` 에 저장됩니다. `data/orders.json`, `data/users.json` 복사본이 생성됩니다.

### 배포 롤백

```bash
# 1. 현재 컨테이너 중지
docker compose down

# 2. 이전 이미지로 되돌리기
docker tag ghcr.io/antny-bot/supabot:latest ghcr.io/antny-bot/supabot:broken
docker pull ghcr.io/antny-bot/supabot:<이전_SHA_태그>
docker tag ghcr.io/antny-bot/supabot:<이전_SHA_태그> ghcr.io/antny-bot/supabot:latest

# 3. 데이터 복원 (필요 시)
cp backups/<YYYYMMDD_HHMMSS>/orders.json data/orders.json
cp backups/<YYYYMMDD_HHMMSS>/users.json  data/users.json
chmod 600 data/orders.json data/users.json

# 4. 재기동
docker compose up -d
```

> ⚠️ `data/users.json` 복원 시 복원 시점 이후의 유저 설정 변경이 유실됩니다. 주문 복원은 거래소 실제 상태와 비교하여 불일치 여부를 확인하세요.
