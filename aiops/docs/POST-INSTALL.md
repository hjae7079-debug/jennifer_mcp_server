# 폐쇄망 이동 후 작업 순서

1. 로컬 콘솔에서 NIC와 Netplan을 확인합니다: `ip -br link`, `ip -br addr`, `ls /etc/netplan/`.
2. 기존 Netplan 파일을 `/backup/aiops-install/backups/`에 복사합니다.
3. 네트워크 담당자가 확인한 인터페이스에 `10.148.216.55/26`, gateway `10.148.216.1`을 설정합니다. 폐쇄망 DNS가 제공될 때만 DNS를 넣습니다.
4. `sudo netplan generate` → `sudo netplan try` → 연결 확인 후 `sudo netplan apply` 순서로 적용합니다.
5. `/data`와 `/backup` 마운트가 유지되는지 확인합니다. `/dev/sda`는 절대 포맷/재파티션하지 않습니다.
6. `sudo bash scripts/55-offline-install.sh`를 실행합니다. 이 스크립트는 이미지 로드 후 `--pull never --no-build`로 기동하며 폐쇄망에서 다운로드하지 않습니다.
7. `sudo bash scripts/70-healthcheck.sh`와 `sudo bash scripts/85-test-llm.sh`를 실행합니다.
8. 다른 내부 PC에서 `http://10.148.216.55:18080` 및 `http://10.148.216.55:18081` 접속을 확인합니다.
9. 관리자 계정은 Open WebUI 첫 화면에서 직접 생성하고, 기관 정책에 맞게 공개 가입을 제한합니다.
10. 실제 API를 제공받은 후 `.env`의 `HISTORY_INCIDENTS_URL`, `HISTORY_EVENTS_URL`을 설정하고 어댑터 필드 매핑을 검증합니다.

## 실행 관리
- 시작: `sudo bash scripts/51-start.sh`
- 중지: `sudo bash scripts/50-stop.sh`
- 상태: `bash scripts/52-status.sh`
- 로그: `bash scripts/53-logs.sh api` 또는 `worker`, `ollama`, `nginx`
- 백업: `sudo bash scripts/90-backup.sh`
- 일일 백업 타이머 설치: `sudo bash scripts/95-install-backup-timer.sh`
- 업데이트: `sudo bash scripts/54-update-online.sh` 안내를 따릅니다. 폐쇄망에서 `pull`이나 `build`를 하지 않습니다.
