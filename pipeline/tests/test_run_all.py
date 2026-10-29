from pathlib import Path

import pytest
import run_all

import common

CONFIG = common.load_config()


def all_outputs() -> set[Path]:
    return {path for step in run_all.STEPS for path in step.outputs(CONFIG)}


def planned(existing: set[Path], **options: object) -> list[str]:
    steps = run_all.plan(
        run_all.STEPS, CONFIG, exists=lambda path: path in existing, **options
    )
    return [step.number for step, run in steps if run]


def output_of(number: str) -> set[Path]:
    step = next(step for step in run_all.STEPS if step.number == number)
    return set(step.outputs(CONFIG))


def test_skip_everything_when_all_outputs_exist() -> None:
    assert planned(all_outputs()) == []


def test_run_everything_on_empty_folder() -> None:
    assert planned(set()) == ["00", "01", "02", "03", "04"]


def test_missing_middle_output_reruns_downstream_only() -> None:
    assert planned(all_outputs() - output_of("03")) == ["03", "04"]


def test_new_dem_reruns_elevation_but_not_network() -> None:
    assert planned(all_outputs() - output_of("00")) == ["00", "02", "03", "04"]


def test_only_export_missing() -> None:
    # 공유 폴더에 중간 결과가 있으면 graph.json.gz 만 만든다
    assert planned(all_outputs() - output_of("04")) == ["04"]


def test_force_and_from() -> None:
    assert planned(all_outputs(), force=True) == ["00", "01", "02", "03", "04"]
    assert planned(all_outputs(), start_from="02") == ["02", "03", "04"]


def test_data_dir_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert common.data_path("raw/dem/x.tif") == tmp_path / "raw" / "dem" / "x.tif"
    # 서버가 읽는 결과는 데이터 폴더와 상관없이 저장소 기준
    assert common.repo_path("data/processed/graph.json.gz") == (
        common.REPO_ROOT / "data" / "processed" / "graph.json.gz"
    )


def test_data_dir_defaults_to_repo_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", "")
    assert common.data_dir() == common.REPO_ROOT / "data"


def test_require_files_explains_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="DATA_DIR"):
        common.require_files(tmp_path / "missing.graphml")
