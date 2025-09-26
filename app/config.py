import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "vale-zap-secret")
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:Mrs36861480%21@evolution_postgres_python:5432/postgres_python",
    )
    SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "change-me")
    EXTERNAL_WEBHOOK_URL = os.getenv(
        "EXTERNAL_WEBHOOK_URL",
        "https://n8n-n8n-webhook.jhbg9t.easypanel.host/webhook/34ae601d-ead7-491e-9bbc-f246089ee5e6",
    )
    CLIENT_API_KEY = os.getenv(
        "CLIENT_API_KEY", "webhook-api-key-placeholder"
    )
    AUTO_REPLY_MODE = os.getenv("AUTO_REPLY_MODE", "echo")
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

