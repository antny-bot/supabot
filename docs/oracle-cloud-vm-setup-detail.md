# Oracle Cloud VM 네트워크 설정 및 SSH 접속 상세 가이드

Oracle Cloud에서 생성한 VM에 안전하게 접속하기 위해 필요한 네트워크 설정과 SSH 접속 절차를 정리한 문서입니다.

## 1. 공인 IP 확인

기본 VNIC(Primary VNIC) 섹션에서 공용 IPv4 주소(Public IPv4 address)가 할당되어 있는지 확인합니다.

- 공용 IPv4 주소가 보이면 해당 IP를 메모해 둡니다.
- 이 IP는 나중에 SSH로 VM에 접속할 때 사용합니다.

## 2. 서브넷(Subnet) 설정으로 이동

같은 네트워킹 화면에서 서브넷(Subnet) 항목의 링크를 클릭합니다.

- 보통 `subnet-...` 형태의 이름으로 표시됩니다.
- 링크를 클릭하면 서브넷 상세 화면으로 이동합니다.

## 3. 보안 목록(Security List) 접근

서브넷 상세 화면에서 보안 목록(Security Lists)으로 이동합니다.

1. 서브넷 상세 화면의 리소스 영역에서 `Security Lists`를 클릭합니다.
2. 목록에 보이는 `Default Security List for ...` 링크를 클릭합니다.

## 4. 수신 규칙(Ingress Rules) 설정

이 단계에서는 외부에서 VM으로 들어오는 접속을 제한합니다. Supabot 운영 용도라면 일반적인 웹 포트(`80`, `443`)를 열 필요가 없으므로 SSH(`22`)만 최소한으로 허용하는 것이 안전합니다.

1. `Ingress Rules` 탭이 선택되어 있는지 확인합니다.
2. 대상 포트 범위(Destination Port Range)가 `22`인 규칙을 찾습니다.
3. 해당 규칙의 편집(Edit) 메뉴를 엽니다.
4. 소스 CIDR(Source CIDR)을 `0.0.0.0/0`에서 현재 작업 중인 PC의 공인 IP로 변경합니다.
5. 변경 사항을 저장합니다.

> 주의: 여기에 입력해야 하는 값은 VM의 공인 IP가 아니라, 현재 접속 중인 PC의 공인 IP입니다.

> 팁: 네이버나 구글에서 `내 아이피`를 검색한 뒤, 확인된 IP 뒤에 `/32`를 붙여 입력합니다. 예: `123.45.67.89/32`

필요 없는 다른 인바운드 포트가 열려 있다면 함께 정리하는 것이 좋습니다.

## 5. 송신 규칙(Egress Rules) 확인

Supabot이 텔레그램과 거래소 API로 요청을 보내야 하므로, 외부로 나가는 트래픽은 허용되어 있어야 합니다.

1. 왼쪽 메뉴에서 `Egress Rules`를 클릭합니다.
2. 대상(Destination)이 `0.0.0.0/0`인지 확인합니다.
3. 프로토콜이 `All Protocols`로 허용되어 있는지 확인합니다.

Oracle Cloud 기본 보안 목록에서는 보통 이 값이 기본 허용으로 설정되어 있습니다.

## 6. VM SSH 접속 및 다음 단계

네트워크 설정이 끝났다면 이제 VM에 SSH로 접속할 수 있습니다.

### 준비물

1. 앞에서 확인한 VM의 공인 IP
2. VM 생성 시 다운로드한 SSH Private Key 파일 (`.key` 또는 `.pem`)

### Windows에서 접속하는 방법

1. `cmd` 또는 PowerShell을 실행합니다.
2. 아래 명령어 형식으로 접속합니다.

```bash
ssh -i /path/to/your/private-key.key ubuntu@YOUR_VM_PUBLIC_IP
```

예시:

```bash
ssh -i C:\path\to\your-ssh-key.key ubuntu@<VM_PUBLIC_IP>
```

처음 접속할 때 아래와 같은 확인 문구가 나오면 `yes`를 입력하고 Enter를 누릅니다.

```text
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

정상적으로 접속되면 `ubuntu@...:~$` 형태의 프롬프트가 표시됩니다.

그 다음에는 별도 문서의 `VM 초기 설정` 단계로 진행하면 됩니다.
