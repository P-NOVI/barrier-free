from pathlib import Path

import pytest

from scripts.vercel_build import FILES, copy_data


def test_copies_every_server_data_file(tmp_path: Path) -> None:
    source = tmp_path / "processed"
    source.mkdir()
    for name in FILES:
        (source / name).write_bytes(name.encode())

    copied = copy_data(source, tmp_path / "vercel_data")

    assert [path.name for path in copied] == list(FILES)
    assert all(path.read_bytes() == path.name.encode() for path in copied)


def test_stops_when_a_file_is_missing(tmp_path: Path) -> None:
    source = tmp_path / "processed"
    source.mkdir()
    (source / FILES[0]).write_bytes(b"graph")

    with pytest.raises(SystemExit):
        copy_data(source, tmp_path / "vercel_data")
