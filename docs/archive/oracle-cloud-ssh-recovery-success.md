# Supabot Oracle Cloud SSH Recovery Success Notes

이 문서는 `supabot-vm-new` 인스턴스의 SSH/직렬 콘솔 복구 과정에서 실제로 성공한 내용만 정리한 기록입니다.

## 대상 인스턴스

- 인스턴스 이름: `supabot-vm-new`
- Region: `ap-chuncheon-1`
- OS: `Canonical Ubuntu 24.04`
- 기본 SSH 사용자: `ubuntu`
- 퍼블릭 IP: `<VM_PUBLIC_IP>`

## Oracle 콘솔에서 확인된 성공 사항

- `OS 관리 > 콘솔 접속 > Cloud Shell 접속 실행` 경로로 직렬 콘솔을 열 수 있음을 확인했습니다.
- `OS 관리 > 콘솔 접속 > 로컬 접속 생성` 경로로 로컬 콘솔 접속 리소스를 생성할 수 있음을 확인했습니다.
- 로컬 콘솔 접속은 `ssh-ed25519` 공개키를 받지 않았고, `ssh-rsa` 공개키로는 정상 생성되었습니다.
- 생성된 로컬 콘솔 접속 리소스는 `활성` 상태가 되었고, 퍼블릭 키 지문이 로컬에서 만든 RSA 키와 일치함을 확인했습니다.
- Oracle 콘솔의 보안 목록에서 SSH 수신 규칙 source를 현재 접속 IP `/32`로 수정할 수 있음을 확인했습니다.
- `80`, `443` 인바운드 규칙이 별도로 열려 있지 않음을 확인했습니다.

## 로컬 콘솔 접속에서 확인된 성공 사항

- Windows OpenSSH로 Oracle Instance Console Connection 1차 터널 연결에 성공했습니다.
- `localhost:22000` 포트 포워딩을 통한 2차 SSH 접속에 성공했습니다.
- 2차 접속 시 `ssh-rsa` 호스트 키 허용 옵션이 필요함을 확인했습니다.
- 로컬 직렬 콘솔에서 다음 로그인 프롬프트를 확인했습니다.

```text
Ubuntu 24.04.4 LTS supabot-vm-new ttyS0
supabot-vm-new login:
```

### PowerShell 두 개로 접속한 실제 절차

아래 절차로 로컬 Windows 환경에서 Oracle 직렬 콘솔에 접속했습니다.

1. RSA 콘솔 접속 키 생성

```powershell
ssh-keygen -t rsa -b 4096 -f C:\path\to\tmp_oracle_console_rsa -N '""'
Get-Content C:\path\to\tmp_oracle_console_rsa.pub
```

2. Oracle 콘솔의 `OS 관리 > 콘솔 접속 > 로컬 접속 생성`에서 위 RSA 공개키를 사용해 콘솔 접속 리소스를 생성

3. PowerShell 창 1개를 열고, Oracle가 제공한 콘솔 접속 문자열을 현재 키 경로에 맞게 수정해 1차 터널 연결

```powershell
ssh -o StrictHostKeyChecking=accept-new -i C:\path\to\tmp_oracle_console_rsa -N -L 22000:<INSTANCE_OCID>:22 -p 443 <CONSOLE_CONNECTION_OCID>@instance-console.ap-chuncheon-1.oci.oraclecloud.com
```

4. 첫 번째 창은 열어둔 채, PowerShell 창 1개를 더 열고 2차 로컬 SSH 접속

```powershell
ssh -o StrictHostKeyChecking=accept-new -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa -i C:\path\to\tmp_oracle_console_rsa -p 22000 <INSTANCE_OCID>@localhost
```

5. 두 번째 창에서 직렬 콘솔 배너와 로그인 프롬프트 확인

```text
Ubuntu 24.04.4 LTS supabot-vm-new ttyS0
supabot-vm-new login:
```

## GRUB/복구 셸에서 확인된 성공 사항

- 부팅 중 UEFI 메뉴(`Boot Manager`)까지 진입할 수 있음을 확인했습니다.
- `grub>` 프롬프트까지 진입할 수 있음을 확인했습니다.
- GRUB 장치 확인 결과:

```text
(proc) (memdisk) (hd0) (hd0,gpt16) (hd0,gpt15) (hd0,gpt14) (hd0,gpt1)
```

- 파티션 구조 확인 결과:
  - `(hd0,gpt1)`: 루트 파일시스템
  - `(hd0,gpt15)`: `efi/`
  - `(hd0,gpt16)`: 커널/부트 파일 보유

- `(hd0,gpt16)`에서 다음 파일들을 확인했습니다.

```text
grub/
vmlinuz
initrd.img
vmlinuz-6.17.0-1011-oracle
vmlinuz-6.17.0-1014-oracle
initrd.img-6.17.0-1011-oracle
initrd.img-6.17.0-1014-oracle
```

- GRUB에서 직접 아래 방식으로 `init=/bin/bash` 셸까지 진입하는 데 성공했습니다.

```text
set root=(hd0,gpt16)
linux /vmlinuz root=/dev/sda1 console=ttyS0 init=/bin/bash
initrd /initrd.img
boot
```

## 인스턴스 내부에서 확인된 성공 사항

- `root@(none):/#` 셸까지 진입했습니다.
- 루트 파일시스템을 쓰기 가능 상태로 다시 마운트할 수 있었습니다.
- `ubuntu` 계정 비밀번호를 재설정했습니다.
- `/usr/sbin/ufw`가 존재하지 않음을 확인했습니다.
- Oracle Cloud Shell의 콘솔 접속 세션에서 일반 사용자 셸 `ubuntu@supabot-vm-new:~$`까지 진입했습니다.
- 인스턴스 내부 네트워크 상태를 확인했습니다.
  - 인터페이스: `ens3`
  - 사설 IP: `<PRIVATE_IP>/24`
  - 기본 게이트웨이: `<GATEWAY_IP>`
- `ssh.service`가 비활성 상태였음을 확인했습니다.

```text
Loaded: loaded (/usr/lib/systemd/system/ssh.service; disabled; preset: enabled)
Active: inactive (dead)
```

- 아래 명령으로 `sshd`를 다시 활성화하고 즉시 기동했습니다.

```bash
sudo systemctl enable --now ssh
```

- 이후 `ssh.service`가 `active (running)` 상태가 되었음을 확인했습니다.

```text
Loaded: loaded (/usr/lib/systemd/system/ssh.service; enabled; preset: enabled)
Active: active (running)
```

- `sshd`가 실제로 `0.0.0.0:22`와 `[::]:22`에서 리슨 중임을 확인했습니다.

```text
LISTEN 0 4096 0.0.0.0:22 0.0.0.0:*
LISTEN 0 4096 [::]:22    [::]:*
```

- `iptables`/`nftables` 규칙에서 `22/tcp` 허용 규칙이 존재함을 확인했습니다.
- 인스턴스 내부에서 공인 IP `<VM_PUBLIC_IP>:22`로 TCP 접속 테스트가 성공했습니다.

```bash
nc -vz <VM_PUBLIC_IP> 22
```

```text
Connection to <VM_PUBLIC_IP> 22 port [tcp/ssh] succeeded!
```

- 따라서 인스턴스 내부 기준으로는 공인 IP와 `sshd`가 모두 정상 동작함을 확인했습니다.
- 외부 로컬 PC에서는 여전히 `<VM_PUBLIC_IP>:22`가 타임아웃임을 확인했습니다. 즉, 복구 시점 기준 병목은 인스턴스 내부가 아니라 외부 접속 경로에 남아 있습니다.

## 현재 서버 초기 상태

- 홈 디렉터리 기준 현재 작업 경로는 `/home/ubuntu`입니다.
- `~/supabot` 디렉터리는 아직 존재하지 않습니다.
- `git`은 설치되어 있습니다.

```text
git version 2.43.0
```

- `docker`와 `docker compose`는 아직 설치되어 있지 않습니다.

```text
Command 'docker' not found
```

## 배포 및 컨테이너 기동 성공 사항

- `scripts/setup_oracle_vm.sh`를 실행해 아래 항목을 한 번에 구성했습니다.
  - 기본 패키지 설치
  - 타임존 `Asia/Seoul` 설정
  - 2GB 스왑 생성
  - `ufw` 설치 및 활성화
  - `fail2ban` 설치 및 활성화
  - Docker / Docker Compose 설치
  - `~/supabot/config/.env` 템플릿 생성

- 스크립트 실행 후 `ufw`의 SSH 허용 규칙이 아래처럼 반영됨을 확인했습니다.

```text
22/tcp  ALLOW IN  <YOUR_IP>
```

- 로컬에서 수정한 `docker-compose.yml`의 `build: .` 구성을 서버에도 반영했습니다.
- `docker compose up -d --build`로 이미지를 로컬에서 직접 빌드하고 컨테이너를 기동했습니다.
- `docker compose ps` 기준으로 `supabot` 컨테이너가 실행 중임을 확인했습니다.

```text
NAME      IMAGE                              COMMAND                SERVICE   STATUS
supabot   ghcr.io/antny-bot/supabot:latest   "python src/main.py"   supabot   Up
```

- `docker compose logs -f --tail=100` 기준으로 봇이 정상 기동함을 확인했습니다.

```text
⚙️ 초기 관리자 등록 중...
🚀 SUTT-Bot V2 가동 중...
🛠️ 시스템 자동 복구 프로세스 가동...
📦 오더 동기화 루프 가동
📡 시그널 분석 루프 가동
```

## 잘못 만든 `lastest` 이미지 정리

배포 중 `docker-compose.yml`의 `image:` 태그를 실수로 `lastest`로 작성한 적이 있었습니다. 이후 `latest`로 수정하고 재빌드한 뒤, 잘못 만든 태그 이미지를 정리했습니다.

### 1. 현재 컨테이너가 올바른 이미지 태그(`latest`)를 사용하는지 확인

```bash
docker compose ps
docker images | grep supabot
```

### 2. 잘못 만든 이미지 태그 삭제

```bash
docker rmi ghcr.io/antny-bot/supabot:lastest
```

### 3. 삭제 후 남은 이미지 확인

```bash
docker images | grep supabot
```

삭제 후 최종적으로 `ghcr.io/antny-bot/supabot:latest`만 남은 상태를 확인했습니다.

## Oracle VM cron 자동배포 설정

현재 Oracle VM은 GHCR pull 기반 자동배포 대신, 서버 내부에서 직접 소스를 갱신하고 다시 빌드하는 cron 기반 자동배포를 사용하도록 설정했습니다.

### 배포 스크립트

배포 스크립트 경로:

```text
/home/ubuntu/supabot/scripts/deploy.sh
```

배포 스크립트 내용:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu/supabot

git pull --ff-only
docker compose up -d --build
docker image prune -f
```

이 방식은 아래 데이터를 유지합니다.

- `/home/ubuntu/supabot/config/.env`
- `/home/ubuntu/supabot/data/`

즉 컨테이너가 새로 교체되더라도 Telegram 토큰, 관리자 ID, 런타임 데이터는 유지됩니다.

### cron 등록 내용

등록된 crontab:

```cron
0 4 * * * /home/ubuntu/supabot/scripts/deploy.sh >> /home/ubuntu/supabot/data/deploy-cron.log 2>&1
```

의미:

- 매일 새벽 4시
- 서버에서 최신 코드를 가져오고
- Docker 이미지를 다시 빌드한 뒤
- 컨테이너를 재기동함

### 로그 확인

자동배포 로그 확인:

```bash
tail -n 100 /home/ubuntu/supabot/data/deploy-cron.log
```

## 복구에 사용한 공개키 정보

### 기존 인스턴스 SSH 키

```text
<YOUR_SSH_PUBLIC_KEY>
```

### 로컬 콘솔 접속 생성용 RSA 공개키

```text
<YOUR_SSH_PUBLIC_KEY>
```

## 트러블슈팅

### 1. 매니저(supabot-manager)와 봇(supabot) 간의 ConnectTimeoutError (8765 포트 통신 실패)

* **증상**: 매니저 대시보드 웹 UI에서 전략 템플릿의 **[가동]** 버튼 클릭 시, `봇 주문 가동 실패: Connection to 168.110.116.238 timed out` 과 같은 연결 시간 초과 에러가 발생함.
* **원인**: 봇 서버 내부의 Linux OS 방화벽(`ufw`) 또는 오라클 클라우드 VCN 수신 규칙(Ingress Rules)에서 봇 백엔드 통신용 포트(`8765/tcp`)가 허용되어 있지 않아 발생함.
* **해결 방법**:
  1. **봇 서버 OS 내부 방화벽 포트 허용**: VM 인스턴스에 SSH로 접속하여 UFW 방화벽에 8765 포트를 허용합니다.
     ```bash
     sudo ufw allow 8765/tcp
     ```
  2. **Oracle Cloud VCN 보안 규칙 추가**: Oracle Cloud 대시보드 ➡️ VCN ➡️ Security Lists(보안 목록)의 **수신 규칙(Ingress Rules)**에 다음 규칙을 추가합니다.
     * **소스 CIDR**: 매니저 서버의 공인 IP (보안을 위해 특정 IP 지정 권장)
     * **IP 프로토콜**: `TCP`
     * **대상 포트 범위**: `8765`

## 참고

- 배포/인수인계 기준 문서: [oracle-cloud-handoff.md](oracle-cloud-handoff.md)
- VM 설정 문서: [oracle-cloud-vm-setup.md](oracle-cloud-vm-setup.md)

