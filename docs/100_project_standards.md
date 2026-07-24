# 100_project_standards.md — 프로젝트 표준 및 안전 규칙

supabot 프로젝트 안전 규칙, 검증 절차, 백업/롤백 절차 정의. 모든 개발 작업 시 최우선 준수.

## 🚨 안전 규칙

1. **모든 주문 경로는 실거래.** `exchange_adapter.create_order()`, `cancel_order()`, `_create_kis_order()` 등 실계좌 직접 영향. 비가역적 취급.

2. **테스트에서 라이브 API 호출 금지.** `_run_upbit_cli`, `_request_bithumb`, `_request_kis` 반드시 mock. 실제 네트워크 도달 시 실주문/취소 발생.

3. **API 키 암호화 저장.** 거래소/Gemini 키 `USER_SECRET_KEY`(Fernet)로 `enc:v1:` 암호화해 Supabase `users` 테이블(폴백: `data/users.json`) 저장. 암복호화: [src/core/secret_crypto.py](file:///E:/apps/supabot/src/core/secret_crypto.py). `get_user()`는 런타임 복호화 copy 반환 — 로그·에러 메시지 평문 노출 및 commit 절대 금지.

4. **KIS paper vs real.** `exchanges.kis.env = "real"` 이면 실계좌 매매. `env` 변경 시 주의.

5. **Supabase 자격증명.** `SUPABASE_SERVICE_KEY`는 RLS 우회 마스터 키 — 공개 채널/로그/commit 금지. `MANAGER_API_KEY`(봇↔manager 공유), `SESSION_SECRET`(manager 세션 서명) 동일 비밀 취급. `config/.env`·`manager/.env` git-ignore 상태 유지.

6. **UTF-8.** 소스 파일 한글 주석/메시지 처리 시 UTF-8 인코딩 명시.

7. **`/resetuser`(관리자 전용, `system_handlers.resetuser_command`)는 비가역적.** 거래소 미체결 주문 취소 → confirm → 대상 유저 `orders`/`trade_logs`(DB+`trades.jsonl`) 전체 삭제. 거래소 취소 실패 시 자동 중단되나 삭제 자체는 백업 없이 복구 불가 — 실행 전 Supabase 백업 확보 권장. 상세: [205_main_handlers.md](file:///E:/apps/supabot/docs/205_main_handlers.md).

---

## 🛠️ 검증 절차

```bash
# 호스트에 Python 없음 → Docker 내부에서 실행
docker compose run --rm supabot python -m pytest tests/
docker compose run --rm supabot python -m py_compile src/main.py
```

주문·거래소·KIS 로직 변경 시 전체 테스트 통과 필수.
manager(`manager/`) 변경 시: `cd manager && python -m py_compile backend/**/*.py` 로 문법 확인.

**테스트 출력 토큰 절약 전략** (`pytest.ini` `addopts` 적용, 테스트 240+개):
- 성공 테스트는 `.` 표시 (`-q`, pytest quiet 모드).
- 실패/에러 테스트만 짧은 traceback(`--tb=short`) + 요약(`-ra`) 출력.
- `-v` 직붙 시 설정 충돌로 테스트명 전수 나열됨. 플래그 없이 `pytest tests/`만 실행.
- 신규 테스트 추가 시 별도 설정 불필요 — `pytest.ini` 자동 적용.

---

## 💾 백업 · 롤백 절차

### 정기 백업

1차 데이터 소스 Supabase. **Supabase 대시보드 자동 백업(또는 `pg_dump`) 우선 확보**, DB 폴백/캐시 파일 함께 백업.

```bash
# 운영 서버에서 직접 실행 (Docker 호스트) — 파일 폴백 백업
./scripts/backup.sh

# 또는 cron 등록 예시 (매일 새벽 3시)
# 0 3 * * * cd /opt/supabot && ./scripts/backup.sh >> /var/log/supabot-backup.log 2>&1
```

백업 결과물 `./backups/YYYYMMDD_HHMMSS/` 저장. `data/orders.json`, `data/users.json` 복사본 생성. DB 운영 시 파일은 스냅샷이므로 권위 복원은 Supabase 백업 사용.

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

> ⚠️ DB 운영 중 파일 복원보다 Supabase 백업 복원 우선. 파일 복원 시 유저 설정 변경 유실 가능. 주문 복원은 거래소 실제 상태 비교 후 불일치 확인.
