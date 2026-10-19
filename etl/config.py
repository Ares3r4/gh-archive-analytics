import os
from dotenv import load_dotenv

load_dotenv()

def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name!r}. "
            "Create a .env file at the repo root (see .env.example)."
        )
    return value

DB_HOST = _require("DB_HOST")
DB_USER = _require("DB_USER")
DB_PASSWORD = _require("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))