import os
from dotenv import load_dotenv


load_dotenv(override=True)

raw_host = os.getenv("DB_HOST", "")
clean_host = raw_host.replace("https://", "").replace("http://", "").split("/")[0].strip()

DB_CONFIG = {
    "host": clean_host,
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
    "port": int(os.getenv("DB_PORT", "5432")),
}