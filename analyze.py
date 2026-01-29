import json
import requests
from config import settings
from log import section, kv, block, trunc, enabled

def ollama_generate(model: str, prompt: str, label: str = "OLLAMA"):
    if enabled("AGENT_LOG_PROMPT"):
        section(f"{label} PROMPT ({model})")
        block("prompt", trunc(prompt, 2500))

    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    r = requests.post(url, json={
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "top_p": 0.9
        }
    }, timeout=90)
    if r.status_code != 200:
        # păstrăm body pentru debug
        err_text = r.text[:2000] if r.text else ""
        raise RuntimeError(f"Ollama HTTP {r.status_code}: {err_text}")

    out = r.json().get("response", "")

    if enabled("AGENT_LOG_RAW"):
        section(f"{label} RAW OUTPUT ({model})")
        block("raw", trunc(out, 2500))

    return out

def safe_json(resp: str, fallback: dict):
    try:
        return json.loads(resp)
    except Exception:
        return fallback

def analyze_minimal(model: str, title: str, description: str, price_ron: int | None):
    prompt = f"""
Returnează STRICT JSON (fără text extra). Limba: română.
Chei: score (0..10), verdict (MERITĂ/MERITĂ LA PIESE/NU MERITĂ),
likely_fix (lvds/tcon/psu/mainboard/panel/unknown),
repair_estimate_low (RON), repair_estimate_high (RON),
parts_suspected (text scurt), reasoning_short (max 2 fraze).

Reguli cost: LVDS 0-50, TCON 80-150, PSU 100-200, MAINBOARD 250-450, PANEL 9999.
Dacă indicii de panel (dungi/pete/crăpat/jumătate ecran) => likely_fix=panel, verdict=NU MERITĂ.

TITLE: {title}
PRICE_RON: {price_ron}
DESCRIPTION: {description}
"""
    resp = ollama_generate(model, prompt, label="MINIMAL")
    return safe_json(resp, {
        "score": 5.0,
        "verdict": "NECLAR",
        "likely_fix": "unknown",
        "repair_estimate_low": 150,
        "repair_estimate_high": 450,
        "parts_suspected": "mainboard/tcon",
        "reasoning_short": "Fallback: output neparsabil."
    })

def analyze_verbose(judge_model: str, title: str, description: str, price_ron: int | None, minimal: dict):
    prompt = f"""
Ești un tehnician TV. Returnează STRICT JSON (fără text în plus). Limba: română.

Obiectiv: explică mai verbose de ce anunțul merită/nu merită și dă plan de test + cost breakdown.

Chei obligatorii:
confidence (0..1),
signals_positive (listă),
signals_negative (listă),
quick_tests (listă 5-10 pași scurți),
repair_items (listă de obiecte: {{"item","low","high","why"}}),
resale_value_low (RON),
resale_value_high (RON),
profit_low (RON),
profit_high (RON),
notes (3-6 fraze, la obiect).

Constrângeri:
- Respectă intervalele costurilor:
  LVDS 0-50, TCON 80-150, PSU 100-200, MAINBOARD 250-450, PANEL 9999.
- Resale pentru Samsung 50" funcțional SH: 900-1500 RON (ajustează realist).
- Profit = resale - (price + repair).

Date anunț:
TITLE: {title}
PRICE_RON: {price_ron}
DESCRIPTION: {description}

Analiză minimală deja făcută:
{json.dumps(minimal, ensure_ascii=False)}
"""
    resp = ollama_generate(judge_model, prompt, label="VERBOSE")

    def safe_json(resp: str, fallback: dict):
        try:
            return json.loads(resp)
        except Exception as e:
            if enabled("AGENT_LOG_PARSE"):
                section("JSON PARSE FAILED")
                kv("error", str(e))
                block("raw", trunc(resp, 2500))
            return fallback

def analyze_ad(
    model: str,
    judge_model: str | None,
    title: str,
    description: str,
    price_ron: int | None,
    verbose_threshold: float = 5.0,
    keyword_bonus: float = 0.0,
):
    minimal = analyze_minimal(model, title, description, price_ron)

    # aplici bonus/malus (dacă vrei păstrezi keyword_score-ul tău existent)
    try:
        minimal_score = float(minimal.get("score", 5.0))
    except Exception:
        minimal_score = 5.0
    minimal_score = max(0.0, min(10.0, minimal_score + keyword_bonus))
    minimal["score"] = minimal_score

    out = {
        "minimal": minimal,
        "verbose": None
    }

    if judge_model and minimal_score >= verbose_threshold:
        try:
            out["verbose"] = analyze_verbose(judge_model, title, description, price_ron, minimal)
        except Exception as e:
            # nu oprim scraperul dacă judge e instabil
            out["verbose"] = None
            minimal["judge_error"] = str(e)[:500]

    return out