import re
import json
import time
from datetime import datetime
from urllib.parse import urljoin
from log import section, kv, block, trunc, enabled

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from config import settings
from db import init_db, upsert_ad
from analyze import analyze_ad
from geo import geocode_nominatim, distance_from_cluj

PRICE_RE = re.compile(r"(\d[\d\.\s]*)")

POSITIVE_KW = [
    "doar lumineaza", "doar luminează", "backlight", "fara imagine", "fără imagine",
    "porneste dar nu afiseaza", "pornește dar nu afișează", "sunet dar"
]
NEGATIVE_KW = [
    "dungi", "linii", "crăpat", "spart", "fisurat", "pata", "pată",
    "jumatate ecran", "jumătate ecran", "lovit", "a cazut", "a căzut"
]

def keyword_score(text: str) -> float:
    t = (text or "").lower()
    score = 0.0
    for k in POSITIVE_KW:
        if k in t:
            score += 1.5
    for k in NEGATIVE_KW:
        if k in t:
            score -= 4.0
    return score


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
    # Many OLX pages include JSON state; if present, we can mine coords/images/location.
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return None
    try:
        return json.loads(script.string)
    except Exception:
        return None

def extract_coords_from_next(next_data: dict):
    # OLX structure varies; try common paths safely.
    try:
        props = next_data.get("props", {})
        page = props.get("pageProps", {})
        # sometimes offer object exists
        offer = page.get("offer") or page.get("ad") or page.get("data")
        if isinstance(offer, dict):
            loc = offer.get("location") or {}
            # Some variants: loc["coordinates"] or loc["lat"]/["lon"]
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
    # Prefer og:image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"]
    img = soup.find("img")
    return img["src"] if img and img.get("src") else None

def extract_title_desc_location_price(html: str):
    soup = BeautifulSoup(html, "html.parser")

    data = {
        "title": None,
        "desc": None,
        "price": None,
    }

    # --- TITLE ---
    h1 = soup.find("h1")
    if h1:
        data["title"] = h1.get_text(strip=True)

    if not data["title"]:
        ogt = soup.find("meta", property="og:title")
        if ogt and ogt.get("content"):
            data["title"] = ogt["content"].strip()

    # --- DESCRIPTION ---
    for sel in [
        "div[data-cy='ad_description']",
        "div[data-testid='ad-description']",
        "div#textContent"
    ]:
        node = soup.select_one(sel)
        if node:
            data["desc"] = node.get_text("\n", strip=True)
            break

    # --- PRICE ---
    meta_price = soup.find("meta", property="product:price:amount")
    if meta_price and meta_price.get("content"):
        try:
            data["price"] = int(float(meta_price["content"]))
        except Exception:
            pass

    if data["price"] is None:
        price_node = soup.find(attrs={"data-testid": "ad-price-container"})
        if price_node:
            data["price"] = parse_price_ron(
                price_node.get_text(" ", strip=True)
            )

    return data
def extract_location_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")

    # Cazul modern OLX: locația e lângă distance-field
    dist = soup.select_one("[data-testid='distance-field']")
    if dist:
        parent = dist.find_parent()
        if parent:
            # căutăm un <p> care NU conține "km"
            for p in parent.find_all("p"):
                txt = p.get_text(strip=True)
                if txt and "km" not in txt.lower() and "anunț" not in txt.lower():
                    return txt

    return None

def scrape(query: str, model: str, max_pages: int | None = None):
    init_db()
    max_pages = max_pages or settings.MAX_PAGES

    search_url = f"{settings.OLX_BASE}/oferte/q-{query}/"
    collected = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=settings.USER_AGENT)
        page = context.new_page()

        page.goto(search_url, wait_until="domcontentloaded")

        for _ in range(max_pages):
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            # ad links: OLX varies; we pick anchors that look like offer links
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/d/oferta/" in href or "/oferta/" in href:
                    full = href if href.startswith("http") else urljoin(settings.OLX_BASE, href)
                    if full not in links:
                        links.append(full)

            for url in links:
                if collected >= settings.MAX_ADS_PER_RUN:
                    break

                ad_page = context.new_page()
                try:
                    ad_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    ad_html = ad_page.content()

                    def extract_distance_from_html(html: str):
                        soup = BeautifulSoup(html, "html.parser")
                        d = soup.select_one("[data-testid='distance-field']")
                        if not d:
                            return None
                        txt = d.get_text(strip=True).lower()
                        # ex: "la 450km de tine"
                        m = re.search(r"(\d+)\s*km", txt)
                        if m:
                            return float(m.group(1))
                        return None

                    parsed = extract_title_desc_location_price(ad_html)
                    title = parsed["title"]
                    desc = parsed["desc"]
                    price = parsed["price"]
                    loc = extract_location_from_html(ad_html)
                    img = extract_image_from_html(ad_html)

                    section("AD FOUND")
                    kv("url", url)
                    kv("title", title)
                    kv("price_ron", price)
                    kv("location", loc)

                    if enabled("AGENT_LOG_DESC"):
                        block("description", trunc(desc or "", 1200))

                    next_data = extract_next_data(ad_html)
                    lat = lon = None
                    if next_data:
                        coords = extract_coords_from_next(next_data)
                        if coords:
                            lat, lon = coords

                    # fallback geocoding if only city text exists
                    if (lat is None or lon is None) and loc:
                        # take first part like "Cluj-Napoca" if possible
                        place = loc.split("-")[0].strip()
                        coords = geocode_nominatim(place + ", Romania")
                        if coords:
                            lat, lon = coords

                    dist = extract_distance_from_html(ad_html)

                    # fallback doar dacă OLX nu dă distanța
                    if dist is None:
                        dist = distance_from_cluj(lat, lon)

                    section("GEO")
                    kv("lat", lat)
                    kv("lon", lon)
                    kv("distance_km", f"{dist:.1f}" if dist else None)

                    from analyze import analyze_ad
                    import json

                    # ...

                    kb = keyword_score((title or "") + "\n" + (desc or ""))


                    section("KEYWORD SCORE")
                    kv("keyword_bonus", kb)
                    analysis = analyze_ad(
                        model=model,
                        judge_model="qwen2.5:7b",  # sau îl dai din CLI
                        title=title or "",
                        description=desc or "",
                        price_ron=price,
                        verbose_threshold=5.0,
                        keyword_bonus=kb
                    )


                    minimal = analysis["minimal"]
                    verbose = analysis["verbose"]
                    if "judge_error" in minimal:
                        section("JUDGE ERROR (fallback to minimal)")
                        kv("error", minimal["judge_error"])

                    # salvezi minimal mereu
                    ad = {
                        # ... existing fields
                        "score": float(minimal.get("score", 5.0)),
                        "verdict": minimal.get("verdict", ""),
                        "repair_estimate_low": int(minimal.get("repair_estimate_low", 0) or 0),
                        "repair_estimate_high": int(minimal.get("repair_estimate_high", 0) or 0),
                        "parts_suspected": minimal.get("parts_suspected", ""),
                        "reasoning": minimal.get("reasoning_short", ""),
                    }

                    # dacă avem verbose, îl serializăm în câmpuri extra
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
                        ad["notes"] = verbose.get("notes", "")
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
                        ad["notes"] = None
                    upsert_ad(ad)
                    collected += 1

                finally:
                    ad_page.close()

            # next page (if exists)
            next_btn = page.query_selector("a[rel='next']")
            if not next_btn:
                break
            next_btn.click()
            time.sleep(settings.MIN_SECONDS_BETWEEN_PAGES)

        context.close()
        browser.close()

    return collected

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    #ap.add_argument("--query", required=True, help="OLX query, ex: 'tv samsung defect'")
    ap.add_argument("--model", default=settings.DEFAULT_MODEL, help="Ollama model name")
    ap.add_argument("--pages", type=int, default=settings.MAX_PAGES)
    args = ap.parse_args()
    from queries import QUERIES

    for q in QUERIES:
        print(f"[SEARCH] {q}")
        scrape(query=q, model=args.model, max_pages=args.pages)
    #n = scrape(query=args.query, model=args.model, max_pages=args.pages)
    #print(f"Scraped+analyzed: {n} ads")