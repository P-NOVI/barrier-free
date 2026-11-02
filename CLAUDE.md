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
| `pipeline/` | 설치 | `uv sync` |
| `pipeline/` | DEM 생성 (원본은 `data/raw/dem/`) | `uv run python steps/00_build_dem.py` |
| `pipeline/` | 린트 · 포맷 | `uv run ruff check .` · `uv run ruff format .` |

- Python 도구는 uv + ruff + pytest로 통일한다. pip, poetry, black은 쓰지 않는다.
- 프론트 도구는 npm + ESLint + Prettier + Vitest로 통일한다. yarn, pnpm은 쓰지 않는다.
- `uv run fastapi dev`는 `fastapi[standard]`가 설치되어 있어야 한다.

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
- 네이버 Client Secret, S-DoT API 키, `DATABASE_URL`, `SECRET_KEY`는 백엔드에서만 쓴다.
- 키·URL·경로·매직 넘버는 코드에 직접 쓰지 않고 설정이나 환경변수로 분리한다.
## 건드리지 않는 것

- `data/raw/`는 원본이므로 수정하거나 커밋하지 않는다.
- `data/processed/`와 `models/*.pkl`은 직접 편집하지 않는다. `pipeline/`, `ml/`로 다시 생성한다.
- `package-lock.json`, `uv.lock`은 직접 편집하지 않는다. 설치 명령으로만 바꾼다.
- `*.db` 파일은 커밋하지 않는다.

## 외부 데이터 · API

- OpenStreetMap 기반 데이터를 쓰는 화면에는 `© OpenStreetMap contributors` 출처 표기를 유지한다.
- S-DoT, 네이버 지도·검색·Geocoding API는 백엔드를 거쳐 호출한다. 프론트에서 비밀 키로 직접 호출하지 않는다.
- 테스트는 외부 API를 실제로 호출하지 않고 mock을 쓴다.
