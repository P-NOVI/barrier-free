import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path


@dataclass(frozen=True)
class Sensor:
    code: int
    position: tuple[float, float]
    address: str


@cache
def load_sensors(path: Path) -> dict[int, Sensor]:
    """sdot_sensors.json 을 센서 코드별로 읽는다. 같은 경로는 한 번만 읽는다."""
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        item["code"]: Sensor(
            code=item["code"],
            position=(item["lon"], item["lat"]),
            address=item["address"],
        )
        for item in document["sensors"]
    }
