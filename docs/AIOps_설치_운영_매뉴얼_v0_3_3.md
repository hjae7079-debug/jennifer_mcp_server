# AI-Ops 설치·운영 매뉴얼 (v0.3.2)

대상: GPU PC(Ubuntu 24.04.5) 설치 담당자
목적: 인터넷망에서 설치·검증 → 폐쇄망 전환 → 연동 → 기능 구현까지 해야 할 일을 순서대로 정리

---

## 0. 원칙

1. **각 단계마다 로그를 남깁니다.** 모든 명령은 `tee`로 기록합니다.
2. **실패하면 다음 단계로 가지 않습니다.** 실패 로그를 보고서로 묶어 보내 주세요.
3. **비밀값은 보내지 않습니다.** `.env`의 값, 토큰, 비밀번호는 제가 필요 없습니다. 보고서 스크립트가 가려 주지만, 보내기 전에 한 번 열어 보세요.
4. **순서를 바꾸지 않습니다.** 특히 폐쇄망 전환 전에는 외부 접속 차단을 확인하기 전까지 끝내지 않습니다.

로그 폴더를 먼저 만듭니다.
```bash
sudo install -d -m 0750 /backup/aiops-install/logs
```

---

## 1. 전체 작업 순서

| 단계 | 작업 | 주요 명령 | 결과 파일 (나에게 전달) |
|---|---|---|---|
| A | 외부 통신 확인 | 4장 | A 결과 (화면 출력 복사) |
| B | 패키지 번들 받기 | `bundle-apt.sh` | `skipped.txt` |
| C | 기반 설치 | 5장 | 단계별 로그 |
| D | 설치 검증 | `70-healthcheck.sh`, `85-test-llm.sh` | 보고서 ZIP |
| E | 오프라인 번들 생성 | `build-offline-caches.sh` | `SHA256SUMS` 목록 |
| F | 폐쇄망 전환 | 6장 | 전환 후 보고서 ZIP |
| G | 연동 샘플 수집 | 7장 | 마스킹된 샘플 |
| H | 기능 구현·활성화 | 제가 진행 | — |

---

## 2. 결과 보고서 만드는 법 (모든 단계 공통)

문제가 생기거나 검증이 끝나면 아래 명령으로 보고서를 만듭니다.

```bash
cd aiops
sudo bash scripts/collect-report.sh
```

완료되면 다음 파일이 생깁니다.
`/backup/aiops-install/report/<시각>.zip`

**이 ZIP 한 개를 대화에 첨부해 주세요.** 포함되는 내용은 다음과 같습니다.
- 호스트 상태(OS, 마운트, 디스크, 네트워크)
- GPU 상태(`nvidia-smi`)
- 설치된 관련 패키지 목록
- Docker 버전, 컨테이너 상태, 이미지 목록, 최근 로그
- 헬스체크와 LLM 테스트 결과
- `.env`의 **키 이름만** (값은 `<값 제외>`)

---

## 3. 준비 파일

패키지 `aiops_integrated_dashboard_v0_3_2.zip`을 `/data/aiops/`에 풉니다. 체크섬을 먼저 확인합니다.
```bash
sha256sum aiops_integrated_dashboard_v0_3_2.zip
cat aiops_integrated_dashboard_v0_3_2_zip.sha256
```
두 값이 같으면 풉니다.
```bash
sudo mkdir -p /opt/aiops && sudo unzip -q aiops_integrated_dashboard_v0_3_2.zip -d /opt/
cd /opt/aiops
sudo cp .env.example .env
```

---

## 4. A단계: 외부 통신 확인 (NAT 열린 뒤)

```bash
for u in https://registry-1.docker.io/v2/ https://ghcr.io/v2/ https://ollama.com \
         https://pypi.org/simple/ https://registry.npmjs.org/ \
         http://archive.ubuntu.com/ubuntu/ https://download.docker.com/linux/ubuntu/gpg \
         https://nvidia.github.io/libnvidia-container/gpgkey; do
  printf "%-62s " "$u"; curl -s -o /dev/null -m 10 -w "%{http_code}\n" "$u" || echo "FAIL"
done
```
- 응답 코드가 `200`, `401`, `301` 등으로 나오면 통과입니다. `FAIL`이 있으면 해당 목적지를 NAT에서 열어 주세요.
- `registry-1.docker.io`는 `401`이 정상입니다(인증 요구).

---

## 5. B~D단계: 설치 순서

### 5.1 패키지 번들 받기 (NAT 열린 상태)
```bash
sudo bash scripts/bundle-apt.sh 2>&1 | sudo tee /backup/aiops-install/logs/bundle-apt.log
```
- 끝나면 `/backup/aiops-install/apt/skipped.txt`를 확인합니다. 저장소에 없는 항목만 들어 있으면 정상입니다.

### 5.2 기본 호스트 점검과 준비
```bash
sudo bash scripts/00-preflight.sh     2>&1 | sudo tee /backup/aiops-install/logs/00.log
sudo bash scripts/10-prepare-host.sh  2>&1 | sudo tee /backup/aiops-install/logs/10.log
sudo bash scripts/20-setup-storage.sh 2>&1 | sudo tee /backup/aiops-install/logs/20.log
sudo bash scripts/30-install-nvidia-container-toolkit.sh 2>&1 | sudo tee /backup/aiops-install/logs/30.log
```
- `00`에서 실패하면 멈추고 보고서를 보내 주세요. 마운트나 GPU 문제는 여기서 드러납니다.
- `20`은 디스크를 **포맷하지 않습니다.** 마운트 상태만 확인합니다.

### 5.2-1 Docker 저장 경로
`10-prepare-host.sh`가 Docker를 켜기 전에 `09-docker-data-root.sh`를 자동으로 실행합니다. Docker 이미지와 레이어는 `/data/docker`에 저장됩니다. 설치 전이라 옮길 데이터가 없으면 그대로 두면 됩니다.
- 확인: `docker info | grep "Docker Root Dir"` → `/data/docker`
- 기존 데이터를 옮길 때만: `sudo MIGRATE=1 bash scripts/09-docker-data-root.sh`
- `30-install-nvidia...`가 NVIDIA 설정을 넣은 뒤에도 두 항목(data-root, runtimes)이 남았는지 자동 확인합니다.

### 5.3 비밀값과 인증서
```bash
sudo bash scripts/06-init-secrets.sh 2>&1 | sudo tee /backup/aiops-install/logs/06.log
sudo bash scripts/07-gen-cert.sh     2>&1 | sudo tee /backup/aiops-install/logs/07.log
```
- `06` 실행 시 **대시보드 관리자 초기 비밀번호가 화면에 한 번만 나옵니다.** 바로 안전한 곳에 적어 두세요. 로그에도 남습니다. 로그 파일은 보고서에 넣지 마세요.
  - 로그가 걱정되면 `06` 실행 후 `sudo sed -i '/초기 비밀번호/d' /backup/aiops-install/logs/06.log`로 지워도 됩니다.

### 5.4 앱 빌드와 모델
```bash
sudo bash scripts/40-build-apps.sh      2>&1 | sudo tee /backup/aiops-install/logs/40.log
sudo bash scripts/60-download-models.sh 2>&1 | sudo tee /backup/aiops-install/logs/60.log
```
- `60`은 모델 용량이 커서 시간이 오래 걸립니다. 중간에 끊기면 같은 명령을 다시 실행하면 이어서 받습니다.

### 5.5 서비스 기동
```bash
sudo bash scripts/50-deploy-services.sh 2>&1 | sudo tee /backup/aiops-install/logs/50.log
```
- `.env`의 `DEPLOY_MODE=online`이어야 빌드와 pull이 됩니다. 확인하세요: `grep DEPLOY_MODE .env`

### 5.6 검증
```bash
sudo bash scripts/70-healthcheck.sh 2>&1 | sudo tee /backup/aiops-install/logs/70.log
sudo bash scripts/85-test-llm.sh    2>&1 | sudo tee /backup/aiops-install/logs/85.log
sudo bash scripts/collect-report.sh
```
- 마지막 명령의 보고서 ZIP을 보내 주세요. **이것이 설치 1차 결과입니다.**

---

## 6. F단계: 폐쇄망 전환

전환 전에 다음을 모두 확인합니다.
- [ ] 보고서 ZIP에서 모든 컨테이너가 `healthy` 또는 `running`인지
- [ ] `85` LLM 테스트가 응답을 주었는지
- [ ] 오프라인 번들을 만들었는지 (`build-offline-caches.sh`)

오프라인 번들:
```bash
sudo bash scripts/build-offline-caches.sh 2>&1 | sudo tee /backup/aiops-install/logs/offline-bundle.log
```
결과는 `/backup/aiops-offline/<날짜>/`에 생깁니다. `SHA256SUMS`를 함께 보관하세요.

### 전환 절차
1. `.env`에서 `DEPLOY_MODE=offline`, `WEB_BIND_IP=10.148.216.55`로 바꿉니다.
2. 네트워크 설정(`netplan`)을 폐쇄망 IP `10.148.216.55/26`, 게이트웨이 `10.148.216.1`로 바꿉니다.
3. NAT를 끊습니다.
4. **외부 차단 확인:** `sudo bash scripts/verify-offline.sh` (외부 접속이 되면 실패로 멈춥니다)
5. 재기동: `sudo bash scripts/50-deploy-services.sh`
6. 보고서를 다시 만들어 보내 주세요.

---

## 7. G단계: 연동 샘플 수집 (폐쇄망 이후)

샘플이 있어야 연동을 만들 수 있습니다. 샘플 수집은 폐쇄망에서만 가능합니다.

1. 연결 확인: 제니퍼 뷰서버(`10.148.222.57`, `10.148.232.57`, `10.148.232.59`), ITSM, SIEM에 접속되는지 확인합니다.
2. 제니퍼 전수 호출 (GET만 호출하고 쓰기 계열은 차단됩니다. 준비 중입니다.)
3. ITSM·SIEM 응답 샘플을 받습니다. 마스킹 후 `tests/fixtures/`에 저장합니다.
4. 보고서 ZIP과 샘플(마스킹된 것)을 보내 주세요.

---

## 8. 부분 실패 시 수동 설치

스크립트가 실패하면 아래 방법으로 직접 시도할 수 있습니다. 어려운 정도를 같이 표시했습니다.

| 구성 | 난이도 | 설명 |
|---|---|---|
| Docker, compose | 쉬움 | 공식 저장소 설치 |
| NVIDIA 컨테이너 툴킷 | 보통 | 런타임 설정 한 번 필요 |
| PostgreSQL, Redis, ClickHouse | 쉬움 | 컨테이너 한 개씩 실행 |
| Ollama (GPU 연결) | 보통 | GPU 인식이 핵심 |
| API, Worker 이미지 빌드 | 보통 | 패키지 설치 실패가 흔함 |
| Nginx TLS | 쉬움 | 설정 파일 그대로 사용 |
| 대시보드 빌드 | 보통 | Node.js 버전이 맞아야 함 |
| 연동 어댑터 수정 | 어려움 | 샘플과 개발이 필요 |

### 8.1 Docker 및 GPU 연결
```bash
docker info | head -20                      # 정상 설치 확인
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```
GPU 확인은 인터넷이 필요합니다. 공개 이미지가 있을 때만 실행하세요.
```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

### 8.2 인프라 컨테이너 (compose 없이 직접 실행)
```bash
source /opt/aiops/.env
docker network create aiops-backend 2>/dev/null || true

docker run -d --name aiops-postgres --network aiops-backend --restart unless-stopped \
  -e POSTGRES_DB=$POSTGRES_DB -e POSTGRES_USER=$POSTGRES_USER -e POSTGRES_PASSWORD=$POSTGRES_PASSWORD \
  -v /data/postgresql:/var/lib/postgresql/data pgvector/pgvector:pg16

docker run -d --name aiops-redis --network aiops-backend --restart unless-stopped \
  -v /data/redis:/data redis:7.4-alpine redis-server --appendonly yes

docker run -d --name aiops-ollama --network aiops-backend --restart unless-stopped --gpus all \
  -e OLLAMA_NUM_PARALLEL=2 -e OLLAMA_MAX_LOADED_MODELS=1 \
  -v /data/models/ollama:/root/.ollama ollama/ollama:0.12.6
```
- 직접 실행하면 `.env` 값을 손으로 넣어야 합니다. 실수가 생기기 쉬우니 가능하면 compose를 다시 시도하세요.
- 실행 후 `docker logs aiops-postgres --tail 20`으로 기동을 확인합니다.

### 8.3 모델 받기
```bash
docker exec aiops-ollama ollama pull qwen3:14b
docker exec aiops-ollama ollama pull bge-m3
docker exec aiops-ollama ollama list
```

### 8.4 API 이미지
```bash
cd /opt/aiops/apps/api
docker build --build-arg PIP_NO_INDEX=0 -t aiops-api:0.3.2 .
```
- `pip` 설치가 실패하면 원인 로그를 보고서로 보내 주세요. 폐쇄망이면 `PIP_NO_INDEX=1`을 씁니다.

### 8.5 Nginx (TLS)
```bash
docker run -d --name aiops-dashboard --network aiops-backend --restart unless-stopped \
  -p 10.148.216.55:18080:18080 -p 10.148.216.55:18081:18081 \
  -v /opt/aiops/config/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
  -v /opt/aiops/apps/web/dist:/usr/share/nginx/html:ro \
  -v /data/certs:/etc/nginx/certs:ro nginx:1.28-alpine
```
- 설치 기간에는 `-p 127.0.0.1:...`로 바꿔 외부 노출을 막으세요.

### 8.6 수동 설치가 어려운 이유
- **가장 어려운 부분은 GPU 연결과 Python 패키지 빌드입니다.** 둘 다 환경 차이에 민감합니다.
- 수동으로 한 단계씩 맞추면 시간이 오래 걸립니다. 실패 지점 하나만 고치고 싶다면 수동이 편합니다. 여러 곳이 동시에 틀리면 compose 재실행이 빠릅니다.
- **제 판단:** 인프라 컨테이너(8.2)와 모델(8.3)은 직접 해도 됩니다. GPU 인식(8.1)과 API 빌드(8.4)는 실패하면 로그를 보내 주세요. 그때 함께 고치겠습니다.

---

## 9. 어디에서 막혔는지 알려 주는 방법

1. 실패한 단계 번호와 로그 파일명을 알려 주세요. 예: `50.log`
2. 보고서 ZIP을 첨부하세요. `collect-report.sh`로 만든 파일입니다.
3. 화면에 나온 오류 문장을 그대로 복사해 주세요. 요약하지 말고 원문을 주시면 원인을 빨리 찾을 수 있습니다.

## 10. 체크리스트 요약

- [ ] A: 외부 통신 확인
- [ ] B: `bundle-apt.sh` 실행
- [ ] C: 00 → 10 → 20 → 30 → 06 → 07 → 40 → 60 → 50 실행
- [ ] D: 70, 85 실행 후 보고서 전달
- [ ] E: 오프라인 번들 생성
- [ ] F: 폐쇄망 전환 및 `verify-offline.sh`
- [ ] G: 제니퍼·ITSM·SIEM 샘플 수집
- [ ] H: 기능 구현 (제가 진행)
