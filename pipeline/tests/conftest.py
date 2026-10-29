import sys
from pathlib import Path

# 단계 스크립트가 같은 폴더의 common.py 를 import 하므로 steps/ 를 경로에 넣는다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steps"))
