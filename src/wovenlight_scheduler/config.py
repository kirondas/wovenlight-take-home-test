from dataclasses import dataclass
import os


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    database_url: str
    tfl_base_url: str = "https://api.tfl.gov.uk"
    request_timeout_seconds: float = 5.0
    host: str = "0.0.0.0"
    port: int = 5555
    start_scheduler: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        raw_url = os.getenv("DATABASE_URL", "").strip()
        if not raw_url:
            raise ConfigError(
                "DATABASE_URL is required, e.g. "
                "postgresql://scheduler:scheduler@localhost:5432/scheduler"
            )
        return cls(
            database_url=raw_url,
            tfl_base_url=os.getenv("TFL_BASE_URL", "https://api.tfl.gov.uk").rstrip("/"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5")),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "5555")),
        )
