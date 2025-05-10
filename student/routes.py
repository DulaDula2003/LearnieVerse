from flask import session, flash, redirect, url_for, render_template, request, current_app, jsonify
from flask import Blueprint
from MySQLdb.cursors import DictCursor
from datetime import datetime
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os


student_bp = Blueprint('student', __name__, template_folder='templates/student')

@student_bp.route('/dashboard')
def dashboard():
    # 🔐 require student login
    if not session.get('logged_in') or session.get('user_type') != 'student':
        return redirect(url_for('auth.login'))

    auth_id = session['user_id']
    conn   = current_app.db.connection
    cur    = conn.cursor(DictCursor)

    # 1) Who am I?
    cur.execute("""
      SELECT s.id AS student_id, s.institute_id, au.email AS student_email
      FROM students s
      JOIN auth_users au ON s.auth_user_id = au.id
      WHERE au.id = %s
    """, (auth_id,))
    me = cur.fetchone()
    if not me:
        flash("Student profile not found.", "danger")
        return redirect(url_for('auth.login'))
    student_id   = me['student_id']
    institute_id = me['institute_id']

    # 2) Institute name
    cur.execute("""
      SELECT institution_name
      FROM institutions
      WHERE id = %s
    """, (institute_id,))
    inst = cur.fetchone()
    institute_name = inst['institution_name'] if inst else "—"

    # 3) Upcoming classes (next 2)
    cur.execute("""
      SELECT c.class_name,
             DATE_FORMAT(c.class_date, '%%Y-%%m-%%d')   AS class_date,
             DATE_FORMAT(c.class_time, '%%H:%%i')       AS class_time
      FROM class_students cs
      JOIN classes c ON cs.class_id = c.id
      WHERE cs.student_id = %s
        AND CONCAT(c.class_date,' ',c.class_time) > NOW()
      ORDER BY c.class_date ASC, c.class_time ASC
      LIMIT 2
    """, (student_id,))
    upcoming_classes = cur.fetchall()

    # 4) Recent Announcements (targeted to students or all)
    cur.execute("""
    SELECT title, content,
            DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i') AS ts
    FROM announcements
    WHERE institute_id = %s
        AND (audience = 'student' OR audience = 'all')
    ORDER BY created_at DESC
    LIMIT 3
    """, (institute_id,))
    recent_announcements = cur.fetchall()

    # 5) Past exam results for performance chart
    cur.execute("""
      SELECT t.title, tr.score
      FROM test_results tr
      JOIN tests t ON tr.test_id = t.id
      WHERE tr.student_id = %s
      ORDER BY tr.submitted_at DESC
      LIMIT 5
    """, (student_id,))
    perf = cur.fetchall()
    perf_labels = [r['title'] for r in perf]
    perf_scores = [r['score'] for r in perf]

    # 6) Recent reports (last 3)
    cur.execute("""
      SELECT DATE_FORMAT(r.report_date,'%%Y-%%m-%%d') AS date,
             r.academic_year,
             r.total_percentage
      FROM student_reports r
      WHERE r.student_id = %s
      ORDER BY r.report_date DESC
      LIMIT 3
    """, (student_id,))
    recent_reports = cur.fetchall()

    cur.close()

    return render_template('student/dashboard.html',
                       institute_name=institute_name,
                       upcoming_classes=upcoming_classes,
                       recent_announcements=recent_announcements,
                       perf_labels=perf_labels,
                       perf_scores=perf_scores,
                       recent_reports=recent_reports)


@student_bp.route('/subjects')
def subjects():
    if not session.get('logged_in') or session.get('user_type') != 'student':
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)
    query = """
      SELECT 
        c.id           AS class_id,
        c.class_name,
        c.class_date,
        c.class_time,
        t.id           AS teacher_id,         -- ✅ Add this line
        t.teacher_name,
        t.subject_expertise1 AS subject,
        ta.email       AS teacher_email
      FROM class_students cs
      JOIN classes c      ON cs.class_id      = c.id
      JOIN teachers t     ON c.teacher_id     = t.id
      JOIN students s     ON cs.student_id    = s.id
      JOIN auth_users ta  ON t.auth_user_id   = ta.id
      JOIN auth_users sa  ON s.auth_user_id   = sa.id
      WHERE sa.id = %s;
    """
    cursor.execute(query, (session['user_id'],))
    subjects = cursor.fetchall()
    cursor.close()

    return render_template("student/subjects.html", subjects=subjects)

@student_bp.route('/classes')
def classes():
    if not session.get('logged_in') or session.get('user_type') != 'student':
        flash("Please log in as a student to access classes.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Fetch student record using auth_user_id
    cursor.execute("SELECT * FROM students WHERE auth_user_id = %s", (session['user_id'],))
    student = cursor.fetchone()
    if not student:
        flash("Student record not found", "danger")
        return redirect(url_for('auth.login'))

    # Get student's institution id
    student_institute_id = student.get('institute_id')
    if not student_institute_id:
        flash("Your account is not linked to an institution.", "danger")
        return redirect(url_for('auth.login'))

    # Fetch classes for the student's institution 
    cursor.execute("""
      SELECT c.*, t.teacher_name, t.profile_pic, t.teacher_id
      FROM classes c
      JOIN teachers t ON c.teacher_id = t.id
      WHERE c.institute_id = %s
      ORDER BY c.class_date DESC, c.class_time ASC
    """, (student_institute_id,))
    all_classes = cursor.fetchall()

    live_class_ids = {cls['id'] for cls in all_classes if cls.get('is_live') == 1}
    upcoming_class_ids = {cls['id'] for cls in all_classes if cls.get('is_live') == 0}

    return render_template('student/classes.html',
                           student=student,
                           classes=all_classes,
                           live_class_ids=live_class_ids,
                           upcoming_class_ids=upcoming_class_ids)

@student_bp.route('/join_class/<int:class_id>', methods=['GET', 'POST'])
def join_class(class_id):
    cur = current_app.db.connection.cursor(DictCursor)

    # Get student ID from session
    cur.execute("SELECT id FROM students WHERE auth_user_id = %s", (session['user_id'],))
    student = cur.fetchone()
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for('student.classes'))
    student_id = student['id']

    # Fetch class and teacher info
    cur.execute("""
        SELECT c.*, t.teacher_name, t.profile_pic, t.teacher_id
        FROM classes c
        JOIN teachers t ON c.teacher_id = t.id
        WHERE c.id = %s
    """, (class_id,))
    class_data = cur.fetchone()
    if not class_data:
        flash("Class not found", "danger")
        return redirect(url_for('student.classes'))

    if request.method == "GET":
        # Insert a new session entry when the student joins a class
        cur.execute("""
            INSERT INTO class_sessions (class_id, student_id)
            VALUES (%s, %s)
        """, (class_id, student_id))
        current_app.db.connection.commit()

    # If a chat message is being sent
    if request.method == "POST" and request.form.get("chat_message"):
        chat_message = request.form.get("chat_message")
        try:
            cur.execute("""
                INSERT INTO class_chats (class_id, sender_id, message)
                VALUES (%s, %s, %s)
            """, (class_id, session['user_id'], chat_message))
            current_app.db.connection.commit()
        except Exception as e:
            current_app.db.connection.rollback()
            flash("Error sending message: " + str(e), "danger")
        return redirect(url_for('student.join_class', class_id=class_id))

    # Fetch chats for the class
    cur.execute("""
        SELECT c.*, a.email as sender_email 
        FROM class_chats c
        JOIN auth_users a ON c.sender_id = a.id
        WHERE c.class_id = %s
        ORDER BY c.created_at ASC
    """, (class_id,))
    chats = cur.fetchall()
    cur.close()

    return render_template('student/join_class.html',
                           class_data=class_data,
                           chats=chats)

@student_bp.route('/leave_class/<int:class_id>', methods=['POST'])
def leave_class(class_id):
    cur = current_app.db.connection.cursor(DictCursor)

    # Get student ID
    cur.execute("SELECT id FROM students WHERE auth_user_id = %s", (session['user_id'],))
    student = cur.fetchone()
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for('student.classes'))
    student_id = student['id']

    # Update the session record for leaving the class
    cur.execute("""
        UPDATE class_sessions
        SET leave_time = NOW()
        WHERE class_id = %s AND student_id = %s AND leave_time IS NULL
        ORDER BY join_time DESC
        LIMIT 1
    """, (class_id, student_id))
    current_app.db.connection.commit()
    cur.close()

    flash("You have left the class.", "success")
    return redirect(url_for('student.classes'))

@student_bp.route('/messages')
def messages():
    if not session.get('logged_in') or session['user_type'] != 'student':
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # 1) Get raw recipients (teachers + classmates)
    cursor.execute("""
      SELECT au.id, au.email, 'Teacher' AS type
      FROM teachers t
      JOIN auth_users au ON t.auth_user_id = au.id
      WHERE t.id = (
        SELECT teacher_id FROM students WHERE auth_user_id = %s
      )
      UNION
      SELECT au.id, au.email, 'Student' AS type
      FROM students s
      JOIN auth_users au ON s.auth_user_id = au.id
      WHERE s.course = (
        SELECT course FROM students WHERE auth_user_id = %s
      ) AND au.id != %s
    """, (session['user_id'], session['user_id'], session['user_id']))
    recipients = list(cursor.fetchall())

    # 2) Fetch unread counts per sender
    cursor.execute("""
      SELECT sender_id, COUNT(*) AS unread
      FROM messages
      WHERE receiver_id = %s
        AND is_read = 0
      GROUP BY sender_id
    """, (session['user_id'],))
    unread_map = {row['sender_id']: row['unread'] for row in cursor.fetchall()}

    # 3) Annotate & sort recipients by unread desc
    for r in recipients:
        r['unread'] = unread_map.get(r['id'], 0)
    recipients.sort(key=lambda x: x['unread'], reverse=True)

    # 4) (Optional) preload all messages if you need them, or just render empty
    cursor.execute("""
      SELECT m.*, su.email AS sender
      FROM messages m
      JOIN auth_users su ON m.sender_id = su.id
      WHERE m.receiver_id = %s OR m.sender_id = %s
      ORDER BY m.created_at ASC
    """, (session['user_id'], session['user_id']))
    messages = cursor.fetchall()

    return render_template('student/messages.html',
                           recipients=recipients,
                           messages=messages)


@student_bp.route('/messages/conversation/<int:other_id>')
def conversation(other_id):
    if not session.get('logged_in') or session['user_type'] != 'student':
        return jsonify([]), 403

    me = session['user_id']
    cursor = current_app.db.connection.cursor(DictCursor)

    # 1) Mark all msgs from them → you as read
    cursor.execute("""
      UPDATE messages
      SET is_read = 1
      WHERE sender_id = %s AND receiver_id = %s
    """, (other_id, me))
    current_app.db.connection.commit()

    # 2) Fetch the convo
    cursor.execute("""
        SELECT m.sender_id,
               m.receiver_id,
               m.content,
               DATE_FORMAT(m.created_at, '%%Y-%%m-%%d %%H:%%i') AS created_at,
               au.email AS sender_email
        FROM messages m
        JOIN auth_users au ON m.sender_id = au.id
        WHERE (m.sender_id = %s AND m.receiver_id = %s)
           OR (m.sender_id = %s AND m.receiver_id = %s)
        ORDER BY m.created_at ASC
    """, (me, other_id, other_id, me))
    msgs = cursor.fetchall()
    return jsonify(msgs)


@student_bp.route('/messages/send', methods=['POST'])
def send_message_student():
    if not session.get('logged_in') or session['user_type']!='student':
        return jsonify({'error':'Unauthorized'}), 403

    data = request.get_json()
    receiver = data.get('receiver_id')
    content  = (data.get('content') or '').strip()
    if not receiver or not content:
        return jsonify({'error':'Missing fields'}), 400

    cursor = current_app.db.connection.cursor()
    cursor.execute("""
      INSERT INTO messages (sender_id, receiver_id, content)
      VALUES (%s, %s, %s)
    """, (session['user_id'], receiver, content))
    current_app.db.connection.commit()
    return jsonify({'success':True})


@student_bp.route('/messages/unread')
def get_unread_counts():
    # AJAX endpoint for polling badges
    user_id = session.get('user_id')
    if not session.get('logged_in'):
        return jsonify({}), 403

    cursor = current_app.db.connection.cursor(DictCursor)
    cursor.execute("""
        SELECT sender_id, COUNT(*) AS unread
        FROM messages
        WHERE receiver_id = %s AND is_read = 0
        GROUP BY sender_id
    """, (user_id,))
    data = cursor.fetchall()
    return jsonify({row['sender_id']: row['unread'] for row in data})

@student_bp.route('/assignments')
def assignments():
    if not session.get('logged_in') or session.get('user_type') != 'student':
        flash("Please log in as a student.", "danger")
        return redirect(url_for('auth.login'))
    
    cursor = current_app.db.connection.cursor(DictCursor)
    auth_user_id = session['user_id']

    # Get the actual student ID from the students table
    cursor.execute("SELECT id FROM students WHERE auth_user_id = %s", (auth_user_id,))
    student = cursor.fetchone()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for('auth.login'))
    student_id = student['id']

    # Ongoing Exams: status 'live', assigned to this student, that haven’t yet been taken
    cursor.execute("""
        SELECT t.* 
        FROM tests t 
        JOIN test_assigned_students ta ON t.id = ta.test_id 
        LEFT JOIN test_results tr ON t.id = tr.test_id AND tr.student_id = %s
        WHERE ta.student_id = %s 
          AND t.status = 'live'
          AND tr.id IS NULL
        ORDER BY t.test_date ASC
    """, (student_id, student_id))
    ongoing_exams = cursor.fetchall()

    # Upcoming Exams: status 'draft' and scheduled for a future datetime
    cursor.execute("""
        SELECT * FROM tests 
        WHERE status = 'draft' 
        AND CONCAT(test_date, ' ', test_time) > NOW()
        ORDER BY test_date ASC, test_time ASC
    """)
    upcoming_exams = cursor.fetchall()
    
    # After fetching upcoming_exams
    for exam in upcoming_exams:
        if exam.get('test_time'):
            exam['formatted_time'] = datetime.strptime(str(exam['test_time']), "%H:%M:%S").strftime("%I:%M %p")
        
    # Past Exams: tests where the student has submitted a result.
    cursor.execute("""
        SELECT t.*, r.score, r.submitted_at
        FROM tests t 
        JOIN test_results r ON t.id = r.test_id
        WHERE r.student_id = %s
        ORDER BY r.submitted_at DESC
    """, (student_id,))
    past_exams = cursor.fetchall()
    
    # Extract chart data
    labels = [exam['title'] for exam in past_exams]
    scores = [exam['score'] for exam in past_exams]

    return render_template(
        'student/assignments.html',
        ongoing_exams=ongoing_exams,
        upcoming_exams=upcoming_exams,
        past_exams=past_exams,
        labels=labels,
        scores=scores
    )
    
@student_bp.route('/tests/<int:test_id>/take', methods=['GET', 'POST'])
def take_test(test_id):
    if not session.get('logged_in') or session.get('user_type') != 'student':
        flash("Please log in as a student to take tests.", "danger")
        return redirect(url_for('auth.login'))

    cursor = current_app.db.connection.cursor(DictCursor)

    # Get the student ID from auth_user_id
    auth_user_id = session['user_id']
    cursor.execute("SELECT id FROM students WHERE auth_user_id = %s", (auth_user_id,))
    student_record = cursor.fetchone()

    if not student_record:
        flash("Student profile not found.", "danger")
        return redirect(url_for('student.assignments'))

    student_id = student_record['id']

    # Fetch test details and ensure the test is live
    cursor.execute("SELECT * FROM tests WHERE id = %s AND status = 'live'", (test_id,))
    test = cursor.fetchone()
    if not test:
        flash("Test is not available at the moment.", "warning")
        return redirect(url_for('student.assignments'))

    # Fetch the test questions
    cursor.execute("""
        SELECT * FROM test_questions 
        WHERE test_id = %s 
        ORDER BY question_number ASC
    """, (test_id,))
    questions = cursor.fetchall()

    # Fetch answer options for each question
    for question in questions:
        cursor.execute("SELECT * FROM test_options WHERE question_id = %s", (question['id'],))
        question['options'] = cursor.fetchall()

    if request.method == 'POST':
        total_questions = len(questions)
        correct_count = 0

        for question in questions:
            answer = request.form.get(f"question_{question['id']}")
            if answer:
                cursor.execute("SELECT is_correct FROM test_options WHERE id = %s", (answer,))
                chosen = cursor.fetchone()
                is_correct = chosen['is_correct'] if chosen else False
                if is_correct:
                    correct_count += 1

                # ✅ Record submission
                cursor.execute("""
                    INSERT INTO test_submissions (test_id, student_id, question_id, option_id, is_correct)
                    VALUES (%s, %s, %s, %s, %s)
                """, (test_id, student_id, question['id'], answer, is_correct))

        score = (correct_count / total_questions) * 100 if total_questions > 0 else 0

        if score >= 90:
            grade = 'A+'
        elif score >= 80:
            grade = 'A'
        elif score >= 70:
            grade = 'B'
        elif score >= 60:
            grade = 'C'
        elif score >= 50:
            grade = 'D'
        else:
            grade = 'F'

        cursor.execute("""
            INSERT INTO test_results (test_id, student_id, score, grade, submitted_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (test_id, student_id, score, grade))
        
        current_app.db.connection.commit()

        flash(f"Test submitted successfully! You scored {score:.2f}% and got a grade of {grade}.", "success")
        return redirect(url_for('student.assignments'))

    return render_template('student/take_test.html', test=test, questions=questions)


@student_bp.route('/reports', defaults={'report_id': None})
@student_bp.route('/reports/<int:report_id>')
def reports(report_id):
    if not session.get('logged_in') or session.get('user_type') != 'student':
        flash("Please log in as a student.", "danger")
        return redirect(url_for('auth.login'))

    auth_user_id = session['user_id']
    cursor = current_app.db.connection.cursor(DictCursor)

    # 1) Who am I?
    cursor.execute("SELECT id, student_name FROM students WHERE auth_user_id=%s", (auth_user_id,))
    student = cursor.fetchone()
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for('auth.login'))

    sid = student['id']

    # 2) Load all their reports
    cursor.execute("""
      SELECT id, report_date, academic_year, attendance_pct, remarks, total_percentage
      FROM student_reports
      WHERE student_id=%s
      ORDER BY report_date DESC
    """, (sid,))
    all_reports = cursor.fetchall()
    for r in all_reports:
        cursor.execute("""
          SELECT subject_name, marks, percentage
          FROM student_report_subjects
          WHERE report_id=%s
        """, (r['id'],))
        r['subjects'] = cursor.fetchall()

    if all_reports:
        # choose which one to display
        if report_id:
            latest = next((r for r in all_reports if r['id']==report_id), all_reports[0])
        else:
            latest = all_reports[0]
        history = [r for r in all_reports if r['id']!=latest['id']]
    else:
        latest = None
        history = []

    # 3) Attendance summary: per‑class %
    cursor.execute("""
      SELECT
        c.id AS class_id,
        c.class_name,
        ROUND(
          SUM(ca.status='present') / COUNT(*) * 100
        ,2) AS pct
      FROM class_attendance ca
      JOIN classes c ON c.id=ca.class_id
      WHERE ca.student_id=%s
      GROUP BY c.id, c.class_name
    """, (sid,))
    classes_att = cursor.fetchall()

    # 4) For each class, grab the date‑by‑date records
    for cl in classes_att:
        cursor.execute("""
          SELECT attendance_date, status
          FROM class_attendance
          WHERE student_id=%s AND class_id=%s
          ORDER BY attendance_date DESC
        """, (sid, cl['class_id']))
        cl['records'] = cursor.fetchall()

    return render_template('student/reports.html',
                           student_name=student['student_name'],
                           latest=latest,
                           history=history,
                           classes_att=classes_att)
    
@student_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    # 🔐 only students
    if not session.get('logged_in') or session['user_type'] != 'student':
        return redirect(url_for('auth.login'))

    me_auth = session['user_id']
    cursor  = current_app.db.connection.cursor(DictCursor)

    # ─── GET: load profile + contacts ───────────────────────────────
    if request.method == 'GET':
        # 1) profile + dark_mode flag
        cursor.execute("""
          SELECT s.student_name, s.phone, s.profile_pic,
                 s.course, s.dark_mode,
                 au.email, au.id AS auth_id
          FROM students s
          JOIN auth_users au ON s.auth_user_id = au.id
          WHERE au.id = %s
        """, (me_auth,))
        profile = cursor.fetchone() or {}

        # 2) who can they complaint against? their teacher + their institute
        contacts = []

        cursor.execute("""
          SELECT au.id, au.email
          FROM students st
          JOIN teachers t ON st.teacher_id = t.id
          JOIN auth_users au ON t.auth_user_id = au.id
          WHERE st.auth_user_id = %s
        """, (me_auth,))
        t = cursor.fetchone()
        if t:
            contacts.append({'id': t['id'], 'email': t['email'], 'type': 'Teacher'})

        cursor.execute("""
          SELECT au.id, au.email
          FROM students st
          JOIN institutions inst ON st.institute_id = inst.id
          JOIN auth_users au ON inst.auth_user_id = au.id
          WHERE st.auth_user_id = %s
        """, (me_auth,))
        i = cursor.fetchone()
        if i:
            contacts.append({'id': i['id'], 'email': i['email'], 'type': 'Institute'})

        return render_template(
            'student/settings.html',
            profile=profile,
            contacts=contacts
        )

    # ─── POST: handle four forms ────────────────────────────────────
    action = request.form.get('action')
    try:
        # 1) PROFILE UPDATE
        if action == 'profile':
            name  = request.form['student_name']
            phone = request.form['phone']
            # handle picture upload
            pic = request.files.get('profile_pic')
            if pic and pic.filename:
                fn = secure_filename(pic.filename)
                upl = os.path.join(current_app.root_path, 'static', 'uploads')
                os.makedirs(upl, exist_ok=True)
                pic.save(os.path.join(upl, fn))
                cursor.execute(
                    "UPDATE students SET profile_pic=%s WHERE auth_user_id=%s",
                    (fn, me_auth)
                )
            cursor.execute(
                "UPDATE students SET student_name=%s, phone=%s WHERE auth_user_id=%s",
                (name, phone, me_auth)
            )
            flash("Profile updated.", "success")

        # 2) PASSWORD CHANGE
        elif action == 'password':
            old = request.form['current_password']
            new = request.form['new_password']
            conf= request.form['confirm_password']

            # check old
            cursor.execute("SELECT password FROM auth_users WHERE id=%s", (me_auth,))
            stored = cursor.fetchone()['password']
            if not check_password_hash(stored, old):
                flash("Current password is incorrect.", "danger")
                return redirect(url_for('student.settings'))
            if new != conf:
                flash("New passwords do not match.", "danger")
                return redirect(url_for('student.settings'))

            new_h = generate_password_hash(new, method='pbkdf2:sha256')
            cursor.execute(
                "UPDATE auth_users SET password=%s WHERE id=%s",
                (new_h, me_auth)
            )
            flash("Password changed—please log in again.", "success")
            current_app.db.connection.commit()
            session.clear()
            return redirect(url_for('auth.login'))

        # 3) APPEARANCE TOGGLE
        elif action == 'appearance':
            dm = 1 if request.form.get('dark_mode') == 'on' else 0
            cursor.execute(
                "UPDATE students SET dark_mode=%s WHERE auth_user_id=%s",
                (dm, me_auth)
            )
            flash("Appearance settings saved.", "success")

        # 4) COMPLAINT SUBMISSION
        elif action == 'complaint':
            against = int(request.form['against_id'])
            cat     = request.form['category']
            subj    = request.form['subject'].strip()
            det     = request.form['details'].strip()
            anon    = 1 if request.form.get('anonymous') == 'on' else 0

            if not (against and cat and subj and det):
                flash("Please fill in all complaint fields.", "danger")
                return redirect(url_for('student.settings'))

            # insert into complaints (needs an against_auth_id column)
            cursor.execute("""
              INSERT INTO complaints
                (user_id, against_auth_id, category, subject, details, is_anonymous)
              VALUES (%s,      %s,                %s,       %s,      %s,      %s)
            """, (
                # lookup your student.id
                cursor.execute("SELECT id FROM students WHERE auth_user_id=%s", (me_auth,)),
                against,
                cat,
                subj,
                det,
                anon
            ))
            flash("Complaint submitted successfully!", "success")

        # commit whatever we did
        current_app.db.connection.commit()

    except Exception as e:
        current_app.db.connection.rollback()
        flash(f"An error occurred: {e}", "danger")

    return redirect(url_for('student.settings'))

@student_bp.app_context_processor
def inject_dark_mode():
    # default off
    dm = False

    if session.get('logged_in') and session.get('user_type') == 'student':
        cur = current_app.db.connection.cursor(DictCursor)
        cur.execute(
            "SELECT dark_mode FROM students WHERE auth_user_id = %s",
            (session['user_id'],)
        )
        row = cur.fetchone()
        dm = bool(row and row.get('dark_mode'))
    return dict(dark_mode=dm)