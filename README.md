# 🧠 AgentScraper – OLX AI Deal Finder

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Ollama](https://img.shields.io/badge/AI-Ollama%20Local-orange?logo=ollama&logoColor=white)
![Playwright](https://img.shields.io/badge/Scraper-Playwright-green?logo=playwright&logoColor=white)

**AgentScraper** is an automated AI agent that hunts for deals on OLX (e.g., defective Samsung TVs), analyzes them intelligently, and estimates **repair chances, component costs, and potential profit margins** using local LLMs via **Ollama**.

This project is designed for:
- 🔌 Electronics technicians / TV repair shops
- 🔄 Flippers (Buy – Repair – Resell)
- 📊 Rapid "Deal vs. No Deal" market analysis

---

## 🚀 Key Features

- **🔎 Automated Scraping:** powered by Playwright to navigate OLX listings.
- **🤖 100% Local AI Analysis:** No cloud APIs, no subscription costs. Privacy-focused.
- **🧮 Smart Scoring:** Assigns a 0–10 profitability score to each listing.
- **🛠️ Repair Estimation:** Identifies likely failures (T-CON, backlight, mainboard, panel) based on symptoms.
- **💰 Profit Calculator:** Calculates `(Est. Resale Price) - (Ask Price + Repair Cost)`.
- **📍 Geolocation Awareness:** Extracts real distances (e.g., "450km from you") to factor in transport.
- **🛡️ Resilience:** Includes a fail-safe mode—if the AI hangs (OOM/Timeout), the scraper continues without crashing.
- **🗃️ SQLite Persistence:** Saves all data for historical analysis and dashboarding.

---

## 🧩 Architecture

```text
AgentScraper/ 
├── scrape.py       # Orchestrator & Scraper logic
├── analyze.py      # AI Logic (Minimal & Verbose/Judge modes)
├── db.py           # Database handling (SQLite)
├── geo.py          # Geocoding & Distance calculation
├── log.py          # Advanced terminal logging
├── config.py       # Global settings
├── queries.py      # List of OLX search queries
├── data/
│   └── olx.db      # Main database
└── README.md


🧠 AI Models
The agent runs locally via Ollama. It utilizes a two-tier analysis system:

Minimal Analysis (The Scanner):

Model: qwen2.5:7b (Recommended)

Role: Fast, stable, initial filtering.

Verbose Judge (The Expert):

Model: gemma3:latest (Optional)

Role: Deep analysis for high-potential items (Score ≥ 5).

Note: Includes automatic fallback to Qwen if Gemma hits memory limits.

⚙️ Installation
1. Prerequisites
Python 3.10+

Ollama installed and running (Download here)

2. Pull AI Models
Open your terminal and download the required weights:

Bash
ollama pull qwen2.5:7b
ollama pull gemma3
3. Setup Project
Bash
# Clone the repository
git clone [https://github.com/PoisonFeather/AgentScraper.git](https://github.com/PoisonFeather/AgentScraper.git)
cd AgentScraper

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install
▶️ Usage
Standard Run
Scrapes the first 5 pages using the Qwen model.

Bash
python scrape.py --model qwen2.5:7b --pages 5
Verbose / Debug Modes
You can control the output using environment variables:

1. Detailed Terminal Logging: Shows the AI's reasoning summary in real-time.

Bash
AGENT_LOG_DESC=1 AGENT_LOG_VERBOSE_SUMMARY=1 python scrape.py --model qwen2.5:7b --pages 5
2. Full Debug (Raw Prompts & Outputs): Use this to debug prompt engineering or LLM parsing errors.

Bash
AGENT_LOG_PROMPT=1 AGENT_LOG_RAW=1 AGENT_LOG_PARSE=1 \
AGENT_LOG_DESC=1 AGENT_LOG_VERBOSE_SUMMARY=1 \
python scrape.py --model qwen2.5:7b --pages 1
📊 Example Output
When running in verbose mode, the terminal will display:

Plaintext
===== AD FOUND =====
Title:       TV Samsung 65" – powers on, no image (blue screen)
Price:       950 RON
Location:    Bucharest Sector 5

===== MINIMAL RESULT =====
Score:           7.2 / 10
Likely Fix:      Backlight / LEDs
Repair Est:      200–350 RON

===== VERBOSE SUMMARY =====
Confidence:      82%
Est. Resale:     1600–2000 RON
Net Profit:      450–700 RON
Recommendation:  BUY
🔮 Roadmap
[ ] Web Dashboard: Flask/React interface to view deals visually.

[ ] Notifications: Telegram/Discord alerts for high-score items.

[ ] Distance Penalty: Automatically lower the score if the item is >100km away.

[ ] Smart Cache: Prevent re-analyzing the same URL twice.

[ ] Fine-tuning: Custom system prompts for specific brands (LG vs Samsung).

⚠️ Disclaimer
All estimates are heuristics based on:

The seller's description (which may be inaccurate).

Common failure patterns known to the LLM.

General market data.

This tool does not replace physical inspection. The author is not responsible for financial losses incurred from flipping decisions made based on this software.
