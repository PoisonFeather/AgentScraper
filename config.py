from dataclasses import dataclass

@dataclass
class Settings:
    # Ollama
    OLLAMA_BASE_URL: str = "http://192.168.0.136:11434"
    DEFAULT_MODEL: str = "deepseek-r1:8b"
    SECRET_KEY: str = "dev-secret-change-in-production"

    # OLX
    OLX_BASE: str = "https://www.olx.ro"
    USER_AGENT: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
    OLLAMA_TIMEOUT_CONNECT: int = 5
    OLLAMA_TIMEOUT_READ: int = 600
    OLLAMA_RETRIES: int = 2

    # Scrape limits
    MAX_PAGES: int = 10
    MAX_ADS_PER_RUN: int = 20
    MIN_SECONDS_BETWEEN_PAGES: float = 1.2

    # Distance reference (Cluj-Napoca)
    CLUJ_LAT: float = 46.7712
    CLUJ_LON: float = 23.6236


settings = Settings()