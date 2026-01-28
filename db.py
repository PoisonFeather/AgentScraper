import sqlite3
from pathlib import Path
import json
from datetime import datetime, timezone

DB_PATH = Path("data/olx.db")

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)

def init_db():
    with connect() as con:
        con.executescript("""
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            notes TEXT,
            queries_json TEXT NOT NULL,
            hard_yes_json TEXT NOT NULL,
            hard_no_json TEXT NOT NULL,
            questions_json TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER,             
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
            notes TEXT,

            FOREIGN KEY(profile_id) REFERENCES profiles(id)
        );

        CREATE INDEX IF NOT EXISTS idx_ads_profile_id ON ads(profile_id);
        CREATE INDEX IF NOT EXISTS idx_ads_score ON ads(score);
        CREATE INDEX IF NOT EXISTS idx_ads_scraped_at ON ads(scraped_at);
        """)
        con.commit()
def upsert_ad(ad: dict):
    # IMPORTANT: cheile din ad trebuie să corespundă exact acestor coloane
    cols = [
        "profile_id",
        "url", "title", "price_ron", "location_text", "lat", "lon", "image_url",
        "description", "scraped_at", "distance_km",
        "score", "verdict", "likely_fix", "repair_estimate_low", "repair_estimate_high",
        "parts_suspected", "reasoning",
        "confidence", "signals_positive", "signals_negative", "quick_tests", "repair_items",
        "resale_value_low", "resale_value_high", "profit_low", "profit_high", "drive_time_min",
        "parse_ok", "judge_error", "notes",
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
            judge_error=excluded.judge_error,
            notes=excluded.notes
        """, values)
        con.commit()

def list_ads(limit=200, min_score=None, profile_id=None):
    q = "SELECT * FROM ads"
    params = []
    where = []

    if profile_id is not None:
        where.append("profile_id = ?")
        params.append(profile_id)

    if min_score is not None:
        where.append("score >= ?")
        params.append(min_score)

    if where:
        q += " WHERE " + " AND ".join(where)

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

def _now_utc():
    return datetime.now(timezone.utc).isoformat()

def _lines_to_list(s: str):
    return [line.strip() for line in (s or "").splitlines() if line.strip()]

def _list_to_lines(lst):
    return "\n".join(lst or [])

def list_profiles():
    with connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM profiles ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

def get_profile(profile_id: int):
    with connect() as con:
        con.row_factory = sqlite3.Row
        r = con.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["queries"] = json.loads(d["queries_json"])
        d["hard_yes"] = json.loads(d["hard_yes_json"])
        d["hard_no"] = json.loads(d["hard_no_json"])
        d["questions"] = json.loads(d["questions_json"])
        return d

def create_profile_from_form(name: str, notes: str, queries_txt: str, yes_txt: str, no_txt: str, questions_txt: str):
    now = _now_utc()
    with connect() as con:
        con.execute("""
            INSERT INTO profiles
            (name, notes, queries_json, hard_yes_json, hard_no_json, questions_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name.strip(),
            (notes or "").strip(),
            json.dumps(_lines_to_list(queries_txt), ensure_ascii=False),
            json.dumps(_lines_to_list(yes_txt), ensure_ascii=False),
            json.dumps(_lines_to_list(no_txt), ensure_ascii=False),
            json.dumps(_lines_to_list(questions_txt), ensure_ascii=False),
            now, now
        ))
        con.commit()

def update_profile_from_form(profile_id: int, name: str, notes: str, queries_txt: str, yes_txt: str, no_txt: str, questions_txt: str):
    now = _now_utc()
    with connect() as con:
        con.execute("""
            UPDATE profiles SET
              name=?,
              notes=?,
              queries_json=?,
              hard_yes_json=?,
              hard_no_json=?,
              questions_json=?,
              updated_at=?
            WHERE id=?
        """, (
            name.strip(),
            (notes or "").strip(),
            json.dumps(_lines_to_list(queries_txt), ensure_ascii=False),
            json.dumps(_lines_to_list(yes_txt), ensure_ascii=False),
            json.dumps(_lines_to_list(no_txt), ensure_ascii=False),
            json.dumps(_lines_to_list(questions_txt), ensure_ascii=False),
            now,
            profile_id
        ))
        con.commit()

def delete_profile(profile_id: int):
    with connect() as con:
        con.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
        con.commit()

def profile_to_form_defaults(profile_row: dict):
    # profile_row e dict-ul întors de get_profile()
    return {
        "name": profile_row.get("name", ""),
        "notes": profile_row.get("notes", "") or "",
        "queries_txt": _list_to_lines(profile_row.get("queries", [])),
        "yes_txt": _list_to_lines(profile_row.get("hard_yes", [])),
        "no_txt": _list_to_lines(profile_row.get("hard_no", [])),
        "questions_txt": _list_to_lines(profile_row.get("questions", [])),
    }

import sqlite3
from datetime import datetime, timezone

def insert_profile(p: dict):
    with connect() as con:
        con.execute("""
        INSERT INTO profiles (name, notes, queries_json, hard_yes_json, hard_no_json, questions_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p["name"], p.get("notes",""),
            p["queries_json"], p["hard_yes_json"], p["hard_no_json"], p["questions_json"],
            p.get("created_at"), p.get("updated_at")
        ))
        con.commit()