"""读取共享业务定义。"""

import json
from pathlib import Path

from utils.paths import BUSINESS_DEFINITION_PATH


def load_business_definition(path: Path | str | None = None) -> dict:
    p = Path(path) if path else BUSINESS_DEFINITION_PATH
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    return json.loads(p.read_text(encoding="utf-8"))
