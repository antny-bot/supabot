# Supabot Oracle Cloud 업로드 방법: Git 없이 배포

이 문서는 Git을 쓰지 않고 로컬 PC의 Supabot 프로젝트를 Oracle Cloud VM으로 올리는 방법을 정리합니다.

대상 상황:
- GitHub 저장소를 아직 만들지 않았을 때
- 서버에서 `git clone` 대신 로컬 작업본을 그대로 올리고 싶을 때
- 빠르게 1회 배포해 보고 싶을 때

관련 문서:
- [oracle-cloud-vm-setup.md](oracle-cloud-vm-setup.md)
- [oracle-cloud-deploy-sequence.md](oracle-cloud-deploy-sequence.md)

## 1. 권장 방식

Git 없이 올릴 때는 아래 둘 중 하나를 권장합니다.

1. `scp`로 프로젝트 파일을 서버에 복사
2. 압축 파일(`zip`)을 서버에 올린 뒤 풀기

둘 다 가능하지만, 규모가 작으면 `scp`, 반복 배포가 많아지면 결국 Git 방식이 더 관리하기 쉽습니다.

## 2. 사전 조건

다음이 준비되어 있어야 합니다.

- Oracle Cloud VM에 SSH 접속 가능
- VM에 `~/supabot` 디렉터리 또는 원하는 배포 디렉터리 생성 가능
- 로컬 PC에서 SSH 키로 서버 접속 가능
- 서버에서 Docker가 이미 설치되어 있음

서버 기본 설정이 아직이라면 먼저 [oracle-cloud-vm-setup.md](oracle-cloud-vm-setup.md) 부터 진행하세요.

## 3. 방법 A: `scp`로 디렉터리 업로드

### Windows PowerShell 예시

로컬 프로젝트 폴더에서 아래처럼 업로드할 수 있습니다.

```powershell
scp -r . ubuntu@<VM_PUBLIC_IP>:~/supabot
```

하지만 이 방식은 `.git`, `node_modules`, `__pycache__`, 로컬 임시 파일까지 전부 올라갈 수 있어서 그대로는 권장하지 않습니다.

실전에서는 불필요한 폴더를 제외한 압축 업로드가 더 안전합니다.

## 4. 방법 B: ZIP으로 압축 후 업로드

이 방식이 Git 없이 올릴 때 가장 관리하기 편합니다.

### 1) 로컬에서 배포용 ZIP 만들기

**권장 방식 (Git Archive):**
로컬에 Git이 설치되어 있다면, `.gitignore`를 준수하며 깨끗한 소스만 압축해주는 이 방식을 가장 권장합니다.

```bash
git archive --format=zip -o supabot-deploy.zip HEAD
```

**대안 방식 (PowerShell):**
Git을 쓰기 어려운 환경이라면 아래처럼 수동으로 압축합니다.

```powershell
Compress-Archive `
  -Path .\src, .\docs, .\config, .\data, .\Dockerfile, .\docker-compose.yml, .\requirements.txt, .\.dockerignore, .\.gitignore, .\README.md `
  -DestinationPath .\supabot-deploy.zip `
  -Force
```

주의:
- `config/.env`에 실제 토큰이 들어 있다면 업로드 전에 포함 여부를 확인하세요.
- `data/users.json`에 실거래 키가 있다면 함부로 배포본에 넣지 마세요.
- `node_modules`, `.git`, `__pycache__` 같은 폴더는 포함하지 않는 편이 좋습니다.

### 2) ZIP 파일 업로드

```powershell
scp .\supabot-deploy.zip ubuntu@<VM_PUBLIC_IP>:~/
```

### 3) 서버에서 압축 풀기

VM에서 실행:

```bash
mkdir -p ~/supabot
sudo apt update
sudo apt install -y unzip
unzip -o ~/supabot-deploy.zip -d ~/supabot
cd ~/supabot
```

## 5. `.env`와 런타임 데이터는 분리하기

배포 시에는 아래 항목을 소스와 분리해서 다루는 편이 안전합니다.

- `config/.env`
- `data/users.json`

이유:
- `.env`에는 Telegram 토큰이 들어감
- `users.json`에는 런타임 중 거래소/Gemini API 키가 저장될 수 있음 (`USER_SECRET_KEY` 설정 시 암호화 저장)

권장 방식:
- 코드만 업로드
- 서버에서 `~/supabot/config/.env`를 직접 작성
- `~/supabot/data`는 서버 영속 데이터로 유지

서버에서 `.env` 직접 작성:

```bash
mkdir -p ~/supabot/config ~/supabot/data
chmod 700 ~/supabot/config ~/supabot/data
nano ~/supabot/config/.env
chmod 600 ~/supabot/config/.env
```

예시:

```env
TELEGRAM_BOT_TOKEN=...
ADMIN_CHAT_ID=...
USER_SECRET_KEY=...
```

`USER_SECRET_KEY`는 거래소/Gemini 키 암호화용 Fernet 마스터키입니다. 서버에서 직접 생성해 `config/.env`에 넣고, 배포 압축본이나 GitHub에는 포함하지 마세요.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Fernet 형식이 아닌 임의 문자열을 넣으면 새 API 키 저장이 실패합니다. 이미 `enc:v1:`로 저장된 `users.json`은 암호화할 때 사용한 같은 `USER_SECRET_KEY`가 있어야 복호화됩니다. 키가 다르면 봇은 기동되지만 `/whoami`에 `보안 키: 복호화 오류`가 표시되고 거래소/Gemini 키는 사용할 수 없습니다.

## 6. 업로드 후 배포

서버에서 아래 순서로 실행합니다.

```bash
cd ~/supabot
docker compose pull
docker compose up -d
docker compose ps
docker compose logs -f --tail=100
```

레지스트리 이미지 대신 서버에서 직접 빌드할 경우:

```bash
cd ~/supabot
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100
```

## 7. 반복 배포 시 갱신 방법

Git 없이 다시 올릴 때는 보통 아래 순서로 갱신합니다.

1. 로컬에서 새 ZIP 생성
2. `scp`로 서버에 덮어쓰기 업로드
3. 서버에서 `unzip -o`로 덮어쓰기
4. `docker compose up -d --build` 또는 `docker compose up -d`

예시:

```bash
unzip -o ~/supabot-deploy.zip -d ~/supabot
cd ~/supabot
docker compose up -d --build
```

## 8. 업로드 후 확인할 것

- `docker compose ps` 에서 컨테이너 상태가 `Up` 인지
- Telegram `/start` 응답이 정상인지
- `data/users.json` 권한이 과도하게 열려 있지 않은지
- `config/.env`가 읽기 가능한 상태인지

## 9. 주의사항

- Git 없이 배포하면 어떤 파일이 서버에 올라갔는지 추적이 약해집니다.
- 실거래 키가 들어 있는 파일을 실수로 압축해서 올리지 않도록 특히 주의하세요.
- 반복 운영할 계획이면 결국 Git 기반 배포로 옮기는 편이 안전하고 관리가 쉽습니다.
