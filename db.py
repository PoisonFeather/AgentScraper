import sqlite3
from pathlib import Path

DB_PATH = Path("data/olx.db")

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)

def init_db():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            price_ron INTEGER,
            location_text TEXT,
            lat REAL,
            lon REAL,
            image_url TEXT,
            description TEXT,
            scraped_at TEXT,

            distance_km REAL,

            score REAL,
            verdict TEXT,
            likely_fix TEXT,
            repair_estimate_low INTEGER,
            repair_estimate_high INTEGER,
            parts_suspected TEXT,
            reasoning TEXT,

            confidence REAL,
            signals_positive TEXT,
            signals_negative TEXT,
            quick_tests TEXT,
            repair_items TEXT,
            resale_value_low INTEGER,
            resale_value_high INTEGER,
            profit_low INTEGER,
            profit_high INTEGER,
            drive_time_min INTEGER,

            parse_ok INTEGER,
            judge_error TEXT,
            notes TEXT
        );
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_ads_score ON ads(score);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ads_scraped_at ON ads(scraped_at);")
        con.commit()

def upsert_ad(ad: dict):
    # IMPORTANT: cheile din ad trebuie să corespundă exact acestor coloane
    cols = [
        "url","title","price_ron","location_text","lat","lon","image_url",
        "description","scraped_at","distance_km",
        "score","verdict","likely_fix","repair_estimate_low","repair_estimate_high",
        "parts_suspected","reasoning",
        "confidence","signals_positive","signals_negative","quick_tests","repair_items",
        "resale_value_low","resale_value_high","profit_low","profit_high","drive_time_min",
        "parse_ok","judge_error","notes",
    ]
    values = [ad.get(c) for c in cols]

    with connect() as con:
        con.execute(f"""
        INSERT INTO ads ({",".join(cols)})
        VALUES ({",".join(["?"]*len(cols))})
        ON CONFLICT(url) DO UPDATE SET
            title=excluded.title,
            price_ron=excluded.price_ron,
            location_text=excluded.location_text,
            lat=excluded.lat,
            lon=excluded.lon,
            image_url=excluded.image_url,
            description=excluded.description,
            scraped_at=excluded.scraped_at,
            distance_km=excluded.distance_km,

            score=excluded.score,
            verdict=excluded.verdict,
            likely_fix=excluded.likely_fix,
            repair_estimate_low=excluded.repair_estimate_low,
            repair_estimate_high=excluded.repair_estimate_high,
            parts_suspected=excluded.parts_suspected,
            reasoning=excluded.reasoning,

            confidence=excluded.confidence,
            signals_positive=excluded.signals_positive,
            signals_negative=excluded.signals_negative,
            quick_tests=excluded.quick_tests,
            repair_items=excluded.repair_items,
            resale_value_low=excluded.resale_value_low,
            resale_value_high=excluded.resale_value_high,
            profit_low=excluded.profit_low,
            profit_high=excluded.profit_high,
            drive_time_min=excluded.drive_time_min,

            parse_ok=excluded.parse_ok,
            judge_error=excluded.judge_error
        """, values)
        con.commit()

def list_ads(limit=200, min_score=None):
    q = "SELECT * FROM ads"
    params = []
    if min_score is not None:
        q += " WHERE score >= ?"
        params.append(min_score)
    q += " ORDER BY score DESC, id DESC LIMIT ?"
    params.append(limit)
    with connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(q, params).fetchall()
        return [dict(r) for r in rows]

def get_ad(ad_id: int):
    with connect() as con:
        con.row_factory = sqlite3.Row
        r = con.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
        return dict(r) if r else None