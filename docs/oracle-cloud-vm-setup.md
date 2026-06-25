# Supabot용 Oracle Cloud VM 설정 가이드

이 문서는 Oracle Cloud VM 한 대에 Docker와 Supabot을 올리고, Telegram long polling 방식으로 운영하는 구성을 기준으로 합니다.

## 1. OCI 콘솔 체크리스트

배포 전에 Oracle Cloud 콘솔에서 아래 항목을 먼저 확인하세요.

### 인스턴스
- Shape: `VM.Standard.E2.1.Micro`
- OS Image: `Canonical Ubuntu 24.04`
- Public IP: 가능하면 생성 시 활성화, 안 되면 생성 후 VNIC에서 할당
- Boot volume backup policy: 활성화
- SSH key login: 활성화
- Password login: 의존하지 않는 편이 안전

### VCN / 서브넷
- SSH로 직접 붙을 계획이면 public subnet에 연결합니다.
- 서브넷 전체 규칙보다, 이 VM 전용 `NSG`를 따로 두는 편이 안전합니다.
- Oracle 생성 위저드에서 `Public IP`가 비활성화되면, 대부분 현재 선택한 서브넷이 public subnet이 아닌 상태입니다.
- 생성 위저드에서 `새 가상 클라우드 네트워크 생성` + `새 퍼블릭 서브넷 생성` 조합을 먼저 맞춘 뒤 `자동으로 퍼블릭 IPv4 주소 지정`을 선택하세요.

### NSG 인바운드 규칙
- `TCP 22`만 열고, 출발지(source)는 본인 공인 IP 또는 집/회사 CIDR로 제한합니다.
- 나중에 webhook이나 reverse proxy를 추가하지 않는 이상 `80`, `443`은 열지 마세요.
- Supabot bot 자체는 거래 API용 인바운드 포트가 필요 없습니다. 다만 manager → bot 알림 채널을 쓰는 경우 아래 `TCP 8765` 규칙이 추가로 필요합니다.

### manager → bot notify 채널 (TCP 8765)
- Synology에서 운영하는 manager가 bot의 `/internal/notify` 엔드포인트(기본 포트 `8765`, 환경변수 `INTERNAL_PORT`)를 호출합니다.
- 따라서 보안 목록 또는 NSG에 인바운드 규칙을 하나 더 추가합니다.
  - 프로토콜: `TCP`
  - 출발지(source): Synology의 공인 IP `/32`만 허용
  - 목적지 포트: `8765` (또는 `INTERNAL_PORT`로 바꾼 값)
- 추가 방어선으로 `MANAGER_API_KEY`를 설정하면 manager 요청이 `X-API-Key` 헤더로 검증됩니다. 보안 목록 IP 제한과 함께 두 겹으로 보호하는 것을 권장합니다.
- `docker-compose.yml`이 `network_mode: host`로 동작하므로 컨테이너 포트 매핑 없이 호스트의 `8765`가 바로 노출됩니다. UFW를 쓰는 경우 호스트 방화벽에도 Synology IP `/32` → `8765` 허용 규칙이 필요합니다.

### NSG 아웃바운드 규칙
- Telegram 및 거래소 API로 나갈 수 있도록 HTTPS 아웃바운드는 허용합니다.

### Security List 경로 (NSG 대신 전통적 UI를 쓰는 경우)
NSG 대신 서브넷의 기본 Security List에서 직접 제어하려면:

1. 인스턴스의 기본 VNIC에서 공인 IP를 확인합니다.
2. 같은 네트워킹 화면에서 서브넷(`subnet-...`) 링크로 이동합니다.
3. 서브넷 상세 → 리소스 영역 → `Security Lists` → `Default Security List for ...`로 들어갑니다.
4. **Ingress Rules**: 대상 포트 `22` 규칙을 편집해 소스 CIDR을 `0.0.0.0/0` 대신 **현재 작업 중인 PC의 공인 IP**로 제한합니다
   (`내 아이피` 검색 → `/32` 부여, 예: `123.45.67.89/32`. **VM의 IP가 아니라 접속하는 PC의 IP**임에 주의).
5. **Egress Rules**: 대상 `0.0.0.0/0`, `All Protocols` 허용 상태인지 확인합니다 (텔레그램/거래소 API 아웃바운드용 — 기본값이 보통 이미 허용).

### Oracle 측 백업
- Boot volume backup policy를 켭니다.
- 나중에 부트 디스크 밖에 중요한 데이터를 저장하면 그 저장소는 별도로 백업해야 합니다.

참고 문서:
- OCI Network Security Groups: <https://docs.oracle.com/iaas/Content/Network/Concepts/networksecuritygroups.htm>
- OCI Security Lists: <https://docs.oracle.com/iaas/Content/Network/Concepts/securitylists.htm>
- OCI Boot Volume Backups: <https://docs.oracle.com/iaas/Content/Block/Concepts/bootvolumebackups.htm>

## 2. VM 초기 설정

### SSH 접속
준비물: 위에서 확인한 VM 공인 IP + 생성 시 받은 SSH Private Key (`.key`/`.pem`).

```bash
ssh -i /path/to/your/private-key.key ubuntu@<VM_PUBLIC_IP>
```

처음 접속 시 `Are you sure you want to continue connecting (yes/no/[fingerprint])?` 프롬프트가 나오면 `yes`를 입력합니다.
정상 접속되면 `ubuntu@...:~$` 프롬프트가 표시되며, 이후 아래 단계로 진행합니다.

### 이번 프로젝트에서 실제로 확인한 OCI 생성값

실제 생성 과정에서 아래 조합으로 동작을 확인했습니다.

- 인스턴스 이름: `supabot-vm-new`
- Shape: `VM.Standard.E2.1.Micro`
- OS Image: `Canonical Ubuntu 24.04`
- 사용자명: `ubuntu`
- VCN: `supabot-vcn`
- 서브넷: `supabot-public-subnet`
- 서브넷 CIDR: `10.0.0.0/24`
- SSH 키: 자동 생성 대신 퍼블릭 키 붙여넣기 방식도 정상 동작

주의:

- Oracle 위저드에서 `새 퍼블릭 서브넷 생성`을 골라도, 실제 검토 화면에서 `퍼블릭 IPv4 주소`가 `아니오`로 남는 경우가 있었습니다.
- 이 경우 생성 자체를 막을 필요는 없고, 인스턴스 생성 후 `연결된 VNIC > IP 관리 > 편집 > 임시 퍼블릭 IP`로 공인 IP를 사후 할당할 수 있습니다.

### Public IP 비활성화 문제 해결

Oracle Cloud 생성 화면에서 `Public IP`가 회색으로 비활성화되는 가장 흔한 원인은 서브넷 선택입니다.

확인 순서:

1. `기본 네트워크`에서 `새 가상 클라우드 네트워크 생성` 또는 public subnet이 붙은 기존 VCN을 선택합니다.
2. `서브넷`에서 `새 퍼블릭 서브넷 생성` 또는 기존 public subnet을 선택합니다.
3. 그다음 `퍼블릭 IPv4 주소 지정`에서 `자동으로 퍼블릭 IPv4 주소 지정`을 선택합니다.

계속 비활성화되면 아래 순서로 우회하는 편이 더 안정적입니다.

1. 우선 인스턴스를 생성합니다.
2. 인스턴스 상세 화면으로 이동합니다.
3. `네트워킹` 탭에서 연결된 VNIC를 엽니다.
4. `IP 관리` 탭으로 이동합니다.
5. 기본 프라이빗 IP 행의 `작업 > 편집`을 누릅니다.
6. `퍼블릭 IP 유형`에서 `임시 퍼블릭 IP`를 선택합니다.
7. `업데이트`를 눌러 반영합니다.

실제 확인 기준:

- 공인 IP는 생성 후에도 정상적으로 붙일 수 있었습니다.
- 이 프로젝트에서 실제로 확인한 예시처럼 임시 퍼블릭 IP가 할당되는 방식이었습니다.

아래 명령은 Ubuntu 기준입니다. SSH 접속 후 순서대로 실행하면 됩니다.

스크립트로 한 번에 진행하려면 레포의 [scripts/setup_oracle_vm.sh](E:\apps\supabot\scripts\setup_oracle_vm.sh) 를 사용할 수 있습니다.

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

`VM.Standard.E2.1.Micro`는 메모리가 작아서 스왑을 잡아두는 편이 안정적입니다.

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

### 기본 방화벽 설정

`YOUR_PUBLIC_IP`는 현재 접속 중인 본인 공인 IP로 바꿔 넣으세요.

예를 들어 Oracle 생성 직후 접속에 사용했던 공인 IP가 `34.64.82.68`이었다면 `34.64.82.68/32`만 SSH에 허용하는 식으로 최소화하세요.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from YOUR_PUBLIC_IP to any port 22 proto tcp
sudo ufw enable
sudo ufw status verbose
```

### SSH 보안 강화

`/etc/ssh/sshd_config`를 열어서 아래 값이 적용되어 있는지 확인하세요.

```text
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
```

적용 후 SSH를 다시 읽게 합니다.

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

`docker` 그룹 반영을 위해 한 번 로그아웃 후 다시 접속하세요.

### 앱 디렉터리 준비

```bash
mkdir -p ~/supabot/config ~/supabot/data
chmod 700 ~/supabot/config ~/supabot/data
```

`~/supabot/config/.env` 파일을 만듭니다.

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

`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`는 bot/manager가 공유하는 Supabase Postgres 접속용 값입니다. `MANAGER_API_KEY`는 manager가 bot의 `/internal/notify`를 호출할 때 `X-API-Key` 헤더로 검증되는 키이고, `INTERNAL_PORT`는 해당 엔드포인트 포트(기본 `8765`)입니다.

`USER_SECRET_KEY`는 `data/users.json`에 저장되는 사용자별 거래소/Gemini 키를 암호화하는 마스터키입니다. 다음 명령으로 생성할 수 있으며, GitHub나 채팅에 공유하지 마세요.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Fernet 형식이 아닌 임의 문자열을 넣으면 새 API 키 저장이 실패합니다. 이미 암호화된 `data/users.json`은 암호화할 때 사용한 같은 `USER_SECRET_KEY`가 필요합니다. 키가 다르면 봇은 기동되지만 `/whoami`에 `보안 키: 복호화 오류`가 표시되고 거래소/Gemini 키는 사용할 수 없습니다.

파일 권한도 제한하세요.

```bash
chmod 600 ~/supabot/config/.env
```

## 3. 이 레포용 Docker Compose

레포의 `docker-compose.yml`을 그대로 써도 되고, VM에서 아래와 같은 동등한 파일을 써도 됩니다.

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

레지스트리 이미지를 pull 하지 않고, VM에서 직접 소스 빌드할 계획이면 아래 변형을 사용하면 됩니다.

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

확인할 항목:
- `docker compose up -d` 후 컨테이너가 바로 죽지 않고 유지되는지
- Telegram에서 `/start`가 정상 동작하는지
- `data/users.json`이 생성되고, 소유자 외에는 읽기 어렵게 권한이 유지되는지
- Oracle 콘솔의 인스턴스 상세에서 `사용자 이름`이 `ubuntu`로 표시되는지
- 인스턴스 액세스 항목에 공인 IP가 실제로 붙어 있는지

## 5. Oracle 콘솔 후처리 체크리스트

인스턴스 생성 직후 Oracle 콘솔에서 아래를 다시 확인하세요.

1. 인스턴스가 `실행 중`인지 확인
2. `네트워킹` 탭에서 공인 IP가 붙어 있는지 확인
3. 공인 IP가 없으면 `연결된 VNIC > IP 관리 > 편집 > 임시 퍼블릭 IP`로 할당
4. 서브넷 보안 목록 또는 NSG에서 `22/tcp`만 본인 공인 IP `/32`로 제한
5. `80`, `443`은 reverse proxy나 webhook 계획이 없으면 열지 않음
6. Boot volume backup policy가 켜져 있는지 확인

## 6. 운영 시 주의사항

- Supabot은 현재 실행 중 `data/users.json`에 사용자별 거래소/Gemini 키를 저장합니다. `USER_SECRET_KEY`가 설정되어 있으면 `enc:v1:` 형식으로 암호화 저장되지만, `.env`와 `users.json`을 모두 읽을 수 있으면 복호화할 수 있으므로 파일 권한을 엄격히 제한하세요.
- 자동화 테스트는 실거래 주문 엔드포인트를 호출하지 않도록 반드시 mock 기반으로 돌리세요.
- 실거래 봇이므로 인바운드 포트는 최소화하고, 공인 IP가 바뀌면 SSH 허용 IP도 같이 갱신하세요.
