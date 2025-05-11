import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "your_secret_key")

    # Railway MySQL config
    MYSQL_HOST = os.environ.get("MYSQLHOST", "mysql.railway.internal")
    MYSQL_USER = os.environ.get("MYSQLUSER", "root")
    MYSQL_PASSWORD = os.environ.get("MYSQLPASSWORD", "zMaHYKnXXPNKehOeLulDVXYKJIFfvcOZ")
    MYSQL_DB = os.environ.get("MYSQLDATABASE", "railway")
    MYSQL_PORT = int(os.environ.get("MYSQLPORT", 3306))

    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
