# Supabot Oracle Cloud 배포 순서

Oracle Cloud VM Supabot 실배포 순서 가이드.

관련 초기 설정 문서는 [oracle-cloud-vm-setup.md](E:\apps\supabot\docs\oracle-cloud-vm-setup.md) 를 참고하세요.

## 구성 개요 (2개 컴포넌트로 분리됨)

현재 Supabot은 두 컴포넌트로 나뉘어 운영됩니다.

- **bot**: Oracle Cloud VM에서 `docker compose`로 실행. 이 문서가 다루는 대상입니다. 이미지: `ghcr.io/antny-bot/supabot:latest`
- **manager**: Synology NAS의 Docker에서 별도 실행(포트 8000). 배포 절차는 별도이며 [manager/README.md](../manager/README.md) 를 참고하세요. 이미지: `ghcr.io/antny-bot/supabot-manager:latest`

두 컴포넌트는 동일한 Supabase Postgres DB를 공유합니다. 이 문서는 bot / Oracle VM 쪽에 집중합니다.

## 1. Oracle 콘솔에서 인스턴스 생성 및 확인

Oracle Cloud 콘솔 Supabot용 VM 생성.

권장 기준:

- Shape: `VM.Standard.E2.1.Micro`
- OS Image: `Canonical Ubuntu 24.04`
- 사용자명: `ubuntu`
- VCN / 서브넷: public subnet 기준
- Public IP: 가능하면 생성 시 활성화

생성 직후 확인 항목:

- 인스턴스 상태가 `실행 중`인지
- 인스턴스 상세의 기본 사용자명이 `ubuntu`인지
- 공인 IP가 실제로 붙어 있는지

`Public IP`가 생성 위저드에서 비활성화되거나 생성 후 빠져도 진행 가능.

공인 IP 사후 할당 순서:

1. 인스턴스 상세 이동
2. `네트워킹` 탭 선택
3. 연결된 VNIC 열기
4. `IP 관리` 탭 이동
5. 기본 프라이빗 IP 행의 `작업 > 편집`
6. `퍼블릭 IP 유형`에서 `임시 퍼블릭 IP` 선택
7. `업데이트`

보안 기준 확인:

- `22/tcp`는 접속 중 본인 공인 IP `/32`만 허용
- webhook/reverse proxy 없으면 `80`, `443`은 열지 않음
- NSG 또는 보안 목록 과도 허용 여부 확인

## 2. SSH 접속

VM SSH 접속:

```bash
ssh ubuntu@<public-ip>
```

기본 사용자 `ubuntu`. 타 이미지 사용 시 해당 계정 확인.

## 3. 서버에 레포 올리기

Git 레포 클론:

```bash
cd ~
git clone <레포주소> supabot
cd ~/supabot
```

디렉터리 존재 시 `git pull` 또는 필요 방식으로 최신 소스 반영.

## 4. 초기 설정 스크립트 실행

초기 설정 스크립트 실행:

```bash
cd ~/supabot
MY_PUBLIC_IP=본인공인IP bash scripts/setup_oracle_vm.sh
```

예시:

```bash
MY_PUBLIC_IP=203.0.113.10 bash scripts/setup_oracle_vm.sh
```

스크립트 설정 항목:

- swap 생성
- `ufw` 방화벽 설정
- `fail2ban` 활성화
- SSH 보안 설정
- Docker 설치
- `~/supabot/config`, `~/supabot/data` 디렉터리 생성
- `.env` 템플릿 생성

## 5. 새 SSH 세션으로 재접속 확인

스크립트 실행 후 기존 세션 유지 상태로 새 터미널 재접속 테스트:

확인 항목:
- SSH 키 로그인 접속 확인
- `ufw` 적용 후 본인 IP 접속 여부 확인

확인 끝나기 전 기존 세션 닫지 말 것.

## 6. `.env` 작성

환경변수 파일 작성:

```bash
nano ~/supabot/config/.env
```

예시:

```env
TELEGRAM_BOT_TOKEN=...
ADMIN_CHAT_ID=...
USER_SECRET_KEY=...
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
# 선택 (manager → bot notify 채널용)
MANAGER_API_KEY=...
INTERNAL_PORT=8765
```

`USER_SECRET_KEY`는 사용자 거래소/Gemini 키 `data/users.json` 암호화용 Fernet 마스터키. VM `config/.env`에만 보관하고 GitHub 올리지 않음.

`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`는 bot/manager 공유 Supabase Postgres 접속용. `MANAGER_API_KEY`와 `INTERNAL_PORT`는 manager가 bot의 `/internal/notify`(기본 8765 포트) 호출 시 사용하며 `MANAGER_API_KEY`는 `X-API-Key` 헤더로 검증됨. 자세한 인바운드 규칙: [oracle-cloud-vm-setup.md](E:\apps\supabot\docs\oracle-cloud-vm-setup.md) 참고.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Fernet 미준수 시 새 API 키 저장 실패. `enc:v1:` 암호화된 `users.json`은 같은 `USER_SECRET_KEY` 필요. 키 다르면 봇 기동돼도 `/whoami`에 `보안 키: 복호화 오류` 표시되고 거래소/Gemini 키 사용 불가.

파일 권한 제한:

```bash
chmod 600 ~/supabot/config/.env
```

## 7. `docker-compose.yml` 확인

[docker-compose.yml](E:\apps\supabot\docker-compose.yml) 기준 배포.

기본 설정:

- 서비스명: `supabot`
- 컨테이너명: `supabot`
- 재시작 정책: `unless-stopped`
- `config/.env`는 읽기 전용 마운트
- `data` 디렉터리는 영속 볼륨 사용

이미지 주소 `ghcr.io/antny-bot/supabot:latest` pull 가능 여부 배포 전 확인.

## 8. 컨테이너 실행

레지스트리 이미지 pull 및 실행:

```bash
cd ~/supabot

# 레포지토리가 Private인 경우 로그인 필요
# echo $CR_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

docker compose pull
docker compose up -d
docker compose ps
```

## 9. 로그 확인

기동 직후 로그 확인:

```bash
docker compose logs -f --tail=100
```

확인 항목:
- 컨테이너가 바로 종료되지 않고 유지되는지
- 환경변수 누락 오류 없는지
- 파일 권한 오류 없는지

## 10. Telegram 동작 확인

Telegram 동작 확인:

- `/start` 명령 정상 응답 확인
- `ADMIN_CHAT_ID` 계정 초기 관리자 처리 확인
- `data/users.json` 생성 확인

## 11. 이미지 pull 이 안 되는 경우

VM 직접 빌드:

`docker-compose.yml`에서 `image:` 대신 `build: .` 사용.

실행 예시:

```bash
cd ~/supabot
docker compose up -d --build
```

## 12. 배포 직후 운영 점검

배포 직후 점검:

- Oracle 콘솔 인스턴스 상태 `실행 중` 유지 확인
- 인스턴스 공인 IP 실제로 붙어 있는지
- Oracle NSG `22/tcp` source 본인 IP 제한 확인
- NSG 또는 보안 목록 `80`, `443` 불필요하게 열리지 않았는지
- OCI boot volume backup 활성화 확인
- `docker compose logs` 반복 에러 없는지
- `data/users.json` 권한 과도 허용 없는지

## 13. 주의사항

- 실거래 경로 포함. 테스트 중 실주문 방지 주의.
- 거래소/Gemini API 키 런타임 `data/users.json` 저장. `USER_SECRET_KEY` 암호화 저장되나 `.env`와 `users.json` 모두 읽을 수 있으면 복호화 가능하므로 파일 권한 엄격 제한.
- **데이터 백업:** `data/users.json` 중요. 정기적 로컬 PC 백업 또는 서버 내 타 경로 복사 권장.
- 공인 IP 변경 시 `ufw` 및 OCI NSG SSH 허용 IP 갱신.
- 임시 퍼블릭 IP 시간 자동 만료 없으나 인스턴스 종료, VNIC/프라이빗 IP 삭제 시 소멸.
