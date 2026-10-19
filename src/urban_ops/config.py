"""Public upstream endpoints and environment-controlled settings."""
import os
from dataclasses import dataclass
from pathlib import Path

INFO_URL = (
    "https://velib-metropole-opendata.smovengo.cloud/opendata/"
    "Velib_Metropole/station_information.json"
)
STATUS_URL = (
    "https://velib-metropole-opendata.smovengo.cloud/opendata/"
    "Velib_Metropole/station_status.json"
)


@dataclass(frozen=True)
class Config:
    database_url: str = "sqlite:///./data/urban_ops.sqlite"
    bronze_dir: Path = Path("data/bronze")
    max_lag_seconds: int = 3600
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.environ.get("URBAN_OPS_DATABASE_URL", "sqlite:///./data/urban_ops.sqlite"),
            bronze_dir=Path(os.environ.get("URBAN_OPS_BRONZE_DIR", "data/bronze")),
            max_lag_seconds=int(os.environ.get("URBAN_OPS_MAX_LAG_SECONDS", "3600")),
            timeout_seconds=float(os.environ.get("URBAN_OPS_REQUEST_TIMEOUT_SECONDS", "20")),
        )
