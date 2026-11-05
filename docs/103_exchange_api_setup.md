# 103_exchange_api_setup.md — 거래소 API 키 발급 및 설정 가이드

supabot에서 지원하는 4개 거래소(업비트, 빗썸, 한국투자증권, 토스증권) 및 Google Gemini API 키 발급 절차와 등록 가이드입니다.

---

## 🔒 보안 원칙 (필독)

1. **`.env` 파일에 거래소 API 키를 넣지 마세요.**
   - 거래소 키와 Gemini 키는 봇 가동 후 Telegram 채팅창에서 `/config` 명령어로 각 사용자 계정에 암호화 등록합니다.
2. **최소 권한 원칙**:
   - 반드시 **자산 조회(Read)** 및 **주문 체결(Trade)** 권한만 부여하세요.
   - **출금(Withdraw) 권한은 절대 부여하지 마세요.**
3. **IP 화이트리스트 등록**:
   - 거래소에서 허용 IP 등록을 지원하는 경우, 반드시 supabot이 실행 중인 서버(예: Oracle Cloud VM의 고정 공인 IP)만 등록하세요.
4. **암호화 저장**:
   - 서버의 `.env`에 설정된 `USER_SECRET_KEY`(Fernet 키)를 기반으로 Supabase `users` 테이블(또는 로컬 `data/users.json`)에 `enc:v1:...` 형식으로 암호화되어 안전하게 보관됩니다.

---

## 1. 업비트 (Upbit)

### 발급 절차
1. [업비트 웹사이트](https://upbit.com)에 로그인합니다.
2. 상단 메뉴에서 `마이페이지` > `Open API 관리`로 이동합니다.
3. 필요한 권한을 선택합니다:
   - **자산조회** (필수)
   - **주문조회** (필수)
   - **주문하기** (매매 기능 사용 시 필수)
   - ⚠️ *출금 권한은 체크하지 마세요.*
4. **특정 IP에서만 호출 허용** 옵션을 켜고, 봇 서버의 공인 IP를 입력합니다.
5. 2차 인증(카카오페이/네이버 인증 등)을 완료합니다.
6. 발급된 **Access Key**와 **Secret Key**를 확인합니다.
   - *Secret Key는 발급 시 단 1회만 표시되므로 즉시 안전한 메모장에 복사해 두세요.*

### 봇에 등록
1. Telegram 봇 채팅방에서 `/config` 입력
2. `업비트 (Upbit)` 버튼 클릭
3. 안내 메시지에 따라 `Access Key` 전송 후 `Secret Key` 전송
4. 입력 즉시 봇이 유효성을 검증하고 원본 메시지를 보안 삭제합니다.

---

## 2. 빗썸 (Bithumb)

### 발급 절차
1. [빗썸 웹사이트](https://www.bithumb.com)에 로그인합니다.
2. `고객센터` > `API 관리` (또는 마이페이지 > API 관리)로 이동합니다.
3. 활성화할 권한을 선택합니다:
   - **회원 정보 및 잔액 조회** (필수)
   - **주문 체결 내역 조회** (필수)
   - **주문 접수 및 취소** (필수)
   - ⚠️ *출금 권한은 체크하지 마세요.*
4. **API 호출 허용 IP 주소**에 봇 서버의 공인 IP를 등록합니다.
5. 보안 비밀번호 및 OTP 인증을 완료하고 API Key를 발급받습니다.
6. **Connect Key (API Key)**와 **Secret Key**를 안전하게 복사해 둡니다.

### 봇에 등록
1. Telegram 봇 채팅방에서 `/config` 입력
2. `빗썸 (Bithumb)` 버튼 클릭
3. `Connect Key` 전송 후 `Secret Key` 전송
4. 유효성 검증 완료 후 키는 암호화 저장되고 메시지는 자동 삭제됩니다.

---

## 3. 한국투자증권 (KIS Open API)

한국투자증권은 국내주식 시세/잔고 조회 및 정규장 지정가 매매를 지원합니다. (모의투자 및 실전투자 지원)

### 발급 절차
1. [KIS Developers](https://apiportal.koreainvestment.com) 포털에 접속하여 로그인합니다.
2. KIS Open API 서비스를 신청하고 앱을 등록합니다.
   - 계좌 선택 후 **App Key** 및 **App Secret**을 발급받습니다.
   - *처음 연동 시에는 모의투자(paper) 환경 키로 테스트하는 것을 강력히 권장합니다.*
3. 본인 종합주식 계좌번호 10자리를 확인합니다:
   - 앞 8자리: 계좌번호 (`CANO`)
   - 뒤 2자리: 계좌상품코드 (`ACNT_PRDT_CD`, 보통 국내주식 종합계좌는 `01`)

### 봇에 등록
1. Telegram 봇 채팅방에서 `/config` 입력
2. `한국투자증권 (KIS)` 버튼 클릭
3. 대화형 안내에 따라 아래 정보를 차례로 입력:
   - **App Key**
   - **App Secret**
   - **계좌번호 앞 8자리**
   - **계좌상품코드 2자리** (예: `01`)
   - **환경 선택**: `paper`(모의투자) 또는 `real`(실전투자)
4. 토큰 발급 및 잔고 조회가 정상 수행되는지 즉시 검증됩니다.

> **참고 (KIS 시장 정책)**:
> - KIS 국내주식은 **일봉 RSI**만 지원하며 분봉 RSI는 지원하지 않습니다.
> - 정규장(평일 09:00~15:35) 외에 접수된 주문은 `reserved`(예약) 상태로 등록되어 다음 정규장 개장 시 자동 실행됩니다.
> - 상세 정책: [302_kis_market_policy.md](file:///E:/apps/supabot/docs/302_kis_market_policy.md)

---

## 4. 토스증권 (Toss Open API)

토스증권은 국내주식 및 해외주식(미국주식) 시세/잔고 조회와 지정가 매매를 지원합니다.

### 발급 절차
1. [Toss Open API 포털](https://openapi.tossinvest.com)에 로그인합니다.
2. 앱을 생성하고 **Client ID**와 **Client Secret**을 발급받습니다.
3. 지원 권한(국내주식/해외주식 잔고 및 주문)을 활성화합니다.

### 봇에 등록
1. Telegram 봇 채팅방에서 `/config` 입력
2. `토스증권 (Toss)` 버튼 클릭
3. `Client ID` 전송 후 `Client Secret` 전송
4. 봇이 즉시 토스 OAuth2 인증을 거쳐 사용자의 증권 계좌 식별자(`account_seq`)를 자동으로 조회하여 저장합니다.

> **참고 (토스 시장 정책)**:
> - 국내주식(예: 005930)과 해외주식(예: AAPL)을 동일한 엔드포인트에서 지원하며 심볼 형태로 시장을 자동 판별합니다.
> - 상세 정책: [303_toss_overseas_stock.md](file:///E:/apps/supabot/docs/303_toss_overseas_stock.md) 및 [206_toss_api_reference.md](file:///E:/apps/supabot/docs/206_toss_api_reference.md)

---

## 5. Google Gemini API (자연어 명령용)

자연어 명령 기능을 사용하려면 Google Gemini API 키가 필요합니다.

### 발급 절차
1. [Google AI Studio](https://aistudio.google.com)에 접속하여 Google 계정으로 로그인합니다.
2. **Get API Key** 버튼을 눌러 새 API 키를 생성합니다.
3. 생성된 키 문자열을 복사합니다.

### 봇에 등록 및 활성화
1. Telegram 봇 채팅방에서 `/config` 입력
2. `Gemini API 키` 버튼 클릭 후 키 전송
3. 자연어 처리 활성화:
   ```text
   /config set llm_enabled on
   ```
4. 설정 확인:
   ```text
   /config -v
   ```
   - `Gemini: 설정됨`, `llm_enabled: on` 상태인지 확인합니다.

---

## 6. 키 등록 확인 및 관리 명령어

- `/config -v`: 등록된 거래소별 키 유효성 및 활성화 상태 확인 (키 원본은 절대 노출되지 않음)
- `/whoami`: 현재 유저의 기본 거래소, 암호화 상태, 권한 확인
- `/config set default_exchange <upbit|bithumb|kis|toss>`: 기본 거래소 변경
