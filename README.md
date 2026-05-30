# TTBot (Telegram Trading Bot)

Oracle Cloud VM Docker 환경에서 24시간 무중단 구동되는 **멀티유저 & 멀티거래소 통합 자동매매 봇**입니다. 단순한 주문 도구를 넘어, 지능형 알고리즘과 실시간 동기화 엔진을 갖춘 전문 트레이딩 시스템입니다.

## 🚀 주요 특징

- **지능형 RSI 순환 매매:** 하단 RSI에서 매집하고 상단 RSI에서 자동 익절하는 `/rsitrade` 전략 지원.
- **실시간 주문 동기화:** 거래소 앱/웹에서 직접 조작한 주문도 1분 이내에 감지하여 봇의 추적 목록을 자동 최신화.
- **전략 대시보드:** 가동 중인 모든 트레이딩 전략을 거래소별로 그룹화하고 진행률(🔵⚪)로 시각화하여 브리핑.
- **Gemini 자연어 명령:** 텔레그램 일반 문장을 기존 명령 의도로 해석합니다. 안전한 조회 표현은 룰 기반 전처리로 즉시 처리하고, 나머지는 Gemini가 해석합니다. 주문/설정 변경은 확인 버튼을 거칩니다.
- **견고한 예외 처리:** 
  - **부분 체결 대응:** 주문이 일부만 체결되어도 즉시 물량을 파악하여 후속 대응(익절 등) 가동.
  - **자동 복구 시스템:** 봇 재시작 시 꼬인 주문 상태를 전수 조사하여 중단된 전략을 자동으로 복구.
  - **수익 보장 버퍼:** 수수료와 슬리피지를 고려한 0.1% 가격 보정을 통해 확실한 체결 유도.
- **통합 거래소 지원:** 업비트(Upbit CLI), 빗썸(Bithumb V2 API), 한국투자증권(KIS Open API) 및 한글 명령어 지원.
- **친절한 상세 가이드:** 모든 명령어 뒤에 `-h`, `-help`, `--help`를 붙여 상세 사용법과 예시를 즉시 확인 가능.

## 📜 주요 명령어 안내

모든 명령어는 `/[명령어] -h`를 통해 상세 가이드를 볼 수 있습니다.

### 1. 기본 및 설정
- `/start` : 시스템 접속 및 메뉴 확인 (최초 접속 시 관리자 승인 필요)
- `/status` : **(NEW)** 가동 중인 트레이딩 전략 통합 대시보드 확인
- `/config` : 거래소별 API 키 설정 및 자동 유효성 검증
- `/config -v` : API 키 상태, RSI 기준, Gemini 자연어 설정 상태 확인
- `/whomai` : 내 Telegram ID, 권한, 활성 상태, 기본 거래소, 자연어 상태 확인 (`/me` alias 지원)
- `/nlstats` : 관리자 전용 자연어 전처리 후보 패턴 통계 조회
- `/help` : 전체 명령어 사용 설명서 출력

봇은 시작 시 Telegram 명령어 메뉴를 자동 갱신합니다. 새 명령이 보이지 않으면 배포 후 봇 프로세스가 새 코드로 재시작되었는지 확인하세요.

### 2. 자산 및 시세 조회
- `/asset` : 통합 자산 현황 조회 (소액 자산 자동 요약 포함)
- `/price` (단축: `/p`) : 특정 종목의 실시간 시세 및 변동률 확인
- `/history` : 최근 체결 완료된 거래 내역 조회 (최근 5건)

### 3. 거래 및 주문 관리
- `/rsitrade` : **(HOT)** RSI 구간 기반 자동 매집 및 익절 순환 전략 시작
- `/grid` : 지정 가격 범위 내 거미줄 분할 매수 셋팅
- `/sgrid` : 보유 수량 기반 거미줄 분할 매도 셋팅
- `/buy` / `/sell` : 단일 지정가 매수/매도 주문 전송
- `/orders` : 현재 추적 중인 모든 미체결 주문 목록
- `/cancel` : 특정 종목의 모든 주문 일괄 취소

### 4. 시그널 및 알림
- `/watch` : RSI 매수 시그널 실시간 감시 종목 추가
- `/unwatch` : 감시 목록에서 종목 제거

## 🛠 설치 및 실행 방법 (Oracle Cloud VM)

Oracle Cloud에서 SSH 복구와 컨테이너 기동까지 실제로 확인한 기록은 [Oracle Cloud SSH 복구 및 컨테이너 기동 성공 기록](docs/oracle-cloud-ssh-recovery-success.md)을 참고하세요.

### 1. 프로젝트 설정
`config/.env` 파일을 생성하고 다음 내용을 입력합니다.
```env
TELEGRAM_BOT_TOKEN=여러분의_봇_토큰
ADMIN_CHAT_ID=최고_관리자_채팅_ID
USER_SECRET_KEY=Fernet_마스터키
```

`TELEGRAM_BOT_TOKEN`은 텔레그램에서 `@BotFather`를 검색한 뒤 `/newbot` 명령으로 새 봇을 만들면 발급됩니다. 봇 이름과 사용자명을 입력하면 BotFather가 긴 토큰 문자열을 보내주며, 이 값을 `TELEGRAM_BOT_TOKEN=` 뒤에 붙여 넣습니다. 토큰은 봇 제어 권한과 같으므로 GitHub, 채팅방, 스크린샷 등에 공개하지 마세요.

`ADMIN_CHAT_ID`는 봇을 처음 관리할 텔레그램 계정의 숫자 ID입니다. 생성한 봇에게 먼저 `/start`를 보내고, 텔레그램에서 `@userinfobot` 또는 `@RawDataBot`을 실행해 표시되는 본인 ID를 확인한 뒤 `ADMIN_CHAT_ID=` 뒤에 입력합니다. 봇은 이 ID를 최초 최고 관리자 기준으로 사용합니다.

`USER_SECRET_KEY`는 `data/users.json`에 저장되는 거래소/Gemini 키를 암호화하는 마스터키입니다. Oracle VM의 `config/.env`에만 보관하고 GitHub에 올리지 마세요. 생성 예시는 다음과 같습니다.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

이미 평문으로 저장된 키가 있더라도 `USER_SECRET_KEY`를 설정한 뒤 봇을 재시작하면 `enc:v1:<ciphertext>` 형식으로 자동 마이그레이션됩니다. `USER_SECRET_KEY`가 없으면 기존 평문 키 읽기는 유지되지만 새 API 키 저장은 거부됩니다.

### 2. 거래소 API 키 발급

업비트와 빗썸에서 각각 API Key와 Secret Key를 발급받아야 자산 조회와 주문 기능을 사용할 수 있습니다. 주문 권한이 포함된 키는 실제 매매가 가능한 권한이므로, 필요한 권한만 선택하고 가능하면 Oracle Cloud VM의 공인 IP를 허용 IP로 등록하세요.

**업비트 API 키**
1. 업비트 PC 웹에 로그인합니다.
2. `마이페이지` > `Open API` 메뉴로 이동합니다.
3. 필요한 권한을 선택합니다. 이 봇에서 주문까지 사용할 경우 자산 조회와 주문 권한이 필요합니다.
4. 주문 또는 출금 권한을 선택하는 경우 허용 IP 등록이 필요할 수 있습니다.
5. 인증을 완료한 뒤 표시되는 Access Key와 Secret Key를 안전한 곳에 보관합니다. Secret Key는 다시 확인할 수 없으므로 발급 직후 복사해 두세요.

**빗썸 API 키**
1. 빗썸 PC 웹에 로그인합니다.
2. API 관리 또는 Open API 메뉴로 이동합니다.
3. API Key를 생성하고 필요한 권한을 선택합니다. 이 봇에서 주문까지 사용할 경우 자산 조회와 주문 권한이 필요합니다.
4. 보안 인증을 완료하고, 필요한 경우 허용 IP 또는 API 사용 설정을 활성화합니다.
5. 표시되는 API Key와 Secret Key를 안전한 곳에 보관합니다. Secret Key는 외부에 공개하지 마세요.

발급한 거래소 키는 `.env`에 넣지 않고, 봇 실행 후 텔레그램에서 `/config` 명령으로 등록합니다. `/config`를 입력하면 거래소 선택 버튼이 나오며, 업비트 또는 빗썸을 선택한 뒤 Access Key와 Secret Key를 순서대로 입력하면 봇이 저장하고 유효성을 확인합니다. 입력한 키 메시지는 보안을 위해 자동 삭제됩니다.

**한국투자증권 Open API**
1. 한국투자증권 계좌를 준비하고 KIS Developers 또는 한국투자증권 Open API 메뉴에서 Open API 서비스를 신청합니다.
2. App Key와 App Secret을 발급받습니다. 모의투자와 실전투자는 별도 키를 사용할 수 있으므로 처음에는 모의투자 키를 권장합니다.
3. 계좌번호 앞 8자리와 계좌상품코드 2자리를 확인합니다. 국내주식 종합계좌는 보통 상품코드가 `01`입니다.
4. 봇에서 `/config`를 입력하고 `한국투자증권`을 선택한 뒤 App Key, App Secret, 계좌번호, 상품코드, `paper` 또는 `real` 환경을 입력합니다.
5. 지원 범위는 국내주식 시세 조회, 잔고 조회, 지정가 매수/매도, 주문 상태 확인, 일봉 RSI 감시(`/watch`), 일봉 RSI 순환전략(`/rsitrade`)입니다. 한국투자증권은 분봉 RSI를 지원하지 않으므로 RSI 기준이 분봉이면 KIS RSI 명령은 실행되지 않습니다.

### 3. Gemini 자연어 명령 설정

Gemini API 키는 `.env`에 넣지 않고 거래소 키처럼 텔레그램 `/config`에서 사용자별로 등록합니다.

1. Google AI Studio에서 Gemini API 키를 발급합니다.
2. 봇에서 `/config`를 입력하고 `Gemini API 키` 버튼을 누릅니다.
3. Gemini API 키를 입력하면 봇이 메시지를 삭제하고 `data/users.json`에 암호화 저장합니다.
4. `/config set llm_enabled on`으로 자연어 기능을 켭니다.
5. `/config -v`로 `Gemini: 설정됨`, `llm_enabled: on`, `llm_model` 상태를 확인합니다.

자연어 기능은 기존 명령어를 대체하지 않습니다. Gemini 키가 없거나 `llm_enabled`가 꺼져 있으면 `/buy`, `/rsitrade`, `/asset` 같은 기존 명령어는 그대로 작동하고, 일반 텍스트에는 설정 안내만 표시됩니다.

### 4. GitHub Actions CI/CD 설정

이 저장소는 `.github/workflows/docker-publish.yml`을 통해 GitHub Release가 발행될 때 Docker 이미지를 빌드하고 Docker Hub로 푸시합니다. 워크플로는 다음 GitHub Actions secrets를 사용합니다.

```text
DOCKERHUB_USERNAME=도커허브_사용자명
DOCKERHUB_TOKEN=도커허브_액세스_토큰
DOCKERHUB_REPO=도커허브_사용자명/저장소명
```

GitHub에서 secrets를 등록하는 위치는 저장소 페이지의 `Settings` > `Secrets and variables` > `Actions` > `Repository secrets`입니다. `New repository secret`을 눌러 위 3개 이름을 정확히 같은 이름으로 추가합니다. secret 값은 GitHub 화면에서 다시 볼 수 없으므로 잘못 입력한 경우 새 값으로 업데이트하세요.

Docker Hub 값은 다음처럼 준비합니다.
1. Docker Hub에 로그인합니다.
2. `DOCKERHUB_USERNAME`에는 Docker Hub 사용자명 또는 organization namespace를 입력합니다.
3. `Repositories`에서 `Create repository`를 눌러 이미지 저장소를 만듭니다. 예를 들어 사용자명이 `myname`이고 저장소명이 `crypto-bot`이면 `DOCKERHUB_REPO`는 `myname/crypto-bot`입니다.
4. 계정 메뉴의 `Account settings` > `Personal access tokens`에서 새 토큰을 발급합니다. GitHub Actions가 이미지를 푸시해야 하므로 권한은 `Read & Write` 이상으로 설정합니다.
5. 발급 직후 표시되는 토큰을 복사해 `DOCKERHUB_TOKEN`에 저장합니다. Docker Hub 토큰은 다시 조회할 수 없으므로 분실하면 새로 발급해야 합니다.

배포는 GitHub에서 새 Release를 발행하면 시작됩니다. 이 워크플로는 `main` 브랜치에 push될 때가 아니라, Release가 `published` 상태가 되는 순간 실행됩니다.

Release 배포 순서는 다음과 같습니다.
1. 변경 사항을 `main` 브랜치에 push합니다.
2. GitHub 저장소에서 `Releases` > `Draft a new release`를 선택합니다.
3. 새 태그를 만듭니다. 예: `v1.0.0`
4. Release title과 설명을 입력하고 `Publish release`를 누릅니다.
5. `Actions` 탭에서 `Docker Publish` 워크플로가 시작되는지 확인합니다.
6. 성공하면 Docker Hub에 `${DOCKERHUB_REPO}:latest`와 `${DOCKERHUB_REPO}:v1.0.0` 이미지가 푸시됩니다.
7. Oracle Cloud VM에서 해당 이미지를 pull하거나 `docker compose`로 재배포해 새 버전을 실행합니다.

예를 들어 `v1.0.0` 태그로 Release를 publish하면 Actions가 이미지를 빌드해 Docker Hub에 `latest`와 `v1.0.0` 태그를 함께 푸시합니다. 이후 Oracle Cloud VM에서는 `DOCKERHUB_REPO:latest` 또는 특정 버전 태그 이미지를 사용해 컨테이너를 실행하면 됩니다.

### 5. 도커 실행 (Oracle Cloud VM)
Oracle Cloud VM에서 Docker Compose로 컨테이너를 실행합니다.

```yaml
version: '3.8'
services:
  sutt-bot:
    image: your-dockerhub-id/crypto-bot:latest
    container_name: upbit-bithumb-bot
    restart: always
    volumes:
      - ./config/.env:/app/config/.env
      - ./data:/app/data
```

## 🏗 시스템 아키텍처

- `src/main.py`: 텔레그램 핸들러 및 **실시간 동기화/자동 대응 엔진**
- `src/core/exchange_adapter.py`: 거래소 API 통합 정규화 레이어
- `src/core/signal_engine.py`: **RSI 가격 역산 수학 알고리즘** 및 지표 분석
- `src/core/order_manager.py`: 전략별 주문 상태 영속화 및 추적 관리
- `src/core/user_manager.py`: 멀티유저 권한 및 개별 설정 관리

## 📈 RSI 기준과 캔들 조회 로직

RSI 기간은 기본적으로 14기간이며, 캔들 기준 기본값은 일봉입니다.

```text
/config set rsi_interval day
/config set rsi_interval 60
/config -v
```

허용되는 RSI 캔들 기준은 다음과 같습니다.

- 일봉: `day`, `daily`, `d`, `1d`
- 분봉: `1`, `3`, `5`, `10`, `15`, `30`, `60`, `240`

거래소별 캔들 조회 방식은 다릅니다.

- Upbit: 일봉은 Upbit CLI `candles list-days`, 분봉은 `candles list-minutes`를 사용합니다.
- Bithumb: 일봉은 `/v1/candles/days`, 분봉은 `/v1/candles/minutes/{unit}`를 사용합니다.
- 한국투자증권: 일봉만 지원하며 KIS `inquire-daily-itemchartprice`(`FHKST03010100`)를 사용합니다.

한국투자증권은 이번 버전에서 분봉 RSI를 지원하지 않습니다. 사용자의 `rsi_interval`이 `60` 같은 분봉일 때 `/watch 한투 005930` 또는 `/rsitrade 한투 005930 ...`을 실행하면 봇은 주문을 만들지 않고 `한국투자증권 RSI는 일봉만 지원합니다`라고 안내합니다.

## 🕘 한국투자증권 주문 추적 정책

코인 거래소는 24시간 거래되지만 한국투자증권 국내주식 주문은 정규장 중심으로 동작합니다. 불필요한 API 호출을 줄이고 만료 주문을 안전하게 다루기 위해 KIS 주문은 다음 정책을 따릅니다.

- KIS 주문 상태 조회는 평일 KST 09:00-15:35에만 수행합니다.
- 장외, 주말에는 KIS 주문 조회를 건너뛰고 다음 평일 09:00 이후로 다시 확인합니다.
- 별도 휴일 캘린더는 관리하지 않습니다. 공휴일처럼 평일이지만 휴장인 날에는 KIS API의 장외/거래불가 응답을 기준으로 다음 평일 09:00로 미룹니다.
- `/status`에서는 KIS 주문을 `대기`, `부분체결`, `장외 대기`, `다음 정규장 재주문 예정`으로 표시합니다.

국내주식 미체결 주문은 다음날 거래소에서 사라질 수 있으므로, 봇은 거래소 주문 ID와 봇의 전략 의도를 분리해 관리합니다.

- 수동 `/buy 한투`, `/sell 한투` 주문은 자동 재주문하지 않습니다. 만료 또는 외부 취소가 감지되면 알림 후 추적을 종료합니다.
- `/rsitrade 한투` 같은 전략 주문은 만료되면 `pending_reorder` 상태로 유지합니다.
- 부분 체결 후 만료된 전략 주문은 전체 수량이 아니라 `주문 수량 - 체결 수량` 잔량만 다음 정규장에 재주문합니다.
- 재주문 성공 시 기존 전략 정보는 유지하고 새 KIS 주문 ID로 교체합니다.

이 정책은 사용자가 직접 낸 수동 주문이 원치 않게 반복되는 일을 막고, 봇이 만든 전략 주문만 다음 정규장에도 의도를 이어가도록 하기 위한 것입니다.

## 🧠 Gemini 자연어 명령 로직

Gemini 자연어 기능은 텔레그램 일반 텍스트를 기존 명령어 의도로 변환하는 보조 계층입니다. LLM은 거래소 API를 직접 호출하지 않고, 봇 내부에서 검증 가능한 JSON 의도만 반환합니다.

처리 순서는 다음과 같습니다.

1. 안전한 조회 표현은 룰 기반 전처리로 먼저 처리합니다. 이 경우 Gemini를 호출하지 않고 로그에도 남기지 않습니다.
2. 전처리로 처리하지 못한 문장만 Gemini로 보내 JSON intent를 받습니다.
3. Gemini 결과는 서버 후처리 규칙으로 한 번 더 보정합니다. 예를 들어 `주문대기중인것은?`, `예약 주문 보여줘`, `추적 중인 전략 주문 있어?`는 전략 대시보드인 `/status`로 보정하고, `미체결 주문`, `오픈오더`, `거래소에 실제 걸린 주문`은 `/orders`로 둡니다.
4. 전처리로 처리하지 못해 Gemini까지 간 문장은 익명화된 형태로 `data/nl_unmatched.jsonl`에 누적합니다. 숫자, 6자리 주식코드, 긴 토큰은 마스킹하며 최근 500줄만 유지합니다.
5. 관리자는 `/nlstats`, `/nlstats export [N]`, `/nlstats hits`, `/nlstats clear confirm`으로 자주 들어오는 미처리 자연어 패턴과 전처리 hit를 확인/정리할 수 있습니다.

즉시 실행되는 조회 의도:

- 자산 조회: `내 자산 보여줘`
- 시세 조회: `삼성전자 현재가 보여줘`, `BTC 가격 알려줘`
- 전략 상태: `주문대기중인것은?`, `예약 주문 보여줘`, `전략 상태 알려줘`
- 미체결 주문: `미체결 주문 뭐 있어?`, `오픈오더 보여줘`
- 설정 조회: `현재 설정 보여줘`
- 체결 내역: `최근 체결 내역 보여줘`
- 애매한 조회: `비트 봐줘`처럼 의도가 불명확하면 시세/자산/전략 상태 중 무엇을 볼지 되묻습니다.

확인 버튼이 필요한 변경 의도:

- 주문: `BTC 100만원어치 RSI 25-30으로 나눠서 사줘`
- 단일 매수/매도: `한투 삼성전자 70000원에 1주 사줘`
- 설정 변경: `RSI 기준 일봉으로 바꿔줘`
- 관심 종목 변경: `삼성전자 RSI 감시해줘`
- 취소: `BTC 주문 취소해줘`

주문과 설정 변경은 Gemini가 해석했더라도 즉시 실행하지 않습니다. 봇이 해석 결과를 요약하고 `실행` 버튼을 보여준 뒤, 사용자가 버튼을 누른 경우에만 서버 측 검증과 기존 주문 로직을 통과합니다. 검증 항목에는 거래소명, 종목, 가격, 수량, RSI 범위, 예산, `max_order_krw`, KIS 일봉 제한, KIS 정규장 정책이 포함됩니다.

거래소 API 키와 Gemini API 키는 `USER_SECRET_KEY`가 설정된 경우 `data/users.json`에 `enc:v1:` 형식으로 암호화 저장됩니다. 이는 `users.json` 단독 유출을 줄이기 위한 보호이며, 서버 운영자가 `.env`와 `users.json`을 모두 읽을 수 있으면 복호화할 수 있습니다.

## ⚠️ 면책 조항
본 소프트웨어는 투자 보조 도구일 뿐이며, 투자에 대한 모든 책임은 사용자 본인에게 있습니다. 매매 수수료 및 호가 단위 보정 등에 유의하여 사용하시기 바랍니다.
