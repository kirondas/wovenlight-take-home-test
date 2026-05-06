from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AppConfig:
    database_url: str
    tfl_base_url: str = "https://api.tfl.gov.uk"
    request_timeout_seconds: float = 10.0
    start_scheduler: bool = True
    testing: bool = False

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg2://tfl:tfl@localhost:5432/tfl_scheduler",
            ),
            tfl_base_url=os.getenv("TFL_BASE_URL", "https://api.tfl.gov.uk"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10")),
            start_scheduler=os.getenv("START_SCHEDULER", "true").lower() != "false",
            testing=os.getenv("FLASK_TESTING", "false").lower() == "true",
        )
