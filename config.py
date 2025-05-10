import os

class Config:
    # Security key for session management
    SECRET_KEY = os.environ.get("SECRET_KEY") or "your_secret_key"

    # Custom MySQL config (used if DATABASE_URL is not set)
    MYSQL_HOST = os.environ.get("MYSQL_HOST") or "localhost"
    MYSQL_USER = os.environ.get("MYSQL_USER") or "root"
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD") or "0000"
    MYSQL_DB = os.environ.get("MYSQL_DB") or "learnieverse_db"

    # Full connection string (used by SQLAlchemy)
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or \
        f"mysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
