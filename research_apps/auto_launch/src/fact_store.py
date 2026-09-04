"""
fact_store.py — SQLite 事实库（事件主表 + 多信源证据 + 弱信号 + 覆盖审计）

架构:
  facts               — 事件主表（confirmed facts）
  signals             — 弱信号表（review signals）
  brand_status        — 品牌状态快照（upsert by brand）
  brand_volume        — 品牌声量观测
  evidence            — 多信源证据（同一事件的不同来源）

用法:
  store = FactStore()
  store.insert(item)              # 插入/更新事实
  store.insert_signal(item)       # 插入弱信号
  store.upsert_brand_status(item) # 更新品牌状态
  store.insert_brand_volume(item) # 插入声量观测
  store.audit_coverage()          # 覆盖审计
"""

import sqlite3, hashlib, json
from pathlib import Path
from datetime import datetime, timedelta

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "outputs" / "facts" / "auto_launch_facts.sqlite"

# ── Schema ─────────────────────────────────────────────────────

BASE_SCHEMA = """
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
    monitor_date    TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_fingerprint ON facts(fingerprint);
CREATE INDEX IF NOT EXISTS idx_facts_brand ON facts(brand);
CREATE INDEX IF NOT EXISTS idx_facts_event_type ON facts(event_type);
CREATE INDEX IF NOT EXISTS idx_facts_last_seen ON facts(last_seen);
"""

_SIGNALS_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id       INTEGER PRIMARY KEY AUTOINCREMENT,
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
    source_tier     TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    note            TEXT,
    monitor_date    TEXT,
    input_channel   TEXT DEFAULT 'inbox',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_fingerprint ON signals(fingerprint);
CREATE INDEX IF NOT EXISTS idx_signals_brand ON signals(brand);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
"""

_BRAND_STATUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS brand_status (
    brand           TEXT PRIMARY KEY,
    status_phase    TEXT,
    last_event      TEXT,
    last_updated    TEXT,
    note            TEXT,
    seen_at         TEXT NOT NULL
);
"""

_BRAND_VOLUME_SCHEMA = """
CREATE TABLE IF NOT EXISTS brand_volume (
    volume_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint     TEXT NOT NULL UNIQUE,
    brand           TEXT,
    volume_trend    TEXT,
    discussion_focus TEXT,
    heat_change     TEXT,
    claim           TEXT,
    action_type     TEXT,
    intensity       TEXT,
    evidence        TEXT,
    observed_at     TEXT NOT NULL,
    input_channel   TEXT DEFAULT 'inbox'
);
CREATE INDEX IF NOT EXISTS idx_brand_volume_fingerprint ON brand_volume(fingerprint);
CREATE INDEX IF NOT EXISTS idx_brand_volume_brand ON brand_volume(brand);
CREATE INDEX IF NOT EXISTS idx_brand_volume_observed_at ON brand_volume(observed_at);
"""

_EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id         INTEGER,
    source_name     TEXT,
    source_url      TEXT,
    source_tier     TEXT,
    claim           TEXT,
    seen_at         TEXT NOT NULL,
    FOREIGN KEY (fact_id) REFERENCES facts(fact_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_fact_id ON evidence(fact_id);
"""

_MIGRATIONS = [
    "ALTER TABLE facts ADD COLUMN source_pipeline TEXT DEFAULT 'manual'",
    "ALTER TABLE facts ADD COLUMN run_id TEXT DEFAULT ''",
    "ALTER TABLE facts ADD COLUMN run_mode TEXT DEFAULT ''",
    "ALTER TABLE facts ADD COLUMN is_test INTEGER DEFAULT 0",
    "ALTER TABLE facts ADD COLUMN quality_status TEXT DEFAULT 'valid'",
    "ALTER TABLE brand_volume ADD COLUMN fingerprint TEXT",
    "ALTER TABLE facts ADD COLUMN monitor_date TEXT",
    "ALTER TABLE signals ADD COLUMN monitor_date TEXT",
]

_MARK_TEST_BRANDS = {"A", "B", "C", "D"}
_DELIVERY_KEYWORDS = ["delivery", "sales", "交付", "销量", "战报", "交付量", "交付数据", "销量数据"]


def _normalize_title(title: str) -> str:
    import re
    t = title.lower().strip()
    t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
    return t[:100]


def _extract_period(event_date: str, title: str) -> str:
    if event_date and len(event_date) >= 7:
        return event_date[:7]
    import re
    for pat in [r"(\d{4})年(\d{1,2})月", r"(\d{4})-(\d{2})", r"(\d{1,2})月", r"上半年", r"下半年"]:
        m = re.search(pat, title)
        if m:
            return m.group(0)
    return ""


def _extract_core_numbers(title: str) -> str:
    import re
    clean = title.replace(",", "").replace("，", "").replace(" ", "")
    all_nums = re.findall(r'(?<!\d)(\d{3,})(?!\d)', clean)
    percentages = set()
    for m in re.finditer(r'(\d{2,})%', title.replace(",", "")):
        percentages.add(m.group(1))
    nums = [n for n in all_nums if n not in percentages]
    return "|".join(sorted(set(nums)))


def _is_delivery_event(event_type: str) -> bool:
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


def _build_signal_fingerprint(brand: str, claim: str) -> str:
    raw = f"signal|{brand or ''}|{_normalize_title(claim)}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _infer_is_test(item: dict) -> bool:
    brand = (item.get("brand") or "").strip()
    title = (item.get("title") or "").strip()
    source_name = (item.get("source_name") or "").strip()
    pipeline = (item.get("source_pipeline") or "").strip()
    if pipeline in ("test", "fixture"):
        return True
    if brand in _MARK_TEST_BRANDS:
        return True
    if title == "Test":
        return True
    if source_name == "src":
        return True
    return False


def _infer_quality_status(item: dict) -> str:
    if _infer_is_test(item):
        return "test"
    return "valid"


# ── Store class ────────────────────────────────────────────────

class FactStore:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DEFAULT_DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(BASE_SCHEMA)
        self._conn.executescript(_SIGNALS_SCHEMA)
        self._conn.executescript(_BRAND_STATUS_SCHEMA)
        self._conn.executescript(_BRAND_VOLUME_SCHEMA)
        self._conn.executescript(_EVIDENCE_SCHEMA)
        self._run_migrations()
        self._cur = self._conn.cursor()
        self._migrate_existing_records()

    def _run_migrations(self):
        for sql in _MIGRATIONS:
            try:
                self._conn.execute(sql)
            except sqlite3.OperationalError:
                pass
        self._conn.commit()

    def _migrate_existing_records(self):
        self._cur.execute(
            "UPDATE facts SET is_test=1, quality_status='test' "
            "WHERE brand IN ('A','B','C','D') AND (is_test IS NULL OR is_test=0)"
        )
        self._cur.execute(
            "UPDATE facts SET is_test=1, quality_status='test' "
            "WHERE title='Test' AND (is_test IS NULL OR is_test=0)"
        )
        self._cur.execute(
            "UPDATE facts SET is_test=1, quality_status='test' "
            "WHERE source_name='src' AND (is_test IS NULL OR is_test=0)"
        )
        self._conn.commit()

    # ── Event master (facts) ──────────────────────────────────

    def insert(self, item: dict) -> dict:
        """
        插入或更新事实（事件主表）。
        自动推断 is_test / quality_status。
        返回: {"action": "inserted" | "updated", "fact_id": int, "seen_count": int}
        """
        brand = item.get("brand", "") or ""
        model = item.get("model", "") or ""
        event_type = item.get("event_type", "") or ""
        event_date = item.get("event_date", "") or ""
        title = item.get("title", "") or ""
        fingerprint = _build_fingerprint(brand, model, event_type, event_date, title)
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        is_test = 1 if _infer_is_test(item) else 0
        quality_status = _infer_quality_status(item)
        source_pipeline = item.get("source_pipeline", "manual")
        run_id = item.get("run_id", "")
        run_mode = item.get("run_mode", "")

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

        monitor_date = item.get("monitor_date") or item.get("event_date") or now[:10]
        self._cur.execute(
            """INSERT INTO facts
               (fingerprint, first_seen, last_seen, seen_count, brand, model,
                event_type, event_date, title, claim, source_name, source_url,
                source_tier, input_channel, raw_excerpt, monitor_date, created_at,
                source_pipeline, run_id, run_mode, is_test, quality_status)
               VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fingerprint, now, now,
                brand or None, model or None, event_type or None,
                event_date or None, title, item.get("claim", ""),
                item.get("source_name") or None, item.get("source_url") or None,
                item.get("source_tier") or None, item.get("input_channel", "inbox"),
                item.get("raw_excerpt", "")[:500], monitor_date, now,
                source_pipeline, run_id, run_mode, is_test, quality_status,
            )
        )
        self._conn.commit()

        fact_id = self._cur.lastrowid

        # If the item has multiple sources, insert as evidence too
        source_name = item.get("source_name") or ""
        source_url = item.get("source_url") or ""
        source_tier = item.get("source_tier") or ""
        claim = item.get("claim") or ""
        if source_name:
            self._cur.execute(
                "INSERT INTO evidence (fact_id, source_name, source_url, source_tier, claim, seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (fact_id, source_name, source_url or None, source_tier or None, claim[:500], now)
            )
            self._conn.commit()

        return {"action": "inserted", "fact_id": fact_id, "seen_count": 1,
                "first_seen": now, "last_seen": now}

    # ── Evidence (multi-source) ───────────────────────────────

    def add_evidence(self, fact_id: int, source_name: str, source_url: str = None,
                     source_tier: str = None, claim: str = None) -> dict:
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        self._cur.execute(
            "INSERT INTO evidence (fact_id, source_name, source_url, source_tier, claim, seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fact_id, source_name, source_url, source_tier, claim, now)
        )
        self._conn.commit()
        return {"evidence_id": self._cur.lastrowid, "fact_id": fact_id, "source_name": source_name}

    def get_evidence(self, fact_id: int) -> list[dict]:
        rows = self._cur.execute(
            "SELECT * FROM evidence WHERE fact_id = ? ORDER BY seen_at", (fact_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Signals (weak signals / review) ───────────────────────

    def insert_signal(self, item: dict) -> dict:
        brand = item.get("brand", "") or ""
        claim = item.get("claim", "") or item.get("title", "") or ""
        fingerprint = _build_signal_fingerprint(brand, claim)
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        existing = self._cur.execute(
            "SELECT signal_id, seen_count, first_seen FROM signals WHERE fingerprint = ?",
            (fingerprint,)
        ).fetchone()

        if existing:
            self._cur.execute(
                "UPDATE signals SET last_seen = ?, seen_count = seen_count + 1 WHERE fingerprint = ?",
                (now, fingerprint)
            )
            self._conn.commit()
            return {
                "action": "updated",
                "signal_id": existing["signal_id"],
                "seen_count": existing["seen_count"] + 1,
            }

        monitor_date = item.get("monitor_date") or item.get("event_date") or now[:10]
        self._cur.execute(
            """INSERT INTO signals
               (fingerprint, first_seen, last_seen, seen_count, brand, model,
                event_type, event_date, title, claim, source_name, source_tier,
                status, note, monitor_date, input_channel, created_at)
               VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)""",
            (
                fingerprint, now, now,
                item.get("brand"), item.get("model"),
                item.get("event_type"), item.get("event_date"),
                item.get("title", "")[:200], item.get("claim", "")[:1000],
                item.get("source_name"), item.get("source_tier"),
                item.get("note", "")[:500],
                monitor_date, item.get("input_channel", "inbox"), now,
            )
        )
        self._conn.commit()
        return {"action": "inserted", "signal_id": self._cur.lastrowid, "seen_count": 1}

    def get_signals(self, brand: str = None, status: str = None,
                    days: int = None, limit: int = 50,
                    monitor_date: str = None) -> list[dict]:
        wheres = []
        params = []
        if brand:
            wheres.append("brand = ?")
            params.append(brand)
        if status:
            wheres.append("status = ?")
            params.append(status)
        if monitor_date:
            wheres.append("monitor_date = ?")
            params.append(monitor_date)
        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
            wheres.append("last_seen >= ?")
            params.append(cutoff)
        sql = "SELECT * FROM signals"
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)
        rows = self._cur.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── Brand status ──────────────────────────────────────────

    def upsert_brand_status(self, item: dict) -> dict:
        brand = item.get("brand", "") or ""
        if not brand:
            return {"action": "skipped", "reason": "no_brand"}
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        existing = self._cur.execute(
            "SELECT * FROM brand_status WHERE brand = ?", (brand,)
        ).fetchone()

        if existing:
            self._cur.execute(
                "UPDATE brand_status SET status_phase=?, last_event=?, last_updated=?, note=?, seen_at=? "
                "WHERE brand=?",
                (item.get("status_phase"), item.get("last_event"),
                 item.get("last_updated"), item.get("note"), now, brand)
            )
            self._conn.commit()
            return {"action": "updated", "brand": brand}
        else:
            self._cur.execute(
                "INSERT INTO brand_status (brand, status_phase, last_event, last_updated, note, seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (brand, item.get("status_phase"), item.get("last_event"),
                 item.get("last_updated"), item.get("note"), now)
            )
            self._conn.commit()
            return {"action": "inserted", "brand": brand}

    def get_brand_status(self, brand: str = None) -> list[dict]:
        if brand:
            rows = self._cur.execute(
                "SELECT * FROM brand_status WHERE brand = ?", (brand,)
            ).fetchall()
        else:
            rows = self._cur.execute(
                "SELECT * FROM brand_status ORDER BY brand"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Brand volume ──────────────────────────────────────────

    def insert_brand_volume(self, item: dict) -> dict:
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        brand = item.get("brand", "") or ""
        today = now[:10]
        fingerprint = hashlib.md5(f"volume|{brand}|{today}".encode("utf-8")).hexdigest()

        existing = self._cur.execute(
            "SELECT volume_id FROM brand_volume WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()

        if existing:
            self._cur.execute(
                "UPDATE brand_volume SET claim=?, action_type=?, intensity=?, evidence=?, observed_at=? "
                "WHERE fingerprint=?",
                (
                    item.get("claim", "")[:500],
                    item.get("event_type") or item.get("action_type") or "",
                    item.get("intensity") or "",
                    item.get("evidence") or "",
                    now, fingerprint,
                )
            )
            self._conn.commit()
            return {"action": "updated", "volume_id": existing["volume_id"], "brand": brand}

        self._cur.execute(
            "INSERT INTO brand_volume (fingerprint, brand, volume_trend, discussion_focus, heat_change, "
            "claim, action_type, intensity, evidence, observed_at, input_channel) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fingerprint,
                brand, item.get("volume_trend"),
                item.get("discussion_focus"), item.get("heat_change"),
                item.get("claim", "")[:500],
                item.get("event_type") or item.get("action_type") or "",
                item.get("intensity") or "",
                item.get("evidence") or "",
                now, item.get("input_channel", "inbox"),
            )
        )
        self._conn.commit()
        return {"action": "inserted", "volume_id": self._cur.lastrowid, "brand": brand}

    def get_brand_volume(self, brand: str = None, days: int = 7, limit: int = 50) -> list[dict]:
        wheres = []
        params = []
        if brand:
            wheres.append("brand = ?")
            params.append(brand)
        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
            wheres.append("observed_at >= ?")
            params.append(cutoff)
        sql = "SELECT * FROM brand_volume"
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY observed_at DESC LIMIT ?"
        params.append(limit)
        rows = self._cur.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── Queries (existing) ────────────────────────────────────

    def query(self, brand: str = None, event_type: str = None,
              model: str = None, source_tier: str = None,
              days: int = None, since: str = None, until: str = None,
              limit: int = 50, exclude_test: bool = True,
              source_pipeline: str = None,
              event_date: str = None,
              monitor_date: str = None) -> list[dict]:
        wheres = []
        params = []
        if brand:
            wheres.append("brand = ?")
            params.append(brand)
        if source_pipeline:
            wheres.append("source_pipeline = ?")
            params.append(source_pipeline)
        if event_type:
            wheres.append("event_type = ?")
            params.append(event_type)
        if model:
            wheres.append("model = ?")
            params.append(model)
        if source_tier:
            wheres.append("source_tier = ?")
            params.append(source_tier)
        if event_date:
            wheres.append("event_date = ?")
            params.append(event_date)
        if monitor_date:
            wheres.append("monitor_date = ?")
            params.append(monitor_date)
        if days is not None:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
            date_cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            wheres.append("(last_seen >= ? OR (event_date IS NOT NULL AND event_date >= ?))")
            params.append(cutoff)
            params.append(date_cutoff)
        if since:
            wheres.append("last_seen >= ?")
            params.append(since)
        if until:
            wheres.append("last_seen <= ?")
            params.append(until)
        if exclude_test:
            wheres.append("(is_test IS NULL OR is_test = 0)")
            wheres.append("(quality_status IS NULL OR quality_status NOT IN ('test', 'invalid'))")

        sql = "SELECT * FROM facts"
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)

        rows = self._cur.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self, exclude_test: bool = True) -> dict:
        exclude_clause = "WHERE (is_test IS NULL OR is_test = 0) AND (quality_status IS NULL OR quality_status NOT IN ('test', 'invalid'))" if exclude_test else ""
        total = self._cur.execute(f"SELECT COUNT(*) as c FROM facts {exclude_clause}").fetchone()["c"]
        by_brand = {
            r["brand"]: r["c"]
            for r in self._cur.execute(
                f"SELECT brand, COUNT(*) as c FROM facts {exclude_clause} AND brand IS NOT NULL GROUP BY brand ORDER BY c DESC"
            ).fetchall()
        }
        by_source_tier = {
            r["source_tier"]: r["c"]
            for r in self._cur.execute(
                f"SELECT source_tier, COUNT(*) as c FROM facts {exclude_clause} AND source_tier IS NOT NULL GROUP BY source_tier ORDER BY c DESC"
            ).fetchall()
        }
        by_event_type = {
            r["event_type"]: r["c"]
            for r in self._cur.execute(
                f"SELECT event_type, COUNT(*) as c FROM facts {exclude_clause} AND event_type IS NOT NULL GROUP BY event_type ORDER BY c DESC"
            ).fetchall()
        }
        by_input_channel = {
            r["input_channel"]: r["c"]
            for r in self._cur.execute(
                f"SELECT input_channel, COUNT(*) as c FROM facts {exclude_clause} GROUP BY input_channel ORDER BY c DESC"
            ).fetchall()
        }
        signal_count = self._cur.execute("SELECT COUNT(*) as c FROM signals").fetchone()["c"]
        brand_status_count = self._cur.execute("SELECT COUNT(*) as c FROM brand_status").fetchone()["c"]
        brand_volume_count = self._cur.execute("SELECT COUNT(*) as c FROM brand_volume").fetchone()["c"]
        return {
            "total_facts": total,
            "by_brand": by_brand,
            "by_source_tier": by_source_tier,
            "by_event_type": by_event_type,
            "by_input_channel": by_input_channel,
            "signals": signal_count,
            "brand_statuses": brand_status_count,
            "brand_volumes": brand_volume_count,
        }

    def stats_by(self, column: str, exclude_test: bool = True) -> dict:
        exclude_clause = "WHERE (is_test IS NULL OR is_test = 0) AND (quality_status IS NULL OR quality_status NOT IN ('test', 'invalid'))" if exclude_test else ""
        rows = self._cur.execute(
            f"SELECT {column} as k, COUNT(*) as c FROM facts {exclude_clause} GROUP BY {column} ORDER BY c DESC"
        ).fetchall()
        return {r["k"] or "(空)": r["c"] for r in rows}

    # ── Audit ─────────────────────────────────────────────────

    def audit(self) -> dict:
        """传统审计：facts 表质量审计。"""
        total = self._cur.execute("SELECT COUNT(*) as c FROM facts").fetchone()["c"]
        if total == 0:
            return {"total": 0, "completeness": {}, "warnings": ["事实库为空"]}

        fields = ["brand", "model", "event_type", "event_date", "source_name", "source_url", "source_tier"]
        completeness = {}
        for f in fields:
            cnt = self._cur.execute(f"SELECT COUNT(*) as c FROM facts WHERE {f} IS NOT NULL AND {f} != ''").fetchone()["c"]
            completeness[f] = {"filled": cnt, "total": total, "pct": round(cnt / total * 100, 1)}

        tier_dist = {
            r["source_tier"]: r["c"]
            for r in self._cur.execute(
                "SELECT source_tier, COUNT(*) as c FROM facts WHERE source_tier IS NOT NULL GROUP BY source_tier ORDER BY c DESC"
            ).fetchall()
        }
        channel_dist = {
            r["input_channel"]: r["c"]
            for r in self._cur.execute(
                "SELECT input_channel, COUNT(*) as c FROM facts GROUP BY input_channel ORDER BY c DESC"
            ).fetchall()
        }
        unique_fps = self._cur.execute("SELECT COUNT(DISTINCT fingerprint) as c FROM facts").fetchone()["c"]
        dup_rate = round((total - unique_fps) / total * 100, 1) if total > 0 else 0
        no_brand = self._cur.execute("SELECT COUNT(*) as c FROM facts WHERE brand IS NULL OR brand = ''").fetchone()["c"]
        no_event = self._cur.execute("SELECT COUNT(*) as c FROM facts WHERE event_type IS NULL OR event_type = ''").fetchone()["c"]
        is_test_cnt = self._cur.execute("SELECT COUNT(*) as c FROM facts WHERE is_test = 1").fetchone()["c"]

        warnings = []
        if no_brand > 0:
            warnings.append(f"{no_brand} 条事实缺少品牌")
        if no_event > 0:
            warnings.append(f"{no_event} 条事实缺少事件类型")
        if is_test_cnt > 0:
            warnings.append(f"{is_test_cnt} 条测试/fixture 数据 (is_test=1)")
        for f, v in completeness.items():
            if v["pct"] < 50:
                warnings.append(f"字段 '{f}' 完成率仅 {v['pct']}%")

        return {
            "total": total,
            "completeness": completeness,
            "source_tier_distribution": tier_dist,
            "input_channel_distribution": channel_dist,
            "dedup": {"unique_fingerprints": unique_fps, "duplicate_rate_pct": dup_rate},
            "quality_flags": {"no_brand": no_brand, "no_event_type": no_event, "is_test": is_test_cnt},
            "warnings": warnings,
        }

    def audit_coverage(self) -> dict:
        """
        覆盖审计：检查 planner 日报中各类型 coverage。
        返回各表的行数统计。
        """
        facts_total = self._cur.execute("SELECT COUNT(*) as c FROM facts "
                                        "WHERE (is_test IS NULL OR is_test = 0) "
                                        "AND (quality_status IS NULL OR quality_status NOT IN ('test', 'invalid'))"
                                        ).fetchone()["c"]
        signals_total = self._cur.execute("SELECT COUNT(*) as c FROM signals").fetchone()["c"]
        brand_status_total = self._cur.execute("SELECT COUNT(*) as c FROM brand_status").fetchone()["c"]
        brand_volume_total = self._cur.execute("SELECT COUNT(*) as c FROM brand_volume").fetchone()["c"]
        evidence_total = self._cur.execute("SELECT COUNT(*) as c FROM evidence").fetchone()["c"]

        brands_with_facts = {
            r["brand"]: r["c"]
            for r in self._cur.execute(
                "SELECT brand, COUNT(*) as c FROM facts WHERE brand IS NOT NULL AND brand != '' "
                "AND (is_test IS NULL OR is_test = 0) "
                "AND (quality_status IS NULL OR quality_status NOT IN ('test', 'invalid')) "
                "GROUP BY brand ORDER BY c DESC"
            ).fetchall()
        }
        brands_with_signals = {
            r["brand"]: r["c"]
            for r in self._cur.execute(
                "SELECT brand, COUNT(*) as c FROM signals WHERE brand IS NOT NULL AND brand != '' "
                "GROUP BY brand ORDER BY c DESC"
            ).fetchall()
        }
        brands_with_status = {
            r["brand"] for r in self._cur.execute(
                "SELECT brand FROM brand_status"
            ).fetchall()
        }
        brands_with_volume = {
            r["brand"] for r in self._cur.execute(
                "SELECT brand FROM brand_volume"
            ).fetchall()
        }

        return {
            "facts_total": facts_total,
            "signals_total": signals_total,
            "brand_status_total": brand_status_total,
            "brand_volume_total": brand_volume_total,
            "evidence_total": evidence_total,
            "brands_with_facts": brands_with_facts,
            "brands_with_signals": brands_with_signals,
            "brands_with_status": sorted(brands_with_status),
            "brands_with_volume": sorted(brands_with_volume),
        }

    def export_json(self, rows: list[dict]) -> str:
        return json.dumps(rows, ensure_ascii=False, indent=2)

    def close(self):
        self._conn.close()
