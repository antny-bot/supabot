# SUTT-Bot V2 사양서: 멀티유저 및 멀티거래소 자동매매 플랫폼 (v2.0)

본 사양서는 Synology NAS의 Container Manager(Docker) 환경에서 구동되는, 다중 사용자(Multi-User) 및 다중 거래소(Upbit & Bithumb) 지원 자동매매 봇의 개발 규격을 정의합니다.

---

## 1. 시스템 개요 및 목표

- **시스템명:** Synology Upbit-Bithumb Multi-user Trading Bot (SUTT-Bot V2)
- **운영 환경:** Synology NAS Container Manager (Docker)
- **핵심 목표:**
  1. **멀티유저 지원:** 다수의 사용자가 각자의 API 키를 등록하여 독립적으로 봇을 활용.
  2. **멀티거래소 통합:** 업비트와 빗썸을 하나의 텔레그램 인터페이스에서 동시 제어.
  3. **안전장치(Fool-proof):** 인라인 버튼을 통한 주문/취소 최종 승인 단계 도입.
  4. **지능형 시그널 엔진:** RSI 등 보조지표 기반 차트 분석 및 매매 타이밍 알림.

---

## 2. 기술 스택 및 라이브러리

- **언어:** Python 3.11-slim
- **거래소 연동:** `upbit CLI` (v0.9.1+), `Bithumb V2 API` (JWT), `ccxt` (거래소 추상화용)
- **텔레그램:** `python-telegram-bot` (Asyncio 기반)
- **데이터 분석:** `pandas`, `ta` (Technical Analysis Library)
- **상태 관리:** `json` 기반 영속성 스토리지 (사용자 정보 및 주문 상태)

---

## 3. 아키텍처 및 데이터 구조

### 3.1 프로젝트 디렉토리
```text
crypto-bot/
├── config/
│   └── .env             # 최고 관리자 설정 (BOT_TOKEN, ADMIN_CHAT_ID)
├── data/
│   ├── users.json       # 사용자별 API 키 및 설정 (암호화 권장)
│   └── orders.json      # 사용자별/거래소별 활성 주문 추적 데이터
├── src/
│   ├── core/            # 거래소별 어댑터 및 시그널 엔진
│   └── main.py          # 텔레그램 핸들러 및 메인 루프
├── Dockerfile
└── docker-compose.yml
```

### 3.2 데이터 스키마 예시 (`data/users.json` & `data/orders.json`)

**사용자 정보 및 설정 (`data/users.json`):**
```json
{
  "123456789": {
    "username": "AdminUser",
    "is_admin": true,
    "is_active": true,
    "preferences": {
      "default_exchange": "upbit",
      "signal_alerts": true
    },
    "exchanges": {
      "upbit": {
        "access_key": "YOUR_UPBIT_ACCESS",
        "secret_key": "YOUR_UPBIT_SECRET",
        "watchlist": ["KRW-BTC", "KRW-ETH"]
      },
      "bithumb": {
        "access_key": "YOUR_BITHUMB_ACCESS",
        "secret_key": "YOUR_BITHUMB_SECRET",
        "watchlist": ["BTC", "XRP"]
      }
    }
  }
}
```

**미체결 주문 추적 목록 (`data/orders.json`):**
```json
[
  {
    "user_id": "123456789",
    "exchange": "upbit",
    "uuid": "cdd92160-3fbf-4051-bcce-6415dd98d63e",
    "ticker": "KRW-BTC",
    "price": 98000000.0,
    "volume": 0.00510204,
    "created_at": "2026-05-16T15:30:00Z"
  }
]
```

---

## 4. 주요 기능 명세

### 4.1 텔레그램 명령어 체계 (V2)

| 명령어 | 매개변수 | 설명 |
| :--- | :--- | :--- |
| **/start** | 없음 | 유저 등록 확인 및 통합 메뉴 안내 |
| **/asset** | `[upbit/bithumb]` | 특정 거래소 또는 전체 자산 현황 조회 |
| **/grid** | `[거래소] [종목] [시작가] [종료가] [개수] [예산]` | 거미줄 매수 셋팅 (버튼 컨펌 단계 포함) |
| **/orders** | `[거래소]` | 현재 대기 중인 미체결 주문 목록 |
| **/cancel** | `[거래소] [종목]` | 특정 종목 일괄 취소 (버튼 컨펌 단계 포함) |
| **/watch** | `[거래소] [종목]` | 시그널 알림을 위한 관심 종목 등록 |
| **/config** | 없음 | 자신의 API 키 등록 및 봇 설정 관리 |

### 4.2 안전장치 및 시그널 엔진
1. **버튼식 Confirm:** `/grid`나 `/cancel` 실행 시 봇이 요약 정보를 보여주며 `[✅ 승인]`, `[❌ 취소]` 버튼을 출력함. 사용자가 클릭할 때만 실제 API가 호출됨.
2. **RSI 시그널 분석:** 1시간봉 기준 RSI가 30 이하(과매도) 혹은 70 이상(과매수) 도달 시 사용자에게 버튼이 포함된 알림 발송.
   - 알림 내 `[💰 즉시 거미줄 셋팅]` 버튼 연동.

---

## 5. 단계별 개발 로드맵

1. **Phase 1:** 멀티유저 및 멀티거래소 추상화 레이어 설계 (데이터 구조 확정)
2. **Phase 2:** 빗썸 API 연동 및 공통 인터페이스 구축
3. **Phase 3:** 텔레그램 인라인 키보드(버튼) 컨펌 시스템 구현
4. **Phase 4:** 보조지표(RSI) 기반 시그널 감시 엔진 및 관심종목 관리 구현
5. **Phase 5:** 사용자별 독립 주문 추적 및 알림 로직 완성
6. **Phase 6:** 도커 인프라 구축 및 시놀로지 배포 테스트
