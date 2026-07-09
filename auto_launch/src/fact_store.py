"""Layer: Inbox Core — SQLite 事实库（fingerprint 去重）"""
"""
fact_store.py — SQLite 本地事实库。

用法:
  store = FactStore()
  store.insert(item)         # 插入或更新
  store.query(brand="智己")  # 查询
  store.query(days=7)        # 最近 7 天
"""

import sqlite3, hashlib, json
from pathlib import Path
from datetime import datetime, timedelta

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "outputs" / "facts" / "auto_launch_facts.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    fact_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint     TEXT NOT NULL UNIQUE,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    seen_count      INTEGER NOT NULL DEFAULT 1,
    brand           TEXT,
    model           TEXT,
    event_type      TEXT,
    event_date      TEXT,
    title           TEXT NOT NULL,
    claim           TEXT,
    source_name     TEXT,
    source_url      TEXT,
    source_tier     TEXT,
    input_channel   TEXT DEFAULT 'inbox',
    raw_excerpt     TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_fingerprint ON facts(fingerprint);
CREATE INDEX IF NOT EXISTS idx_facts_brand ON facts(brand);
CREATE INDEX IF NOT EXISTS idx_facts_event_type ON facts(event_type);
CREATE INDEX IF NOT EXISTS idx_facts_last_seen ON facts(last_seen);
"""


_DELIVERY_KEYWORDS = ["delivery", "sales", "交付", "销量", "战报", "交付量", "交付数据", "销量数据"]


def _normalize_title(title: str) -> str:
    """简单的 title 归一化：去空格、去标点、小写"""
    import re
    t = title.lower().strip()
    t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
    return t[:100]


def _extract_period(event_date: str, title: str) -> str:
    """从 event_date 或 title 提取时间段（如 2026-06、6月）"""
    if event_date and len(event_date) >= 7:
        return event_date[:7]
    import re
    for pat in [r"(\d{4})年(\d{1,2})月", r"(\d{4})-(\d{2})", r"(\d{1,2})月", r"上半年", r"下半年"]:
        m = re.search(pat, title)
        if m:
            return m.group(0)
    return ""


def _extract_core_numbers(title: str) -> str:
    """提取 title 中的核心数字用于交付类事件去重，排除百分比"""
    import re
    clean = title.replace(",", "").replace("，", "").replace(" ", "")
    all_nums = re.findall(r'(?<!\d)(\d{3,})(?!\d)', clean)
    # Exclude numbers that are clearly percentages (followed by %)
    percentages = set()
    for m in re.finditer(r'(\d{2,})%', title.replace(",", "")):
        percentages.add(m.group(1))
    nums = [n for n in all_nums if n not in percentages]
    return "|".join(sorted(set(nums)))


def _is_delivery_event(event_type: str) -> bool:
    """判断是否属于需语义去重的交付/销量类事件"""
    if not event_type:
        return False
    et = event_type.lower()
    return any(kw in et for kw in _DELIVERY_KEYWORDS)


def _build_fingerprint(brand: str, model: str, event_type: str, event_date: str, title: str) -> str:
    if _is_delivery_event(event_type):
        period = _extract_period(event_date, title)
        numbers = _extract_core_numbers(title)
        raw = f"delivery_metric|{brand or ''}|{model or ''}|{period}|{numbers}"
    else:
        raw = f"{brand or ''}|{model or ''}|{event_type or ''}|{event_date or ''}|{_normalize_title(title)}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class FactStore:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DEFAULT_DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._cur = self._conn.cursor()

    def insert(self, item: dict) -> dict:
        """
        插入或更新事实。
        返回: {"action": "inserted" | "updated", "fact_id": int, "seen_count": int}
        """
        brand = item.get("brand", "") or ""
        model = item.get("model", "") or ""
        event_type = item.get("event_type", "") or ""
        event_date = item.get("event_date", "") or ""
        title = item.get("title", "") or ""
        fingerprint = _build_fingerprint(brand, model, event_type, event_date, title)
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        existing = self._cur.execute(
            "SELECT fact_id, seen_count, first_seen FROM facts WHERE fingerprint = ?",
            (fingerprint,)
        ).fetchone()

        if existing:
            self._cur.execute(
                "UPDATE facts SET last_seen = ?, seen_count = seen_count + 1 WHERE fingerprint = ?",
                (now, fingerprint)
            )
            self._conn.commit()
            return {
                "action": "updated",
                "fact_id": existing["fact_id"],
                "seen_count": existing["seen_count"] + 1,
                "first_seen": existing["first_seen"],
                "last_seen": now,
            }

        self._cur.execute(
            """INSERT INTO facts
               (fingerprint, first_seen, last_seen, seen_count, brand, model,
                event_type, event_date, title, claim, source_name, source_url,
                source_tier, input_channel, raw_excerpt, created_at)
               VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fingerprint, now, now,
                brand or None, model or None, event_type or None,
                event_date or None, title, item.get("claim", ""),
                item.get("source_name") or None, item.get("source_url") or None,
                item.get("source_tier") or None, item.get("input_channel", "inbox"),
                item.get("raw_excerpt", "")[:500], now,
            )
        )
        self._conn.commit()
        return {"action": "inserted", "fact_id": self._cur.lastrowid, "seen_count": 1,
                "first_seen": now, "last_seen": now}

    def query(self, brand: str = None, event_type: str = None,
              model: str = None, source_tier: str = None,
              days: int = None, since: str = None, until: str = None,
              limit: int = 50) -> list[dict]:
        """查询事实，支持按 brand / event_type / model / source_tier / days / since / until 过滤"""
        wheres = []
        params = []
        if brand:
            wheres.append("brand = ?")
            params.append(brand)
        if event_type:
            wheres.append("event_type = ?")
            params.append(event_type)
        if model:
            wheres.append("model = ?")
            params.append(model)
        if source_tier:
            wheres.append("source_tier = ?")
            params.append(source_tier)
        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
            date_cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            # Include facts seen recently OR with a recent event_date
            wheres.append("(last_seen >= ? OR (event_date IS NOT NULL AND event_date >= ?))")
            params.append(cutoff)
            params.append(date_cutoff)
        if since:
            wheres.append("last_seen >= ?")
            params.append(since)
        if until:
            wheres.append("last_seen <= ?")
            params.append(until)

        sql = "SELECT * FROM facts"
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)

        rows = self._cur.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        total = self._cur.execute("SELECT COUNT(*) as c FROM facts").fetchone()["c"]
        by_brand = {
            r["brand"]: r["c"]
            for r in self._cur.execute(
                "SELECT brand, COUNT(*) as c FROM facts WHERE brand IS NOT NULL GROUP BY brand ORDER BY c DESC"
            ).fetchall()
        }
        by_source_tier = {
            r["source_tier"]: r["c"]
            for r in self._cur.execute(
                "SELECT source_tier, COUNT(*) as c FROM facts WHERE source_tier IS NOT NULL GROUP BY source_tier ORDER BY c DESC"
            ).fetchall()
        }
        by_event_type = {
            r["event_type"]: r["c"]
            for r in self._cur.execute(
                "SELECT event_type, COUNT(*) as c FROM facts WHERE event_type IS NOT NULL GROUP BY event_type ORDER BY c DESC"
            ).fetchall()
        }
        by_input_channel = {
            r["input_channel"]: r["c"]
            for r in self._cur.execute(
                "SELECT input_channel, COUNT(*) as c FROM facts GROUP BY input_channel ORDER BY c DESC"
            ).fetchall()
        }
        return {
            "total_facts": total,
            "by_brand": by_brand,
            "by_source_tier": by_source_tier,
            "by_event_type": by_event_type,
            "by_input_channel": by_input_channel,
        }

    def stats_by(self, column: str) -> dict:
        """按任意字段分组统计"""
        rows = self._cur.execute(
            f"SELECT {column} as k, COUNT(*) as c FROM facts GROUP BY {column} ORDER BY c DESC"
        ).fetchall()
        return {r["k"] or "(空)": r["c"] for r in rows}

    def audit(self) -> dict:
        """事实库质量审计"""
        total = self._cur.execute("SELECT COUNT(*) as c FROM facts").fetchone()["c"]
        if total == 0:
            return {"total": 0, "completeness": {}, "warnings": ["事实库为空"]}

        # 字段完成率
        fields = ["brand", "model", "event_type", "event_date", "source_name", "source_url", "source_tier"]
        completeness = {}
        for f in fields:
            cnt = self._cur.execute(f"SELECT COUNT(*) as c FROM facts WHERE {f} IS NOT NULL AND {f} != ''").fetchone()["c"]
            completeness[f] = {"filled": cnt, "total": total, "pct": round(cnt / total * 100, 1)}

        # 信源质量分布
        tier_dist = {
            r["source_tier"]: r["c"]
            for r in self._cur.execute(
                "SELECT source_tier, COUNT(*) as c FROM facts WHERE source_tier IS NOT NULL GROUP BY source_tier ORDER BY c DESC"
            ).fetchall()
        }

        # 输入渠道分布
        channel_dist = {
            r["input_channel"]: r["c"]
            for r in self._cur.execute(
                "SELECT input_channel, COUNT(*) as c FROM facts GROUP BY input_channel ORDER BY c DESC"
            ).fetchall()
        }

        # 去重效果：fingerprint 碰撞率
        unique_fps = self._cur.execute("SELECT COUNT(DISTINCT fingerprint) as c FROM facts").fetchone()["c"]
        dup_rate = round((total - unique_fps) / total * 100, 1) if total > 0 else 0

        # 无品牌/无事件类型的事实
        no_brand = self._cur.execute("SELECT COUNT(*) as c FROM facts WHERE brand IS NULL OR brand = ''").fetchone()["c"]
        no_event = self._cur.execute("SELECT COUNT(*) as c FROM facts WHERE event_type IS NULL OR event_type = ''").fetchone()["c"]

        warnings = []
        if no_brand > 0:
            warnings.append(f"{no_brand} 条事实缺少品牌")
        if no_event > 0:
            warnings.append(f"{no_event} 条事实缺少事件类型")
        if no_brand > 0 and no_brand == total:
            warnings.append("所有事实均缺少品牌，inbox_filter 可能未生效")
        for f, v in completeness.items():
            if v["pct"] < 50:
                warnings.append(f"字段 '{f}' 完成率仅 {v['pct']}%")

        return {
            "total": total,
            "completeness": completeness,
            "source_tier_distribution": tier_dist,
            "input_channel_distribution": channel_dist,
            "dedup": {"unique_fingerprints": unique_fps, "duplicate_rate_pct": dup_rate},
            "quality_flags": {"no_brand": no_brand, "no_event_type": no_event},
            "warnings": warnings,
        }

    def export_json(self, rows: list[dict]) -> str:
        """将查询结果导出为 JSON 字符串"""
        return json.dumps(rows, ensure_ascii=False, indent=2)

    def close(self):
        self._conn.close()
