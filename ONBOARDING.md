# 팀원 온보딩

저장소를 처음 받은 팀원이 개발 환경을 맞추고 첫 작업을 시작하기까지의 순서입니다.
규칙의 상세 내용은 [CLAUDE.md](CLAUDE.md)에 있습니다. Claude Code도 이 파일을 자동으로 읽습니다.

## 1. 준비물

| 도구 | 용도 | 확인 명령 |
| --- | --- | --- |
| Git | 버전 관리 | `git --version` |
| Node.js (LTS) + npm | frontend | `node --version` |
| uv | backend (Python 3.12을 자동으로 받아 줌) | `uv --version` |
| GitHub 계정 | P-NOVI 조직 초대 수락 필요 | |
| GitHub CLI (선택) | 이슈·PR을 터미널에서 | `gh --version` |

uv 설치: `winget install --id astral-sh.uv`

## 2. 저장소 받기

```powershell
git clone https://github.com/P-NOVI/barrier-free.git
cd barrier-free
git switch dev
```

작업은 항상 `dev`에서 시작합니다. `main`과 `dev`에는 직접 push하지 않습니다.

## 3. backend 실행

```powershell
cd backend
uv sync
Copy-Item .env.example .env
uv run fastapi dev
```

- http://127.0.0.1:8000/health 에서 `{"status":"ok"}`가 나오면 성공입니다.
- Python은 루트의 `.python-version`(3.12)을 uv가 읽어 자동으로 설치합니다. 직접 설치하지 않아도 됩니다.
- 테스트와 린트: `uv run pytest` · `uv run ruff check .` · `uv run ruff format .`

## 4. frontend 실행

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

- 터미널에 나온 주소(보통 http://localhost:5173)에서 화면이 뜨면 성공입니다.
- 테스트와 린트: `npm run test` · `npm run lint` · `npm run format`

## 5. 환경변수

- `.env`는 커밋하지 않습니다. 값이 필요한 키는 팀 채널에서 받습니다.
- 새 키를 추가하면 같은 폴더의 `.env.example`에 키 이름만 적습니다. 값은 비웁니다.

## 6. 데이터 (pipeline 담당만)

backend·frontend 개발에는 필요 없습니다. 서버가 읽는 `data/processed/graph.json.gz`는 Git에 들어 있어 `git pull`이면 됩니다.

DEM·도로망 같은 큰 원본·중간 데이터는 Git 대신 팀 Google Drive 공유 폴더(링크는 팀 채널)에 둡니다.

```
공유 폴더/
├── raw/dem/        등고선 5000/, 표고 5000/, seoul_dem_5m.tif
└── interim/        walk.graphml, walk_elevation.graphml, walk_tagged.graphml
```

- 데이터를 새로 만들거나 고치는 사람은 한 명(데이터 담당)으로 정합니다. 여러 명이 같은 파일을 바꾸면 Drive에 충돌 사본이 생깁니다.
- DB는 이 폴더에 두지 않습니다.
- 필요한 것만 받으면 됩니다. graph.json.gz를 다시 만들기만 하려면 `interim/walk_tagged.graphml`(약 300MB) 하나면 되고, 경사를 다시 계산하려면 `raw/dem/seoul_dem_5m.tif`와 `interim/walk.graphml`이 필요합니다.

### 데이터 가져오기 (둘 중 하나)

**A. 직접 내려받기** — 가끔 쓰는 경우

1. 공유 폴더에서 `raw/`, `interim/`을 내려받아 저장소의 `data/` 아래에 같은 구조로 넣습니다. (`data/raw/dem/...`, `data/interim/...`)
2. `pipeline/.env`의 `DATA_DIR`은 비워 둡니다. 비어 있으면 저장소의 `data/`를 씁니다.

**B. Google Drive 데스크톱** — 자주 쓰거나 데이터를 만드는 경우

1. [Google Drive 데스크톱](https://www.google.com/drive/download/)을 설치하고 로그인합니다.
2. 웹에서 공유 폴더를 열고 **바로가기 추가 → 내 드라이브**를 누릅니다. (공유받은 폴더는 이렇게 해야 PC에 보입니다)
3. 탐색기의 Google Drive(보통 `G:`)에서 그 폴더를 우클릭 → **오프라인 사용 가능**으로 설정합니다.
4. `pipeline/.env`에 폴더 경로를 적습니다.
   ```
   DATA_DIR=G:\내 드라이브\공유폴더이름
   ```
   Mac은 `~/Library/CloudStorage/GoogleDrive-계정/내 드라이브/공유폴더이름` 형태입니다.

### 한 번에 실행

```powershell
cd pipeline
uv sync
Copy-Item .env.example .env   # 처음 한 번
uv run python steps/run_all.py
```

- 최종 결과(graph.json.gz)에 필요한 단계만 실행합니다. `interim/walk_tagged.graphml`이 있으면 04 단계(1분 정도)만 실행하고, 이미 graph.json.gz가 있으면 아무것도 하지 않습니다.
- 다시 만들려면 `--from 02`(02 단계부터) 또는 `--force`(전부)를 붙입니다.
- 필요한 파일이 없으면 어떤 파일이 어디 없는지 알려 줍니다.

## 7. 첫 작업 시작하기

1. GitHub에서 이슈를 만듭니다. (feat / fix / 기타 템플릿 선택, 제목 앞의 `[#번호]`는 자동으로 붙음)
2. `dev`를 최신으로 받고 브랜치를 만듭니다.
   ```powershell
   git switch dev
   git pull origin dev
   git switch -c feat/12-login
   ```
   브랜치 이름은 `타입/이슈번호-설명`입니다.
3. 커밋 메시지는 `<gitmoji> <type>: <내용>` 형식입니다. 예: `✨ feat: 로그인 화면 추가`
4. push 후 PR을 올립니다. base는 `dev`, 본문에 `Closes #12`를 씁니다.
5. 리뷰어 1명이 승인하면 **Squash and merge** 합니다. 이슈는 자동으로 닫힙니다.
6. 머지 후 브랜치를 지우고 `dev`를 최신화합니다.

## 8. Claude Code로 작업할 때

- 저장소 루트에서 실행하면 `CLAUDE.md`가 자동으로 적용됩니다.
- 개인 설정은 `.claude/settings.local.json`에 둡니다. 커밋되지 않습니다.

## 9. 자주 막히는 곳

| 증상 | 원인과 해결 |
| --- | --- |
| `uv add`가 pyyaml 빌드에서 실패 | uv가 Python 3.12가 아닌 다른 버전을 쓰는 경우입니다. 루트에 `.python-version`이 있는지, `backend/.venv`를 지우고 `uv sync` 했는지 확인합니다. |
| `npm install`에서 typescript 충돌(ERESOLVE) | `typescript-eslint`가 TS 6.1 미만만 지원합니다. `package.json`의 `typescript`가 `~6.0.x`인지 확인합니다. `--force`는 쓰지 않습니다. |
| PowerShell에서 `uv add fastapi[standard]` 오류 | 따옴표로 감쌉니다: `uv add "fastapi[standard]"` |
| `fastapi: program not found` | `backend/`에서 `uv sync`를 먼저 실행합니다. |
| PR 본문 템플릿이 비어 있음 | 템플릿은 `main`에 있어야 보입니다. `dev`가 `main`과 같은지 확인합니다. |
