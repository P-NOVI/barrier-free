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
- 장소 검색(`/api/places/search`)을 쓰려면 `.env`의 `KAKAO_REST_API_KEY`에 카카오 REST API 키를 넣습니다. 없으면 검색만 503으로 실패합니다.
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

## 6. 첫 작업 시작하기

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

## 7. Claude Code로 작업할 때

- 저장소 루트에서 실행하면 `CLAUDE.md`가 자동으로 적용됩니다.
- 개인 설정은 `.claude/settings.local.json`에 둡니다. 커밋되지 않습니다.

## 8. 자주 막히는 곳

| 증상 | 원인과 해결 |
| --- | --- |
| `uv add`가 pyyaml 빌드에서 실패 | uv가 Python 3.12가 아닌 다른 버전을 쓰는 경우입니다. 루트에 `.python-version`이 있는지, `backend/.venv`를 지우고 `uv sync` 했는지 확인합니다. |
| `npm install`에서 typescript 충돌(ERESOLVE) | `typescript-eslint`가 TS 6.1 미만만 지원합니다. `package.json`의 `typescript`가 `~6.0.x`인지 확인합니다. `--force`는 쓰지 않습니다. |
| PowerShell에서 `uv add fastapi[standard]` 오류 | 따옴표로 감쌉니다: `uv add "fastapi[standard]"` |
| `fastapi: program not found` | `backend/`에서 `uv sync`를 먼저 실행합니다. |
| PR 본문 템플릿이 비어 있음 | 템플릿은 `main`에 있어야 보입니다. `dev`가 `main`과 같은지 확인합니다. |
