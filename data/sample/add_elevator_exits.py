"""elevators.json 의 엘리베이터마다 가장 가까운 지하철 출구 번호(exit)를 넣는다.

실행: uv run --project backend python data/sample/add_elevator_exits.py [.env 경로]
- 카카오 키워드 검색으로 엘리베이터 근처의 '지하철출구' 장소를 찾는다. 키는 backend/.env 의
  KAKAO_REST_API_KEY 를 쓴다.
- EXIT_RADIUS_M 안에 출구가 없으면 exit 는 null 이다.
- make_elevators.py 처럼 임시 스크립트다.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
ELEVATORS = ROOT / "frontend" / "public" / "data" / "elevators.json"
ENV = ROOT / "backend" / ".env"
KAKAO_BASE_URL = "https://dapi.kakao.com"
KEYWORD_SEARCH_PATH = "/v2/local/search/keyword.json"
EXIT_CATEGORY = "지하철출구"
# 엘리베이터는 보통 출구 바로 옆에 있다. 이보다 먼 출구는 그 엘리베이터 출구로 보지 않는다.
EXIT_RADIUS_M = 50
EXIT_NUMBER = re.compile(r"(\d+(?:-\d+)?)번\s*출구")


def exit_number(documents: list[dict[str, Any]]) -> str | None:
    """거리순 검색 결과에서 가장 가까운 지하철 출구 번호"""
    for document in documents:
        if not document.get("category_name", "").endswith(EXIT_CATEGORY):
            continue
        match = EXIT_NUMBER.search(document["place_name"])
        if match:
            return match[1]
    return None


def find_exit(client: httpx.Client, position: list[float]) -> str | None:
    response = client.get(
        KEYWORD_SEARCH_PATH,
        params={
            "query": "출구",
            "x": position[0],
            "y": position[1],
            "radius": EXIT_RADIUS_M,
            "sort": "distance",
        },
    )
    response.raise_for_status()
    return exit_number(response.json()["documents"])


def main() -> None:
    env = Path(sys.argv[1]) if len(sys.argv) > 1 else ENV
    key = dotenv_values(env).get("KAKAO_REST_API_KEY")
    if not key:
        raise SystemExit(f"{env} 에 KAKAO_REST_API_KEY 가 없습니다.")
    elevators = json.loads(ELEVATORS.read_text(encoding="utf-8"))
    with httpx.Client(
        base_url=KAKAO_BASE_URL, headers={"Authorization": f"KakaoAK {key}"}
    ) as client:
        for elevator in elevators:
            elevator["exit"] = find_exit(client, elevator["position"])
    ELEVATORS.write_bytes(
        (json.dumps(elevators, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    found = sum(1 for elevator in elevators if elevator["exit"])
    print(f"출구 번호 {found}/{len(elevators)}건 -> {ELEVATORS}")


if __name__ == "__main__":
    main()
