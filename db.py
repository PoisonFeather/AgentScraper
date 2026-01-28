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

            score REAL,
            verdict TEXT,
            repair_estimate_low INTEGER,
            repair_estimate_high INTEGER,
            parts_suspected TEXT,
            reasoning TEXT,

            distance_km REAL
            signals_positive TEXT

            signals_negative TEXT

likely_fix TEXT

confidence REAL

repair_items TEXT TXT

quick_tests TEXT TXT

resale_value_low INTEGER

resale_value_high INTEGER

profit_low INTEGER

profit_high INTEGER

drive_time_min INTEGER
        );
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_ads_score ON ads(score);")
        con.commit()

def upsert_ad(ad: dict):
    cols = [
        "url","title","price_ron","location_text","lat","lon","image_url",
        "description","scraped_at","score","verdict","repair_estimate_low",
        "repair_estimate_high","parts_suspected","reasoning","distance_km"
    ]
    values = [ad.get(c) for c in cols]
    with connect() as con:
        con.execute(f"""
        INSERT INTO ads ({",".join(cols)}) VALUES ({",".join(["?"]*len(cols))})
        ON CONFLICT(url) DO UPDATE SET
            title=excluded.title,
            price_ron=excluded.price_ron,
            location_text=excluded.location_text,
            lat=excluded.lat, lon=excluded.lon,
            image_url=excluded.image_url,
            description=excluded.description,
            scraped_at=excluded.scraped_at,
            score=excluded.score,
            verdict=excluded.verdict,
            repair_estimate_low=excluded.repair_estimate_low,
            repair_estimate_high=excluded.repair_estimate_high,
            parts_suspected=excluded.parts_suspected,
            reasoning=excluded.reasoning,
            distance_km=excluded.distance_km
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