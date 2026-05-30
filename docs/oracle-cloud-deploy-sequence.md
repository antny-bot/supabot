# Supabot Oracle Cloud 배포 순서

이 문서는 Oracle Cloud VM에 Supabot을 실제로 올릴 때의 순서를 짧게 정리한 실행 가이드입니다.

관련 초기 설정 문서는 [oracle-cloud-vm-setup.md](E:\apps\supabot\docs\oracle-cloud-vm-setup.md) 를 참고하세요.

## 1. Oracle 콘솔에서 인스턴스 생성 및 확인

먼저 Oracle Cloud 콘솔에서 Supabot용 VM을 생성합니다.

권장 기준:

- Shape: `VM.Standard.E2.1.Micro`
- OS Image: `Canonical Ubuntu 24.04`
- 사용자명: `ubuntu`
- VCN / 서브넷: public subnet 기준
- Public IP: 가능하면 생성 시 활성화

생성 직후 확인할 항목:

- 인스턴스 상태가 `실행 중`인지
- 인스턴스 상세의 기본 사용자명이 `ubuntu`인지
- 공인 IP가 실제로 붙어 있는지

`Public IP`가 생성 위저드에서 비활성화되거나, 검토 화면에서는 켰는데 생성 후 빠져 있는 경우가 있습니다. 이 경우에도 정상적으로 진행할 수 있습니다.

공인 IP 사후 할당 순서:

1. 인스턴스 상세로 이동
2. `네트워킹` 탭 선택
3. 연결된 VNIC 열기
4. `IP 관리` 탭 이동
5. 기본 프라이빗 IP 행의 `작업 > 편집`
6. `퍼블릭 IP 유형`에서 `임시 퍼블릭 IP` 선택
7. `업데이트`

보안 기준도 같이 확인하세요.

- `22/tcp`는 현재 접속 중인 본인 공인 IP `/32`만 허용
- webhook이나 reverse proxy 계획이 없으면 `80`, `443`은 열지 않음
- NSG 또는 보안 목록이 너무 넓게 열려 있지 않은지 확인

## 2. SSH 접속

먼저 VM에 SSH로 접속합니다.

```bash
ssh ubuntu@<public-ip>
```

이 문서 기준 기본 사용자는 `ubuntu`입니다. 다른 이미지를 썼다면 해당 이미지의 기본 계정을 확인하세요.

## 3. 서버에 레포 올리기

가장 단순한 방법은 Git으로 레포를 가져오는 방식입니다.

```bash
cd ~
git clone <레포주소> supabot
cd ~/supabot
```

이미 서버에 디렉터리가 있다면 `git pull` 또는 필요한 방식으로 최신 소스를 반영하세요.

## 4. 초기 설정 스크립트 실행

서버에 올라온 소스 코드 내의 초기 설정 스크립트를 실행합니다.

```bash
cd ~/supabot
MY_PUBLIC_IP=본인공인IP bash scripts/setup_oracle_vm.sh
```

예시:

```bash
MY_PUBLIC_IP=203.0.113.10 bash scripts/setup_oracle_vm.sh
```

이 스크립트는 아래 항목을 설정합니다.

- swap 생성
- `ufw` 방화벽 설정
- `fail2ban` 활성화
- SSH 보안 설정
- Docker 설치
- `~/supabot/config`, `~/supabot/data` 디렉터리 생성
- `.env` 템플릿 생성

## 5. 새 SSH 세션으로 재접속 확인

스크립트 실행 후에는 현재 세션을 바로 끊지 말고, 새 터미널에서 한 번 더 접속해 보세요.

확인할 항목:
- SSH 키 로그인으로 정상 접속되는지
- `ufw` 적용 후에도 본인 IP에서 접속이 막히지 않는지

이 확인이 끝나기 전에는 기존 세션을 닫지 않는 편이 안전합니다.

## 6. `.env` 작성

환경변수 파일을 작성합니다.

```bash
nano ~/supabot/config/.env
```

예시:

```env
TELEGRAM_BOT_TOKEN=...
ADMIN_CHAT_ID=...
USER_SECRET_KEY=...
```

`USER_SECRET_KEY`는 사용자별 거래소/Gemini 키를 `data/users.json`에 암호화 저장하기 위한 Fernet 마스터키입니다. VM의 `config/.env`에만 보관하고 GitHub에 올리지 않습니다.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Fernet 형식이 아닌 임의 문자열을 넣으면 새 API 키 저장이 실패합니다. 이미 `enc:v1:`로 암호화된 `users.json`은 암호화할 때 사용한 같은 `USER_SECRET_KEY`가 있어야 복호화됩니다. 키가 다르면 봇은 기동되지만 `/whomai`에 `보안 키: 복호화 오류`가 표시되고 거래소/Gemini 키는 사용할 수 없습니다.

파일 권한도 제한합니다.

```bash
chmod 600 ~/supabot/config/.env
```

## 7. `docker-compose.yml` 확인

이 레포의 [docker-compose.yml](E:\apps\supabot\docker-compose.yml) 기준으로 배포할 수 있습니다.

현재 기본 설정은 다음 방향입니다.

- 서비스명: `supabot`
- 컨테이너명: `supabot`
- 재시작 정책: `unless-stopped`
- `config/.env`는 읽기 전용 마운트
- `data` 디렉터리는 영속 볼륨으로 사용

이미지 주소 `ghcr.io/antny-bot/supabot:latest` 가 실제로 pull 가능한지는 배포 전에 확인하세요.

## 8. 컨테이너 실행

레지스트리 이미지를 pull 해서 실행하는 경우:

```bash
cd ~/supabot

# 레포지토리가 Private인 경우 로그인 필요
# echo $CR_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

docker compose pull
docker compose up -d
docker compose ps
```

## 9. 로그 확인

기동 직후 로그를 확인합니다.

```bash
docker compose logs -f --tail=100
```

확인할 항목:
- 컨테이너가 바로 종료되지 않고 계속 유지되는지
- 환경변수 누락 오류가 없는지
- 파일 권한 오류가 없는지

## 10. Telegram 동작 확인

실제 Telegram에서 아래를 확인합니다.

- `/start` 명령이 정상 응답하는지
- `ADMIN_CHAT_ID` 계정이 초기 관리자 처리되는지
- `data/users.json` 이 생성되는지

## 11. 이미지 pull 이 안 되는 경우

레지스트리 이미지 대신 VM에서 직접 빌드할 수 있습니다.

`docker-compose.yml`에서 `image:` 대신 `build: .` 구성을 사용하세요.

실행 예시:

```bash
cd ~/supabot
docker compose up -d --build
```

## 12. 배포 직후 운영 점검

배포 후에는 아래를 바로 확인하세요.

- Oracle 콘솔에서 인스턴스 상태가 계속 `실행 중`인지
- 인스턴스 액세스 항목에 공인 IP가 실제로 붙어 있는지
- Oracle NSG에서 `22/tcp` source가 본인 IP로 제한되어 있는지
- NSG 또는 보안 목록에서 `80`, `443`이 불필요하게 열려 있지 않은지
- OCI boot volume backup 이 켜져 있는지
- `docker compose logs` 에 반복 에러가 없는지
- `data/users.json` 권한이 과도하게 열려 있지 않은지

## 13. 주의사항

- 이 봇은 실거래 경로를 포함하므로, 테스트 중에도 실주문이 나가지 않게 특히 주의해야 합니다.
- 거래소/Gemini API 키는 런타임에 `data/users.json`에 저장됩니다. `USER_SECRET_KEY`가 설정되어 있으면 암호화 저장되지만, `.env`와 `users.json`을 모두 읽을 수 있으면 복호화할 수 있으므로 파일 접근 권한을 엄격히 제한해야 합니다.
- **데이터 백업:** `data/users.json`은 봇 운영에 가장 중요한 파일입니다. 정기적으로 로컬 PC에 백업하거나, 서버 내 다른 경로로 복사해두는 것을 권장합니다.
- 공인 IP가 바뀌면 `ufw` 및 OCI NSG의 SSH 허용 IP도 같이 갱신해야 합니다.
- 임시 퍼블릭 IP는 시간 기준으로 자동 만료되지는 않지만, 인스턴스 종료나 VNIC/프라이빗 IP 삭제 시 함께 사라질 수 있습니다.
