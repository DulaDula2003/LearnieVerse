import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "your_secret_key"
    MYSQL_HOST = "localhost"
    MYSQL_USER = "root"
    MYSQL_PASSWORD = "0000"
    MYSQL_DB = "learnieverse_db"
