# barrier-free

신체적 이동 제약이 있는 교통약자(휠체어·목발·보행 보조기 사용자, 고령자, 유모차 이용자, 임산부 등)를 위한 맞춤형 이동 경로를 제공하는 서비스.

## 구성

폴더 구조는 개발 중 자주 바뀌므로 최상위 역할만 적는다. 세부는 코드를 직접 확인한다.

- `frontend/` — React + Vite + TypeScript PWA (Vercel 배포)
- `backend/` — FastAPI, Python 3.12
- `data/` · `ml/` · `pipeline/` — 데이터 전처리와 AI 학습 (Python, 배포하지 않음)
- `docs/` — 기획서, 발표 자료, 데이터 출처

## 명령어

각 폴더(`frontend/`, `backend/`, `pipeline/`)에서 실행한다. 실제 스크립트와 다르면 이 파일을 먼저 고친다.

| 위치 | 용도 | 명령어 |
| --- | --- | --- |
| `frontend/` | 실행 | `npm run dev` |
| `frontend/` | 설치 · 빌드 | `npm ci` · `npm run build` |
| `frontend/` | 린트 · 포맷 · 테스트 | `npm run lint` · `npm run format` · `npm run test` |
| `backend/` | 실행 | `uv run fastapi dev` |
| `backend/` | 설치 | `uv sync` |
| `backend/` | 린트 · 포맷 | `uv run ruff check .` · `uv run ruff format .` |
| `backend/` | 테스트 | `uv run pytest` |
| `backend/` | 앱 DB 테이블 최신화 (`dev`를 받은 뒤) | `uv run alembic upgrade head` |
| `backend/` | 모델을 바꾼 뒤 마이그레이션 만들기 | `uv run alembic revision --autogenerate -m "설명"` (수집 DB는 `-n collector`) |
| `pipeline/` | 설치 | `uv sync` |
| `pipeline/` | 전체 실행 (결과 있는 단계는 건너뜀) | `uv run python steps/run_all.py` · `--from 02` · `--force` |
| `pipeline/` | 학습셋 갱신 (수집 DB 유동인구 반영, 16 → 13 순서) | `uv run python steps/16_export_sdot_realtime.py` · `uv run python steps/13_build_training_set.py` |
| `pipeline/` | 테스트 | `uv run pytest` |
| `pipeline/` | 린트 · 포맷 | `uv run ruff check .` · `uv run ruff format .` |
| `ml/` | 설치 | `uv sync` |
| `ml/` | 검증 (walk-forward · 최종 테스트) | `uv run python -m foot_traffic.walk_forward` · `--skip-final` · `--final-only` |
| `ml/` | 서비스 모델 학습 · 공유 폴더 저장 (검증 후) | `uv run python -m foot_traffic.train` |
| `ml/` | 예측 (실측 없는 날, 학습 불필요) | `uv run python -m foot_traffic.forecast --sensor 4015 --date 2026-10-27` |
| `ml/` | 매일 예측 배치 (학습셋 갱신 뒤, 수집 DB에 저장) | `uv run python -m foot_traffic.daily` · `--date 2026-11-06` |
| `ml/` | 배치 입력 파일을 Storage에 올리기 · 받기 | `uv run python -m foot_traffic.storage upload` · `download --dest 폴더` |
| `ml/` | 실측과 비교 (표 · 그래프 PNG) | `uv run python -m foot_traffic.predict --sensor 4015 --date 2026-10-17` |
| `ml/` | 테스트 | `uv run pytest` |
| `ml/` | 린트 · 포맷 | `uv run ruff check .` · `uv run ruff format .` |

- Python 도구는 uv + ruff + pytest로 통일한다. pip, poetry, black은 쓰지 않는다.
- 프론트 도구는 npm + ESLint + Prettier + Vitest로 통일한다. yarn, pnpm은 쓰지 않는다.
- `uv run fastapi dev`는 `fastapi[standard]`가 설치되어 있어야 한다.
- 테이블 모델(`app/models.py`, `app/collector/models.py`)을 바꾸면 같은 PR에 마이그레이션을 넣는다. 자동으로 만든 파일은 열어서 확인한다. 빠뜨리면 `tests/test_migrations.py`가 실패한다.
- `backend/alembic.ini`에는 한글을 쓰지 않는다. Alembic이 OS 기본 인코딩(cp949)으로 읽어 멈춘다.

## 코드 스타일

- 주석, 문서, 커밋, PR, 이슈는 한국어로 쓴다. 변수·함수·파일 이름은 영어로 쓴다.
- Python은 ruff 설정을 따르고 타입 힌트를 단다. 포맷은 ruff format이 정한다.
- TypeScript는 strict 모드를 유지하고, 포맷은 Prettier가 정한다. `any`로 타입 오류를 덮지 않는다.
- 들여쓰기는 4칸이다. TypeScript는 Prettier(`.prettierrc`), Python은 ruff가 맞춘다.
- 린트가 통과하지 않는 코드는 커밋하지 않는다.

## 브랜치

```
main   ← 배포용 (직접 push 금지)
 └─ dev   ← 통합 (직접 push 금지)
     └─ 타입/이슈번호-설명   예: feat/12-login
```

- 작업 브랜치는 항상 `dev`에서 분기한다.
- 이름은 `타입/이슈번호-설명`이다. 설명은 영어 소문자이고 단어는 `-`로 잇는다.

## 커밋

형식: `<gitmoji> <type>: <내용>` 예: `✨ feat: 로그인 화면 추가`

| 타입 | 설명 | gitmoji |
| --- | --- | --- |
| feat | 새로운 기능 추가 | ✨ |
| fix | 버그 수정 | 🐛 |
| docs | 문서 수정 | 📝 |
| style | 코드 포맷 변경, 코드 변경 없음 | 🎨 |
| refactor | 프로덕션 코드 리팩터링 | ♻️ |
| test | 테스트 추가·리팩터링, 프로덕션 코드 변경 없음 | ✅ |
| chore | 빌드·패키지·설정 변경, 프로덕션 코드 변경 없음 | 🔧 |

## 이슈-PR 워크플로

1. 이슈를 먼저 만든다. 템플릿은 feat, fix, 문서·리팩터링·기타 3종이다. 제목 앞의 `[#번호]`는 Action이 붙인다.
2. `dev`를 최신으로 받고 작업 브랜치를 만든다.
3. 작업 브랜치를 push하고 PR을 올린다. base는 `dev`, 본문에 `Closes #번호`를 쓴다.
4. 리뷰어 1명 이상이 승인하면 `dev`에 **Squash and merge** 한다. Action이 `Closes` 이슈를 닫는다.
5. `dev` → `main` 배포 PR은 **Create a merge commit**으로 머지한다. Squash는 쓰지 않는다.
6. 머지 후 작업 브랜치를 지우고 로컬 `dev`를 최신화한다.

- PR 하나에는 이슈 하나만 담는다.
- GitHub 기본 기능은 `main`으로 머지될 때만 이슈를 닫는다. `dev` 머지에서 닫히는 것은 `close-issue-on-dev-merge` Action 덕분이다.
- 이슈·PR 템플릿과 Action은 `.github/`에 있다.

## 환경변수

- `.env`와 키 파일의 내용은 출력하거나 커밋하지 않는다. `.gitignore`에 둔다.
- 새 환경변수를 추가하면 같은 폴더의 `.env.example`에 키 이름만 추가한다. 값은 비운다.
- `VITE_`로 시작하는 프론트 환경변수는 브라우저에 노출된다. 비밀 값을 넣지 않는다.
- 카카오 REST API 키, S-DoT API 키, `DATABASE_URL`, `SECRET_KEY`는 백엔드에서만 쓴다. 카카오 JavaScript 키(`VITE_KAKAO_MAP_APP_KEY`)는 등록 도메인에서만 동작하므로 프론트에 둔다.
- 키·URL·경로·매직 넘버는 코드에 직접 쓰지 않고 설정이나 환경변수로 분리한다.
## 건드리지 않는 것

- `data/raw/`는 원본이므로 수정하거나 커밋하지 않는다.
- pipeline 원본·중간 데이터(`raw/`, `interim/`)는 `pipeline/.env`의 `DATA_DIR`(팀 Google Drive 공유 폴더) 기준이다. 비어 있으면 저장소 `data/`를 쓴다. 공유 폴더 링크는 저장소에 적지 않는다.
- `data/processed/`와 `models/*.pkl`은 직접 편집하지 않는다. `pipeline/`, `ml/`로 다시 생성한다.
- `package-lock.json`, `uv.lock`은 직접 편집하지 않는다. 설치 명령으로만 바꾼다.
- `*.db` 파일은 커밋하지 않는다.
- `dev`에 머지된 마이그레이션 파일(`backend/migrations/*/versions/`)은 고치지 않는다. 바꿀 내용은 새 마이그레이션으로 만든다.
- 공용 수집 DB(Supabase)에는 직접 `upgrade` 하지 않는다. 수집 워크플로가 `dev`의 마이그레이션을 적용한다.

## 외부 데이터 · API

- OpenStreetMap 기반 데이터를 쓰는 화면에는 `© OpenStreetMap contributors` 출처 표기를 유지한다.
- 지도는 카카오맵 JavaScript SDK로 띄운다. S-DoT, 카카오 로컬(주소·장소 검색) API는 백엔드를 거쳐 호출한다. 프론트에서 비밀 키로 직접 호출하지 않는다.
- 테스트는 외부 API를 실제로 호출하지 않고 mock을 쓴다.
