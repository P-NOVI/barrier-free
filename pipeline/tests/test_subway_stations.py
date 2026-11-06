import importlib.util
from pathlib import Path

import pyarrow.parquet as pq
import pytest

STEPS = Path(__file__).resolve().parents[1] / "steps"


def load_step(filename: str):
    spec = importlib.util.spec_from_file_location(filename[3:-3], STEPS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stations = load_step("15_build_subway_stations.py")
ALIASES = {"lines": {"경의선": "경의중앙선"}, "names": {"당고개": "불암산"}}


def master_row(route: str, name: str, lon: float, lat: float) -> dict:
    return {"BLDN_ID": "0", "BLDN_NM": name, "ROUTE": route, "LAT": lat, "LOT": lon}


def test_name_key_drops_parenthesis() -> None:
    assert stations.name_key("청량리(서울시립대입구)") == "청량리"
    assert stations.name_key("서울역") == "서울역"


def test_match_prefers_same_line_and_uses_aliases() -> None:
    master = [
        master_row("5호선", "양평", 126.886, 37.526),
        master_row("중앙선", "양평", 127.491, 37.492),
        master_row("2호선", "신촌", 126.937, 37.555),
        master_row("경의중앙선", "신촌", 126.943, 37.560),
        master_row("4호선", "불암산", 127.079, 37.670),
    ]
    pairs = [("5호선", "양평"), ("경의선", "신촌"), ("4호선", "당고개")]
    matched, failed = stations.match_stations(pairs, master, ALIASES, 1000)
    by_pair = {(row["line"], row["station"]): row for row in matched}
    assert by_pair[("5호선", "양평")]["lon"] == pytest.approx(126.886)
    assert by_pair[("경의선", "신촌")]["lon"] == pytest.approx(126.943)
    assert by_pair[("4호선", "당고개")]["lat"] == pytest.approx(37.670)
    assert failed == {"no_name": [], "scattered": []}


def test_match_falls_back_to_name_and_leaves_scattered() -> None:
    master = [
        master_row("1호선", "회기", 127.0580, 37.5895),
        master_row("경의중앙선", "회기", 127.0584, 37.5899),
        master_row("5호선", "양평", 126.886, 37.526),
        master_row("중앙선", "양평", 127.491, 37.492),
    ]
    pairs = [("중앙선", "회기"), ("8호선", "양평"), ("경원선", "초성리")]
    matched, failed = stations.match_stations(pairs, master, ALIASES, 1000)
    assert [(r["station"], r["matched_by"]) for r in matched] == [("회기", "name")]
    assert matched[0]["lon"] == pytest.approx(127.0582)
    assert failed == {"no_name": ["경원선 초성리"], "scattered": ["8호선 양평"]}


def test_parse_response_stops_on_key_error_and_overflow() -> None:
    body = "<RESULT><CODE>INFO-100</CODE></RESULT>"
    with pytest.raises(SystemExit, match="INFO-100"):
        stations.parse_response(body, "subwayStationMaster", 1000)
    overflow = (
        '{"subwayStationMaster": {"list_total_count": 1001,'
        ' "RESULT": {"CODE": "INFO-000", "MESSAGE": ""}, "row": []}}'
    )
    with pytest.raises(SystemExit):
        stations.parse_response(overflow, "subwayStationMaster", 1000)


def test_write_parquet_and_report(tmp_path: Path) -> None:
    matched = [
        {"line": "1호선", "station": "서울역", "lon": 126.97, "lat": 37.55},
    ]
    output = tmp_path / "stations.parquet"
    stations.write_parquet(matched, output)
    assert pq.read_table(output).column_names == ["line", "station", "lon", "lat"]
    report = stations.make_report(
        [("1호선", "서울역"), ("경원선", "초성리")],
        [{**matched[0], "matched_by": "line"}],
        {"no_name": ["경원선 초성리"], "scattered": []},
        784,
    )
    assert report["matched"] == 1
    assert report["matched_by_line"] == 1
    assert report["no_name"] == ["경원선 초성리"]
