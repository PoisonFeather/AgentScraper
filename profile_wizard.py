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
    Ești un expert în căutări OLX și construiești un profil de căutare pentru un scraper.

    GOAL: {goal}

    Returnează STRICT JSON valid (fără text extra) cu schema:

    {{
      "name": "...",
      "notes": "...",
      "queries": ["..."],
      "hard_yes": ["..."],
      "hard_no": ["..."],
      "questions": ["..."]
    }}

    Reguli critice:
    - queries: 4-10 expresii de căutare OLX, scurte, orientate pe ce scriu oamenii în anunțuri.
      * Include variante cu și fără diacritice (ex: "inchiriere" și "închiriere").
      * Include sinonime uzuale (ex: "cabana/cabană/chalet/pensiune", "TV/televizor", "defect/stricat/nu porneste").
      * Include forme "de inchiriat", "inchiriez", "ofer spre inchiriere", "pentru piese", "defect", "nu porneste" când se potrivesc.
    - hard_yes: 8-25 termeni/expresii care cresc scorul (semnale puternice din titlu/descriere).
    - hard_no: 8-25 termeni/expresii care scad scorul sau exclud (capcane, alt tip de anunț, stare nedorită).
    - questions: 2-6 întrebări doar dacă lipsesc constrângeri importante pentru a căuta bine.

    Foarte important:
    - Nu inventa lucruri din aer. Folosește GOAL + ANSWERS.
    - Dacă GOAL e despre închiriere: pune termeni de închiriere + exclude vânzare.
    - Dacă GOAL e despre reparație/piese: pune termeni de defect + exclude "perfect funcțional"/"nou".

    Doar JSON.
    """.strip()

    resp = ollama_generate(model, prompt, label="WIZARD_Q")
    data = _safe_json_loads(resp)

    if not data or "questions" not in data or not isinstance(data["questions"], list) or len(data["questions"]) < 3:
        # fallback ca să nu crape wizardul
        return _DEFAULT_QUESTIONS

    # normalizează minim
    out = []
    for i, q in enumerate(data["questions"], start=1):
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
Construiește un profil pentru agentul OLX.

GOAL: {goal}

ANSWERS (dicționar id->răspuns):
{json.dumps(answers, ensure_ascii=False, indent=2)}

Returnează STRICT un JSON valid cu schema:

{{
  "name": "...",
  "notes": "...",
  "queries": ["...","..."],
  "hard_yes": ["..."],
  "hard_no": ["..."],
  "questions": ["..."]
}}

Reguli:
- queries: 2-8 expresii OLX (ex: "tv samsung defect", "televizor smart spart" etc) adaptate goal-ului.
- hard_yes/hard_no: keywords utile pt detectare rapidă în titlu/descriere.
- questions: întrebări de follow-up dacă verdictul e NECLAR.
- Fără explicații, doar JSON.
""".strip()

    resp = ollama_generate(model, prompt, label="WIZARD_PROFILE")
    data = _safe_json_loads(resp)

    if not data:
        # fallback minimal
        return {
            "name": "Profile (auto)",
            "notes": goal,
            "queries": [goal],
            "hard_yes": [],
            "hard_no": [],
            "questions": ["Poți da mai multe detalii despre defect și stare?"],
        }

    # normalizează câmpurile
    def _as_list(x):
        if x is None:
            return []
        if isinstance(x, list):
            return [str(v).strip() for v in x if str(v).strip()]
        if isinstance(x, str):
            return [v.strip() for v in x.splitlines() if v.strip()]
        return []

    return {
        "name": str(data.get("name") or "Profile (auto)").strip(),
        "notes": str(data.get("notes") or goal).strip(),
        "queries": _as_list(data.get("queries")),
        "hard_yes": _as_list(data.get("hard_yes")),
        "hard_no": _as_list(data.get("hard_no")),
        "questions": _as_list(data.get("questions")),
    }