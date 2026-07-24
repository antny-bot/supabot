# Supabot용 Oracle Cloud VM 설정 가이드

Oracle Cloud VM 1대에 Docker + Supabot 올리고 Telegram long polling 운영하는 구성 기준.

## 1. OCI 콘솔 체크리스트

배포 전 Oracle Cloud 콘솔 확인 항목:

### 인스턴스
- Shape: `VM.Standard.E2.1.Micro`
- OS Image: `Canonical Ubuntu 24.04`
- Public IP: 가능하면 생성 시 활성화, 안 되면 생성 후 VNIC에서 할당
- Boot volume backup policy: 활성화
- SSH key login: 활성화
- Password login: 의존하지 않는 편이 안전

### VCN / 서브넷
- SSH 접속용 public subnet 연결.
- VM 전용 `NSG` 사용 권장.
- `Public IP` 비활성화 시 서브넷 public 여부 확인.
- `새 가상 클라우드 네트워크 생성` + `새 퍼블릭 서브넷 생성` 선택 후 `자동으로 퍼블릭 IPv4 주소 지정` 선택.

### NSG 인바운드 규칙
- `TCP 22`만 허용, source는 본인 공인 IP 또는 집/회사 CIDR 제한.
- webhook/reverse proxy 미사용 시 `80`, `443` 차단.
- manager → bot 알림 채널 사용 시 `TCP 8765` 추가 필요.

### manager → bot notify 채널 (TCP 8765)
- Synology manager가 bot `/internal/notify` (포트 `8765`, `INTERNAL_PORT`) 호출.
- NSG/보안 목록 인바운드 추가:
  - 프로토콜: `TCP`
  - 출발지: Synology 공인 IP `/32`
  - 목적지 포트: `8765` (또는 `INTERNAL_PORT`)
- `MANAGER_API_KEY` 설정 시 `X-API-Key` 헤더 검증 (보안 강화).
- `docker-compose.yml` `network_mode: host` 사용으로 호스트 `8765` 노출. UFW 사용 시 Synology IP `/32` → `8765` 허용 규칙 작성.

### NSG 아웃바운드 규칙
- Telegram 및 거래소 API용 HTTPS 아웃바운드 허용.

### Security List 경로 (NSG 대신 전통적 UI를 쓰는 경우)
서브넷 Default Security List 직접 제어 시:

1. VNIC 공인 IP 확인.
2. 서브넷(`subnet-...`) 링크 이동.
3. 서브넷 상세 → `Security Lists` → `Default Security List for ...` 이동.
4. **Ingress Rules**: 포트 `22` 소스 CIDR을 `0.0.0.0/0` 대신 PC 공인 IP (`내 아이피` 검색 → `/32`, 예: `123.45.67.89/32`)로 제한.
5. **Egress Rules**: `0.0.0.0/0`, `All Protocols` 허용 확인.

### Oracle 측 백업
- Boot volume backup policy 활성화.
- 부트 디스크 외 저장 데이터는 별도 백업.

참고 문서:
- OCI Network Security Groups: <https://docs.oracle.com/iaas/Content/Network/Concepts/networksecuritygroups.htm>
- OCI Security Lists: <https://docs.oracle.com/iaas/Content/Network/Concepts/securitylists.htm>
- OCI Boot Volume Backups: <https://docs.oracle.com/iaas/Content/Block/Concepts/bootvolumebackups.htm>

## 2. VM 초기 설정

### SSH 접속
준비물: VM 공인 IP + SSH Private Key (`.key`/`.pem`).

```bash
ssh -i /path/to/your/private-key.key ubuntu@<VM_PUBLIC_IP>
```

`Are you sure you want to continue connecting (yes/no/[fingerprint])?` 프롬프트 시 `yes` 입력.
`ubuntu@...:~$` 확인.

### 이번 프로젝트에서 실제로 확인한 OCI 생성값

확인된 OCI 설정 조합:

- 인스턴스 이름: `supabot-vm-new`
- Shape: `VM.Standard.E2.1.Micro`
- OS Image: `Canonical Ubuntu 24.04`
- 사용자명: `ubuntu`
- VCN: `supabot-vcn`
- 서브넷: `supabot-public-subnet`
- 서브넷 CIDR: `10.0.0.0/24`
- SSH 키: 퍼블릭 키 직접 입력 사용 가능

주의:

- `새 퍼블릭 서브넷 생성` 선택 후에도 `퍼블릭 IPv4 주소` `아니오`로 남는 현상 발생 가능.
- 생성 후 `연결된 VNIC > IP 관리 > 편집 > 임시 퍼블릭 IP`로 수동 할당 가능.

### Public IP 비활성화 문제 해결

`Public IP` 비활성화 원인: 서브넷 선택 오류.

해결 절차:

1. `기본 네트워크`에서 `새 가상 클라우드 네트워크 생성` 또는 VCN 선택.
2. `서브넷`에서 `새 퍼블릭 서브넷 생성` 또는 public subnet 선택.
3. `퍼블릭 IPv4 주소 지정`에서 `자동으로 퍼블릭 IPv4 주소 지정` 선택.

우회 방법:

1. 인스턴스 생성.
2. 인스턴스 상세 → `네트워킹` 탭 VNIC 선택.
3. `IP 관리` 탭 이동.
4. 프라이빗 IP 행 `작업 > 편집` 클릭.
5. `퍼블릭 IP 유형` → `임시 퍼블릭 IP` 선택.
6. `업데이트` 클릭.

실제 확인 기준:

- 생성 후 공인 IP 수동 할당 가능.
- 임시 퍼블릭 IP 할당 정상 동작.

스크립트 일괄 실행: [scripts/setup_oracle_vm.sh](E:\apps\supabot\scripts\setup_oracle_vm.sh)

예시:

```bash
MY_PUBLIC_IP=203.0.113.10 bash scripts/setup_oracle_vm.sh
```

옵션 환경변수:
- `APP_DIR`: 기본값 `~/supabot`
- `SWAP_SIZE_GB`: 기본값 `2`
- `ENABLE_UFW`: 기본값 `true`
- `ENABLE_FAIL2BAN`: 기본값 `true`

### 기본 패키지 설치

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg ufw fail2ban

# 호스트 OS 타임존 설정 (한국 시간)
sudo timedatectl set-timezone Asia/Seoul
```

### Micro shape용 스왑 생성

`VM.Standard.E2.1.Micro` 메모리 부족 방지용 스왑 2G 생성.

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

### 기본 방화벽 설정

`YOUR_PUBLIC_IP`는 접속 PC 공인 IP (`34.64.82.68`인 경우 `34.64.82.68/32` 허용).

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from YOUR_PUBLIC_IP to any port 22 proto tcp
sudo ufw enable
sudo ufw status verbose
```

### SSH 보안 강화

`/etc/ssh/sshd_config` 설정 확인:

```text
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
```

SSH 재설정 적용:

```bash
sudo systemctl reload ssh
```

### Docker 설치

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

`docker` 그룹 적용 위해 재접속 필요.

### 앱 디렉터리 준비

```bash
mkdir -p ~/supabot/config ~/supabot/data
chmod 700 ~/supabot/config ~/supabot/data
```

`~/supabot/config/.env` 파일 생성:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
ADMIN_CHAT_ID=your_admin_chat_id
USER_SECRET_KEY=your_fernet_master_key
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_supabase_service_key
# 선택 (manager → bot notify 채널용)
MANAGER_API_KEY=your_manager_api_key
INTERNAL_PORT=8765
```

`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`: bot/manager 공유 Supabase Postgres 접속 정보.
`MANAGER_API_KEY`: manager의 bot `/internal/notify` 호출시 `X-API-Key` 헤더 검증 키.
`INTERNAL_PORT`: 엔드포인트 포트 (`8765`).

`USER_SECRET_KEY`: `data/users.json` 암호화 마스터키. 비밀 유지 필수.

생성 명령:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Fernet 미준수시 키 저장 실패. 기존 `data/users.json` 복호화에 동일 `USER_SECRET_KEY` 필요 (불일치 시 `/whoami`에 `보안 키: 복호화 오류` 표시, API 키 사용 불가).

파일 권한 설정:

```bash
chmod 600 ~/supabot/config/.env
```

## 3. 이 레포용 Docker Compose

`docker-compose.yml` 기본 파일:

```yaml
version: "3.8"

services:
  supabot:
    image: ghcr.io/antny-bot/supabot:latest
    container_name: supabot
    restart: unless-stopped
    environment:
      TZ: Asia/Seoul
    volumes:
      - ./config/.env:/app/config/.env:ro
      - ./data:/app/data
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

소스 빌드용 파일:

```yaml
version: "3.8"

services:
  supabot:
    build: .
    container_name: supabot
    restart: unless-stopped
    environment:
      TZ: Asia/Seoul
    volumes:
      - ./config/.env:/app/config/.env:ro
      - ./data:/app/data
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

## 4. 배포 및 확인

```bash
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f --tail=100
```

확인 항목:
- `docker compose up -d` 실행 후 컨테이너 유지 여부
- Telegram `/start` 정상 동작 여부
- `data/users.json` 생성 및 권한 제한 유지 여부
- Oracle 콘솔 인스턴스 `사용자 이름` `ubuntu` 확인
- 인스턴스 공인 IP 할당 확인

## 5. Oracle 콘솔 후처리 체크리스트

인스턴스 생성 후 Oracle 콘솔 확인:

1. 인스턴스 `실행 중` 상태 확인
2. `네트워킹` 탭 공인 IP 확인
3. 공인 IP 미할당 시 `연결된 VNIC > IP 관리 > 편집 > 임시 퍼블릭 IP` 할당
4. 서브넷 보안 목록/NSG `22/tcp` PC 공인 IP `/32` 제한
5. `80`, `443` 미사용 시 차단 유지
6. Boot volume backup policy 활성화 확인

## 6. 운영 시 주의사항

- `data/users.json` 키 저장: `USER_SECRET_KEY` 설정 시 `enc:v1:` 암호화. `.env` 및 `users.json` 보안 권한 철저 관리.
- 자동화 테스트: 실거래 엔드포인트 호출 금지 (mock 전용).
- 인바운드 포트 최소화 및 IP 변경 시 SSH 허용 IP 갱신.
