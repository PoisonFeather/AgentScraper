# 🧠 AgentScraper – OLX AI Deal Finder (Local LLM)

**AgentScraper** este un agent automat care caută anunțuri pe OLX, le extrage (Playwright) și le evaluează cu modele locale prin **Ollama** (scor, verdict, risc, estimări). Proiectul suportă profiluri + wizard pentru a adapta căutarea la scopul tău (ex. cabane de închiriat, televizoare defecte pentru reparații).

> Totul rulează local. Fără API-uri cloud.

---

## ✅ Ce face (pe scurt)

- 🔎 **Scrape OLX** cu Playwright (căutări pe query-uri)
- 🧠 **Analiză cu LLM local** (Ollama): intent, scoring, verdict
- 🧩 **Profiluri + Wizard**: definești reguli de filtrare (buget, rază, must-have, avoid etc.)
- 🗺️ **Geo**: încearcă să estimeze distanța (OLX distance / coords / fallback)
- 🗃️ **Persistență SQLite**: păstrează anunțuri + scoruri + meta
- 🧾 **UI Flask**: listare + rulare + “live run” cu SSE (stream token cu token)

---

## 🧱 Arhitectură (fișiere)

```text
AgentScraper/
├── app.py              # Flask UI + run worker + Live SSE
├── scrape.py           # Scraper & orchestrare
├── analyze.py          # AI: intent + minimal/verbose + streaming callbacks
├── profile_wizard.py   # Wizard: întrebări + construirea profilului (CFG + rubric)
├── db.py               # SQLite (ads, profiles)
├── geo.py              # geocoding + distance helpers
├── config.py           # settings
├── queries.py          # query-uri de căutare
├── log.py              # logging util
└── data/olx.db         # baza de date

## 🧠 Modele AI (Ollama)

### Recomandare practică
- **Wizard/UI text**: un model “fluent” (ex. `qwen2.5:7b`)
- **Analiză / judge**: un model “reasoning” (ex. `deepseek-r1:8b`)

> Notă: modelele “reasoning” pot avea latență mai mare până la primul token (normal).

```
## ⚙️ Instalare

### 1) Prerequisite
- Python 3.10+
- Ollama instalat și pornit
- Playwright browsers

### 2) Clone + venv
```bash
git clone https://github.com/PoisonFeather/AgentScraper.git
cd AgentScraper

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
playwright install

```
### Pull modele
```bash
ollama pull qwen2.5:7b
ollama pull deepseek-r1:8b

```


## ▶️ Rulare

### UI (recomandat)
```bash
python app.py
# http://127.0.0.1:5005
```
### În UI poți:

#### crea profil din wizard

#### edita profil (hard_yes/hard_no/notes CFG)

#### porni un run și vedea stream live

#### CLI (opțional)

#### Dacă folosești direct orchestratorul:
```bash
python scrape.py --model deepseek-r1:8b --pages 3



