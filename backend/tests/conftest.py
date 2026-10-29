import json
from pathlib import Path

import pytest

from core.graph import Graph, build_graph

SAMPLE_GRAPH = Path(__file__).resolve().parents[2] / "data" / "sample" / "graph.json"


@pytest.fixture(scope="session")
def sample_graph() -> Graph:
    return build_graph(json.loads(SAMPLE_GRAPH.read_text(encoding="utf-8")))
