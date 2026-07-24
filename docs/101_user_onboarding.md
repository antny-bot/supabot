# 사용자 온보딩 가이드

`supabot` 신규 사용자 등록 및 `supabot-manager` 연동 절차 가이드.

## 한눈에 보는 흐름

1. 사용자 텔레그램 봇에 `/start` 전송.
2. 봇 사용자 `pending` 등록, 관리자 승인 알림.
3. 관리자 `supabot-manager` 화면에서 `active` 승인.
4. 사용자 텔레그램 봇 기능 사용.
5. 웹 대시보드 필요 시 `manager_email` 연결 및 Supabase Auth 계정 생성.
6. 사용자 `supabot-manager` 로그인.

## 1. 사전 준비

사전 준비 사항:

- `supabot` 봇 실행 필수.
- `supabot-manager` 사용 시 manager 배포 필수.
- 봇과 manager 동일 Supabase 프로젝트 참조 필수.
- 관리자 승인 권한 필요.

배포 참고 문서:

- 봇/전체 구조: [README.md](/E:/apps/supabot/README.md)
- manager 배포: [manager/README.md](/E:/apps/supabot/manager/README.md)

## 2. 텔레그램 봇 사용자 등록

### 사용자가 할 일

1. 텔레그램 봇 실행.
2. `/start` 전송.
3. 승인 대기 안내 확인 후 대기.

첫 `/start` 전송 시 사용자 자동 생성되나 상태 `pending`. 승인 전 기능 사용 불가.

### 관리자가 할 일

1. `supabot-manager` 사용자 목록 이동.
2. 신규 `pending` 사용자 검색.
3. `Approve` 또는 활성화로 상태 `active` 변경.

승인 시 manager 텔레그램 알림 전송. 사용자 봇 정상 사용 가능.

## 3. manager까지 열어줘야 하는 경우

웹 대시보드 `supabot-manager` 필요 시 추가 절차 진행.

### 3-1. 관리자: 로그인 이메일 연결

1. `supabot-manager` 사용자 화면 대상 선택.
2. `manager_email`에 로그인 이메일 저장.

이메일은 봇-manager 연결 키. 로그인 후 `users.manager_email` 일치 사용자 세션 오픈.

### 3-2. 관리자: Supabase Auth 계정 생성

**권장: manager 화면에서 초대 메일 발송**

1. `supabot-manager` 사용자 화면 대상 선택.
2. `manager_email` 존재 시 `초대 메일 발송` 버튼 표시.
3. 클릭 시 Supabase Auth 계정 생성 및 비밀번호 설정 링크 메일 발송.
4. 메일 링크 접속해 비밀번호 설정 시 계정 활성화.
5. 메일 발송 완료(`manager_invited_at` 기록) 시 버튼 `초대 메일 발송` -> `비밀번호 재설정` 변경 (중복 방지).

> Supabase `Authentication > Email Templates` 및 SMTP 설정 필요. 메일 미도착 시 설정 확인.

**대안: Supabase 대시보드 수동 생성**

SMTP 미설정 등 시 수동 생성:

1. Supabase 대시보드 이동.
2. `Authentication > Users` 새 사용자 생성.
3. 동일 이메일 주소 사용.
4. 초기 비밀번호 설정.
5. 필요 시 `Auto Confirm` 활성화.

중요사항:

- `manager_email`과 Supabase Auth 계정 이메일 동일 필수.
- 불일치 시 manager 로그인 성공해도 봇 사용자 미연결.

### 3-3. 사용자: manager 로그인

1. 이메일/비밀번호로 `supabot-manager` 로그인.
2. 로그인 성공 시 봇 사용자 권한으로 대시보드 사용.

MFA 활성화 시 OTP 2차 인증 추가 필요.

## 4. 권장 운영 순서

신규 사용자 추가 권장 순서:

1. 사용자 텔레그램 `/start`
2. 관리자 확인 및 `active` 승인
3. 텔레그램 기능 확인
4. manager 필요 시 `manager_email` 설정
5. Supabase Auth 계정 생성
6. manager 로그인 확인
7. 필요 시 MFA 설정

텔레그램 사용자 식별자(`user_id`) 사전 생성되어야 manager 계정 연결 명확.

## 5. 자주 막히는 지점

### 텔레그램에서 `/start` 했는데 계속 대기 상태인 경우

- 사용자 `pending` 상태일 가능성 높음.
- manager 사용자 화면에서 `active` 상태 확인.

### manager 로그인이 안 되는 경우

확인 순서:

1. Supabase Auth 계정 생성 여부.
2. 로그인 이메일과 `manager_email` 값 동일 여부.
3. 비밀번호 일치 여부.
4. manager의 Supabase 프로젝트 참조 여부.

### manager는 로그인되는데 원하는 사용자 데이터가 안 보이는 경우

- `manager_email` 오연결 가능성 높음.
- 타 사용자에 동일 이메일 중복 연결 확인.

### MFA 때문에 로그인 진행이 안 되는 경우

- MFA 설정/비활성화 UI 대시보드 내 위치.
- OTP 앱 코드 필요 여부 확인.
- 관리자 MFA 운영 정책 별도 안내.

## 6. 운영 체크리스트

- 텔레그램 `/start` 사용자 사전 생성 완료
- 사용자 상태 `active` 확인
- 거래소 키 등록 전 승인 정책 결정
- manager 필요 시 `manager_email` 설정 완료
- 동일 이메일 Supabase Auth 계정 생성 완료
- 로그인 및 MFA 동작 실증 완료

## 7. 문서 위치

- 전체 소개/배포: [README.md](/E:/apps/supabot/README.md)
- manager 배포/운영: [manager/README.md](/E:/apps/supabot/manager/README.md)
