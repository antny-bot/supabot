# Supabase 정기 백업 및 관리자 연동 수정(Fix) 개발 계획서

## 1. 개요
커밋 `deeb9fe`에서 구현된 Supabase 정기 백업, Google Drive 연동, 관리자 UI(`AdminBackupTab`), 로컬 SQLite 폴백 기능에 대한 코드 검수 결과 발견된 **치명적 이슈 4건**과 **중요 이슈 4건**을 수정하기 위한 작업 명세서이다.

작업 완료 후 반드시 아래 **6절의 검증 명령어(`pytest`, `npm run build`)**를 모두 실행하여 에러가 0건인지 확인해야 한다.

---

## 2. 치명적 이슈 수정 명세 (Critical — 필수 수정)

### Fix 1: Manager 프론트엔드 TypeScript 빌드 에러 수정 (`AdminBackupTab.tsx`)
- **대상 파일**: `manager/frontend/src/pages/admin/AdminBackupTab.tsx`
- **원인**:
  1. `ErrorBanner` 컴포넌트(`src/components/ui/ErrorBanner.tsx`)는 `{ message: string }`만 받으며 `onClose` prop이 없다.
  2. `Badge` 컴포넌트(`src/components/ui/Badge.tsx`)는 `{ value: string, label?: string, className?: string }`만 받으며 `variant`나 `children` prop이 없다.
- **수정 방법**:
  1. **151행 부근 (`ErrorBanner`)**:
     ```tsx
     // 변경 전
     {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
     // 변경 후
     {error && <ErrorBanner message={error} />}
     ```
  2. **172~176행 부근 (`Badge`)**:
     ```tsx
     // 변경 전
     <Badge
       variant={state?.last_status === 'success' ? 'success' : state?.last_status === 'error' ? 'danger' : 'neutral'}
     >
       {state?.last_status === 'success' ? '정상' : state?.last_status === 'error' ? '실패' : '대기'}
     </Badge>

     // 변경 후 (Badge의 value 매핑 활용: active=초록, error=빨강, warning=노랑, pending=대기)
     <Badge
       value={
         state?.last_status === 'success'
           ? 'active'
           : state?.last_status === 'error'
             ? 'error'
             : state?.last_status === 'partial_error'
               ? 'warning'
               : 'pending'
       }
       label={
         state?.last_status === 'success'
           ? '정상'
           : state?.last_status === 'error'
             ? '실패'
             : state?.last_status === 'partial_error'
               ? '일부실패(GDrive)'
               : '대기'
       }
     />
     ```
  3. **204~208행 부근 (`Badge`)**:
     ```tsx
     // 변경 전
     {config?.gdrive_enabled ? (
       <Badge variant="success">연동 완료 (.env)</Badge>
     ) : (
       <Badge variant="warning">미연동 (.env 필요)</Badge>
     )}

     // 변경 후
     {config?.gdrive_enabled ? (
       <Badge value="active" label="연동 완료 (.env)" />
     ) : (
       <Badge value="warning" label="미연동 (.env 필요)" />
     )}
     ```

---

### Fix 2: Manager ↔ Bot 분리 컨테이너 간 내부 Webhook 연동 완성
- **대상 파일**:
  - `src/main.py`
  - `src/internal_api.py`
  - `manager/backend/bot_client.py`
  - `manager/backend/routers/backup.py`
- **원인**:
  - Bot(Oracle VM)과 Manager(별도 컨테이너)는 파일시스템(`data/`)과 `.env`를 공유하지 않는다.
  - 따라서 Manager가 로컬에서 `data/backup_state.json`, `data/backups/`, `os.environ.get("GDRIVE_...")`을 읽으면 항상 빈 값/미연동으로 나온다.
  - 또한 `backup.py:162`의 `from core.backup_manager import ...`는 Manager 컨테이너에 `src/core`가 없으므로 `ModuleNotFoundError`가 발생한다.
- **수정 방법**:
  1. **`src/internal_api.py` (`_internal_backup_status_handler`)**:
     - 로컬 백업 파일 목록(`local_files`)까지 함께 반환하도록 확장한다.
     ```python
     async def _internal_backup_status_handler(request: _web.Request) -> _web.Response:
         """백업 상태, 설정 정보, 로컬 백업 파일 목록 조회 webhook."""
         if not await _verify_webhook_request(request):
             return _web.Response(status=401)
         try:
             from core.backup_manager import load_backup_state, get_backup_config, list_local_backup_files
             state = load_backup_state()
             config = get_backup_config()
             local_files = list_local_backup_files()
             return _web.Response(
                 text=_json.dumps({"state": state, "config": config, "local_files": local_files}, ensure_ascii=False),
                 content_type="application/json",
             )
         except Exception as e:
             _log.error("Internal backup status failed", exc_info=e)
             return _web.Response(status=500, text=str(e))
     ```
     - `src/core/backup_manager.py`에 `list_local_backup_files() -> List[Dict[str, Any]]` 헬퍼 함수를 추가한다 (`BACKUP_DIR` 내 `supabot-backup-*.zip` 파일의 `filename`, `sizeBytes`, `createdAt` 리스트를 최신순 반환).
  2. **`src/main.py` (612행)**:
     - `bot_client._send_signed_request_async`는 `POST` 요청으로 HMAC 서명을 전송하므로, `/internal/backup/status` 라우트도 `add_post`로 등록(또는 `add_post`와 `add_get` 모두 등록)한다.
     ```python
     notify_app.router.add_post("/internal/backup/trigger", internal_api._internal_backup_trigger_handler)
     notify_app.router.add_post("/internal/backup/status", internal_api._internal_backup_status_handler)
     ```
  3. **`manager/backend/bot_client.py`**:
     - `get_bot_backup_status() -> tuple[bool, dict]` 함수를 추가하여 `/internal/backup/status`를 호출한다.
     - `trigger_bot_backup()` 호출 시 타임아웃을 `120.0`초로 전달할 수 있도록 `_send_signed_request_async(endpoint: str, payload: dict, timeout: float = 10.0)`에 `timeout` 기본값 인자를 추가한다 (아래 **Fix 3**과 연계).
  4. **`manager/backend/routers/backup.py`**:
     - `/api/backup/config`: DB `system_config`를 읽되, `get_bot_backup_status()`가 성공하면 Bot이 반환한 `config["gdrive_enabled"]`와 `config["gdrive_folder"]`를 우선 반영한다.
     - `/api/backup/status`: `get_bot_backup_status()`를 우선 호출하여 Bot의 `state`와 `local_files`를 반환하고, Bot 연결 실패 시에만 로컬 `STATE_FILE` / `BACKUP_DIR` 폴백을 읽는다.
     - `/api/backup/trigger`: `from core.backup_manager import execute_full_backup_sync` 폴백 블록을 제거하거나 `ImportError`를 안전하게 처리하고, `trigger_bot_backup()` 결과를 그대로 반환한다.

---

### Fix 3: 즉시 백업 Webhook 10초 타임아웃 문제 해결
- **대상 파일**: `manager/backend/bot_client.py`
- **원인**: `_send_signed_request_async`의 `httpx.AsyncClient(timeout=10.0)` 고정으로 인해, 14개 테이블 덤프 + 압축 + Google Drive 업로드가 10초를 초과하면 백업은 성공해도 Manager는 타임아웃 에러를 받는다.
- **수정 방법**:
  - `_send_signed_request_async(endpoint: str, payload: dict, timeout: float = 10.0)`으로 시그니처를 확장(기존 호출부 하위 호환 유지).
  - `trigger_bot_backup()`에서는 `await _send_signed_request_async("/internal/backup/trigger", {}, timeout=180.0)`으로 호출하여 대용량 업로드 시에도 타임아웃되지 않도록 한다.

---

### Fix 4: 테이블 덤프 실패 시 빈 테이블로 백업/폴백 DB를 덮어쓰는 버그 수정
- **대상 파일**: `src/core/backup_manager.py` (393~403행)
- **원인**:
  ```python
  for tname in BACKUP_TABLES:
      try:
          rows = dump_supabase_table(tname)
          ...
      except Exception as e:
          logger.warning("Failed to dump table %s: %s", tname, e)
          tables_data[tname] = []
  ```
  Supabase 일시 장애 시 모든 테이블이 `[]` 빈 리스트로 들어간 채 `create_sqlite_snapshot`이 실행되어, 정상적인 `data/fallback_latest.sqlite3`까지 빈 DB로 덮어써지고 `last_status = "success"`가 된다.
- **수정 방법**:
  - 테이블 덤프 중 하나라도 예외가 발생하면 빈 배열로 무시하지 않고 **예외를 그대로 raise**하여 바깥 `except Exception as e:` 블록으로 보내야 한다.
  - 그러면 스냅샷 생성 및 `fallback_latest.sqlite3` 덮어쓰기가 중단되고, `last_status = "error"`와 `last_error`가 정확히 기록되며 기존 `fallback_latest.sqlite3`가 안전하게 보존된다.

---

## 3. 중요 이슈 수정 명세 (Major — 정합성 및 품질 개선)

### Fix 5: `dump_supabase_table` 페이지네이션 시 정렬 보장
- **대상 파일**: `src/core/db.py`, `src/core/backup_manager.py`
- **원인**: PostgREST에서 `order` 파라미터 없이 `Range: 0-999`, `1000-1999`로 페이지네이션하면 Postgres가 행 순서를 보장하지 않아 페이지 경계에서 행이 중복되거나 누락될 수 있다.
- **수정 방법**:
  1. `src/core/db.py`의 `_FilteredQuery` 클래스에 `order` 메서드를 추가한다:
     ```python
     def order(self, column: str, desc: bool = False) -> "_FilteredQuery":
         direction = "desc" if desc else "asc"
         self._params["order"] = f"{column}.{direction}"
         return self
     ```
  2. `src/core/backup_manager.py`에 테이블별 기본 정렬 컬럼 매핑(`TABLE_ORDER_KEYS`)을 정의하거나, `dump_supabase_table`에서 기본 PK 컬럼으로 정렬 후 `.range(start, end)`를 호출한다:
     - `users`: `"user_id"`
     - `orders`: `"uuid"`
     - `system_config`: `"key"`
     - `command_log_daily`: `"day,user_id,command"` (또는 `"day"`)
     - `kr_stock_cache`: `"code"`
     - `market_top_snapshots`: `"exchange,snapshot_date,rank"` (또는 `"snapshot_date"`)
     - 그 외(`trade_logs`, `operational_events`, `nl_logs`, `strategy_templates`, `command_logs`, `dca_schedules`, `budget_ledger`, `feedbacks`): `"id"`

---

### Fix 6: Google Drive 업로드 실패 시 상태(`partial_error`) 및 에러 기록
- **대상 파일**: `src/core/backup_manager.py` (436~482행)
- **원인**: Google Drive 업로드가 실패해도 로그만 찍고 `last_status = "success"`, `last_error = None`으로 덮어써서 관리자가 Drive 연동 장애를 알 수 없다.
- **수정 방법**:
  - `gdrive_error: Optional[str] = None` 변수를 두고, Google Drive 업로드/Prune 블록에서 예외 발생 시 `gdrive_error = f"GDrive upload failed: {e}"`로 저장한다.
  - 상태 저장 시:
    - `state["last_status"] = "partial_error" if gdrive_error else "success"`
    - `state["last_error"] = gdrive_error`
  - 반환값에도 `"status": state["last_status"]`, `"error": gdrive_error`를 포함한다.

---

### Fix 7: 스케줄러 실패 시 `operational_events` 로깅 누락 수정
- **대상 파일**: `src/core/backup_manager.py` (`backup_loop`, 552~567행)
- **원인**: `trigger_backup()` 내부의 `execute_full_backup_sync()`가 예외를 잡아서 `{"status": "error", "error": ...}` dict를 반환하므로, `backup_loop`의 `except` 블록이 타지 않는다.
- **수정 방법**:
  ```python
  if should_run_backup():
      logger.info("Backup condition met. Starting scheduled backup...")
      res = await trigger_backup()
      if res.get("status") in ("error", "partial_error"):
          try:
              from core.operational_events import log_operational_event
              log_operational_event(
                  "backup_failed",
                  "backup_manager",
                  res.get("error") or "Scheduled backup failed",
              )
          except Exception:
              pass
  ```
  *(참고: `src/core/operational_events.py`의 실제 함수명을 확인하여 호출할 것)*

---

### Fix 8: Fallback SQLite `BOOLEAN` 컬럼 복원 지원
- **대상 파일**: `src/core/backup_manager.py`, `src/core/db.py`
- **원인**: `create_sqlite_snapshot`에서 `bool`을 `1`/`0`(`INTEGER`)으로 변환하여 저장하므로, `query_fallback`으로 읽을 때 원래 `True`/`False`였던 값(`is_active`, `is_admin`, `enabled` 등)이 정수 `1`/`0`으로 반환된다.
- **수정 방법**:
  - `create_sqlite_snapshot`에서 `bool` 타입 컬럼의 SQLite 컬럼 선언 타입을 `"BOOLEAN"`으로 지정한다 (`_sqlite_type(value)`에서 `isinstance(value, bool)`이면 `"BOOLEAN"` 반환 — SQLite는 `"BOOLEAN"`을 NUMERIC affinity로 정상 처리함).
  - `db.py`의 `query_fallback`에서 `PRAGMA table_info("{table_name}")`로 `"BOOLEAN"` 타입인 컬럼 목록을 확인한 뒤, 해당 컬럼 값이 `0` 또는 `1`이면 `bool(v)`로 복원한다.

---

## 4. 단위 테스트 보강 (`tests/test_backup_manager.py`)
기존 13개 테스트를 유지하면서 아래 테스트 케이스를 추가/갱신한다:
1. **테이블 덤프 중 일부 실패 시 백업 중단 테스트**:
   - 특정 테이블(`orders`)에서 예외 발생 시 `execute_full_backup_sync()`가 `"status": "error"`를 반환하고, 기존 `fallback_latest.sqlite3` 파일이 덮어써지지 않고 유지되는지 검증.
2. **Fallback `BOOLEAN` 및 `JSON` 복원 테스트**:
   - `{"user_id": "u1", "is_admin": True, "preferences": {"a": 1}}`를 스냅샷 저장 후 `db.query_fallback("users")`로 읽었을 때 `row["is_admin"] is True`(정수 `1`이 아닌 `bool`)이고 `row["preferences"] == {"a": 1}`인지 검증.
3. **Google Drive 업로드 실패 시 `partial_error` 상태 검증**:
   - 로컬 스냅샷/ZIP은 성공하고 Drive 업로드만 실패했을 때 `status == "partial_error"` 및 `last_error`가 기록되는지 검증.

---

## 5. 수정 대상 파일 체크리스트
- [ ] `manager/frontend/src/pages/admin/AdminBackupTab.tsx` (Fix 1)
- [ ] `src/core/backup_manager.py` (Fix 2, 4, 5, 6, 7, 8)
- [ ] `src/core/db.py` (Fix 5, 8)
- [ ] `src/internal_api.py` (Fix 2)
- [ ] `src/main.py` (Fix 2)
- [ ] `manager/backend/bot_client.py` (Fix 2, 3)
- [ ] `manager/backend/routers/backup.py` (Fix 2)
- [ ] `tests/test_backup_manager.py` (테스트 추가)

---

## 6. 완료 검증 기준 (Verification Commands)
수정이 끝나면 반드시 아래 두 명령어를 실행하여 모두 통과하는지 확인한다:

```powershell
# 1. 백업 및 Google Drive 단위 테스트 실행
pytest tests/test_backup_manager.py tests/test_gdrive_client.py -v

# 2. Manager 프론트엔드 TypeScript 타입 체크 및 프로덕션 빌드 검증
npm --prefix manager/frontend run build
```
