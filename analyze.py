import json
import time
import requests
from config import settings
from log import section, kv, block, trunc, enabled

def _extract_first_json_object(s: str) -> str | None:
    if not s:
        return None
    start = s.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False

    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:i+1]
    return None

def safe_json(resp: str, fallback: dict):
    try:
        return json.loads(resp)
    except Exception:
        j = _extract_first_json_object(resp or "")
        if j:
            try:
                return json.loads(j)
            except Exception:
                pass
        return fallback


def ollama_generate(model: str, prompt: str, label: str = "OLLAMA", stream_cb=None):
    """
    - dacă stream_cb e None: comportament clasic (returnează text complet)
    - dacă stream_cb e setat: stream token-by-token + returnează text complet la final

    stream_cb(label, kind, payload)
      kind: "prompt" | "chunk" | "done" | "error"
    """
    if enabled("AGENT_LOG_PROMPT"):
        section(f"{label} PROMPT ({model})")
        block("prompt", trunc(prompt, 2500))

    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    timeout = (settings.OLLAMA_TIMEOUT_CONNECT, settings.OLLAMA_TIMEOUT_READ)
    wants_stream = stream_cb is not None

    if wants_stream:
        stream_cb(label, "prompt", {"model": model, "prompt": trunc(prompt, 4000)})

    last_err = None
    for attempt in range(settings.OLLAMA_RETRIES + 1):
        try:
            with requests.post(
                url,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": wants_stream,
                    #"raw": True,
                    "options": {"temperature": 0, "top_p": 0.9},
                },
                stream=wants_stream,
                timeout=timeout,
            ) as r:
                if r.status_code != 200:
                    err_text = r.text[:2000] if r.text else ""
                    raise RuntimeError(f"Ollama HTTP {r.status_code}: {err_text}")

                if not wants_stream:
                    out = r.json().get("response", "")
                    if enabled("AGENT_LOG_RAW"):
                        section(f"{label} RAW OUTPUT ({model})")
                        block("raw", trunc(out, 2500))
                    return out

                full = []
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    obj = json.loads(line)
                    chunk = obj.get("response", "")
                    if chunk:
                        full.append(chunk)
                        stream_cb(label, "chunk", {"text": chunk})
                    if obj.get("done"):
                        break

                out = "".join(full)
                stream_cb(label, "done", {"len": len(out)})
                return out

        except Exception as e:
            last_err = e
            if wants_stream:
                stream_cb(label, "error", {"error": str(e)})
            if attempt < settings.OLLAMA_RETRIES:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise

def classify_intent(model: str, title: str, description: str, stream_cb=None):
    """
    Return labels:
    - OFFER_SERVICE
    - SELL_ITEM
    - RENTAL
    - WANTED
    - IRRELEVANT
    """
    prompt = f"""
Returnează STRICT un singur cuvânt din: OFFER_SERVICE | SELL_ITEM | RENTAL | WANTED | IRRELEVANT

Reguli rapide:
- OFFER_SERVICE: repar/service/la domiciliu/firmă/atelier/intervenții/instalări
- RENTAL: închiriez/de închiriat/noapte/cazare/booking/airbnb/chalet/cabană/pensiune (ca ofertă)
- SELL_ITEM: vând/vanzare/preț fix/negociabil/defect/stricat (ca produs)
- WANTED: cumpăr/caut să cumpăr/achiziționez/caut
- IRRELEVANT: altceva

TITLE: {title}
DESCRIPTION: {description}
""".strip()

    try:
        out = (ollama_generate(model, prompt, label="INTENT", stream_cb=stream_cb) or "").strip().upper()
    except Exception:
        return "IRRELEVANT"

    out = out.split()[0] if out else "IRRELEVANT"
    if out not in {"OFFER_SERVICE","SELL_ITEM","RENTAL","WANTED","IRRELEVANT"}:
        return "IRRELEVANT"
    return out

def analyze_cabin_minimal(model: str, title: str, description: str, price_ron: int | None, stream_cb=None):
    prompt = f"""
Returnează STRICT JSON (fără text extra). Limba: română.
Chei:
score (0..10),
verdict (MERITĂ/NECLAR/NU MERITĂ),
price_hint (text scurt, ex: "450 lei/noapte" sau "preț lipsă"),
signals_positive (listă scurtă),
signals_negative (listă scurtă),
scam_risk (0..10),
reasoning_short (max 2 fraze).

Reguli:
- Penalizează: "avans integral", "whatsapp", "fără contract", "fără acte", "doar azi", "urgent", "plătește acum", "link", "telegram".
- Bonus: locație clară, poze multe, facilități detaliate, capacitate clară, disponibilitate/perioadă, reguli clare.
- Dacă pare vânzare (de vanzare/vând/teren) => verdict=NU MERITĂ.

TITLE: {title}
PRICE_RON: {price_ron}
DESCRIPTION: {description}
""".strip()

    resp = ollama_generate(model, prompt, label="CABIN_MIN", stream_cb=stream_cb)
    return safe_json(resp, {
        "score": 5.0,
        "verdict": "NECLAR",
        "price_hint": "fallback",
        "signals_positive": [],
        "signals_negative": [],
        "scam_risk": 5.0,
        "reasoning_short": "Fallback: output neparsabil."
    })

def analyze_cabin_verbose(model: str, title: str, description: str, price_ron: int | None, minimal: dict, stream_cb=None):
    prompt = f"""
Returnează STRICT JSON (fără text extra). Limba: română.
Scop: să ajuți utilizatorul să aleagă o cabană bună.

Chei:
confidence (0..1),
must_ask_seller (listă 5-10 întrebări),
dealbreakers_found (listă),
pros (listă),
cons (listă),
booking_plan (listă pași scurți),
notes (3-6 fraze).

TITLE: {title}
PRICE_RON: {price_ron}
DESCRIPTION: {description}
MINIMAL:
{json.dumps(minimal, ensure_ascii=False)}
""".strip()

    resp = ollama_generate(model, prompt, label="CABIN_VERBOSE", stream_cb=stream_cb)
    return safe_json(resp, {
        "confidence": 0.4,
        "must_ask_seller": ["Care e prețul pe noapte și pentru ce perioadă?"],
        "dealbreakers_found": [],
        "pros": [],
        "cons": [],
        "booking_plan": ["Cere locația exactă și condițiile."],
        "notes": "Fallback: output neparsabil."
    })

def analyze_minimal(model: str, title: str, description: str, price_ron: int | None, stream_cb=None):
    prompt = f"""
    Răspunde în DOUĂ părți, în ordinea exactă:

    1) <think> ... </think>  (gândirea ta, liber)
    2) JSON STRICT (fără text extra după JSON)

    JSON schema:
    {{
      "score": 0..10,
      "verdict": "MERITĂ" | "MERITĂ LA PIESE" | "NU MERITĂ",
      "likely_fix": "lvds"|"tcon"|"psu"|"mainboard"|"panel"|"unknown",
      "repair_estimate_low": int,
      "repair_estimate_high": int,
      "parts_suspected": "text scurt",
      "reasoning_short": "max 2 fraze"
    }}

    Reguli cost: LVDS 0-50, TCON 80-150, PSU 100-200, MAINBOARD 250-450, PANEL 9999.
    Dacă indicii de panel (dungi/pete/crăpat/jumătate ecran) => likely_fix=panel, verdict=NU MERITĂ.
    Regulă STRICTĂ:
- Dacă descrierea spune "funcționează / fără defect" și NU există simptome tehnice descrise,
  atunci likely_fix="unknown" și parts_suspected="necunoscut".
- Nu menționa LVDS/TCON/PSU/Mainboard decât dacă există simptome specifice.


    TITLE: {title}
    PRICE_RON: {price_ron}
    DESCRIPTION: {description}
    """.strip()

    resp = ollama_generate(model, prompt, label="MINIMAL", stream_cb=stream_cb)
    return safe_json(resp, {
        "score": 5.0,
        "verdict": "NECLAR",
        "likely_fix": "unknown",
        "repair_estimate_low": 150,
        "repair_estimate_high": 450,
        "parts_suspected": "mainboard/tcon",
        "reasoning_short": "Fallback: output neparsabil."
    })

def analyze_verbose(judge_model: str, title: str, description: str, price_ron: int | None, minimal: dict, stream_cb=None):
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
Regulă STRICTĂ:
- Dacă descrierea spune "funcționează / fără defect" și NU există simptome tehnice descrise,
  atunci likely_fix="unknown" și parts_suspected="necunoscut".
- Nu menționa LVDS/TCON/PSU/Mainboard decât dacă există simptome specifice.


Constrângeri:
- Respectă intervalele costurilor:
  LVDS 0-50, TCON 80-150, PSU 100-200, MAINBOARD 250-450, PANEL 9999.
- Profit = resale - (price + repair).

Date anunț:
TITLE: {title}
PRICE_RON: {price_ron}
DESCRIPTION: {description}

Analiză minimală deja făcută:
{json.dumps(minimal, ensure_ascii=False)}
""".strip()

    resp = ollama_generate(judge_model, prompt, label="VERBOSE", stream_cb=stream_cb)
    return safe_json(resp, {
        "confidence": 0.4,
        "signals_positive": [],
        "signals_negative": ["Fallback: output neparsabil."],
        "quick_tests": [],
        "repair_items": [],
        "resale_value_low": 0,
        "resale_value_high": 0,
        "profit_low": 0,
        "profit_high": 0,
        "notes": "Fallback: output neparsabil."
    })

def analyze_ad(
    model: str,
    judge_model: str | None,
    title: str,
    description: str,
    price_ron: int | None,
    verbose_threshold: float = 5.0,
    keyword_bonus: float = 0.0,
    domain: str = "generic",
    stream_cb=None,
):
    if domain == "rentals_cabins":
        minimal = analyze_cabin_minimal(model, title, description, price_ron, stream_cb=stream_cb)
    else:
        minimal = analyze_minimal(model, title, description, price_ron, stream_cb=stream_cb)

    try:
        minimal_score = float(minimal.get("score", 5.0))
    except Exception:
        minimal_score = 5.0

    minimal_score = max(0.0, min(10.0, minimal_score + keyword_bonus))
    minimal["score"] = minimal_score

    out = {"minimal": minimal, "verbose": None}

    if judge_model and minimal_score >= verbose_threshold:
        try:
            if domain == "rentals_cabins":
                out["verbose"] = analyze_cabin_verbose(judge_model, title, description, price_ron, minimal, stream_cb=stream_cb)
            else:
                out["verbose"] = analyze_verbose(judge_model, title, description, price_ron, minimal, stream_cb=stream_cb)
        except Exception as e:
            out["verbose"] = None
            minimal["judge_error"] = str(e)[:500]

    return out
