# GitHub Actions Workflows

이 문서는 `E:/apps/supabot/.github/workflows/` 아래 GitHub Actions 워크플로의 현재 동작을 설명합니다.

운영 규칙:

- 워크플로 파일을 수정하면 이 문서도 함께 업데이트합니다.
- 특히 트리거, 이미지 태그 정책, 배포 조건, cleanup 정책이 바뀌면 같은 커밋에서 반영합니다.

## 현재 워크플로 목록

| Workflow | 파일 | 역할 |
| --- | --- | --- |
| Build Bot | `.github/workflows/build-bot.yml` | bot Docker 이미지 빌드 및 GHCR 푸시, release 시 Oracle VM 배포 |
| Build Manager | `.github/workflows/build-manager.yml` | manager Docker 이미지 빌드 및 GHCR 푸시 |
| Test | `.github/workflows/ci-test.yml` | Python 테스트 실행 |
| Cleanup Registry and Cache | `.github/workflows/cleanup-registry-and-cache.yml` | GHCR 오래된 이미지 정리, 필요 시 수동 cache 삭제 |

## Build Bot

파일: [build-bot.yml](/E:/apps/supabot/.github/workflows/build-bot.yml)

트리거:

- `main` 브랜치 push
- 단, 다음 경로가 바뀐 경우만 실행
- `src/**`
- `scripts/**`
- `requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
- GitHub Release `published`
- 실제 job 실행은 release tag가 `bot-`로 시작할 때만 허용

동작:

1. 저장소 checkout
2. `ghcr.io` 로그인
3. Docker Buildx 설정
4. 이미지 태그 결정
5. Docker 이미지 빌드 및 GHCR 푸시
6. release tag가 `bot-...` 이면 Oracle VM에 SSH 접속 후 배포

이미지 태그:

- 기본: `ghcr.io/antny-bot/supabot:latest`
- release: `latest` + `ghcr.io/antny-bot/supabot:<release-tag>`

배포 단계:

```bash
cd "${OCI_DEPLOY_PATH}"
docker compose pull
docker compose up -d
docker image prune -f
```

주의:

- `main` push만으로는 Oracle VM 배포가 일어나지 않습니다.
- Oracle VM 자동 배포는 `bot-*` release publish일 때만 실행됩니다.
- 사용 secret: `OCI_HOST`, `OCI_USER`, `OCI_SSH_PRIVATE_KEY`, `OCI_SSH_PORT`, `OCI_DEPLOY_PATH`

## Build Manager

파일: [build-manager.yml](/E:/apps/supabot/.github/workflows/build-manager.yml)

트리거:

- `main` 브랜치 push
- 단, `manager/**` 변경일 때만 실행
- GitHub Release `published`
- 실제 job 실행은 release tag가 `manager-`로 시작할 때만 허용

동작:

1. 저장소 checkout
2. `ghcr.io` 로그인
3. Docker Buildx 설정
4. 이미지 태그 결정
5. `manager/` 컨텍스트로 이미지 빌드 및 GHCR 푸시

이미지 태그:

- 기본: `ghcr.io/antny-bot/supabot-manager:latest`
- release: `latest` + `ghcr.io/antny-bot/supabot-manager:<release-tag>`

주의:

- manager 워크플로에는 별도 자동 배포 job이 없습니다.

## Test

파일: [ci-test.yml](/E:/apps/supabot/.github/workflows/ci-test.yml)

트리거:

- `main` push
- `claude/**` push
- `main` 대상 pull request

동작:

1. 저장소 checkout
2. Python `3.11` 설정
3. 루트 `requirements.txt`, `manager/requirements.txt` 설치
4. `pytest tests/ -v` 실행

특징:

- artifact 업로드나 GHCR 푸시는 하지 않습니다.
- 테스트 게이트 역할의 워크플로입니다.

## Cleanup Registry and Cache

파일: [cleanup-registry-and-cache.yml](/E:/apps/supabot/.github/workflows/cleanup-registry-and-cache.yml)

트리거:

- 매주 스케줄 실행
- `cron: '25 18 * * 0'`
- GitHub Actions 기준 UTC이므로 한국 시간으로는 월요일 `03:25`
- 수동 실행 `workflow_dispatch`

기본 정책:

- GHCR 패키지 `supabot`, `supabot-manager` 각각 최신 `10`개 버전 유지
- 오래된 버전만 삭제
- Actions cache 삭제는 기본 비활성화
- Actions cache 삭제는 수동 실행에서 `cleanup_caches=true`일 때만 수행

세부 동작:

1. 패키지 버전 목록 조회
2. 생성일 기준 내림차순 정렬
3. 최신 `keep_versions`개 유지
4. 초과분 삭제
5. 수동 실행 + `cleanup_caches=true`이면 Actions cache 전체 삭제

현재 운영 해석:

- push 때마다 cleanup을 붙이지 않습니다.
- build 워크플로와 cleanup 워크플로는 분리 유지합니다.
- cleanup은 주기 실행으로 GHCR만 정리하고, cache 삭제는 필요할 때만 수동으로 켭니다.

## 배포 트러블슈팅 (자동배포 실패 시 점검 포인트)

`build-bot.yml`의 release 자동배포(`appleboy/ssh-action` → `docker compose pull && up -d`)가 실패하면 아래 순서로 점검합니다.

1. **Oracle VM SSH 접근 제한**: NSG/Security List가 `22/tcp`를 특정 IP `/32`로 제한하면, 고정 IP가 아닌
   GitHub Actions runner에서 SSH가 막힐 수 있습니다 (`OCI_HOST`/`OCI_USER`/`OCI_SSH_PRIVATE_KEY`/`OCI_SSH_PORT` 시크릿 대상 경로의
   인바운드 규칙 확인 — `oracle-cloud-vm-setup.md` 참고).
2. **GHCR pull 권한**: 서버에서 `Error response from daemon: error from registry: denied`가 뜨면 GHCR 패키지가
   private인데 `docker login ghcr.io`가 안 되어 있거나 `read:packages` 토큰이 없는 경우입니다 → 패키지를 public으로
   전환하거나 read 권한 토큰으로 로그인합니다.
3. **빌드 방식 불일치**: `docker-compose.yml`이 `image:`(GHCR pull) 기준인지 `build: .`(로컬 빌드) 기준인지 먼저
   맞춰야 합니다. 서버에서 `git pull` + `--build`로 로컬 빌드 운영 중이라면 워크플로의 GHCR pull 전제와 충돌합니다.

긴급 fallback (자동배포가 막힌 경우): VM에 직접 SSH 접속 후 수동 배포

```bash
git pull
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100
```

## 운영 체크포인트

- 새 워크플로 추가 시 이 문서의 목록과 트리거 설명을 먼저 갱신합니다.
- `paths`, `release tag prefix`, `image name`, `cron`, `keep_versions`, `cache` 정책 변경 시 반드시 문서를 같이 수정합니다.
- README에는 요약만 두고, 상세 설명은 이 문서를 기준으로 유지합니다.
