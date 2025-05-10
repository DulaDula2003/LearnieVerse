import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "your_secret_key"

    # Try to fetch DATABASE_URL (Railway's preferred way)
    MYSQL_URL = os.environ.get("DATABASE_URL")
    
    # Fallback MySQL configurations (for local development or Render's environment variables)
    MYSQL_HOST = os.environ.get("MYSQL_HOST") or "localhost"
    MYSQL_USER = os.environ.get("MYSQL_USER") or "root"
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD") or "0000"
    MYSQL_DB = os.environ.get("MYSQL_DB") or "learnieverse_db"

    # If DATABASE_URL is available (Railway or Render):
    if MYSQL_URL:
        SQLALCHEMY_DATABASE_URI = MYSQL_URL
    else:
        # Fallback to manual settings if DATABASE_URL isn't available
        SQLALCHEMY_DATABASE_URI = f"mysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
