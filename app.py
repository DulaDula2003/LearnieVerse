from flask import Flask, render_template, session, current_app
from config import Config
from MySQLdb.cursors import DictCursor
from db import init_db
from datetime import datetime, time

# Routes Import
from auth.routes import auth_bp
from admin.routes import admin_bp
from institute.routes import institute_bp
from teacher.routes import teacher_bp
from student.routes import student_bp

app = Flask(__name__)
app.config.from_object(Config)

# Initialize the database
init_db(app)

# Register the blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(institute_bp, url_prefix='/institute')
app.register_blueprint(teacher_bp, url_prefix='/teacher')
app.register_blueprint(student_bp, url_prefix='/student')

@app.template_filter('timeformat')
def timeformat(value, format='%I:%M %p'):
    """Format a datetime.time or datetime.datetime object to a string."""
    if isinstance(value, (datetime,)):
        return value.strftime(format)
    elif hasattr(value, 'strftime'):
        return value.strftime(format)
    return value

@app.context_processor
def inject_institute_name():
    if 'user_type' in session and session['user_type'] == 'teacher':
        cursor = current_app.db.connection.cursor(DictCursor)
        cursor.execute("""
            SELECT i.institution_name 
            FROM teachers t 
            JOIN institutions i ON t.institution_id = i.id 
            WHERE t.auth_user_id = %s
        """, (session['user_id'],))
        result = cursor.fetchone()
        return dict(institute_name=result['institution_name'] if result else '')
    return {}

@app.route('/')
def home():
    # Renders the Home.html template
    return render_template('index.html')

@app.route('/about')
def about_us():
    # Renders the Home.html template
    return render_template('about_us.html')

if __name__ == "__main__":
    app.run(debug=True, host='127.0.0.1', port=8080)