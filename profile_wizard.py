# profile_wizard.py
import json
import re
from analyze import ollama_generate

_DEFAULT_QUESTIONS = [
    {"id": "q1", "q": "Ce vrei să găsească agentul? (ex: cabane de închiriat, TV-uri defecte reparabile, teren intravilan etc.)", "type": "text"},
    {"id": "q2", "q": "Care e scopul tău? (cumperi / închiriezi / cauți servicii / cauți pentru piese / revânzare)", "type": "text"},
    {"id": "q3", "q": "Care e bugetul maxim (RON) pe anunț? (sau gol)", "type": "text"},
    {"id": "q4", "q": "În ce zone/orașe te interesează? (sau 'oricunde')", "type": "text"},
    {"id": "q5", "q": "Ce condiție/stare vrei? (nou / folosit / defect / orice)", "type": "text"},
    {"id": "q6", "q": "Ce cuvinte/semnale sunt obligatorii? (separate prin virgulă / gol)", "type": "text"},
    {"id": "q7", "q": "Ce cuvinte/semnale sunt interzise? (separate prin virgulă / gol)", "type": "text"},
    {"id": "q8", "q": "Detalii extra utile (brand, model, dimensiune, facilități etc.) (sau gol)", "type": "text"},
]

def _strip_fences(s: str) -> str:
    s = s.strip()
    # scoate ```json ... ``` sau ``` ... ```
    s = re.sub(r"^\s*```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()

def _extract_json_object(s: str) -> str | None:
    # încearcă să scoată un obiect JSON dintr-un text mai lung
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start:end + 1]
    return None

def _safe_json_loads(resp: str) -> dict | None:
    if not resp or not resp.strip():
        return None
    t = _strip_fences(resp)

    # 1) direct
    try:
        return json.loads(t)
    except Exception:
        pass

    # 2) încearcă să extragi doar obiectul JSON din text
    candidate = _extract_json_object(t)
    if candidate:
        try:
            return json.loads(candidate)
        except Exception:
            return None
    return None

def wizard_generate_questions(model: str, goal: str):
    prompt = f"""
Ești un expert în căutări OLX și construiești un wizard de întrebări pentru a înțelege exact ce vrea utilizatorul.

GOAL (cerința inițială): {goal}

Returnează STRICT JSON valid (fără text extra) cu schema:

{{
  "questions": [
    {{"id":"q1","q":"...","type":"text"}},
    {{"id":"q2","q":"...","type":"select","choices":["...","..."]}}
  ]
}}

Reguli:
- 3-8 întrebări, doar ce e necesar ca să faci o căutare bună și să filtrezi rezultate.
- Întrebările trebuie să fie adaptate la GOAL.
- Folosește type: "text" sau "select". La "select" pune choices.
- Nu pune întrebări generice inutile.

Exemple de domenii:
- Cabane de închiriat: perioadă, buget/noapte, locație+rază, nr persoane, facilități, deal-breakers.
- TV flip (TV defect pt reparat/revândut): buget max, diagonala, brand, defecte acceptate/interzise, scop (revânzare vs piese).

Doar JSON.
""".strip()

    resp = ollama_generate(model, prompt, label="WIZARD_Q")
    data = _safe_json_loads(resp)

    qs = (data or {}).get("questions")
    if not isinstance(qs, list) or len(qs) < 2:
        return _DEFAULT_QUESTIONS

    out = []
    for i, q in enumerate(qs, start=1):
        if not isinstance(q, dict):
            continue
        qid = q.get("id") or f"q{i}"
        text = q.get("q") or q.get("question") or ""
        qtype = q.get("type") or "text"
        item = {"id": str(qid), "q": str(text).strip(), "type": str(qtype)}
        if q.get("choices"):
            item["choices"] = q["choices"]
        if item["q"]:
            out.append(item)

    return out if out else _DEFAULT_QUESTIONS

def wizard_build_profile(model: str, goal: str, answers: dict):
    prompt = f"""
Construiește un profil de căutare OLX pentru un agent scraper.

GOAL: {goal}

ANSWERS (dicționar id->răspuns):
{json.dumps(answers, ensure_ascii=False, indent=2)}

Returnează STRICT JSON valid (fără text extra) cu schema:

{{
  "name": "...",
  "domain": "rentals_cabins" | "electronics_tv_flip" | "generic",
  "cfg": {{
    "intent": "RENT" | "BUY_BROKEN",
    "max_price_ron": null | number,
    "radius_km": null | number,
    "areas": [ ... ],
    "min_capacity": null | number,
    "must_have": [ ... ],
    "avoid": [ ... ],

    "max_buy_ron": null | number,
    "min_profit_ron": null | number,
    "diag_min": null | number,
    "diag_max": null | number,
    "brands": [ ... ],
    "avoid_fix": [ ... ]
  }},
  "rubric": "TEXT SCURT cu reguli de evaluare (ce e bun/rău, ce să penalizeze).",
  "queries": ["...","..."],
  "hard_yes": ["..."],
  "hard_no": ["..."],
  "questions": ["..."]
}}

Reguli critice:
- Dacă goal/answers indică închiriere cabane => domain="rentals_cabins", cfg.intent="RENT"
  - queries să fie WIDE: "cabana de inchiriat", "cabană de închiriat", "chalet inchiriat", "inchiriez cabana", "ofer spre inchiriere cabana"
  - hard_no să excludă vânzări: "de vanzare", "vând", "teren", "imobil", "proprietate de vanzare"
- Dacă goal/answers indică TV-uri defecte pentru reparat/revânzare => domain="electronics_tv_flip", cfg.intent="BUY_BROKEN"
  - queries să fie WIDE (NU include "reparatii/service"): "tv defect", "televizor defect", "nu porneste", "fara imagine", "se aude dar nu se vede"
  - hard_no să penalizeze servicii: "repar", "service", "la domiciliu", "firma", "interventii"
- rubric trebuie să fie specific domeniului:
  - cabane: buget, locație, capacitate, facilități, scam signals (avans integral, whatsapp, fără contract etc.)
  - tv flip: exclude panel/dungi/crăpat, estimează costuri TCON/PSU/mainboard/backlight, estimare revânzare + profit.

Doar JSON.
""".strip()

    resp = ollama_generate(model, prompt, label="WIZARD_PROFILE")
    data = _safe_json_loads(resp)

    if not data:
        return {
            "name": "Profile (auto)",
            "notes": goal,
            "queries": [goal],
            "hard_yes": [],
            "hard_no": [],
            "questions": ["Poți da mai multe detalii?"],
        }

    def _as_list(x):
        if x is None:
            return []
        if isinstance(x, list):
            return [str(v).strip() for v in x if str(v).strip()]
        if isinstance(x, str):
            return [v.strip() for v in x.splitlines() if v.strip()]
        return []

    domain = str(data.get("domain") or "generic").strip()
    cfg = data.get("cfg") if isinstance(data.get("cfg"), dict) else {}
    rubric = str(data.get("rubric") or "").strip()

    # Împachetăm cfg + rubric în notes ca să nu schimbi DB schema acum
    notes_human = str(data.get("notes") or goal).strip()
    notes = "CFG: " + json.dumps({"domain": domain, **cfg}, ensure_ascii=False) + "\n"
    if rubric:
        notes += "RUBRIC:\n" + rubric + "\n"
    notes += "\n" + notes_human

    return {
        "name": str(data.get("name") or "Profile (auto)").strip(),
        "notes": notes,
        "queries": _as_list(data.get("queries")),
        "hard_yes": _as_list(data.get("hard_yes")),
        "hard_no": _as_list(data.get("hard_no")),
        "questions": _as_list(data.get("questions")),
    }