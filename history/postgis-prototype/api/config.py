from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_set_role: str | None
    data_root: Path
    api_host: str
    api_port: int
    cors_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        raw_data_root = Path(os.getenv("HYLOGGER_DATA_ROOT", "data/processed"))
        data_root = raw_data_root if raw_data_root.is_absolute() else PROJECT_ROOT / raw_data_root
        origins = tuple(
            item.strip()
            for item in os.getenv(
                "HYLOGGER_CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            ).split(",")
            if item.strip()
        )
        return cls(
            db_host=os.getenv("HYLOGGER_DB_HOST", "localhost"),
            db_port=int(os.getenv("HYLOGGER_DB_PORT", "5432")),
            db_name=os.getenv("HYLOGGER_DB_NAME", "hylogger"),
            db_user=os.getenv("HYLOGGER_DB_USER", ""),
            db_password=os.getenv("HYLOGGER_DB_PASSWORD", "") or os.getenv("PGPASSWORD", ""),
            db_set_role=os.getenv("HYLOGGER_DB_SET_ROLE") or None,
            data_root=data_root.resolve(),
            api_host=os.getenv("HYLOGGER_API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("HYLOGGER_API_PORT", "8000")),
            cors_origins=origins,
        )

    def validate(self) -> None:
        if not self.db_user:
            raise RuntimeError("HYLOGGER_DB_USER is required")
        if not self.db_password:
            raise RuntimeError("HYLOGGER_DB_PASSWORD or PGPASSWORD is required")
        if not self.data_root.is_dir():
            raise RuntimeError(f"HYLOGGER_DATA_ROOT does not exist: {self.data_root}")
