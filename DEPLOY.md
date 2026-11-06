# 배포 (Vercel)

프론트와 백엔드를 같은 저장소에서 Vercel 프로젝트 두 개로 올린다. 화면은 프론트 프로젝트 주소 하나로 열고, `/api` 요청은 프론트 프로젝트가 백엔드 프로젝트로 넘긴다(`frontend/vercel.json`). 화면과 API 주소가 같아 로그인 쿠키가 막히지 않는다.

| 프로젝트 | Root Directory | 설정 파일 |
| --- | --- | --- |
| 프론트 | `frontend` | `frontend/vercel.json` |
| 백엔드 | `backend` | `backend/vercel.json`, `backend/pyproject.toml` 의 `[tool.vercel]` |

## 1. 앱 DB (Supabase)

수집 DB와 다른 Supabase 프로젝트로 만든다. 두 DB 모두 Alembic 기록을 `alembic_version` 테이블에 남겨 같은 DB에 두면 섞인다.

1. Supabase 에서 New project (리전 Seoul).
2. Connect → Session pooler 주소를 복사하고 맨 앞을 `postgresql+psycopg://` 로, `[YOUR-PASSWORD]` 를 비밀번호로 바꾼다.
3. 로컬 `backend/.env` 의 `DATABASE_URL` 에 넣고 `backend/` 에서 `uv run alembic upgrade head`.

## 2. 백엔드 프로젝트

1. Vercel 에서 같은 저장소로 새 프로젝트를 만든다. 이름은 `barrier-free-backend` 로 한다. 프론트 `vercel.json` 이 `https://barrier-free-backend.vercel.app` 로 넘기므로, 이름이 다르면 그 주소도 바꾼다.
2. Root Directory 는 `backend`. Settings → Build and Deployment 의 "Include files outside the root directory in the Build Step" 을 켠다. 빌드 스크립트(`backend/scripts/vercel_build.py`)가 루트 `data/processed` 를 `backend/vercel_data` 로 복사한다.
3. Environment Variables 에 넣는다. 비밀 값은 Sensitive 로 표시한다.

| 이름 | 값 |
| --- | --- |
| `GRAPH_PATH` | `vercel_data/graph.json.gz` |
| `ENTRANCES_PATH` | `vercel_data/entrances.json.gz` |
| `SITES_PATH` | `vercel_data/sites.json.gz` |
| `SENSORS_PATH` | `vercel_data/sdot_sensors.json` |
| `DATABASE_URL` | 1번 앱 DB 주소 |
| `COLLECTOR_DATABASE_URL` | 수집 DB 주소 |
| `KAKAO_REST_API_KEY`, `SDOT_API_KEY`, `KMA_API_KEY` | 팀 채널 |
| `KAKAO_CLIENT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | 팀 채널 |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | 제보 사진 저장(비공개 버킷 `report-photos`) |
| `ADMIN_ACCOUNTS` | 관리자 계정 (`kakao:1234,google:5678`) |
| `FRONTEND_URL`, `OAUTH_REDIRECT_BASE_URL` | 프론트 주소 (`https://<프론트>.vercel.app`) |
| `ALLOWED_ORIGINS` | `["https://<프론트>.vercel.app"]` |
| `AUTH_COOKIE_SECURE` | `true` |

4. 배포 후 `https://barrier-free-backend.vercel.app/health` 와 `/health/db` 가 `{"status":"ok"}` 인지 본다. 첫 요청은 그래프를 읽느라 10초 정도 걸린다.

## 3. 프론트 프로젝트

1. Root Directory 는 `frontend`, Framework 는 Vite.
2. 다시 배포한 뒤 화면에서 경로 찾기가 되는지 본다.

## 4. 로그인 콜백 등록

카카오·구글 개발자 콘솔에 프론트 주소의 콜백을 추가한다.

- `https://<프론트>.vercel.app/api/auth/kakao/callback`
- `https://<프론트>.vercel.app/api/auth/google/callback`

## 그래프를 바꾼 뒤

`data/processed/graph.json.gz` 가 바뀐 `main` 이 배포되면 제보 길 번호를 맞춘다. 로컬 `backend/.env` 의 `DATABASE_URL` 을 앱 DB 로 두고 `backend/` 에서 `uv run python -m app.resnap_reports`.
