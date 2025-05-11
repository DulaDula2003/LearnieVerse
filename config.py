import os
from urllib.parse import urlparse

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "your_secret_key")

    # Parse the DATABASE_URL
    url = urlparse(os.environ.get("DATABASE_URL", "mysql://root:zMaHYKnXXPNKehOeLulDVXYKJIFfvcOZ@tramway.proxy.rlwy.net:34169/railway"))

    MYSQL_HOST = url.hostname
    MYSQL_USER = url.username
    MYSQL_PASSWORD = url.password
    MYSQL_DB = url.path[1:]
    MYSQL_PORT = url.port or 3306
