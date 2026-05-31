# supabot-manager

봇과 Supabase DB를 공유하는 관리 웹 대시보드 (FastAPI + Jinja2 + HTMX).
Synology Docker에 배포한다. 봇과 직접 의존하지 않으며, Telegram 알림이 필요할 때만
봇의 `/internal/notify`(포트 8765)를 단방향 호출한다.

## Synology 배포 순서

1. **이미지 빌드** — `manager/**` 변경이 `main`에 머지되면 GitHub Actions가
   `ghcr.io/antny-bot/supabot-manager:latest` 를 빌드·push 한다.

2. **GHCR 접근** — 패키지를 Public으로 전환하거나, private 유지 시 PAT(`read:packages`)로 로그인:
   ```bash
   echo "<GITHUB_PAT>" | docker login ghcr.io -u <github_user> --password-stdin
   ```

3. **배포 폴더 + `.env`** — 예: `/volume1/docker/supabot-manager/` 에 `.env.template`을
   복사해 `.env` 작성:
   ```
   SUPABASE_URL=https://<project>.supabase.co
   SUPABASE_SERVICE_KEY=<service_role 키>
   SUPABASE_ANON_KEY=<anon public 키>
   SESSION_SECRET=<python3 -c "import secrets; print(secrets.token_hex(32))">
   BOT_NOTIFY_URL=http://<Oracle VM 공인 IP>:8765
   MANAGER_API_KEY=<봇 config/.env의 MANAGER_API_KEY와 동일>
   ```

4. **실행** — 같은 폴더에 `docker-compose.yml`을 두고:
   ```bash
   docker compose up -d
   ```
   (DSM GUI 사용 시: 이미지 pull → 포트 `8000:8000` 매핑 → 환경변수 입력 → 실행)

5. **방화벽** — Oracle VCN Security List에서 Synology 공인 IP만 8765 Ingress 허용.

6. **확인** — `http://<Synology IP>:8000` → Supabase Auth 계정으로 로그인 → 유저 목록.

## 관리자 계정

Supabase 대시보드 → Authentication → Users → Add user 로 이메일+비밀번호 계정 생성
(Auto Confirm 체크). 이 계정으로 manager에 로그인한다.

## 로컬 테스트

```bash
cd manager
pip install -r requirements.txt
cp .env.template .env   # 값 채우기
uvicorn backend.main:app --reload --port 8000
```
