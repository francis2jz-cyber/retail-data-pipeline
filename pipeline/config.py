"""Settings. Anything here can be overridden with an env var or a .env file.

With nothing set it falls back to a local SQLite file, so Python is all you need.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _path(env_var: str, default: Path) -> Path:
    """Relative paths in .env are resolved from the project root, not the current folder."""
    value = Path(os.getenv(env_var) or default)
    return value if value.is_absolute() else PROJECT_ROOT / value


def _default_sqlite_url() -> str:
    db_path = PROJECT_ROOT / "data" / "retail.db"
    return f"sqlite:///{db_path.as_posix()}"


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL") or _default_sqlite_url())
    raw_data_dir: Path = field(default_factory=lambda: _path("RAW_DATA_DIR", PROJECT_ROOT / "data" / "raw"))
    api_data_file: Path = field(
        default_factory=lambda: _path("API_DATA_FILE", PROJECT_ROOT / "data" / "api" / "payments.json"))
    reports_dir: Path = field(default_factory=lambda: _path("REPORTS_DIR", PROJECT_ROOT / "reports"))
    payment_api_url: str = field(default_factory=lambda: os.getenv("PAYMENT_API_URL", "http://127.0.0.1:8765"))
    payment_api_page_size: int = field(default_factory=lambda: int(os.getenv("PAYMENT_API_PAGE_SIZE", "250")))
    amount_tolerance: float = field(default_factory=lambda: float(os.getenv("AMOUNT_TOLERANCE", "0.01")))
    auto_start_mock_api: bool = field(
        default_factory=lambda: os.getenv("AUTO_START_MOCK_API", "true").lower() in {"1", "true", "yes"}
    )

    # Where payments come from: "mock" (bundled offline API) or "paystack" (real test-mode API)
    payment_source: str = field(default_factory=lambda: os.getenv("PAYMENT_SOURCE", "mock").lower())
    paystack_secret_key: str = field(default_factory=lambda: os.getenv("PAYSTACK_SECRET_KEY", ""))
    paystack_base_url: str = field(default_factory=lambda: os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co"))

    # Currency that orders are priced in; payments in any other currency are rejected
    base_currency: str = field(default_factory=lambda: os.getenv("BASE_CURRENCY", "USD").upper())

    # A billable order only counts as MISSING_PAYMENT once it is older than this many days
    settlement_window_days: int = field(default_factory=lambda: int(os.getenv("SETTLEMENT_WINDOW_DAYS", "2")))
    # Date to measure order age against (YYYY-MM-DD). Empty = latest order date in the extract.
    as_of_date: str = field(default_factory=lambda: os.getenv("AS_OF_DATE", ""))

    sql_dir: Path = PROJECT_ROOT / "sql"

    @property
    def backend(self) -> str:
        return "postgresql" if self.database_url.startswith("postgresql") else "sqlite"
