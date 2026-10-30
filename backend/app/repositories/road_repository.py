import gzip
import json
from functools import cache
from pathlib import Path

from core.graph import Graph, build_graph


@cache
def load_graph(path: Path) -> Graph:
    """graph.json 또는 graph.json.gz 를 읽는다. 같은 경로는 한 번만 읽는다."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return build_graph(json.load(f))
    return build_graph(json.loads(path.read_text(encoding="utf-8")))
