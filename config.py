import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "your_secret_key")

    # For Flask-MySQLdb
    MYSQL_HOST = os.environ.get("MYSQL_HOST") or "mysql.railway.internal"  # Internal Railway MySQL host
    MYSQL_USER = os.environ.get("MYSQL_USER") or "root"
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD") or "zMaHYKnXXPNKehOeLulDVXYKJIFfvcOZ"
    MYSQL_DB = os.environ.get("MYSQL_DB") or "learnieverse_db"
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT") or 3306)  # Default MySQL port
