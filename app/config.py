from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    # App General Info
    APP_NAME: str = "Async IP & VPN Node Checker"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Server Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Concurrency & Network Limits
    MAX_CONCURRENT_CHECKS: int = Field(default=150, ge=1, le=1000)
    TIMEOUT_SECONDS: float = Field(default=5.0, ge=0.5, le=30.0)
    MAX_RETRIES: int = Field(default=1, ge=0, le=5)
    TCP_PING_TIMEOUT: float = Field(default=3.0, ge=0.2, le=10.0)

    # GeoIP & Enrichment
    ENABLE_GEOIP: bool = True
    GEOIP_CACHE_TTL: int = 86400  # 24 hours in seconds

    # Storage & Paths
    DB_PATH: Path = Path("data/nodes.db")
    OUTPUT_DIR: Path = Path("data/output")
    INPUT_SOURCES_FILE: Path = Path("data/input/sources.txt")

    # Git Auto-commit
    AUTO_GIT_COMMIT: bool = False
    GIT_COMMIT_MESSAGE: str = "chore: auto-update validated active nodes list [skip ci]"
    GIT_REMOTE: str = "origin"
    GIT_BRANCH: str = "main"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def init_directories(self) -> None:
        """Ensure necessary runtime directories exist."""
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.INPUT_SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.init_directories()
