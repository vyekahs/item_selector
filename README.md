# itemSelector — Infra Skeleton

중국 소싱 기회 발굴 도구의 인프라 베이스라인입니다. 이 저장소에 들어 있는 코드는
모두 **Infra Agent 범위** (docker-compose 골격, 헬스체크, 빈 스켈레톤) 이며
비즈니스 로직은 후속 에이전트 (Database / Data Collection / Scoring / Backend API /
Frontend) 가 채웁니다.

전체 맥락은 다음 문서를 참고하세요.

- `기획서.md` — 제품 기획
- `개발_에이전트_구성.md` — 에이전트별 담당 범위와 순서

---

## 0. 사전 준비

- Docker Desktop (Compose v2 포함) 또는 docker engine + compose 플러그인
- macOS/Linux 셸 (smoke test 는 `bash` 필요)

```bash
cp .env.example .env   # 그대로 두면 개발 기본값으로 동작
```

---

## 1. 서비스 구성

| 서비스     | 역할                          | 내부 포트 | 호스트 노출                 |
|-----------|-------------------------------|----------|----------------------------|
| `postgres`| PostgreSQL 16                 | 5432     | dev 오버레이 시 5432        |
| `redis`   | Redis 7 (appendonly)          | 6379     | dev 오버레이 시 6379        |
| `api`     | FastAPI (`/health`)           | 8000     | dev 오버레이 시 8000        |
| `web`     | Next.js 14 (App Router, TS)   | 3000     | dev 오버레이 시 3000        |
| `nginx`   | 리버스 프록시                  | 80       | **80 (기본)**              |

- 네트워크: `itemselector_net` (bridge) 단일
- `nginx` 라우팅
  - `/`      → `web:3000`
  - `/api/*` → `api:8000/*` (`/api` 프리픽스 제거)
  - `/health`→ `api:8000/health` (smoke 용 숏컷)
- 영속 볼륨: `postgres_data`, `redis_data`
- 모든 서비스 `restart: unless-stopped`

---

## 2. 실행

### 2.1 프로덕션 모드 (nginx 경유만 노출)

```bash
docker compose up -d --build
# 확인
curl -i http://localhost/health     # {"status":"ok"}
curl -I http://localhost/           # 200 from Next.js
docker compose ps                   # 모든 서비스 healthy
docker compose down                 # 종료 (볼륨 유지)
docker compose down -v              # 종료 (볼륨 삭제)
```

### 2.2 개발 모드 (핫 리로드 + 포트 직접 노출)

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
# 엔드포인트
#   http://localhost:8000/health   (FastAPI 직결, --reload)
#   http://localhost:3000          (Next.js dev server)
#   http://localhost               (nginx 경유)
```

- `backend/app/` 와 `frontend/` 가 바인드 마운트되어 코드 수정이 즉시 반영됩니다.
- 개발 모드에서 api 는 `Dockerfile` 의 `builder` 스테이지(= uv 포함)를 사용합니다.

---

## 3. 테스트

### 3.1 End-to-end 스모크 (Docker 필요)

```bash
bash scripts/smoke_test.sh
```

스크립트가 수행하는 것:

1. `docker compose up -d --build`
2. 서비스 `healthy` 대기 (최대 `WAIT_TIMEOUT` 초, 기본 180)
3. `docker compose exec postgres pg_isready`
4. `docker compose exec redis redis-cli ping` == `PONG`
5. `GET http://localhost/health` → 200 + `{"status":"ok"}`
6. `GET http://localhost/`        → 200
7. 성공/실패 여부와 무관하게 `docker compose down -v` 로 정리
   (실패 시에만 각 컨테이너 로그를 먼저 덤프)

### 3.2 Backend 단위 테스트 (pytest, Docker 불필요)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

### 3.3 Frontend 단위 테스트 (vitest, Docker 불필요)

```bash
cd frontend
pnpm install           # 또는 npm install / yarn
pnpm test              # vitest run (단발)
```

### 3.4 통합 테스트 + E2E + CI

cross-agent 통합 테스트·Playwright E2E·CI 파이프라인에 대한 상세한 안내는
[`docs/testing.md`](docs/testing.md) 참고. 한 줄 요약:

```bash
# 로컬에서 CI와 동일한 파이프라인 재현
bash scripts/ci-test.sh
```

---

## 4. 환경 변수

전체 목록과 설명은 `.env.example` 를 참고하세요. 주요 그룹:

- `POSTGRES_*`, `DATABASE_URL`
- `REDIS_*`, `REDIS_URL`
- `API_*`, `NEXT_PUBLIC_API_BASE_URL`, `INTERNAL_API_BASE_URL`
- `NAVER_SEARCHAD_*`, `NAVER_OPENAPI_*`
- `COUPANG_PARTNERS_*`
- `CUSTOMS_API_KEY`, `HS_CODE_API_KEY`, `EXIM_BANK_API_KEY`
- `YOUTUBE_API_KEY`
- `USE_MOCK_CLIENTS` (Mock 클라이언트 사용 여부, Data Collection Agent 가 참조 예정)

`.env` 는 gitignore 되어 있으며, compose 는 루트의 `.env` 를 자동으로 로드합니다.

---

## 5. 다음 에이전트 인수 체크리스트

- **Database Agent**: `postgres` 서비스 연결 문자열은 `DATABASE_URL`. Alembic/모델 작업은
  `backend/app/` 아래에서 수행하되, `backend/Dockerfile` 은 건드릴 필요가 없습니다.
- **Data Collection / Scoring / Backend API Agent**: `backend/app/main.py` 에 이미
  `app = FastAPI(...)` 인스턴스가 있습니다. 라우터는 `app.include_router(...)` 로 붙이세요.
- **Frontend Agent**: `frontend/app/` 가 Next.js App Router 엔트리입니다.
  API 호출은 브라우저에선 `NEXT_PUBLIC_API_BASE_URL`, 서버사이드에선
  `INTERNAL_API_BASE_URL` 을 사용합니다.
- **Scheduler Agent**: `docker-compose.yml` 에 `scheduler` 서비스가 아직 없습니다.
  동일한 네트워크 (`itemselector_net`) 에 새 서비스로 추가하고 `depends_on` 에
  `postgres`/`redis` 를 healthy 조건으로 넣으면 됩니다.

---

## 6. 범위 밖

이 디렉토리의 Infra Agent 작업물에는 의도적으로 포함되지 않은 것:

- DB 스키마, Alembic, SQLAlchemy 모델 → Database Agent
- 외부 API 클라이언트 / Mock → Data Collection Agent
- 점수 엔진, 수익 계산 → Scoring Engine Agent
- FastAPI 라우터·서비스 레이어 → Backend API Agent
- 실제 대시보드 UI, 차트, API 클라이언트 → Frontend Agent
- 배치 워커 컨테이너 → Scheduler Agent
- Cloudflare Tunnel, 백업 스크립트 → 운영 단계에서 추가
