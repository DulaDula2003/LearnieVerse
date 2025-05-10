from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask import jsonify, current_app, session
from MySQLdb.cursors import DictCursor
from email_utils import send_email
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
import datetime

teacher_bp = Blueprint('teacher', __name__, template_folder='templates/teacher')

@teacher_bp.route('/dashboard')
def dashboard():
    if not session.get('logged_in') or session['user_type'] != 'teacher':
        return redirect(url_for('auth.login'))

    auth_id = session['user_id']
    cursor = current_app.db.connection.cursor(DictCursor)

    # Get teacher & institute name
    cursor.execute("""
        SELECT t.teacher_name, i.institution_name, t.id AS teacher_id, t.institution_id
        FROM teachers t
        JOIN institutions i ON t.institution_id = i.id
        WHERE t.auth_user_id = %s
    """, (auth_id,))
    data = cursor.fetchone()
    teacher_id = data['teacher_id']
    institution_id = data['institution_id']

    # Classes this week
    cursor.execute("""
        SELECT COUNT(*) AS total FROM classes 
        WHERE teacher_id = %s AND WEEK(class_date) = WEEK(CURDATE())
    """, (teacher_id,))
    total_classes = cursor.fetchone()['total']

    # Messages (not read)
    cursor.execute("""
        SELECT COUNT(*) AS pending FROM messages 
        WHERE receiver_id = %s AND is_read = 0
    """, (auth_id,))
    pending_messages = cursor.fetchone()['pending']

    # Assignments to grade = pending test results without a grade
    cursor.execute("""
        SELECT COUNT(*) AS total FROM test_results tr
        JOIN tests t ON tr.test_id = t.id
        WHERE t.teacher_id = %s AND (tr.grade IS NULL OR tr.grade = '')
    """, (teacher_id,))
    assignments_to_grade = cursor.fetchone()['total']

    # Upcoming classes
    cursor.execute("""
        SELECT class_name AS course_name, class_time AS time, class_date AS date 
        FROM classes 
        WHERE teacher_id = %s AND class_date >= CURDATE() 
        ORDER BY class_date, class_time
        LIMIT 5
    """, (teacher_id,))
    upcoming_classes = cursor.fetchall()

    # Recent activities (show latest 5 class creations or updates)
    cursor.execute("""
        SELECT CONCAT('Class "', class_name, '" scheduled for ', class_date) AS activity 
        FROM classes 
        WHERE teacher_id = %s 
        ORDER BY created_at DESC LIMIT 5
    """, (teacher_id,))
    recent_activities = [row['activity'] for row in cursor.fetchall()]

    # Messages preview
    cursor.execute("""
        SELECT content FROM messages 
        WHERE receiver_id = %s 
        ORDER BY created_at DESC 
        LIMIT 5
    """, (auth_id,))
    messages = [row['content'] for row in cursor.fetchall()]

    # Announcements
    cursor.execute("""
        SELECT title FROM announcements 
        WHERE institute_id = %s AND audience IN ('teacher', 'all')
        ORDER BY created_at DESC LIMIT 5
    """, (institution_id,))
    announcements = [row['title'] for row in cursor.fetchall()]
    
    # Class performance: avg score per class
    cursor.execute("""
        SELECT c.class_name, 
            ROUND(AVG(tr.score), 1) AS avg_score
        FROM test_results tr
        JOIN tests t ON tr.test_id = t.id
        JOIN classes c ON t.teacher_id = %s AND c.teacher_id = t.teacher_id
        WHERE t.teacher_id = %s
        GROUP BY c.class_name
        ORDER BY avg_score DESC
        LIMIT 5
    """, (teacher_id, teacher_id))

    performance_data = cursor.fetchall()
    labels = [row['class_name'] for row in performance_data]
    scores = [row['avg_score'] for row in performance_data]

    return render_template("teacher/dashboard.html",
        teacher_name=data['teacher_name'],
        institute_name=data['institution_name'],
        total_classes=total_classes,
        assignments_to_grade=assignments_to_grade,
        pending_messages=pending_messages,
        upcoming_classes=upcoming_classes,
        recent_activities=recent_activities,
        messages=messages,
        announcements=announcements,
        perf_labels=labels,
        perf_scores=scores
    )

@teacher_bp.route('/manage_classes')
def manage_classes():
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher to view your classes.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    cursor.execute("SELECT id FROM teachers WHERE auth_user_id = %s", (session['user_id'],))
    teacher = cursor.fetchone()
    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for('auth.login'))

    teacher_id = teacher['id']
    cursor.execute("SELECT * FROM classes WHERE teacher_id = %s ORDER BY class_date DESC, class_time ASC", (teacher_id,))
    classes = cursor.fetchall()

    return render_template('teacher/manage_classes.html', classes=classes)

@teacher_bp.route('/class/<int:class_id>/live')
def make_class_live(class_id):
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher to manage live sessions.", "danger")
        return redirect(url_for('auth.login'))
  
    # Here, you could update a flag in the database to mark the class as live.
    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("UPDATE classes SET is_live = 1 WHERE id = %s", (class_id,))
    current_app.db.connection.commit()
  
    flash("Class is now live!", "success")
    return redirect(url_for('teacher.manage_classes'))

@teacher_bp.route('/class/<int:class_id>/end_live')
def end_class_live(class_id):
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher to manage live sessions.", "danger")
        return redirect(url_for('auth.login'))
  
    # Update the class to end the live session.
    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("UPDATE classes SET is_live = 0 WHERE id = %s", (class_id,))
    current_app.db.connection.commit()
  
    flash("Live session ended!", "success")
    return redirect(url_for('teacher.manage_classes'))

@teacher_bp.route('/delete_class/<int:class_id>', methods=['POST'])
def delete_class(class_id):
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Unauthorized access. Please log in as a teacher.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Get the teacher_id of the logged-in user
    cursor.execute("SELECT id FROM teachers WHERE auth_user_id = %s", (session['user_id'],))
    teacher = cursor.fetchone()

    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for('auth.login'))

    teacher_id = teacher['id']

    # Check if the class belongs to the current teacher
    cursor.execute("SELECT * FROM classes WHERE id = %s AND teacher_id = %s", (class_id, teacher_id))
    class_entry = cursor.fetchone()

    if not class_entry:
        flash("Class not found or you're not authorized to delete this class.", "danger")
        return redirect(url_for('teacher.manage_classes'))

    try:
        # First, delete student associations
        cursor.execute("DELETE FROM class_students WHERE class_id = %s", (class_id,))

        # Then delete the class
        cursor.execute("DELETE FROM classes WHERE id = %s", (class_id,))
        current_app.db.connection.commit()

        flash("Class deleted successfully!", "success")

    except Exception as e:
        current_app.db.connection.rollback()
        flash("Error deleting class: " + str(e), "danger")

    return redirect(url_for('teacher.manage_classes'))

@teacher_bp.route('/edit_class/<int:class_id>', methods=['GET', 'POST'])
def edit_class(class_id):
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher to access this page.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Fetch the class details
    cursor.execute("SELECT * FROM classes WHERE id = %s", (class_id,))
    class_data = cursor.fetchone()

    if not class_data:
        flash("Class not found.", "danger")
        return redirect(url_for('teacher.manage_classes'))

    if request.method == 'POST':
        class_name = request.form.get('class_name')
        class_time = request.form.get('class_time')
        class_date = request.form.get('class_date')
        join_link = request.form.get('join_link')
        visibility = request.form.get('visibility')

        try:
            cursor.execute("""
                UPDATE classes
                SET class_name=%s, class_time=%s, class_date=%s, join_link=%s, visibility=%s
                WHERE id=%s
            """, (class_name, class_time, class_date, join_link, visibility, class_id))
            current_app.db.connection.commit()
            flash("Class updated successfully!", "success")
            return redirect(url_for('teacher.manage_classes'))
        except Exception as e:
            current_app.db.connection.rollback()
            flash("Error updating class: " + str(e), "danger")

    return render_template('teacher/edit_class.html', class_data=class_data)

@teacher_bp.route('/take_class/<int:class_id>', methods=['GET', 'POST'])
def take_class(class_id):
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Here, you could update a flag in the database to mark the class as live.
    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("UPDATE classes SET is_live = 1 WHERE id = %s", (class_id,))
    current_app.db.connection.commit()

    # Get teacher
    cursor.execute("SELECT id FROM teachers WHERE auth_user_id = %s", (session['user_id'],))
    teacher = cursor.fetchone()
    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for('auth.login'))

    teacher_id = teacher['id']

    # Get class info
    cursor.execute("SELECT * FROM classes WHERE id = %s AND teacher_id = %s", (class_id, teacher_id))
    class_info = cursor.fetchone()
    if not class_info:
        flash("Class not found or unauthorized access.", "danger")
        return redirect(url_for('teacher.manage_classes'))

    # Get students in class
    cursor.execute("""
        SELECT s.* FROM students s
        JOIN class_students cs ON s.id = cs.student_id
        WHERE cs.class_id = %s
    """, (class_id,))
    students = cursor.fetchall()

    # If no students explicitly selected, fallback to teacher's full list
    if not students:
        cursor.execute("SELECT * FROM students WHERE teacher_id = %s", (teacher_id,))
        students = cursor.fetchall()

    today = datetime.date.today()

    # 🔍 Enhance each student with join/leave stats
    for student in students:
        # Fetch all sessions for this student and class
        cursor.execute("""
            SELECT join_time, leave_time
            FROM class_sessions
            WHERE class_id = %s AND student_id = %s
        """, (class_id, student['id']))
        sessions = cursor.fetchall()

        # Count stats
        student['join_count'] = len(sessions)
        student['leave_count'] = sum(1 for s in sessions if s['leave_time'])
        student['last_join'] = max((s['join_time'] for s in sessions), default=None)
        student['last_leave'] = max((s['leave_time'] for s in sessions if s['leave_time']), default=None)

        # Determine current session status
        latest_session = max(sessions, key=lambda s: s['join_time']) if sessions else None
        if latest_session:
            if latest_session['leave_time'] is None:
                student['status'] = "In Class"
            else:
                student['status'] = "Left Class"
        else:
            student['status'] = "Not Joined"

        # Fetch today's attendance
        cursor.execute("""
            SELECT status FROM class_attendance
            WHERE class_id = %s AND student_id = %s AND attendance_date = %s
        """, (class_id, student['id'], today))
        attendance = cursor.fetchone()
        student['attendance_status'] = attendance['status'].capitalize() if attendance else 'Pending'

    # 📝 Handle attendance submission
    if request.method == "POST" and request.form.get('attendance_submit'):
        for student in students:
            status = request.form.get(f"attendance_{student['id']}")
            if status:
                cursor.execute("""
                    SELECT id FROM class_attendance
                    WHERE class_id = %s AND student_id = %s AND attendance_date = %s
                """, (class_id, student['id'], today))
                existing = cursor.fetchone()
                if existing:
                    cursor.execute("""
                        UPDATE class_attendance SET status = %s, marked_at = NOW()
                        WHERE id = %s
                    """, (status, existing['id']))
                else:
                    cursor.execute("""
                        INSERT INTO class_attendance (class_id, student_id, attendance_date, status)
                        VALUES (%s, %s, %s, %s)
                    """, (class_id, student['id'], today, status))
        current_app.db.connection.commit()
        flash("Attendance updated successfully.", "success")
        return redirect(url_for('teacher.take_class', class_id=class_id))

    # 💬 Fetch chat messages
    cursor.execute("""
        SELECT c.*, a.email AS sender_email
        FROM class_chats c
        JOIN auth_users a ON c.sender_id = a.id
        WHERE c.class_id = %s
        ORDER BY c.created_at ASC
    """, (class_id,))
    chats = cursor.fetchall()

    return render_template("teacher/take_class.html",
                           class_info=class_info,
                           students=students,
                           chats=chats)

@teacher_bp.route('/add_class_chat/<int:class_id>', methods=['POST'])
def add_class_chat(class_id):
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('auth.login'))
    
    chat_message = request.form.get('chat_message')
    if not chat_message:
        flash("Empty message not allowed.", "warning")
        return redirect(url_for('teacher.take_class', class_id=class_id))
    
    cursor = current_app.db.connection.cursor(DictCursor)
    try:
        # Save chat message: sender_id is the teacher's auth user id.
        cursor.execute("""
            INSERT INTO class_chats (class_id, sender_id, message)
            VALUES (%s, %s, %s)
        """, (class_id, session['user_id'], chat_message))
        current_app.db.connection.commit()
    except Exception as e:
        current_app.db.connection.rollback()
        flash("Error sending message: " + str(e), "danger")
    
    return redirect(url_for('teacher.take_class', class_id=class_id))

@teacher_bp.route('/add_new_class', methods=['GET', 'POST'])
def add_new_class():
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher to access this page.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Fetch teacher info from session, now including institution_id
    cursor.execute("SELECT id, institution_id FROM teachers WHERE auth_user_id = %s", (session['user_id'],))
    teacher = cursor.fetchone()
    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for('auth.login'))

    teacher_id = teacher['id']
    institute_id = teacher.get('institution_id')  # May return None if not set; ensure your teacher table is updated

    # Fetch students assigned to this teacher
    cursor.execute("SELECT * FROM students WHERE teacher_id = %s", (teacher_id,))
    students = cursor.fetchall()

    if request.method == 'POST':
        class_name = request.form.get('class-name')
        class_time = request.form.get('class-time')
        class_date = request.form.get('class-date')
        visibility = request.form.get('visibility')
        join_link = request.form.get('join-link') or ''  # optional
        selected_students = request.form.getlist('students')

        try:
            # Insert class, now including institute_id
            cursor.execute("""
                INSERT INTO classes (teacher_id, institute_id, class_name, class_date, class_time, visibility, join_link)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (teacher_id, institute_id, class_name, class_date, class_time, visibility, join_link))
            class_id = cursor.lastrowid

            # If "everyone" is not selected, associate specific students with this class
            if 'everyone' not in selected_students:
                for student_id in selected_students:
                    cursor.execute("""
                        INSERT INTO class_students (class_id, student_id)
                        VALUES (%s, %s)
                    """, (class_id, student_id))

            current_app.db.connection.commit()
            flash("Class created successfully!", "success")
            return redirect(url_for('teacher.manage_classes'))

        except Exception as e:
            current_app.db.connection.rollback()
            flash("Error creating class: " + str(e), "danger")

    return render_template('teacher/add_new_class.html', students=students)

@teacher_bp.route('/make_take_test', methods=['GET', 'POST'])
def make_take_test():
    # Ensure teacher is logged in
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher to create tests.", "danger")
        return redirect(url_for('auth.login'))
    
    cursor = current_app.db.connection.cursor(DictCursor)

    # Get teacher info
    cursor.execute("SELECT id, institution_id FROM teachers WHERE auth_user_id = %s", (session['user_id'],))
    teacher = cursor.fetchone()
    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for('auth.login'))

    teacher_id = teacher['id']
    institute_id = teacher['institution_id']

    # Get the list of students for this teacher
    cursor.execute("SELECT * FROM students WHERE teacher_id = %s", (teacher_id,))
    student_list = cursor.fetchall()
    
    # If submitting form to create new test paper
    if request.method == 'POST':
        test_title = request.form.get('test-title')
        test_subject = request.form.get('test-subject')
        test_duration = request.form.get('test-duration')
        test_date = request.form.get('test-date')
        test_time = request.form.get('test-time')
        selected_students = request.form.getlist('students')  # List of selected student IDs or "everyone"

        try:
            # Insert the new test
            cursor.execute("""
                INSERT INTO tests (teacher_id, institute_id, title, subject, duration, test_date, test_time, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (teacher_id, institute_id, test_title, test_subject, test_duration, test_date, test_time, 'draft'))
            test_id = cursor.lastrowid

            # If "everyone" is selected, override individual selections.
            if "everyone" in selected_students:
                # Assign to all students for this teacher
                for student in student_list:
                    cursor.execute("""
                        INSERT INTO test_assigned_students (test_id, student_id)
                        VALUES (%s, %s)
                    """, (test_id, student['id']))
            else:
                # Otherwise, assign only selected students.
                for student_id in selected_students:
                    cursor.execute("""
                        INSERT INTO test_assigned_students (test_id, student_id)
                        VALUES (%s, %s)
                    """, (test_id, student_id))
                    
            current_app.db.connection.commit()
            flash("Test created successfully! Now add questions.", "success")
            return redirect(url_for('teacher.test', test_id=test_id))
        except Exception as e:
            current_app.db.connection.rollback()
            flash("Failed to create test: " + str(e), "danger")

    # Fetch tests for this teacher segmented by status
    cursor.execute("SELECT * FROM tests WHERE teacher_id = %s ORDER BY test_date DESC", (teacher_id,))
    all_tests = cursor.fetchall()
    for test in all_tests:
        if isinstance(test.get('test_time'), datetime.timedelta):
            test['test_time'] = str(test['test_time'])[:-3]  # e.g. '10:30:00' → '10:30'

    current_tests = [t for t in all_tests if t['status'] == 'draft']
    live_tests = [t for t in all_tests if t['status'] == 'live']
    past_tests = [t for t in all_tests if t['status'] == 'past']

    return render_template(
        'teacher/make_take_test.html',
        current_tests=current_tests,
        live_tests=live_tests,
        past_tests=past_tests,
        student_list=student_list)

@teacher_bp.route('/update_test_status/<int:test_id>/<new_status>', methods=['POST'])
def update_test_status(test_id, new_status):
    # Validate allowed status transitions
    allowed_statuses = ['draft', 'live', 'past']
    if new_status not in allowed_statuses:
        flash("Invalid status.", "danger")
        return redirect(url_for('teacher.make_take_test'))

    cursor = current_app.db.connection.cursor(DictCursor)
    
    try:
        cursor.execute("UPDATE tests SET status = %s WHERE id = %s", (new_status, test_id))
        current_app.db.connection.commit()
        flash(f"Test status updated to {new_status}!", "success")
    except Exception as e:
        current_app.db.connection.rollback()
        flash("Error updating test status: " + str(e), "danger")

    return redirect(url_for('teacher.make_take_test'))

@teacher_bp.route('/assignments_grading')
def assignments_grading():
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher.", "danger")
        return redirect(url_for('auth.login'))

    filter_by = request.args.get('filter', 'all')  # all | graded | ungraded | not_taken

    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("SELECT id FROM teachers WHERE auth_user_id = %s",
                   (session['user_id'],))
    teacher = cursor.fetchone()
    teacher_id = teacher['id']

    if filter_by == 'graded':
        # Tests with ≥1 confirmed result
        cursor.execute("""
          SELECT t.id, t.title, t.test_date, t.status
          FROM tests t
          WHERE t.teacher_id = %s
            AND EXISTS (
              SELECT 1 FROM test_results tr
              WHERE tr.test_id = t.id AND tr.confirmed = 1
            )
          ORDER BY t.test_date DESC
        """, (teacher_id,))

    elif filter_by == 'ungraded':
        # Tests taken (any result) but none confirmed
        cursor.execute("""
          SELECT t.id, t.title, t.test_date, t.status
          FROM tests t
          WHERE t.teacher_id = %s
            AND EXISTS (
              SELECT 1 FROM test_results tr
              WHERE tr.test_id = t.id
            )
            AND NOT EXISTS (
              SELECT 1 FROM test_results tr2
              WHERE tr2.test_id = t.id AND tr2.confirmed = 1
            )
          ORDER BY t.test_date DESC
        """, (teacher_id,))

    elif filter_by == 'not_taken':
        # Tests with no submissions at all
        cursor.execute("""
          SELECT t.id, t.title, t.test_date, t.status
          FROM tests t
          WHERE t.teacher_id = %s
            AND NOT EXISTS (
              SELECT 1 FROM test_results tr
              WHERE tr.test_id = t.id
            )
          ORDER BY t.test_date DESC
        """, (teacher_id,))

    else:
        # All tests
        cursor.execute("""
          SELECT t.id, t.title, t.test_date, t.status
          FROM tests t
          WHERE t.teacher_id = %s
          ORDER BY t.test_date DESC
        """, (teacher_id,))

    tests = cursor.fetchall()
    
    # ➡️ NEW: fetch this teacher’s students
    cursor.execute("""
      SELECT s.id, s.student_name, s.course
      FROM students s
      WHERE s.teacher_id = %s
      ORDER BY s.student_name
    """, (teacher_id,))
    students = cursor.fetchall()

    return render_template(
        'teacher/assignments_grading.html',
        tests=tests,
        filter_by=filter_by,
        students=students
    )

@teacher_bp.route('/grade_assignment/<int:test_id>', methods=['GET'])
def grade_assignment(test_id):
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("SELECT title FROM tests WHERE id = %s", (test_id,))
    test = cursor.fetchone()

    # Now also pull the `confirmed` flag
    cursor.execute("""
        SELECT tr.student_id,
               au.email AS name,
               tr.score,
               tr.grade,
               tr.confirmed
        FROM test_results tr
        JOIN students s ON tr.student_id = s.id
        JOIN auth_users au ON s.auth_user_id = au.id
        WHERE tr.test_id = %s
    """, (test_id,))
    rows = cursor.fetchall()

    student_results = []
    for r in rows:
        student_results.append({
            'id': r['student_id'],
            'name': r['name'],
            'score_pct': r['score'],
            'grade': r['grade'],
            'result': 'Passed' if r['score'] >= 60 else 'Failed',
            'confirmed': bool(r['confirmed'])
        })

    return render_template(
        'teacher/grade_assignment.html',
        test_title=test['title'],
        students=student_results,
        test_id=test_id
    )

@teacher_bp.route('/grade_assignment/<int:test_id>/student/<int:student_id>')
def review_submission(test_id, student_id):
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Fetch test title
    cursor.execute("SELECT title FROM tests WHERE id = %s", (test_id,))
    title = cursor.fetchone()['title']

    # Fetch student email (name)
    cursor.execute("""
        SELECT au.email 
        FROM students s 
        JOIN auth_users au ON s.auth_user_id = au.id 
        WHERE s.id = %s
    """, (student_id,))
    name = cursor.fetchone()['email']

    # Fetch per-question details
    cursor.execute("""
        SELECT 
          q.question_number, 
          q.question_text,
          opt_sel.option_text AS student_answer,
          opt_corr.option_text AS correct_answer,
          ts.is_correct
        FROM test_questions q
        JOIN test_submissions ts 
          ON q.id = ts.question_id 
         AND ts.student_id = %s
        JOIN test_options opt_sel 
          ON opt_sel.id = ts.option_id
        JOIN test_options opt_corr 
          ON opt_corr.question_id = q.id 
         AND opt_corr.is_correct = 1
        WHERE q.test_id = %s
        ORDER BY q.question_number
    """, (student_id, test_id))
    details = cursor.fetchall()

    # Fetch overall result + confirmed flag
    cursor.execute("""
        SELECT score, grade, confirmed 
        FROM test_results 
        WHERE test_id = %s 
          AND student_id = %s
    """, (test_id, student_id))
    result = cursor.fetchone()

    return render_template(
        'teacher/review_submission.html',
        test_title=title,
        student_name=name,
        student_id=student_id,
        test_id=test_id,
        details=details,
        score=result['score'],
        grade=result['grade'],
        result_text=('Passed' if result['score'] >= 60 else 'Failed'),
        confirmed=bool(result['confirmed'])
    )

@teacher_bp.route('/confirm_result', methods=['POST'])
def confirm_result():
    data = request.get_json()
    cursor = current_app.db.connection.cursor()
    cursor.execute(
        "UPDATE test_results SET confirmed = 1 WHERE test_id = %s AND student_id = %s",
        (data['test_id'], data['student_id'])
    )
    current_app.db.connection.commit()
    return jsonify({'success': True})

@teacher_bp.route('/make_report/<int:student_id>')
def make_report(student_id):
    if not session.get('logged_in') or session['user_type'] != 'teacher':
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    try:
        # Get student info
        cursor.execute("""
            SELECT s.student_name, s.id, s.course
            FROM students s WHERE s.id = %s
        """, (student_id,))
        student = cursor.fetchone()

        if not student:
            flash("Student not found!", "danger")
            return redirect(url_for('teacher.dashboard'))

        # Get test results
        cursor.execute("""
            SELECT t.title AS subject, tr.score
            FROM test_results tr
            JOIN tests t ON t.id = tr.test_id
            WHERE tr.student_id = %s
        """, (student_id,))
        tests = cursor.fetchall()

        # Get attendance records
        cursor.execute("""
            SELECT c.class_name, ca.attendance_date, ca.status
            FROM class_attendance ca
            JOIN classes c ON ca.class_id = c.id
            WHERE ca.student_id = %s
            ORDER BY ca.attendance_date DESC
        """, (student_id,))
        attendance_records = cursor.fetchall()

        # Compute attendance percentage
        total_classes = len(attendance_records)
        present_count = sum(1 for a in attendance_records if a['status'] == 'present')
        percentage = round((present_count / total_classes) * 100, 2) if total_classes > 0 else 0

        return render_template(
            'teacher/make_report.html',
            student=student,
            tests=tests,
            attendance_records=attendance_records,
            attendance_percentage=percentage
        )

    except Exception as e:
        flash(f"An error occurred while fetching data: {e}", "danger")
        return redirect(url_for('teacher.dashboard'))

@teacher_bp.route('/submit_report', methods=['POST'])
def submit_report():
    if 'logged_in' not in session or session.get('user_type') != 'teacher':
        flash("Unauthorized", "danger")
        return redirect(url_for('auth.login'))

    data = request.form
    cursor = current_app.db.connection.cursor(DictCursor)

    # ✅ Get actual teacher_id using auth_user_id
    auth_user_id = session['user_id']
    cursor.execute("SELECT id FROM teachers WHERE auth_user_id = %s", (auth_user_id,))
    teacher_row = cursor.fetchone()

    if not teacher_row:
        flash("Teacher not found in system", "danger")
        return redirect(url_for('teacher.dashboard'))

    teacher_id = teacher_row['id']

    # Insert main report
    cursor.execute("""
        INSERT INTO student_reports (student_id, teacher_id, class_name, report_date, academic_year, attendance_pct, remarks, total_percentage)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data['student_id'],
        teacher_id,  # ✅ Now inserting the correct teacher_id
        data['class_name'],
        data['date'],
        data['year'],
        data['attendance_pct'],
        data['remarks'],
        float(data['total_percentage'].replace('%', ''))
    ))

    report_id = cursor.lastrowid

    # Insert subject-wise marks
    subjects = request.form.getlist('subject[]')
    marks = request.form.getlist('marks[]')
    for subj, mark in zip(subjects, marks):
        pct = float(mark)
        cursor.execute("""
            INSERT INTO student_report_subjects (report_id, subject_name, marks, percentage)
            VALUES (%s, %s, %s, %s)
        """, (report_id, subj, mark, pct))

    current_app.db.connection.commit()
    flash("Report submitted successfully!", "success")
    return redirect(url_for('teacher.reports'))

@teacher_bp.route('/test', methods=['GET', 'POST'])
def test():
    # First, try to get test_id from the query parameters or fall back to form data
    test_id = request.args.get('test_id') or request.form.get('test_id')
    if not test_id:
        flash("No test selected.", "danger")
        return redirect(url_for('teacher.make_take_test'))
    
    cursor = current_app.db.connection.cursor(DictCursor)
    
    if request.method == 'POST':
        # Process submitted questions and options.
        questions = request.form.getlist('question[]')
        for idx, question_text in enumerate(questions, start=1):
            # Insert each question for the test.
            cursor.execute("""
                INSERT INTO test_questions (test_id, question_text, question_number)
                VALUES (%s, %s, %s)
            """, (test_id, question_text, idx))
            question_id = cursor.lastrowid
            
            # Get options for this question. They should be named like option_1[], option_2[], etc.
            options = request.form.getlist(f'option_{idx}[]')
            correct_answer = request.form.get(f'correct_answer_{idx}')  # Expected to be a string, like "0"
            for opt_index, opt_text in enumerate(options):
                is_correct = (str(opt_index) == correct_answer)
                cursor.execute("""
                    INSERT INTO test_options (question_id, option_text, is_correct)
                    VALUES (%s, %s, %s)
                """, (question_id, opt_text, is_correct))
        current_app.db.connection.commit()
        flash("Test created successfully!", "success")
        return redirect(url_for('teacher.make_take_test'))
    
    return render_template('teacher/test.html', test_id=test_id)

@teacher_bp.route('/edit_test/<int:test_id>', methods=['GET', 'POST'])
def edit_test(test_id):
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    if request.method == 'POST':
        # Update test info
        title = request.form.get('title')
        subject = request.form.get('subject')
        duration = request.form.get('duration')
        test_date = request.form.get('test_date')
        test_time = request.form.get('test_time')
        
        cursor.execute("""
            UPDATE tests SET title=%s, subject=%s, duration=%s, test_date=%s, test_time=%s
            WHERE id=%s
        """, (title, subject, duration, test_date, test_time, test_id))

        # Update each question and options
        question_ids = request.form.getlist('question_ids')
        for qid in question_ids:
            q_text = request.form.get(f'question_text_{qid}')
            cursor.execute("UPDATE test_questions SET question_text=%s WHERE id=%s", (q_text, qid))

            for i in range(1, 5):  # Assuming 4 options
                opt_text = request.form.get(f'option_text_{qid}_{i}')
                opt_id = request.form.get(f'option_id_{qid}_{i}')
                cursor.execute("UPDATE test_options SET option_text=%s WHERE id=%s", (opt_text, opt_id))

            # Mark the correct answer
            correct_idx = int(request.form.get(f'correct_answer_{qid}'))
            for i in range(1, 5):
                opt_id = request.form.get(f'option_id_{qid}_{i}')
                is_correct = (i == correct_idx)
                cursor.execute("UPDATE test_options SET is_correct=%s WHERE id=%s", (is_correct, opt_id))

        current_app.db.connection.commit()
        flash("Test updated successfully!", "success")
        return redirect(url_for('teacher.make_take_test'))

    # GET — load test and questions
    cursor.execute("SELECT * FROM tests WHERE id = %s", (test_id,))
    test = cursor.fetchone()
    formatted_date = test['test_date'].strftime('%Y-%m-%d') if test['test_date'] else ''
    formatted_time = str(test['test_time']) if test['test_time'] else ''
    
    if test['test_time']:
        minutes = test['test_time'].seconds // 60
        hours = test['test_time'].seconds // 3600
        formatted_time = f"{hours:02}:{minutes:02}"
    else:
        formatted_time = ''

    cursor.execute("SELECT * FROM test_questions WHERE test_id = %s ORDER BY question_number", (test_id,))
    questions = cursor.fetchall()

    for q in questions:
        cursor.execute("SELECT * FROM test_options WHERE question_id = %s", (q['id'],))
        q['options'] = cursor.fetchall()

    return render_template("teacher/edit_test.html", test=test, formatted_date=formatted_date, formatted_time=formatted_time, questions=questions)

@teacher_bp.route('/delete_test/<int:test_id>', methods=['POST'])
def delete_test(test_id):
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        return jsonify({"error": "Unauthorized"}), 401

    cursor = current_app.db.connection.cursor()
    cursor.execute("DELETE FROM tests WHERE id = %s", (test_id,))
    current_app.db.connection.commit()
    flash("Test Deleted successfully!", "success")
    return redirect(url_for('teacher.make_take_test'))

@teacher_bp.route('/students')
def students():
    if 'logged_in' not in session or session.get('user_type') != 'teacher':
        flash("You need to log in as a teacher to access this page.", "danger")
        return redirect(url_for('auth.login'))

    # 🔧 Fetch the teacher ID using auth_user_id
    auth_user_id = session.get('user_id')
    cursor = current_app.db.connection.cursor(DictCursor)
    
    cursor.execute("SELECT id FROM teachers WHERE auth_user_id = %s", (auth_user_id,))
    teacher = cursor.fetchone()
    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for('auth.login'))

    teacher_id = teacher['id']

    query = """
    SELECT s.*, au.email
    FROM students s
    JOIN auth_users au ON s.auth_user_id = au.id
    WHERE s.teacher_id = %s
    """
    cursor.execute(query, (teacher_id,))
    students = cursor.fetchall()

    return render_template('teacher/teacher_students.html', students=students)

@teacher_bp.route('/student_info/<int:student_id>')
def student_info(student_id):
    """Return JSON with student profile, classes, and tests taken."""
    if not session.get('logged_in') or session.get('user_type')!='teacher':
        return jsonify({'error':'Unauthorized'}), 403

    cursor = current_app.db.connection.cursor(DictCursor)
    # 1) Basic student info
    cursor.execute("""
      SELECT s.id, s.student_name, s.enroll_number, au.email
      FROM students s
      JOIN auth_users au ON s.auth_user_id=au.id
      WHERE s.id=%s
    """, (student_id,))
    student = cursor.fetchone()
    if not student:
        return jsonify({'error':'Not found'}), 404

    # 2) Classes student is in
    cursor.execute("""
      SELECT c.id, c.class_name, DATE_FORMAT(c.class_date,'%%Y-%%m-%%d') AS class_date
      FROM classes c
      JOIN class_students cs ON cs.class_id=c.id
      WHERE cs.student_id=%s
      ORDER BY c.class_date DESC
    """, (student_id,))
    classes = cursor.fetchall()

    # 3) Tests student has taken
    cursor.execute("""
      SELECT t.id, t.title,
             tr.score, tr.grade,
             DATE_FORMAT(tr.submitted_at,'%%Y-%%m-%%d') AS submitted_at,
             tr.confirmed
      FROM test_results tr
      JOIN tests t ON t.id=tr.test_id
      WHERE tr.student_id=%s
      ORDER BY tr.submitted_at DESC
    """, (student_id,))
    tests = cursor.fetchall()

    return jsonify({
      'student': student,
      'classes': classes,
      'tests': tests
    })

@teacher_bp.route('/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    """Delete a student (or disassociate)."""
    if not session.get('logged_in') or session.get('user_type')!='teacher':
        return jsonify({'error':'Unauthorized'}), 403

    cursor = current_app.db.connection.cursor()
    try:
        cursor.execute("DELETE FROM students WHERE id=%s", (student_id,))
        current_app.db.connection.commit()
        return jsonify({'success': True})
    except Exception as e:
        current_app.db.connection.rollback()
        return jsonify({'error': str(e)}), 500

@teacher_bp.route('/attendance')
def attendance():
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash("Please log in as a teacher to access attendance.", "danger")
        return redirect(url_for('auth.login'))

    from datetime import date
    selected_date = request.args.get('att_date')
    if not selected_date:
        selected_date = date.today().isoformat()

    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("SELECT id, institution_id FROM teachers WHERE auth_user_id = %s", (session['user_id'],))
    teacher = cursor.fetchone()
    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for('auth.login'))

    teacher_id = teacher['id']
    classes, percent_present, percent_absent, percent_late = get_classes_with_attendance_for_date(teacher_id, selected_date)

    return render_template('teacher/attendance.html',
                           institution=teacher,
                           classes=classes,
                           selected_date=selected_date,
                           percent_present=round(percent_present, 2),
                           percent_absent=round(percent_absent, 2),
                           percent_late=round(percent_late, 2))
    
def get_classes_with_attendance_for_date(teacher_id, selected_date):
    cursor = current_app.db.connection.cursor(DictCursor)
    
    cursor.execute("""
         SELECT id, class_name, class_time, class_date 
         FROM classes
         WHERE teacher_id = %s AND class_date = %s
         ORDER BY class_time ASC
    """, (teacher_id, selected_date))
    classes_data = cursor.fetchall()
    
    total_present = 0
    total_absent = 0
    total_late = 0
    total_records = 0
    
    classes = []
    for class_entry in classes_data:
        class_id = class_entry['id']
        cursor.execute("""
         SELECT ca.status, s.student_name, s.enroll_number, s.profile_pic
         FROM class_attendance ca
         JOIN students s ON ca.student_id = s.id
         WHERE ca.class_id = %s AND ca.attendance_date = %s
         ORDER BY s.student_name ASC
        """, (class_id, selected_date))
        attendance_records = cursor.fetchall()

        for record in attendance_records:
            status = record['status'].lower()
            total_records += 1
            if status == 'present':
                total_present += 1
            elif status == 'absent':
                total_absent += 1
            elif status == 'late':
                total_late += 1

        class_entry['attendance'] = attendance_records
        classes.append(class_entry)

    if total_records == 0:
        return classes, 0.0, 0.0, 0.0

    percent_present = (total_present / total_records) * 100
    percent_absent = (total_absent / total_records) * 100
    percent_late = (total_late / total_records) * 100

    return classes, percent_present, percent_absent, percent_late

@teacher_bp.route('/reports')
def reports():
    if not session.get('logged_in') or session.get('user_type')!='teacher':
        flash("Please log in as a teacher.", "danger")
        return redirect(url_for('auth.login'))

    # 1️⃣ get teacher_id
    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("SELECT id FROM teachers WHERE auth_user_id=%s", (session['user_id'],))
    teacher = cursor.fetchone()
    if not teacher:
        flash("Teacher not found.", "danger")
        return redirect(url_for('auth.login'))
    tid = teacher['id']

    # 2️⃣ Class attendance averages
    cursor.execute("""
      SELECT c.class_name,
             ROUND( AVG(CASE WHEN ca.status='present' THEN 1 ELSE 0 END)*100,0) AS avg_attendance
      FROM classes c
      LEFT JOIN class_attendance ca
        ON ca.class_id=c.id
      WHERE c.teacher_id=%s
      GROUP BY c.id
      ORDER BY c.class_name
    """, (tid,))
    classes = cursor.fetchall()

    # 3️⃣ Test results: avg score & top performer
    cursor.execute("""
      SELECT t.title,
             ROUND(AVG(tr.score),0) AS avg_score,
             (SELECT au.email
              FROM test_results tr2
              JOIN students s2 ON tr2.student_id=s2.id
              JOIN auth_users au ON s2.auth_user_id=au.id
              WHERE tr2.test_id=t.id
              ORDER BY tr2.score DESC
              LIMIT 1
             ) AS top_name,
             (SELECT MAX(tr2.score)
              FROM test_results tr2
              WHERE tr2.test_id=t.id
             ) AS top_score
      FROM tests t
      LEFT JOIN test_results tr
        ON tr.test_id=t.id
      WHERE t.teacher_id=%s AND tr.id IS NOT NULL
      GROUP BY t.id
      ORDER BY t.test_date DESC
    """, (tid,))
    test_stats = cursor.fetchall()

    # 4️⃣ (Optional) any other analytics…

    return render_template(
      'teacher/reports_teacher.html',
      classes=classes,
      test_stats=test_stats
    )

@teacher_bp.route('/find_student')
def find_student():
    """Lookup student by name or ID, return full profile + classes + tests."""
    if not session.get('logged_in') or session.get('user_type')!='teacher':
        return jsonify({'error':'Unauthorized'}), 403

    q = request.args.get('q','').strip()
    if not q:
        return jsonify({'error':'Empty query'}), 400

    cursor = current_app.db.connection.cursor(DictCursor)
    # Try numeric ID first
    if q.isdigit():
        cursor.execute("SELECT id FROM students WHERE enroll_number=%s", (q,))
    else:
        cursor.execute("SELECT id FROM students WHERE student_name LIKE %s LIMIT 1", (f"%{q}%",))
    row = cursor.fetchone()
    if not row:
        return jsonify({'error':'Student not found'}), 404
    student_id = row['id']

    # Delegate to existing student_info route logic
    return redirect(url_for('teacher.student_info', student_id=student_id, _external=False))

@teacher_bp.route('/messages')
def messages():
    if not session.get('logged_in') or session['user_type'] != 'teacher':
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Recipients: students under this teacher + other teachers from same institute
    cursor.execute("""
      SELECT au.id, au.email, 'Student' AS type
      FROM students s
      JOIN auth_users au ON s.auth_user_id = au.id
      WHERE s.teacher_id = (
        SELECT id FROM teachers WHERE auth_user_id = %s
      )
      UNION
      SELECT au.id, au.email, 'Teacher' AS type
      FROM teachers t
      JOIN auth_users au ON t.auth_user_id = au.id
      WHERE t.institution_id = (
        SELECT institution_id FROM teachers WHERE auth_user_id = %s
      ) AND au.id != %s
    """, (session['user_id'], session['user_id'], session['user_id']))
    recipients = list(cursor.fetchall())  # convert from tuple to list

    # Add unread counts
    cursor.execute("""
        SELECT sender_id, COUNT(*) AS unread
        FROM messages
        WHERE receiver_id = %s AND is_read = 0
        GROUP BY sender_id
    """, (session['user_id'],))
    unread_map = {row['sender_id']: row['unread'] for row in cursor.fetchall()}

    for r in recipients:
        r['unread'] = unread_map.get(r['id'], 0)

    recipients.sort(key=lambda x: x['unread'], reverse=True)

    return render_template('teacher/teacher_messages.html', recipients=recipients)

@teacher_bp.route('/messages/unread')
def teacher_unread_counts():
    if not session.get('logged_in') or session['user_type'] != 'teacher':
        return jsonify({}), 403

    user_id = session['user_id']
    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("""
        SELECT sender_id, COUNT(*) AS unread
        FROM messages
        WHERE receiver_id = %s AND is_read = 0
        GROUP BY sender_id
    """, (user_id,))
    data = cursor.fetchall()
    return jsonify({row['sender_id']: row['unread'] for row in data})

@teacher_bp.route('/messages/send', methods=['POST'])
def send_message_teacher():
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        return jsonify({'error':'Unauthorized'}), 403

    data = request.get_json()
    receiver = data.get('receiver_id')
    content  = data.get('content','').strip()
    if not receiver or not content:
        return jsonify({'error':'Missing fields'}), 400

    cursor = current_app.db.connection.cursor()
    cursor.execute("""
      INSERT INTO messages (sender_id, receiver_id, content)
      VALUES (%s, %s, %s)
    """, (session['user_id'], receiver, content))
    current_app.db.connection.commit()
    return jsonify({'success':True})

@teacher_bp.route('/messages/conversation/<int:other_id>')
def conversation(other_id):
    if not session.get('logged_in') or session['user_type'] != 'teacher':
        return jsonify({'error':'Unauthorized'}), 403

    me = session['user_id']
    cur = current_app.db.connection.cursor(DictCursor)

    # Mark as read
    cur.execute("""
      UPDATE messages
      SET is_read = 1
      WHERE sender_id = %s AND receiver_id = %s
    """, (other_id, me))
    current_app.db.connection.commit()

    cur.execute("""
      SELECT m.*, su.email AS sender, ru.email AS receiver
      FROM messages m
      JOIN auth_users su ON m.sender_id = su.id
      JOIN auth_users ru ON m.receiver_id = ru.id
      WHERE (m.sender_id = %s AND m.receiver_id = %s)
         OR (m.sender_id = %s AND m.receiver_id = %s)
      ORDER BY m.created_at ASC
    """, (me, other_id, other_id, me))
    convo = cur.fetchall()
    return jsonify(convo)


@teacher_bp.context_processor
def inject_dark_mode():
    """Expose `dark_mode` to teacher templates."""
    dm = False
    if session.get('logged_in') and session.get('user_type') == 'teacher':
        cur = current_app.db.connection.cursor(DictCursor)
        cur.execute(
            "SELECT dark_mode FROM teachers WHERE auth_user_id = %s",
            (session['user_id'],)
        )
        row = cur.fetchone()
        dm = bool(row and row.get('dark_mode'))
    return dict(dark_mode=dm)

@teacher_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if not session.get('logged_in') or session['user_type'] != 'teacher':
        return redirect(url_for('auth.login'))

    auth_id = session['user_id']
    cursor  = current_app.db.connection.cursor(DictCursor)

    if request.method == 'GET':
        # ─── Fetch profile + contacts ────────────────────────────────
        cursor.execute("""
          SELECT t.teacher_name, t.phone, t.profile_pic, t.department,
                 au.email, t.dark_mode, i.institution_name
          FROM teachers t
          JOIN auth_users au ON t.auth_user_id = au.id
          JOIN institutions i ON t.institution_id = i.id
          WHERE au.id = %s
        """, (auth_id,))
        profile = cursor.fetchone() or {}

        # Who can they complain against?
        contacts = []
        # → all students in this institute
        cursor.execute("""
          SELECT au.id, au.email
          FROM students s
          JOIN auth_users au ON s.auth_user_id = au.id
          WHERE s.institute_id = (
            SELECT institution_id FROM teachers WHERE auth_user_id = %s
          )
        """, (auth_id,))
        for r in cursor.fetchall():
            contacts.append({'id': r['id'], 'email': r['email'], 'type': 'Student'})

        # → institute admin
        cursor.execute("""
          SELECT au.id, au.email
          FROM institutions inst
          JOIN auth_users au ON inst.auth_user_id = au.id
          WHERE inst.id = (
            SELECT institution_id FROM teachers WHERE auth_user_id = %s
          )
        """, (auth_id,))
        inst = cursor.fetchone()
        if inst:
            contacts.append({'id': inst['id'], 'email': inst['email'], 'type': 'Institute'})

        return render_template(
            'teacher/teacher_settings.html',
            institute_name=profile.get('institution_name'),
            profile=profile,
            contacts=contacts
        )

    # ─── POST: handle the four panels ────────────────────────────
    action = request.form.get('action')
    try:
        if action == 'profile':
            # ─── Update name/phone/picture
            name = request.form['teacher_name']
            phone = request.form['phone']
            pic = request.files.get('profile_pic')
            if pic and pic.filename:
                fn = secure_filename(pic.filename)
                upl = os.path.join(current_app.root_path, 'static', 'uploads')
                os.makedirs(upl, exist_ok=True)
                pic.save(os.path.join(upl, fn))
                cursor.execute(
                    "UPDATE teachers SET profile_pic=%s WHERE auth_user_id=%s",
                    (fn, auth_id)
                )
            cursor.execute(
                "UPDATE teachers SET teacher_name=%s, phone=%s WHERE auth_user_id=%s",
                (name, phone, auth_id)
            )
            flash("Profile updated.", "success")

        elif action == 'password':
            # ─── Change password
            old = request.form['current_password']
            new = request.form['new_password']
            conf= request.form['confirm_password']
            cursor.execute("SELECT password FROM auth_users WHERE id=%s", (auth_id,))
            stored = cursor.fetchone()['password']
            if not check_password_hash(stored, old):
                flash("Current password incorrect.", "danger")
                return redirect(url_for('teacher.settings'))
            if new != conf:
                flash("New passwords do not match.", "danger")
                return redirect(url_for('teacher.settings'))
            new_hash = generate_password_hash(new)
            cursor.execute("UPDATE auth_users SET password=%s WHERE id=%s", (new_hash, auth_id))
            current_app.db.connection.commit()
            session.clear()
            flash("Password changed—please log in again.", "success")
            return redirect(url_for('auth.login'))

        elif action == 'appearance':
            # ─── Toggle dark mode flag
            dm = 1 if request.form.get('dark_mode') == 'on' else 0
            cursor.execute(
                "UPDATE teachers SET dark_mode=%s WHERE auth_user_id=%s",
                (dm, auth_id)
            )
            flash("Appearance settings saved.", "success")

        elif action == 'complaint':
            # ─── Submit a complaint
            auth_user_id = auth_id
            against    = int(request.form['against_id'])
            category   = request.form['category'].strip()
            subject    = request.form['subject'].strip()
            details    = request.form['details'].strip()
            anon       = 1 if request.form.get('anonymous') else 0

            if not (against and category and subject and details):
                flash("All complaint fields are required.", "danger")
                return redirect(url_for('teacher.settings'))

            cursor.execute("""
              INSERT INTO complaints
                (user_id, against_auth_id, category, subject, details, is_anonymous)
              VALUES (%s,      %s,               %s,       %s,      %s,      %s)
            """, (
              auth_user_id,
              against,
              category,
              subject,
              details,
              anon
            ))
            flash("Complaint submitted!", "success")

        current_app.db.connection.commit()

    except Exception as e:
        current_app.db.connection.rollback()
        flash(f"Error: {e}", "danger")

    return redirect(url_for('teacher.settings'))

@teacher_bp.route('/invite_student', methods=['POST'])
def invite_student():
    data = request.get_json()
    student_email = data.get('student_email')
    if not student_email:
        return jsonify({'error': 'Student email is required'}), 400

    token = str(uuid.uuid4())
    auth_user_id = session.get('user_id')
    if not auth_user_id:
        return jsonify({'error': 'Teacher not logged in'}), 403

    cursor = current_app.db.connection.cursor()
    cursor.execute("SELECT id, institution_id FROM teachers WHERE auth_user_id = %s", (auth_user_id,))
    teacher_record = cursor.fetchone()
    if not teacher_record:
        return jsonify({'error': 'Teacher record not found'}), 400
    teacher_id, institute_id = teacher_record

    try:
        sql = """
            INSERT INTO student_invites (token, student_email, teacher_id, institute_id)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(sql, (token, student_email, teacher_id, institute_id))
        current_app.db.connection.commit()

        signup_link = current_app.url_for('auth.student_signup', token=token, _external=True)

        subject = "You're invited to join LearnieVerse as a Student"
        body = f"Hello,\n\nYou've been invited to join LearnieVerse as a student. Please sign up using the following link:\n\n{signup_link}\n\nThank you!"
        send_email(student_email, subject, body)

        return jsonify({'message': 'Invitation sent successfully', 'signup_link': signup_link})
    except Exception as e:
        current_app.db.connection.rollback()
        return jsonify({'error': str(e)}), 500
