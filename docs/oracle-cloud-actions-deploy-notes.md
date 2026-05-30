# GitHub Actions / GHCR / Oracle VM 배포 메모

이 문서는 현재 `supabot` 저장소의 GitHub Actions 배포 방식이 언제 트리거되는지, 지금 Oracle VM 상태에서 어떤 지점이 실패할 수 있는지, 그리고 권장 배포 방식을 정리한 메모입니다.

## 현재 GitHub Actions 트리거 조건

현재 워크플로 파일은 [docker-publish.yml](/E:/apps/supabot/.github/workflows/docker-publish.yml) 하나입니다.

트리거 조건:

- `release` 이벤트
- 그중 `published` 타입만 대상

즉, 다음은 **트리거되지 않습니다**.

- 일반 `git push`
- `main` 브랜치 업데이트
- 태그만 생성하고 release를 publish하지 않은 경우

즉, 현재 기준으로는 **GitHub Release를 publish해야만** Action이 실행됩니다.

## 현재 워크플로 동작 방식

워크플로는 두 단계로 동작합니다.

### 1. `build-and-push`

- 소스 체크아웃
- GHCR 로그인
- Docker 이미지 빌드
- GHCR에 아래 태그로 push
  - `ghcr.io/antny-bot/supabot:latest`
  - `ghcr.io/antny-bot/supabot:${release_tag}`

### 2. `deploy`

`appleboy/ssh-action`으로 Oracle VM에 SSH 접속한 뒤 아래를 실행합니다.

```bash
cd "${{ secrets.OCI_DEPLOY_PATH }}"
docker compose pull
docker compose up -d
docker image prune -f
```

즉, 현재 배포 전략은:

- 서버에서 다시 빌드하지 않음
- 서버는 GHCR 이미지를 pull만 함
- 서버 코드도 `git pull` 하지 않음

## 현재 상태에서 자동배포가 실패할 가능성이 높은 지점

### 1. Oracle VM SSH 접근 제한

현재 Oracle VM은 보안상 `22/tcp`를 특정 IP `/32`로 제한하는 운영 방식을 사용했습니다.

문제:

- GitHub Actions runner의 공인 IP는 고정되지 않음
- 따라서 GitHub에서 Oracle VM으로 직접 SSH 접속하는 `deploy` 단계는 막힐 가능성이 높음

즉, 현재 보안 규칙을 유지하면 `appleboy/ssh-action` 기반 자동배포는 안정적으로 동작하기 어렵습니다.

### 2. GHCR 이미지 pull 권한 문제

실제 서버 배포 중 아래 문제가 이미 확인되었습니다.

```text
Error response from daemon: error from registry: denied
```

즉, Oracle VM에서 `ghcr.io/antny-bot/supabot:latest`를 pull할 권한이 없었습니다.

문제 원인 후보:

- GHCR 패키지가 private
- 서버에 `docker login ghcr.io`가 안 되어 있음
- `GITHUB_TOKEN`은 GitHub Actions 내부 푸시에는 충분하지만 Oracle VM pull 권한과는 별개

즉, 현재 `deploy` 단계의 `docker compose pull`은 바로 실패할 가능성이 높습니다.

### 3. 서버 코드와 배포 방식의 불일치

현재 Oracle VM에서는 실제로 아래 방식으로 성공 배포했습니다.

- 서버에 레포 clone
- `docker compose up -d --build`
- VM 로컬에서 직접 이미지 빌드

반면 GitHub Actions는 아래 방식입니다.

- GHCR에 push
- VM에서는 `pull`만 수행

즉, 현재 서버 운영 방식과 워크플로 배포 방식이 서로 다릅니다.

### 4. `docker-compose.yml`이 GHCR pull 중심으로 작성됨

현재 `docker-compose.yml`은 `image:`를 기준으로 실행되며, 서버에서 로컬 소스 빌드를 하려면 `build: .`가 필요합니다.

수동 배포 시에는 `build: .`를 써서 해결했지만, 자동배포 전략을 GHCR pull로 유지할지, VM 로컬 빌드로 유지할지 먼저 결정해야 합니다.

## 권장 배포 방식

현재 상태 기준으로는 아래 둘 중 하나로 정리하는 것이 좋습니다.

### 권장안 A: GHCR 기반 자동배포

이 방식을 쓰면 Oracle VM에서 다시 빌드할 필요가 없습니다.

필요 조건:

1. GHCR 패키지를 Oracle VM이 pull 가능해야 함
2. Oracle VM이 GitHub Actions runner에서 SSH 가능해야 함

추가 작업:

- GHCR 패키지를 public으로 바꾸거나
- Oracle VM에 GHCR read 권한 토큰으로 `docker login ghcr.io` 구성
- Oracle SSH 접근 제한을 GitHub Actions에서 접근 가능한 방식으로 재설계
  - 예: bastion
  - 예: self-hosted runner on Oracle VM
  - 예: Oracle 쪽 pull-based deploy agent

장점:

- Release publish 후 자동 배포 가능
- 서버에서 재빌드 불필요

단점:

- 현재 Oracle 보안 정책과 바로 충돌
- 초기 세팅이 더 까다로움

### 권장안 B: Oracle VM 로컬 빌드 수동배포

현재 실제로 성공한 방식입니다.

방식:

```bash
git pull
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100
```

장점:

- 지금 상태에서 바로 재현 가능
- GHCR 권한 문제 없음
- GitHub Actions SSH 접근 문제 없음

단점:

- Release만으로 자동 배포되지 않음
- 배포 시 Oracle VM에 직접 들어가야 함

## 현재 상태 기준 최종 권장

현재 Oracle VM의 운영/보안 상태를 보면 **권장안 B**가 더 현실적입니다.

즉, 당분간은:

1. GitHub에서 코드 업데이트
2. Oracle VM에서 `git pull`
3. `docker compose up -d --build`

이 흐름이 가장 단순하고 안정적입니다.

## 자동배포를 유지하고 싶다면 가장 현실적인 수정 방향

현재 워크플로를 그대로 두는 것보다, 아래 중 하나가 더 낫습니다.

### 옵션 1. `deploy` 잡 제거

GitHub Actions는 GHCR 이미지만 만들고, Oracle 배포는 수동으로 진행:

- 장점: 단순함
- 단점: 완전 자동은 아님

### 옵션 2. self-hosted runner를 Oracle VM에 설치

이 경우 GitHub Actions가 Oracle VM 내부에서 직접 실행되므로:

- 외부 SSH inbound 허용 필요가 줄어듦
- GHCR pull 또는 로컬 빌드 중 원하는 방식 선택 가능

### 옵션 3. Oracle VM에서 GHCR pull 가능한 구조로 정리

필요 작업:

- GHCR public/package 권한 정리
- 서버 `docker login ghcr.io` 구성
- Oracle SSH 접근 경로 재설계

## 실무적으로 추천하는 다음 단계

1. 당분간은 Oracle VM에서 수동 배포 유지
2. GitHub Actions는 이미지 빌드/검증 전용으로만 사용 여부 검토
3. 자동배포가 꼭 필요해지면 self-hosted runner 방식으로 전환 검토

## 참고 파일

- 워크플로: [docker-publish.yml](/E:/apps/supabot/.github/workflows/docker-publish.yml)
- SSH/직렬 콘솔 복구 기록: [oracle-cloud-ssh-recovery-success.md](/E:/apps/supabot/docs/oracle-cloud-ssh-recovery-success.md)
