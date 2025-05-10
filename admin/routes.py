from flask import Blueprint, render_template, redirect, url_for, session, flash, request, jsonify, current_app
from MySQLdb.cursors import DictCursor

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/')
def admin_home():
    if not (session.get('logged_in') and session.get('user_type') == 'admin'):
        flash('Please log in as an admin to access the dashboard.', 'warning')
        return redirect(url_for('get_started'))

    cur = current_app.db.connection.cursor(DictCursor)

    # Quick Stats
    cur.execute("SELECT COUNT(*) AS total FROM auth_users")
    total_users = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) AS active FROM auth_users WHERE created_at >= NOW() - INTERVAL 30 DAY")
    active_users = cur.fetchone()['active']
    cur.execute("SELECT COUNT(*) AS pending FROM institutions WHERE status = 'pending'")
    pending_in = cur.fetchone()['pending']

    # Recent Activity (past week)
    cur.execute("SELECT COUNT(*) AS regs FROM auth_users WHERE created_at >= NOW() - INTERVAL 7 DAY")
    recent_regs = cur.fetchone()['regs']
    cur.execute("SELECT COUNT(*) AS tickets FROM complaints WHERE created_at >= NOW() - INTERVAL 7 DAY")
    recent_tix = cur.fetchone()['tickets']

    return render_template('admin/admin_dashboard.html',
        total_users=total_users,
        active_users=active_users,
        pending_institutes=pending_in,
        recent_regs=recent_regs,
        recent_tickets=recent_tix
    )
    
@admin_bp.route('/user_management')
def user_management():
    # Auth check
    if not (session.get('logged_in') and session.get('user_type') == 'admin'):
        flash('Please log in as an admin.', 'warning')
        return redirect(url_for('auth.login'))

    search = request.args.get('search', '').strip()
    role   = request.args.get('role', '').strip()

    query = """
      SELECT id, email, role, created_at
      FROM auth_users
      WHERE role != 'admin'
    """
    params = []

    if search:
        query += " AND (email LIKE %s OR id LIKE %s)"
        params.extend([f"%{search}%"] * 2)

    if role:
        query += " AND role = %s"
        params.append(role)

    query += " ORDER BY created_at DESC"

    cur = current_app.db.connection.cursor(DictCursor)
    cur.execute(query, tuple(params))
    users = cur.fetchall()
    cur.close()

    return render_template(
        'admin/user_management.html',
        users=users,
        search=search,
        role=role
    )

@admin_bp.route('/institution/<int:inst_id>/view')
def view_institution(inst_id):
    # Auth check
    if not (session.get('logged_in') and session.get('user_type')=='admin'):
        flash('Please log in as an admin.', 'warning')
        return redirect(url_for('auth.login'))

    cur = current_app.db.connection.cursor(DictCursor)
    cur.execute("SELECT * FROM institutions WHERE id=%s", (inst_id,))
    institution = cur.fetchone()
    cur.close()

    if not institution:
        flash('Institution not found.', 'danger')
        return redirect(url_for('admin.user_management'))

    return render_template('admin/view_institution.html', inst=institution)

@admin_bp.route('/user/<int:user_id>')
def view_user(user_id):
    if not (session.get('logged_in') and session.get('user_type') == 'admin'):
        flash('Please log in as an admin.', 'warning')
        return redirect(url_for('auth.login'))

    cur = current_app.db.connection.cursor(DictCursor)

    # Fetch base user info
    cur.execute("SELECT * FROM auth_users WHERE id = %s", (user_id,))
    user = cur.fetchone()

    if not user:
        cur.close()
        flash('User not found.', 'danger')
        return redirect(url_for('admin.user_management'))

    # Convert SQL datetime fields into Python datetime (for Jinja formatting)
    if 'created_at' in user and isinstance(user['created_at'], str):
        from datetime import datetime
        user['created_at'] = datetime.strptime(user['created_at'], "%Y-%m-%d %H:%M:%S")

    # Fetch additional details based on role
    details = None
    role = user.get('role')

    if role == 'student':
        cur.execute("SELECT * FROM students WHERE auth_user_id = %s", (user_id,))
        details = cur.fetchone()

    elif role == 'teacher':
        cur.execute("SELECT * FROM teachers WHERE auth_user_id = %s", (user_id,))
        details = cur.fetchone()

    elif role == 'institution':
        cur.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (user_id,))
        details = cur.fetchone()

    cur.close()

    return render_template("admin/view_user.html", user=user, details=details)

@admin_bp.route('/user/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    if not (session.get('logged_in') and session.get('user_type') == 'admin'):
        flash("Unauthorized access.", "danger")
        return redirect(url_for('admin.user_management'))  # Adjust destination

    try:
        cur = current_app.db.connection.cursor()

        # Check if user exists
        cur.execute("SELECT * FROM auth_users WHERE id=%s", (user_id,))
        user = cur.fetchone()
        if not user:
            cur.close()
            flash("User not found.", "danger")
            return redirect(url_for('admin.user_management'))

        # Dependency cleanup
        cur.execute("DELETE FROM student_reports WHERE student_id = %s", (user_id,))
        cur.execute("DELETE FROM complaints WHERE user_id = %s OR against_auth_id = %s", (user_id, user_id))
        cur.execute("DELETE FROM teachers WHERE auth_user_id = %s", (user_id,))
        cur.execute("DELETE FROM institutions WHERE auth_user_id = %s", (user_id,))
        cur.execute("DELETE FROM students WHERE auth_user_id = %s", (user_id,))
        cur.execute("DELETE FROM auth_users WHERE id = %s", (user_id,))

        current_app.db.connection.commit()
        cur.close()

        flash("User permanently deleted successfully.", "success")
        return redirect(url_for('admin.user_management'))  # Adjust to your admin page

    except Exception as e:
        current_app.db.connection.rollback()
        cur.close()
        flash(f"Error deleting user: {str(e)}", "danger")
        return redirect(url_for('admin.user_management'))

@admin_bp.route('/requests')
def requests():
    # Ensure the admin is logged in
    if not (session.get('logged_in') and session.get('user_type') == 'admin'):
        flash('Please log in as an admin to access this page.', 'warning')
        return redirect(url_for('auth.get_started'))

    # Get search and status filter from the request
    search_query = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()

    # SQL query with optional filtering
    query = "SELECT * FROM institutions WHERE 1=1"
    params = []

    if search_query:
        query += " AND (institution_name LIKE %s OR id LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])

    if status_filter:
        query += " AND status = %s"
        params.append(status_filter)

    # Execute the query
    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute(query, tuple(params))
    institutions = cursor.fetchall()
    cursor.close()

    return render_template('admin/requests.html', institutions=institutions)

@admin_bp.route('/statistics')
def statistics():
    if not session.get('logged_in') or session.get('user_type') != 'admin':
        flash("Please log in as an admin.", "warning")
        return redirect(url_for('auth.login'))

    cur = current_app.db.connection.cursor(DictCursor)

    # User stats
    cur.execute("SELECT COUNT(*) AS total FROM auth_users")
    total_users = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) AS active FROM auth_users WHERE created_at >= NOW() - INTERVAL 30 DAY")
    new_users = cur.fetchone()['active']

    # Institute stats
    cur.execute("SELECT COUNT(*) AS total FROM institutions")
    total_institutes = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) AS pending FROM institutions WHERE status = 'pending'")
    pending_institutes = cur.fetchone()['pending']
    cur.execute("SELECT COUNT(*) AS approved FROM institutions WHERE status = 'approved'")
    approved_institutes = cur.fetchone()['approved']

    return render_template(
        'admin/statistics.html',
        total_users=total_users,
        new_users=new_users,
        total_institutes=total_institutes,
        pending_institutes=pending_institutes,
        approved_institutes=approved_institutes
    )

@admin_bp.route('/settings')
def settings():
    return render_template('admin/settings.html')

@admin_bp.route('/update_institution_status', methods=['POST'])
def update_institution_status():
    # Ensure the admin is logged in
    if not (session.get('logged_in') and session.get('user_type') == 'admin'):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    institute_id = data.get('instituteId')
    action = data.get('action')

    if not institute_id or not action:
        return jsonify({'error': 'Missing parameters'}), 400

    try:
        cursor = current_app.db.connection.cursor()
        sql = "UPDATE institutions SET status = %s WHERE id = %s"
        cursor.execute(sql, (action, institute_id))
        current_app.db.connection.commit()
        return jsonify({'message': 'Status updated successfully'})
    except Exception as e:
        current_app.db.connection.rollback()
        return jsonify({'error': str(e)}), 500
