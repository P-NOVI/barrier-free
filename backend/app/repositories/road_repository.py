import gzip
import json
from functools import cache
from pathlib import Path

from core.entrance import NO_ENTRANCES, EntranceIndex, build_entrance_index
from core.graph import Graph, build_graph
from core.site import NO_SITES, SiteIndex, build_site_index


def read_json(path: Path) -> dict:
    """.json 또는 .json.gz 를 읽는다."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def load_graph(path: Path) -> Graph:
    """graph.json 또는 graph.json.gz 를 읽는다. 같은 경로는 한 번만 읽는다."""
    return build_graph(read_json(path))


@cache
def load_entrances(path: Path) -> EntranceIndex:
    """entrances.json.gz 를 읽는다. 파일이 없으면 출입구 없는 색인을 준다."""
    if not path.exists():
        return NO_ENTRANCES
    return build_entrance_index(read_json(path))


@cache
def load_sites(path: Path) -> SiteIndex:
    """sites.json.gz 를 읽는다. 파일이 없으면 시설 없는 색인을 준다."""
    if not path.exists():
        return NO_SITES
    return build_site_index(read_json(path))
