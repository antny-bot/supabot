# Supabot Oracle Cloud Handoff

이 문서는 다른 컴퓨터에서 Oracle Cloud 배포 작업을 이어서 진행할 수 있도록 현재 상태를 정리한 handoff 문서입니다.

## 현재 Oracle Cloud 상태

- 인스턴스 이름: `supabot-vm-new`
- 상태: `실행 중`
- Region: `ap-chuncheon-1` (South Korea North / Chuncheon)
- Shape: `VM.Standard.E2.1.Micro`
- OS Image: `Canonical Ubuntu 24.04`
- 기본 SSH 사용자: `ubuntu`
- VCN: `supabot-vcn`
- 서브넷: `supabot-public-subnet`
- 서브넷 CIDR: `10.0.0.0/24`
- 퍼블릭 IP: `<VM_PUBLIC_IP>`
- 프라이빗 IP: `<PRIVATE_IP>`

## SSH 키 정보

보안상 private key 본문은 이 문서와 Git 저장소에 포함하지 않습니다.

- private key 로컬 경로: `C:\path\to\tmp_oracle_supabot_key`
- public key 로컬 경로: `C:\path\to\tmp_oracle_supabot_key.pub`
- public key fingerprint: `<YOUR_KEY_FINGERPRINT>`
- public key:

```text
<YOUR_SSH_PUBLIC_KEY>
```

다른 컴퓨터에서 이어서 작업하려면 위 private key 파일을 안전한 방식으로 별도 전달한 뒤, 파일 권한을 제한해서 사용하세요.

## Oracle 콘솔에서 실제 확인한 점

- 인스턴스 생성 위저드에서 `Public IP`가 비활성화되거나, 검토 화면에서는 켰는데 생성 후 빠져 있는 경우가 있었습니다.
- 이 경우 인스턴스 생성 후 `네트워킹 > 연결된 VNIC > IP 관리 > 작업 > 편집 > 임시 퍼블릭 IP`로 사후 할당할 수 있음을 확인했습니다.
- 이 프로젝트는 Telegram long polling 방식이라 기본적으로 `80`, `443` 인바운드가 필요하지 않습니다.
- SSH는 `22/tcp`만 열고, source는 현재 작업 중인 공인 IP `/32`로 제한하는 구성이 적합합니다.

## 이어서 해야 할 작업

1. 다른 컴퓨터에 private key를 안전하게 복사합니다.
2. Oracle 콘솔에서 NSG 또는 보안 목록을 확인합니다.
3. `22/tcp`가 현재 접속할 공인 IP `/32`로 제한되어 있는지 확인합니다.
4. `80`, `443`이 불필요하게 열려 있으면 닫습니다.
5. VM에 SSH 접속합니다.

```bash
ssh -i <private-key-path> ubuntu@<VM_PUBLIC_IP>
```

6. 서버에 레포를 반영합니다.
7. `scripts/setup_oracle_vm.sh` 실행 여부를 확인하거나 필요 시 다시 수행합니다.
8. `~/supabot/config/.env`에 `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`를 채웁니다.
9. `docker compose pull && docker compose up -d` 또는 `docker compose up -d --build`를 실행합니다.
10. `docker compose logs -f --tail=100`으로 기동 상태를 확인합니다.
11. Telegram에서 `/start` 스모크 테스트를 수행합니다.

## 참고 문서

- [oracle-cloud-vm-setup.md](oracle-cloud-vm-setup.md)
- [oracle-cloud-deploy-sequence.md](oracle-cloud-deploy-sequence.md)
