from flask_mysqldb import MySQL

mysql = MySQL()

def init_db(app):
    mysql.init_app(app)
    # Attach the MySQL instance to the app for global access
    app.db = mysql
