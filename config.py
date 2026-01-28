from dataclasses import dataclass

@dataclass
class Settings:
    # Ollama
    OLLAMA_BASE_URL: str = "http://192.168.0.136:11434"
    DEFAULT_MODEL: str = "qwen2.5-coder:7b"

    # OLX
    OLX_BASE: str = "https://www.olx.ro"
    USER_AGENT: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )

    # Scrape limits
    MAX_PAGES: int = 2
    MAX_ADS_PER_RUN: int = 1
    MIN_SECONDS_BETWEEN_PAGES: float = 1.2

    # Distance reference (Cluj-Napoca)
    CLUJ_LAT: float = 46.7712
    CLUJ_LON: float = 23.6236


settings = Settings()