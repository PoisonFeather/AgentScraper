import re
import json
import time
from datetime import datetime
from urllib.parse import urljoin
from log import section, kv, block, trunc, enabled

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from config import settings
from db import init_db, upsert_ad, get_profile
from analyze import analyze_ad, classify_intent
from geo import geocode_nominatim, distance_from_cluj

from events import emit

PRICE_RE = re.compile(r"(\d[\d\.\s]*)")

def keyword_score(text: str, hard_yes: list[str], hard_no: list[str]) -> float:
    t = (text or "").lower()
    score = 0.0

    for k in (hard_yes or []):
        kk = (k or "").lower().strip()
        if kk and kk in t:
            score += 1.5

    for k in (hard_no or []):
        kk = (k or "").lower().strip()
        if kk and kk in t:
            score -= 4.0

    return score

def parse_profile_cfg(notes: str | None):
    """
    Așteaptă în notes:
    CFG: {...json...}
    RUBRIC:
    ...
    (acceptă și cazul: }RUBRIC: pe aceeași linie)
    """
    notes = notes or ""
    cfg = {"domain": "generic"}
    rubric = ""

    # ia tot ce e după "CFG:" până la "RUBRIC:" (cu sau fără newline), sau până la final
    m = re.search(r"CFG:\s*(\{.*?\})\s*(?=RUBRIC:|$)", notes, flags=re.DOTALL)
    if m:
        raw = m.group(1).strip()
        try:
            cfg = json.loads(raw)
        except Exception:
            cfg = {"domain": "generic"}

    mr = re.search(r"RUBRIC:\s*(.*)$", notes, flags=re.DOTALL)
    if mr:
        rubric = mr.group(1).strip()

    domain = str(cfg.get("domain") or "generic").strip()
    return cfg, rubric, domain


def parse_price_ron(text: str | None):
    if not text:
        return None
    t = text.replace("\xa0", " ").lower()
    m = PRICE_RE.search(t)
    if not m:
        return None
    digits = m.group(1).replace(".", "").replace(" ", "")
    try:
        return int(digits)
    except Exception:
        return None

def extract_next_data(html: str):
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return None
    try:
        return json.loads(script.string)
    except Exception:
        return None

def extract_coords_from_next(next_data: dict):
    try:
        props = next_data.get("props", {})
        page = props.get("pageProps", {})
        offer = page.get("offer") or page.get("ad") or page.get("data")
        if isinstance(offer, dict):
            loc = offer.get("location") or {}
            coords = loc.get("coordinates")
            if isinstance(coords, dict):
                lat = coords.get("latitude") or coords.get("lat")
                lon = coords.get("longitude") or coords.get("lon")
                if lat and lon:
                    return float(lat), float(lon)
            lat = loc.get("lat") or offer.get("latitude")
            lon = loc.get("lon") or offer.get("longitude")
            if lat and lon:
                return float(lat), float(lon)
    except Exception:
        pass
    return None

def extract_image_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"]
    img = soup.find("img")
    return img["src"] if img and img.get("src") else None

def extract_title_desc_location_price(html: str):
    soup = BeautifulSoup(html, "html.parser")
    data = {"title": None, "desc": None, "price": None}

    h1 = soup.find("h1")
    if h1:
        data["title"] = h1.get_text(strip=True)

    if not data["title"]:
        ogt = soup.find("meta", property="og:title")
        if ogt and ogt.get("content"):
            data["title"] = ogt["content"].strip()

    for sel in [
        "div[data-cy='ad_description']",
        "div[data-testid='ad-description']",
        "div#textContent"
    ]:
        node = soup.select_one(sel)
        if node:
            data["desc"] = node.get_text("\n", strip=True)
            break

    meta_price = soup.find("meta", property="product:price:amount")
    if meta_price and meta_price.get("content"):
        try:
            data["price"] = int(float(meta_price["content"]))
        except Exception:
            pass

    if data["price"] is None:
        price_node = soup.find(attrs={"data-testid": "ad-price-container"})
        if price_node:
            data["price"] = parse_price_ron(price_node.get_text(" ", strip=True))

    return data

def normalize_city(loc: str) -> str:
    parts = [p.strip() for p in (loc or "").split(",") if p.strip()]
    if not parts:
        return ""
    if len(parts) >= 2:
        return parts[1]
    return parts[0]

def extract_location_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    img = soup.select_one(".qa-static-ad-map-container img[alt]")
    if img and img.get("alt"):
        full = img["alt"].strip()
        city = normalize_city(full)
        return city or full
    return None

def extract_distance_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    d = soup.select_one("[data-testid='distance-field']")
    if not d:
        return None
    txt = d.get_text(strip=True).lower()
    m = re.search(r"(\d+)\s*km", txt)
    if m:
        return float(m.group(1))
    return None

def scrape(query: str, model: str, profile_id: int, max_pages: int | None = None, max_ads: int | None = None, run_id: str | None = None):
    init_db()
    max_pages = max_pages or settings.MAX_PAGES
    search_url = f"{settings.OLX_BASE}/oferte/q-{query}/"
    collected = 0

    # --- LIVE wrappers (log + emit) ---
    def live_section(title: str):
        section(title)
        emit(run_id, "section", {"title": title})

    def live_kv(k: str, v):
        kv(k, v)
        emit(run_id, "kv", {"key": k, "value": v})

    def live_block(lbl: str, content: str):
        block(lbl, content)
        emit(run_id, "block", {"label": lbl, "content": content})

    def stream_cb(label: str, kind: str, payload: dict):
        # ✅ probe: apare în Log, deci sigur vine din LLM
        emit(run_id, "kv", {"key": f"LLM:{label}", "value": kind})
        emit(run_id, "llm", {"label": label, "kind": kind, **payload})

    emit(run_id, "section", {"title": "SEARCH"})
    emit(run_id, "kv", {"key": "query", "value": query})
    emit(run_id, "kv", {"key": "model", "value": model})
    emit(run_id, "kv", {"key": "max_pages", "value": max_pages})
    emit(run_id, "kv", {"key": "max_ads", "value": (max_ads or settings.MAX_ADS_PER_RUN)})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=settings.USER_AGENT)
        page = context.new_page()

        page.goto(search_url, wait_until="domcontentloaded")

        for _ in range(max_pages):
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/d/oferta/" in href or "/oferta/" in href:
                    full = href if href.startswith("http") else urljoin(settings.OLX_BASE, href)
                    if full not in links:
                        links.append(full)

            for url in links:
                limit_ads = max_ads or settings.MAX_ADS_PER_RUN
                if collected >= limit_ads:
                    break

                ad_page = context.new_page()
                try:
                    ad_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    ad_html = ad_page.content()

                    parsed = extract_title_desc_location_price(ad_html)
                    title = parsed["title"]
                    desc = parsed["desc"]
                    price = parsed["price"]
                    loc = extract_location_from_html(ad_html)
                    img = extract_image_from_html(ad_html)

                    live_section("AD FOUND")
                    live_kv("url", url)
                    live_kv("title", title)
                    live_kv("price_ron", price)
                    live_kv("location", loc)

                    if enabled("AGENT_LOG_DESC"):
                        live_block("description", trunc(desc or "", 1200))

                    next_data = extract_next_data(ad_html)
                    lat = lon = None
                    if next_data:
                        coords = extract_coords_from_next(next_data)
                        if coords:
                            lat, lon = coords

                    if (lat is None or lon is None) and loc:
                        place = loc.split("-")[0].strip()
                        coords = geocode_nominatim(place + ", Romania")
                        if coords:
                            lat, lon = coords

                    dist = extract_distance_from_html(ad_html)
                    if dist is None:
                        dist = distance_from_cluj(lat, lon)

                    live_section("GEO")
                    live_kv("lat", lat)
                    live_kv("lon", lon)
                    live_kv("distance_km", f"{dist:.1f}" if dist else None)

                    prof = get_profile(profile_id)
                    hard_yes = prof.get("hard_yes", []) if prof else []
                    hard_no = prof.get("hard_no", []) if prof else []
                    notes = prof.get("notes", "") if prof else ""

                    cfg, rubric, domain = parse_profile_cfg(notes)

                    def norm(s: str) -> str:
                        return (s or "").lower()

                    def contains_any(text: str, phrases: list[str]) -> str | None:
                        t = norm(text)
                        for p in phrases or []:
                            pp = norm(p).strip()
                            if pp and pp in t:
                                return pp
                        return None

                    def apply_cfg_soft_filters(cfg: dict, title: str, desc: str, price: int | None,
                                               dist_km: float | None):
                        """
                        - avoid: HARD (drop)
                        - max_price/radius: soft cu toleranță, hard drop doar dacă e MULT peste
                        - must_have: SOFT (bonus dacă apare, mic penalty dacă lipsește)
                        """
                        text = (title or "") + "\n" + (desc or "")

                        # 1) HARD negatives (avoid)
                        avoid_hit = contains_any(text, cfg.get("avoid") or [])
                        if avoid_hit:
                            return {"drop": True, "reason": f"cfg_avoid:{avoid_hit}", "bonus": 0.0}

                        bonus = 0.0

                        # 2) price soft/hard
                        max_price = cfg.get("max_price_ron")
                        try:
                            max_price = int(max_price) if max_price is not None else None
                        except Exception:
                            max_price = None

                        if max_price and price:
                            # wiggle room: +15% soft, peste +35% drop (tune aici)
                            soft = 1.15
                            hard = 1.35
                            if price > max_price * hard:
                                return {"drop": True, "reason": "over_budget_hard", "bonus": 0.0}
                            if price > max_price:
                                # penalty gradual, max ~ -2.0
                                ratio = (price - max_price) / max_price
                                bonus -= min(2.0, ratio * 10.0)  # 10% peste => -1.0
                            else:
                                bonus += 0.4  # sub buget = mic bonus

                        # 3) radius soft/hard (doar dacă ai distanță)
                        radius = cfg.get("radius_km")
                        try:
                            radius = float(radius) if radius is not None else None
                        except Exception:
                            radius = None

                        if radius and dist_km:
                            soft = 1.20
                            hard = 1.60
                            if dist_km > radius * hard:
                                return {"drop": True, "reason": "over_radius_hard", "bonus": 0.0}
                            if dist_km > radius:
                                ratio = (dist_km - radius) / radius
                                bonus -= min(1.5, ratio * 5.0)  # 20% peste => -1.0
                            else:
                                bonus += 0.3

                        # 4) must_have: SOFT
                        must = cfg.get("must_have") or []
                        if must:
                            hit = contains_any(text, must)
                            if hit:
                                bonus += 0.8
                            else:
                                bonus -= 0.4  # nu omori anunțul, doar îl împingi în jos

                        return {"drop": False, "reason": None, "bonus": bonus}

                    # 1) intent
                    intent = classify_intent(model, title or "", desc or "", stream_cb=stream_cb)
                    live_section("INTENT")
                    live_kv("intent", intent)
                    live_kv("domain", domain)

                    # stricte: domain-level exclude (rămân hard)
                    if domain == "rentals_cabins":
                        if intent != "RENTAL":
                            live_section("DROP")
                            live_kv("reason", "intent_mismatch_for_rentals")
                            # (nu salvăm anunțuri irelevante pt rentals)
                            continue

                    elif domain == "electronics_tv_flip":
                        if intent == "OFFER_SERVICE":
                            live_section("DROP")
                            live_kv("reason", "service_ad_excluded")
                            # (nu salvăm servicii)
                            continue

                    # 2) keyword bonus
                    kb = keyword_score((title or "") + "\n" + (desc or ""), hard_yes, hard_no)
                    live_section("KEYWORD SCORE")
                    live_kv("keyword_bonus", kb)
                    cfg_res = apply_cfg_soft_filters(cfg, title or "", desc or "", price, dist)

                    if cfg_res["drop"]:
                        section("DROP")
                        kv("reason", cfg_res["reason"])
                        continue

                    cfg_bonus = cfg_res["bonus"]
                    section("CFG SCORE")
                    kv("cfg_bonus", cfg_bonus)

                    analysis = analyze_ad(
                        model=model,
                        judge_model="deepseek-r1:8b",
                        title=title or "",
                        description=desc or "",
                        price_ron=price,
                        verbose_threshold=5.0,
                        keyword_bonus=kb + cfg_bonus,
                        domain=domain,
                        stream_cb=stream_cb,
                    )

                    minimal = analysis["minimal"]
                    verbose = analysis["verbose"]

                    # --- Decide save vs soft drop ---
                    save_strict = True
                    if domain == "rentals_cabins":
                        try:
                            score = float(minimal.get("score", 0))
                            scam = float(minimal.get("scam_risk", 10))
                        except Exception:
                            score, scam = 0, 10
                        save_strict = (score >= 7.0 and scam <= 5.0 and minimal.get("verdict") != "NU MERITĂ")

                    elif domain == "electronics_tv_flip":
                        try:
                            score = float(minimal.get("score", 0))
                        except Exception:
                            score = 0
                        verdict = (minimal.get("verdict") or "").upper()
                        save_strict = (score >= 7.0 and verdict in {"MERITĂ", "MERITĂ LA PIESE"})

                    # ✅ tu ai zis: să nu mai “dispară” — deci salvăm și soft-drop
                    soft_drop_reason = None
                    if not save_strict:
                        live_section("DROP")
                        live_kv("reason", "not_good_enough_after_analysis")
                        live_kv("score", minimal.get("score"))
                        live_kv("verdict", minimal.get("verdict"))
                        soft_drop_reason = f"[SOFT DROP] not_good_enough_after_analysis | score={minimal.get('score')} | verdict={minimal.get('verdict')}"

                    if "judge_error" in minimal:
                        live_section("JUDGE ERROR (fallback to minimal)")
                        live_kv("error", minimal["judge_error"])

                    from datetime import timezone

                    ad = {
                        "profile_id": profile_id,
                        "url": url,
                        "title": title or "",
                        "description": desc or "",
                        "location_text": loc or "",
                        "image_url": img or "",
                        "price_ron": int(price) if price is not None else None,
                        "distance_km": float(dist) if dist is not None else None,
                        "lat": float(lat) if lat is not None else None,
                        "lon": float(lon) if lon is not None else None,
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                    }

                    ad.update({
                        "score": float(minimal.get("score", 5.0)),
                        "verdict": minimal.get("verdict", ""),
                        "likely_fix": minimal.get("likely_fix", ""),
                        "repair_estimate_low": int(minimal.get("repair_estimate_low", 0) or 0),
                        "repair_estimate_high": int(minimal.get("repair_estimate_high", 0) or 0),
                        "parts_suspected": minimal.get("parts_suspected", ""),
                        "reasoning": minimal.get("reasoning_short", ""),
                    })

                    # parse_ok heuristic
                    ad["parse_ok"] = 0 if (minimal.get("reasoning_short", "").startswith("Fallback")) else 1

                    # verbose fields
                    if verbose:
                        ad["confidence"] = float(verbose.get("confidence", 0.5))
                        ad["signals_positive"] = json.dumps(verbose.get("signals_positive", []), ensure_ascii=False)
                        ad["signals_negative"] = json.dumps(verbose.get("signals_negative", []), ensure_ascii=False)
                        ad["quick_tests"] = json.dumps(verbose.get("quick_tests", []), ensure_ascii=False)
                        ad["repair_items"] = json.dumps(verbose.get("repair_items", []), ensure_ascii=False)
                        ad["resale_value_low"] = int(verbose.get("resale_value_low", 0) or 0)
                        ad["resale_value_high"] = int(verbose.get("resale_value_high", 0) or 0)
                        ad["profit_low"] = int(verbose.get("profit_low", 0) or 0)
                        ad["profit_high"] = int(verbose.get("profit_high", 0) or 0)
                        n = verbose.get("notes", "")
                        if isinstance(n, (list, dict)):
                            n = json.dumps(n, ensure_ascii=False)
                        ad["notes"] = n
                        ad["drive_time_min"] = None
                    else:
                        ad["confidence"] = None
                        ad["signals_positive"] = None
                        ad["signals_negative"] = None
                        ad["quick_tests"] = None
                        ad["repair_items"] = None
                        ad["resale_value_low"] = None
                        ad["resale_value_high"] = None
                        ad["profit_low"] = None
                        ad["profit_high"] = None
                        ad["drive_time_min"] = None
                        ad["notes"] = ""

                    if "judge_error" in minimal:
                        ad["judge_error"] = minimal["judge_error"]
                    else:
                        ad["judge_error"] = None

                    if soft_drop_reason:
                        # nu avem coloană “drop_reason” în DB, deci o punem în notes
                        ad["notes"] = (ad.get("notes") or "").strip()
                        ad["notes"] = (ad["notes"] + "\n" + soft_drop_reason).strip()

                    upsert_ad(ad)

                    # “collected” = câte am procesat, nu câte au trecut strict
                    collected += 1

                finally:
                    ad_page.close()

            next_btn = page.query_selector("a[rel='next']")
            if not next_btn:
                break
            next_btn.click()
            time.sleep(settings.MIN_SECONDS_BETWEEN_PAGES)

        context.close()
        browser.close()

    return collected
