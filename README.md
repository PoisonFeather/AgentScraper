# 🧠 AgentScraper – OLX AI Deal Finder

AgentScraper este un **agent AI automat** care caută anunțuri OLX (ex: televizoare Samsung defecte), le analizează inteligent și estimează **șansele de reparare, costurile și profitul potențial**, folosind modele LLM rulate local prin **Ollama**.

Proiectul este gândit pentru:
- electroniști / service TV
- flipping (cumpărat – reparat – revândut)
- analiză rapidă a anunțurilor „merită / nu merită”

---

## 🚀 Funcționalități

- 🔎 Scraping OLX automat (Playwright)
- 🤖 Analiză AI locală (fără cloud, fără API-uri externe)
- 🧮 Scor inteligent (0–10) pentru fiecare anunț
- 🛠️ Estimare cost reparație (T-CON, backlight, mainboard, panel)
- 💰 Estimare profit (preț + reparație vs. valoare de revânzare)
- 📍 Distanță reală extrasă direct din OLX (ex: „la 450km de tine”)
- 🧠 Verbose mode: vezi în terminal exact ce analizează modelul
- 🗃️ Persistență în SQLite
- 🛡️ Fail-safe: dacă AI-ul pică (OOM / timeout), scraperul continuă

---

## 🧩 Arhitectură
- AgentScraper/ 
- ├── scrape.py # scraper + orchestrare
- ├── analyze.py # logică AI (minimal + verbose)
- ├── db.py # SQLite (persistență)
- ├── geo.py # geocoding / distanță
- ├── log.py # logging verbose în terminal
- ├── config.py # setări globale
- ├── queries.py # liste de căutări OLX
- ├── data/olx.db # baza de date
- └── README.md

---

## 🧠 Modele AI suportate

Rulează **100% local** prin Ollama.

Testat cu:
- `qwen2.5:7b` – rapid, stabil (recomandat ca model principal)
- `gemma3:latest` – mai analitic, dar mai sensibil la memorie (opțional ca judge)

Configurare implicită:
- **Minimal analysis** → `qwen2.5:7b`
- **Verbose judge (score ≥ 5)** → `gemma3:latest`  
  (cu fallback automat dacă pică)

---

## ⚙️ Cerințe

- Python **3.10+**
- Ollama instalat și pornit
- Modele descărcate:
  ```bash
  ollama pull qwen2.5:7b
  ollama pull gemma3
  
## Dependințe Python
- pip install playwright beautifulsoup4 requests
- playwright install

▶️ Rulare
Rulare standard
python scrape.py --model qwen2.5:7b --pages 5
Rulare cu logging verbose în terminal
AGENT_LOG_DESC=1 AGENT_LOG_VERBOSE_SUMMARY=1 \
python scrape.py --model qwen2.5:7b --pages 5
Debug complet (prompt + raw LLM output)
AGENT_LOG_PROMPT=1 AGENT_LOG_RAW=1 AGENT_LOG_PARSE=1 \
AGENT_LOG_DESC=1 AGENT_LOG_VERBOSE_SUMMARY=1 \
python scrape.py --model qwen2.5:7b --pages 1
📊 Exemplu output în terminal (verbose)
===== AD FOUND =====
title: TV Samsung 65" – pornește, bandă LED defectă
price_ron: 950
location: București Sector 5


===== KEYWORD SCORE =====
keyword_bonus: +1.5


===== MINIMAL RESULT =====
score: 7.2
likely_fix: backlight
repair_estimate: 200–350 RON


===== VERBOSE SUMMARY =====
confidence: 0.82
resale: 1600–2000 RON
profit: 450–700 RON
🛡️ Stabilitate & Fail-safe

Dacă Ollama returnează 500 / OOM / timeout:

analiza verbose este ignorată

anunțul rămâne analizat minimal

scraperul NU se oprește

Acest lucru permite rulări lungi (zeci/sute de anunțuri).

🗃️ Baza de date

SQLite (data/olx.db)

JSON-urile (signals, repair_items etc.) sunt salvate ca TEXT

Structura este gândită pentru:

dashboard Flask

export CSV

filtrare ulterioară

🔮 Idei de extindere

📊 Dashboard Flask / React

🔔 Notificări (Telegram / Discord) la „deal bun”

📉 Penalizare scor după distanță

♻️ Cache pe URL (nu reanalizezi același anunț)

🧠 Fine-tuning reguli per brand / model

⚠️ Disclaimer

Estimările sunt heuristice, bazate pe:

descrierea vânzătorului

pattern-uri comune de defecte

experiență generală service

Nu înlocuiește verificarea fizică a produsului.