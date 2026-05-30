#!/usr/bin/env bash
set -euo pipefail

# Supabot용 Oracle Cloud Ubuntu 초기 설정 스크립트
# 주의:
# - Ubuntu VM 기준입니다.
# - 실수 방지를 위해 MY_PUBLIC_IP를 직접 지정해야 실행됩니다.
# - SSH 설정을 바꾸므로, 실행 전 현재 접속에 사용 중인 공개키가 서버에 등록되어 있어야 합니다.

MY_PUBLIC_IP="${MY_PUBLIC_IP:-}"
APP_DIR="${APP_DIR:-$HOME/supabot}"
SWAP_SIZE_GB="${SWAP_SIZE_GB:-2}"
ENABLE_UFW="${ENABLE_UFW:-true}"
ENABLE_FAIL2BAN="${ENABLE_FAIL2BAN:-true}"

if [[ -z "$MY_PUBLIC_IP" ]]; then
  echo "오류: MY_PUBLIC_IP 환경변수를 설정해야 합니다."
  echo "예시: MY_PUBLIC_IP=203.0.113.10 bash scripts/setup_oracle_vm.sh"
  exit 1
fi

if [[ ! -f /etc/os-release ]]; then
  echo "오류: /etc/os-release 파일이 없습니다."
  exit 1
fi

. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  echo "오류: 이 스크립트는 Ubuntu 기준입니다. 현재 OS: ${PRETTY_NAME:-unknown}"
  exit 1
fi

echo "[1/8] 기본 패키지 설치"
sudo apt update
sudo apt install -y ca-certificates curl gnupg ufw fail2ban apt-transport-https software-properties-common

echo "[2/8] 타임존 설정"
sudo timedatectl set-timezone Asia/Seoul

echo "[3/8] 스왑 설정"
if sudo swapon --show | grep -q "/swapfile"; then
  echo "기존 /swapfile 스왑이 이미 활성화되어 있습니다."
elif [[ -f /swapfile ]]; then
  echo "/swapfile 이 이미 존재합니다. 기존 파일을 재사용합니다."
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
else
  sudo fallocate -l "${SWAP_SIZE_GB}G" /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
fi

if ! grep -q '^/swapfile none swap sw 0 0$' /etc/fstab; then
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
fi
free -h

echo "[4/8] UFW 방화벽 설정"
if [[ "$ENABLE_UFW" == "true" ]]; then
  sudo ufw default deny incoming
  sudo ufw default allow outgoing
  sudo ufw delete allow 22/tcp >/dev/null 2>&1 || true
  sudo ufw allow from "$MY_PUBLIC_IP" to any port 22 proto tcp
  sudo ufw --force enable
  sudo ufw status verbose
else
  echo "UFW 설정을 건너뜁니다."
fi

echo "[5/8] SSH 보안 설정"
sudo cp /etc/ssh/sshd_config "/etc/ssh/sshd_config.bak.$(date +%Y%m%d%H%M%S)"

sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PubkeyAuthentication .*/PubkeyAuthentication yes/' /etc/ssh/sshd_config

if ! grep -q '^PasswordAuthentication no$' /etc/ssh/sshd_config; then
  echo 'PasswordAuthentication no' | sudo tee -a /etc/ssh/sshd_config > /dev/null
fi
if ! grep -q '^PermitRootLogin no$' /etc/ssh/sshd_config; then
  echo 'PermitRootLogin no' | sudo tee -a /etc/ssh/sshd_config > /dev/null
fi
if ! grep -q '^PubkeyAuthentication yes$' /etc/ssh/sshd_config; then
  echo 'PubkeyAuthentication yes' | sudo tee -a /etc/ssh/sshd_config > /dev/null
fi

sudo sshd -t
sudo systemctl reload ssh

echo "[6/8] fail2ban 설정"
if [[ "$ENABLE_FAIL2BAN" == "true" ]]; then
  sudo systemctl enable --now fail2ban
  sudo tee /etc/fail2ban/jail.local > /dev/null <<EOF
[sshd]
enabled = true
port = ssh
logpath = %(sshd_log)s
backend = systemd
maxretry = 5
bantime = 1h
findtime = 10m
EOF
  sudo systemctl restart fail2ban
  sudo systemctl status fail2ban --no-pager || true
else
  echo "fail2ban 설정을 건너뜁니다."
fi

echo "[7/8] Docker 설치"
sudo install -m 0755 -d /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
fi
sudo chmod a+r /etc/apt/keyrings/docker.gpg

if [[ ! -f /etc/apt/sources.list.d/docker.list ]]; then
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    ${VERSION_CODENAME} stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
fi

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

echo "[8/8] Supabot 디렉터리 준비"
mkdir -p "$APP_DIR/config" "$APP_DIR/data"
chmod 700 "$APP_DIR/config" "$APP_DIR/data"

ENV_FILE="$APP_DIR/config/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<'EOF'
TELEGRAM_BOT_TOKEN=your_bot_token
ADMIN_CHAT_ID=your_admin_chat_id
EOF
  chmod 600 "$ENV_FILE"
  echo ".env 템플릿을 생성했습니다: $ENV_FILE"
else
  chmod 600 "$ENV_FILE"
  echo "기존 .env 파일 권한만 조정했습니다: $ENV_FILE"
fi

cat <<EOF

초기 설정이 끝났습니다.

다음 단계:
1. 새 SSH 접속을 하나 더 열어서 키 로그인과 UFW 접근이 유지되는지 먼저 확인
2. $ENV_FILE 에 TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID 입력
3. 앱 소스 또는 docker-compose.yml 을 $APP_DIR 아래에 배치
4. 다시 로그인해서 docker 그룹 권한 반영
5. 배포 실행:
   cd $APP_DIR
   docker compose pull
   docker compose up -d

EOF
