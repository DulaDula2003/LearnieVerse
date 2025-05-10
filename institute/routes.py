from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, jsonify
from MySQLdb.cursors import DictCursor
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash  # ← add this
import os, uuid
from email_utils import send_email


# Create the institute blueprint.
# Optionally, you can specify a template_folder if your templates are organized separately.
institute_bp = Blueprint('institute', __name__, template_folder='templates/institute')

@institute_bp.route('/dashboard')
def dashboard():
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)
    
    # Get institute profile
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()
    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    institute_id = institute['id']

    # Count students
    cursor.execute("SELECT COUNT(*) AS total_students FROM students WHERE institute_id = %s", (institute_id,))
    total_students = cursor.fetchone()['total_students']

    # Count teachers
    cursor.execute("SELECT COUNT(*) AS total_teachers FROM teachers WHERE institution_id = %s", (institute_id,))
    total_teachers = cursor.fetchone()['total_teachers']

    # Fetch recent announcements
    cursor.execute("""
        SELECT title FROM announcements
        WHERE institute_id = %s
        ORDER BY created_at DESC LIMIT 3
    """, (institute_id,))
    announcements = cursor.fetchall()

    # Fetch pending complaints
    cursor.execute("""
        SELECT subject FROM complaints
        WHERE status = 'pending'
        ORDER BY created_at DESC LIMIT 3
    """)
    complaints = cursor.fetchall()

    return render_template(
        'institute/dashboard.html',
        institute=institute,
        total_students=total_students,
        total_teachers=total_teachers,
        announcements=announcements,
        complaints=complaints
    )

@institute_bp.route('/students')
def students():
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution to access students.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()

    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    institute_id = institute['id']
    cursor.execute("SELECT * FROM students WHERE institute_id = %s", (institute_id,))
    print(institute_id)
    students = cursor.fetchall()

    return render_template('institute/students.html', institute=institute, students=students)

@institute_bp.route('/student/delete/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution to delete students.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Get institute info
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()
    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    institute_id = institute['id']

    # Check if the student exists in this institute
    cursor.execute("SELECT * FROM students WHERE id = %s AND institute_id = %s", (student_id, institute_id))
    student = cursor.fetchone()
    if not student:
        flash("Student not found or unauthorized.", "danger")
        return redirect(url_for('institute.students'))

    try:
        # OPTIONAL: Delete other related data (submissions, attendance, etc.)

        # Delete student record
        cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
        current_app.db.connection.commit()
        flash("Student successfully deleted.", "success")
    except Exception as e:
        current_app.db.connection.rollback()
        flash("Error deleting student: " + str(e), "danger")

    return redirect(url_for('institute.students'))

@institute_bp.route('/student/edit/<int:student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Get institute
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()
    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    institute_id = institute['id']

    # Get student info
    cursor.execute("SELECT s.*, a.email FROM students s JOIN auth_users a ON s.auth_user_id = a.id WHERE s.id = %s AND s.institute_id = %s", (student_id, institute_id))
    student = cursor.fetchone()
    if not student:
        flash("Student not found or unauthorized.", "danger")
        return redirect(url_for('institute.students'))

    if request.method == 'POST':
        try:
            # Get updated data
            student_name = request.form.get('student_name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            dob = request.form.get('dob')
            gender = request.form.get('gender')
            city = request.form.get('city')
            state = request.form.get('state')
            address = request.form.get('address')
            enroll_number = request.form.get('enroll_number')
            course = request.form.get('course')
            guardian_name = request.form.get('guardian_name')
            guardian_phone = request.form.get('guardian_phone')
            username = request.form.get('username')

            # Update profile pic if reuploaded
            profile_pic_file = request.files.get('profile_pic')
            if profile_pic_file and profile_pic_file.filename:
                profile_pic_filename = secure_filename(profile_pic_file.filename)
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                profile_pic_file.save(os.path.join(upload_folder, profile_pic_filename))
            else:
                profile_pic_filename = student['profile_pic']

            # Update auth_users table (email)
            cursor.execute("UPDATE auth_users SET email = %s WHERE id = %s", (email, student['auth_user_id']))

            # Update students table
            sql = """
                UPDATE students SET
                    student_name=%s, phone=%s, dob=%s, gender=%s, city=%s, state=%s, address=%s,
                    enroll_number=%s, course=%s, profile_pic=%s, guardian_name=%s, guardian_phone=%s,
                    username=%s
                WHERE id = %s
            """
            cursor.execute(sql, (
                student_name, phone, dob, gender, city, state, address,
                enroll_number, course, profile_pic_filename, guardian_name, guardian_phone,
                username, student_id
            ))

            current_app.db.connection.commit()
            flash("Student updated successfully!", "success")
            return redirect(url_for('institute.students'))

        except Exception as e:
            current_app.db.connection.rollback()
            flash("Error updating student: " + str(e), "danger")

    return render_template("institute/edit_student.html", student=student, institute=institute)

@institute_bp.route('/student_profile/<int:student_id>')
def student_profile(student_id):
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Institute info
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()
    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    # Student info + email
    cursor.execute("""
        SELECT s.*, a.email 
        FROM students s
        JOIN auth_users a ON s.auth_user_id = a.id
        WHERE s.id = %s
    """, (student_id,))
    student = cursor.fetchone()
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for('institute.students'))

    # Attendance % (overall)
    cursor.execute("""
        SELECT 
          ROUND(SUM(status = 'present') / COUNT(*) * 100, 2) AS attendance_pct
        FROM class_attendance
        WHERE student_id = %s
    """, (student_id,))
    attendance_result = cursor.fetchone()
    attendance_pct = attendance_result['attendance_pct'] if attendance_result and attendance_result['attendance_pct'] is not None else "N/A"

    # Latest Grades (from reports)
    cursor.execute("""
        SELECT subject_name, marks, percentage 
        FROM student_report_subjects 
        WHERE report_id = (
            SELECT id FROM student_reports 
            WHERE student_id = %s 
            ORDER BY report_date DESC 
            LIMIT 1
        )
    """, (student_id,))
    grades = cursor.fetchall()

    # Notifications: Upcoming exams or due tests
    cursor.execute("""
        SELECT title, test_date 
        FROM tests 
        JOIN test_assigned_students tas ON tests.id = tas.test_id
        WHERE tas.student_id = %s
          AND status IN ('draft', 'live')
          AND CONCAT(test_date, ' ', test_time) > NOW()
        ORDER BY test_date ASC
    """, (student_id,))
    notifications = cursor.fetchall()

    return render_template(
        'institute/student_profile.html',
        institute=institute,
        student=student,
        attendance_pct=attendance_pct,
        grades=grades,
        notifications=notifications
    )

@institute_bp.route('/teachers')
def teachers():
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution to access announcements.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Fetch institute info using session's user_id
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()

    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    institute_id = institute['id']

    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("SELECT * FROM teachers WHERE institution_id = %s", (institute_id,))
    teachers = cursor.fetchall()

    return render_template('institute/teachers.html', institute=institute, teachers=teachers)

@institute_bp.route('/teacher/edit/<int:teacher_id>', methods=['GET', 'POST'])
def edit_teacher(teacher_id):
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Get the logged-in institute
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()
    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    institute_id = institute['id']

    # Get the teacher with auth_user email join
    cursor.execute("""
        SELECT t.*, a.email FROM teachers t
        JOIN auth_users a ON t.auth_user_id = a.id
        WHERE t.id = %s AND t.institution_id = %s
    """, (teacher_id, institute_id))
    teacher = cursor.fetchone()

    if not teacher:
        flash("Teacher not found or unauthorized.", "danger")
        return redirect(url_for('institute.teachers'))

    if request.method == 'POST':
        try:
            # Get all updated form data
            teacher_name = request.form.get('teacher_name')
            email = request.form.get('email')
            username = request.form.get('username')
            phone = request.form.get('phone')
            dob = request.form.get('dob')
            gender = request.form.get('gender')
            city = request.form.get('city')
            state = request.form.get('state')
            address = request.form.get('address')
            department = request.form.get('department')
            subject_expertise1 = request.form.get('subject_expertise1')
            subject_expertise2 = request.form.get('subject_expertise2')
            years_experience = request.form.get('years_experience')
            highest_qualification = request.form.get('highest_qualification')
            specialization = request.form.get('specialization')
            teacher_code = request.form.get('teacher_id')  # field name is teacher_id in form

            # FILES
            profile_pic_file = request.files.get('profile_pic')
            resume_file = request.files.get('resume')

            profile_pic_filename = teacher['profile_pic']
            resume_filename = teacher['resume']

            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)

            if profile_pic_file and profile_pic_file.filename:
                profile_pic_filename = secure_filename(profile_pic_file.filename)
                profile_pic_file.save(os.path.join(upload_folder, profile_pic_filename))

            if resume_file and resume_file.filename:
                resume_filename = secure_filename(resume_file.filename)
                resume_file.save(os.path.join(upload_folder, resume_filename))

            # Update auth_users email
            cursor.execute("UPDATE auth_users SET email = %s WHERE id = %s", (email, teacher['auth_user_id']))

            # Update teachers
            cursor.execute("""
                UPDATE teachers SET
                    teacher_name=%s, username=%s, phone=%s, dob=%s, gender=%s,
                    city=%s, state=%s, address=%s, department=%s,
                    subject_expertise1=%s, subject_expertise2=%s,
                    years_experience=%s, highest_qualification=%s, specialization=%s,
                    teacher_id=%s, profile_pic=%s, resume=%s
                WHERE id = %s
            """, (
                teacher_name, username, phone, dob, gender,
                city, state, address, department,
                subject_expertise1, subject_expertise2,
                years_experience, highest_qualification, specialization,
                teacher_code, profile_pic_filename, resume_filename,
                teacher_id
            ))

            current_app.db.connection.commit()
            flash("Teacher updated successfully!", "success")
            return redirect(url_for('institute.teachers'))

        except Exception as e:
            current_app.db.connection.rollback()
            flash("Update failed: " + str(e), "danger")

    return render_template("institute/edit_teacher.html", teacher=teacher, institute=institute)

@institute_bp.route('/teacher/delete/<int:teacher_id>', methods=['POST'])
def delete_teacher(teacher_id):
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution to delete teachers.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Get the logged-in institute
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()
    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    institute_id = institute['id']

    # Check if the teacher belongs to this institute
    cursor.execute("SELECT * FROM teachers WHERE id = %s AND institution_id = %s", (teacher_id, institute_id))
    teacher = cursor.fetchone()
    if not teacher:
        flash("Teacher not found or unauthorized.", "danger")
        return redirect(url_for('institute.teachers'))

    try:
        # Delete related student_invites
        cursor.execute("DELETE FROM student_invites WHERE teacher_id = %s", (teacher_id,))

        # Now delete the teacher
        cursor.execute("DELETE FROM teachers WHERE id = %s", (teacher_id,))
        
        current_app.db.connection.commit()
        flash("Teacher successfully deleted.", "success")
    except Exception as e:
        current_app.db.connection.rollback()
        flash("Error deleting teacher: " + str(e), "danger")

    return redirect(url_for('institute.teachers'))

@institute_bp.route('/teacher_profile/<int:teacher_id>')
def teacher_profile(teacher_id):
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution to view teacher profiles.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Get the institute info (optional, for name in header)
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()

    # Get the teacher's info
    cursor.execute("""
    SELECT t.*, a.email 
    FROM teachers t
    JOIN auth_users a ON t.auth_user_id = a.id
    WHERE t.id = %s
""", (teacher_id,))
    teacher = cursor.fetchone()

    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for('institute.teachers'))

    return render_template('institute/teacher_profile.html', teacher=teacher, institute=institute)

@institute_bp.route('/announcements', methods=['GET', 'POST'])
def announcements():
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Get institute info
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()
    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    institute_id = institute['id']

    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        audience = request.form.get('audience')

        if not title or not content or not audience:
            flash("All fields are required.", "warning")
            return redirect(url_for('institute.announcements'))

        try:
            cursor.execute("""
                INSERT INTO announcements (institute_id, title, content, audience)
                VALUES (%s, %s, %s, %s)
            """, (institute_id, title, content, audience))
            current_app.db.connection.commit()
            flash("Announcement posted!", "success")
            return redirect(url_for('institute.announcements'))
        except Exception as e:
            current_app.db.connection.rollback()
            flash("Error posting announcement: " + str(e), "danger")

    # Fetch recent 2 announcements
    cursor.execute("""
        SELECT * FROM announcements
        WHERE institute_id = %s
        ORDER BY created_at DESC
        LIMIT 2
    """, (institute_id,))
    recent_announcements = cursor.fetchall()

    # Fetch all announcements for popup
    cursor.execute("""
        SELECT * FROM announcements
        WHERE institute_id = %s
        ORDER BY created_at DESC
    """, (institute_id,))
    all_announcements = cursor.fetchall()

    return render_template('institute/announcements.html',
                           institute=institute,
                           recent_announcements=recent_announcements,
                           all_announcements=all_announcements)

@institute_bp.route('/reports')
def reports():
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Get the logged-in institute
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()
    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    institute_id = institute['id']

    # Get all student reports where the report's teacher is part of this institute
    cursor.execute("""
        SELECT 
            sr.id AS report_id,
            sr.class_name,
            sr.academic_year,
            sr.attendance_pct,
            sr.total_percentage,
            sr.report_date,
            sr.created_at,
            t.teacher_name,
            s.student_name
        FROM student_reports sr
        JOIN teachers t ON sr.teacher_id = t.id
        JOIN students s ON sr.student_id = s.id
        WHERE t.institution_id = %s
        ORDER BY sr.report_date DESC
    """, (institute_id,))
    
    reports = cursor.fetchall()

    return render_template("institute/reports.html", institute=institute, reports=reports)

@institute_bp.route('/complaints')
def complaints():
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Fetch institute info
    cursor.execute("SELECT * FROM institutions WHERE auth_user_id = %s", (session['user_id'],))
    institute = cursor.fetchone()
    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    # Fetch complaints where institution is the target (against_auth_id matches logged-in user's auth ID)
    cursor.execute("""
      SELECT
        c.id,
        c.category,
        c.subject,
        c.details,
        c.is_anonymous,
        c.status,
        c.created_at,
        fu.email       AS from_email,
        fu.role        AS from_role,
        au.email       AS against_email,
        au.role        AS against_role
      FROM complaints c
      JOIN auth_users fu ON c.user_id = fu.id
      JOIN auth_users au ON c.against_auth_id = au.id
      WHERE c.against_auth_id = %s
      ORDER BY c.created_at DESC
    """, (session['user_id'],))
    
    complaints = cursor.fetchall()
    cursor.close()

    return render_template(
        'institute/complaints.html',
        institute=institute,
        complaints=complaints
    )


@institute_bp.route('/complaints/approve/<int:complaint_id>', methods=['POST'])
def approve_complaint(complaint_id):
    """Mark a complaint as reviewed/approved."""
    cursor = current_app.db.connection.cursor()
    cursor.execute(
        "UPDATE complaints SET status = 'reviewed' WHERE id = %s",
        (complaint_id,)
    )
    current_app.db.connection.commit()
    flash(f"Complaint #{complaint_id} approved.", "success")
    return redirect(url_for('institute.complaints'))

@institute_bp.route('/complaints/pending/<int:complaint_id>', methods=['POST'])
def pending_complaint(complaint_id):
    """Revert a complaint back to pending."""
    cursor = current_app.db.connection.cursor()
    cursor.execute(
        "UPDATE complaints SET status = 'pending' WHERE id = %s",
        (complaint_id,)
    )
    current_app.db.connection.commit()
    flash(f"Complaint #{complaint_id} set back to pending.", "info")
    return redirect(url_for('institute.complaints'))


@institute_bp.route('/complaints/delete/<int:complaint_id>', methods=['POST'])
def delete_complaint(complaint_id):
    cursor = current_app.db.connection.cursor()
    cursor.execute("DELETE FROM complaints WHERE id = %s", (complaint_id,))
    current_app.db.connection.commit()
    flash(f"Complaint #{complaint_id} deleted.", "info")
    return redirect(url_for('institute.complaints'))


@institute_bp.route('/attendance')
def attendance():
    # 1. Auth guard
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        flash("Please log in as an institution.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # 2. Fetch institute record
    cursor.execute(
    "SELECT id, institution_name, dark_mode FROM institutions WHERE auth_user_id = %s",
    (session['user_id'],)
    )
    institute = cursor.fetchone()
    if not institute:
        flash("Institute not found.", "danger")
        return redirect(url_for('auth.login'))

    inst_id = institute['id']

    # 3. Aggregate attendance per student
    cursor.execute("""
        SELECT
          s.id                AS student_id,
          s.student_name      AS student_name,
          COUNT(ca.id)        AS total_days,
          SUM(CASE WHEN ca.status = 'present' THEN 1 ELSE 0 END) AS present,
          SUM(CASE WHEN ca.status = 'absent'  THEN 1 ELSE 0 END) AS absent,
          ROUND(
            SUM(CASE WHEN ca.status = 'present' THEN 1 ELSE 0 END)
            / NULLIF(COUNT(ca.id), 0) * 100
          , 2)                AS attendance_pct
        FROM students s
        LEFT JOIN class_attendance ca
          ON ca.student_id = s.id
        WHERE s.institute_id = %s
        GROUP BY s.id, s.student_name
        ORDER BY s.student_name ASC
    """, (inst_id,))

    attendance_records = cursor.fetchall()

    return render_template(
        'institute/attendance.html',
        institute=institute,
        attendance_records=attendance_records
    )


@institute_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if not session.get('logged_in') or session.get('user_type') != 'institution':
        return redirect(url_for('auth.login'))

    auth_id = session['user_id']
    cur     = current_app.db.connection.cursor(DictCursor)

    if request.method == 'GET':
        # ─── Fetch institute profile & its user email ─────────────────
        cur.execute("""
          SELECT i.*, au.email
          FROM institutions i
          JOIN auth_users au ON i.auth_user_id = au.id
          WHERE i.auth_user_id = %s
        """, (auth_id,))
        profile = cur.fetchone() or {}

        # ─── Build contacts list: all teachers & students under this institute ──
        contacts = []
        # Teachers
        cur.execute("""
          SELECT au.id, au.email
          FROM teachers t
          JOIN auth_users au ON t.auth_user_id = au.id
          WHERE t.institution_id = %s
        """, (profile.get('id'),))
        for r in cur.fetchall():
            contacts.append({'id':r['id'],'email':r['email'],'type':'Teacher'})
        # Students
        cur.execute("""
          SELECT au.id, au.email
          FROM students s
          JOIN auth_users au ON s.auth_user_id = au.id
          WHERE s.institute_id = %s
        """, (profile.get('id'),))
        for r in cur.fetchall():
            contacts.append({'id':r['id'],'email':r['email'],'type':'Student'})

        return render_template(
        'institute/settings.html',
        institute = profile,
        profile   = profile,
        contacts  = contacts
        )
        
    # ─── POST: dispatch on action ─────────────────────────────────────
    action = request.form.get('action')
    try:
        if action == 'profile':
            # update name / phone / logo
            name  = request.form['institution_name']
            phone = request.form['phone']
            logo  = request.files.get('logo')
            if logo and logo.filename:
                fn = secure_filename(logo.filename)
                path = os.path.join(current_app.root_path,'static','uploads')
                os.makedirs(path,exist_ok=True)
                logo.save(os.path.join(path,fn))
                cur.execute("UPDATE institutions SET logo=%s WHERE auth_user_id=%s",(fn,auth_id))
            cur.execute("UPDATE institutions SET institution_name=%s, phone=%s WHERE auth_user_id=%s",(name,phone,auth_id))
            flash("Profile updated","success")

        elif action == 'password':
            old = request.form['current_password']
            new = request.form['new_password']
            cf  = request.form['confirm_password']
            cur.execute("SELECT password FROM auth_users WHERE id=%s",(auth_id,))
            if not check_password_hash(cur.fetchone()['password'],old):
                flash("Wrong current password","danger")
                return redirect(url_for('institute.settings'))
            if new!=cf:
                flash("Passwords do not match","danger")
                return redirect(url_for('institute.settings'))
            cur.execute("UPDATE auth_users SET password=%s WHERE id=%s",(generate_password_hash(new),auth_id))
            session.clear()
            flash("Password changed, please log in again","success")
            return redirect(url_for('auth.login'))

        elif action == 'appearance':
            dm = 1 if request.form.get('dark_mode')=='on' else 0
            cur.execute("UPDATE institutions SET dark_mode=%s WHERE auth_user_id=%s",(dm,auth_id))
            flash("Appearance saved","success")

        elif action == 'complaint':
            cat     = request.form['category']
            against = int(request.form['against_id'])
            subj    = request.form['subject']
            det     = request.form['details']
            anon    = 1 if request.form.get('anonymous') else 0
            cur.execute("""
              INSERT INTO complaints
                (user_id,against_auth_id,category,subject,details,is_anonymous)
              VALUES(%s,%s,%s,%s,%s,%s)
            """,(auth_id,against,cat,subj,det,anon))
            flash("Complaint submitted","success")

        current_app.db.connection.commit()

    except Exception as e:
        current_app.db.connection.rollback()
        flash(f"Error: {e}","danger")

    return redirect(url_for('institute.settings'))


@institute_bp.route('/invite_teacher', methods=['POST'])
def invite_teacher():
    data = request.get_json()
    teacher_email = data.get('teacher_email')
    if not teacher_email:
        return jsonify({'error': 'Teacher email is required'}), 400

    # Generate a unique invitation token
    token = str(uuid.uuid4())

    # Get the auth_user_id from session (from auth_users table)
    auth_user_id = session.get('user_id')
    if not auth_user_id:
        return jsonify({'error': 'Institute not logged in'}), 403

    # Look up the institute's record in the institutions table using auth_user_id
    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("SELECT id FROM institutions WHERE auth_user_id = %s", (auth_user_id,))
    institute = cursor.fetchone()
    if not institute:
        return jsonify({'error': 'Institute record not found'}), 400
    institute_id = institute['id']

    try:
        # Now use the institute_id from the institutions table for the foreign key
        cursor = current_app.db.connection.cursor()
        sql = "INSERT INTO teacher_invites (token, teacher_email, institute_id) VALUES (%s, %s, %s)"
        cursor.execute(sql, (token, teacher_email, institute_id))
        current_app.db.connection.commit()

        # Build a unique signup link for the teacher (adjust the endpoint as needed)
        signup_link = current_app.url_for('auth.teacher_signup', token=token, _external=True)

        # Send the invite email (make sure send_email is defined and imported)
        subject = "You're invited to join LearnieVerse as a Teacher"
        body = f"Hello,\n\nYou've been invited to join LearnieVerse as a teacher. Please sign up using the following link:\n\n{signup_link}\n\nThank you!"
        send_email(teacher_email, subject, body)

        return jsonify({'message': 'Invitation sent successfully', 'signup_link': signup_link})
    except Exception as e:
        current_app.db.connection.rollback()
        return jsonify({'error': str(e)}), 500
