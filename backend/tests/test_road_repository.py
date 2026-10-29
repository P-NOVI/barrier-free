import gzip
from pathlib import Path

from app.repositories.road_repository import load_graph

SAMPLE_GRAPH = Path(__file__).resolve().parents[2] / "data" / "sample" / "graph.json"


def test_load_json_and_gzip_give_same_graph(tmp_path: Path) -> None:
    compressed = tmp_path / "graph.json.gz"
    compressed.write_bytes(gzip.compress(SAMPLE_GRAPH.read_bytes()))

    plain = load_graph(SAMPLE_GRAPH)
    packed = load_graph(compressed)

    assert len(plain.nodes) == len(packed.nodes) == 100
    assert plain.nodes == packed.nodes
    assert plain.adjacency == packed.adjacency


def test_same_path_is_loaded_once() -> None:
    assert load_graph(SAMPLE_GRAPH) is load_graph(SAMPLE_GRAPH)
