from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from MySQLdb.cursors import DictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import urllib.parse as urlparse
import os

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        cursor = current_app.db.connection.cursor(DictCursor)
        
        # Query the central auth_users table
        cursor.execute("SELECT * FROM auth_users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True
            session['user_type'] = user['role']
            session['user_id'] = user['id']
            
            # If institution, check its approval status from the institutions table
            if user['role'] == 'institution':
                cursor.execute("SELECT status FROM institutions WHERE auth_user_id = %s", (user['id'],))
                inst_status = cursor.fetchone()
                if inst_status:
                    status = inst_status['status']
                    # Redirect to a status page that displays the status message
                    return redirect(url_for('auth.institution_status', status=status))
                else:
                    flash("Institution profile not found", "danger")
                    return redirect(url_for('auth.get_started'))
            # For other roles, redirect accordingly
            elif user['role'] == 'admin':
                return redirect(url_for('admin.admin_home'))
            elif user['role'] == 'teacher':
                return redirect(url_for('teacher.dashboard'))
            elif user['role'] == 'student':
                return redirect(url_for('student.dashboard'))
            else:
                flash("User role not recognized", "danger")
                return redirect(url_for('auth.get_started'))
        else:
            flash("Invalid email or password", "danger")
            return redirect(url_for('auth.get_started'))
    
    return redirect(url_for('auth.get_started'))

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@auth_bp.route('/institution_signup', methods=['GET', 'POST'])
def institution_signup():
    if request.method == 'POST':
        # Retrieve form data
        institution_name = request.form.get('institution_name')
        reg_number = request.form.get('reg_number')
        city = request.form.get('city')
        state = request.form.get('state')
        address = request.form.get('address')
        admin_name = request.form.get('admin_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        agree_terms = request.form.get('agree_terms')  # 'on' if checked

        # Validate password confirmation
        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return redirect(url_for('auth.institution_signup'))

        # Hash the password securely using pbkdf2:sha256
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Process file upload for institute logo
        logo_file = request.files.get('logo')
        logo_filename = None
        if logo_file and logo_file.filename:
            logo_filename = secure_filename(logo_file.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            logo_file.save(os.path.join(upload_folder, logo_filename))

        # Convert agree_terms checkbox value to boolean
        terms_agreed = True if agree_terms == 'on' else False

        try:
            cursor = current_app.db.connection.cursor()
            # Insert authentication record
            sql_auth = """
                INSERT INTO auth_users (email, password, role)
                VALUES (%s, %s, %s)
            """
            cursor.execute(sql_auth, (email, hashed_password, 'institution'))
            auth_user_id = cursor.lastrowid

            # Insert institution profile with status defaulting to 'pending'
            sql_inst = """
                INSERT INTO institutions 
                (auth_user_id, institution_name, reg_number, city, state, address, admin_name, phone, username, logo, agree_terms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql_inst, (
                auth_user_id, institution_name, reg_number, city, state, address,
                admin_name, phone, username, logo_filename, terms_agreed
            ))
            current_app.db.connection.commit()
            flash("Institution registered successfully! Your request is pending admin approval.", "success")
            return redirect(url_for('auth.login'))
        except Exception as e:
            current_app.db.connection.rollback()
            flash("Registration failed: " + str(e), "danger")
    return render_template('singup/institution_signup.html')

@auth_bp.route('/teacher_signup', methods=['GET', 'POST'])
def teacher_signup():
    token = request.args.get('token')
    institution_id = None

    if token:
        cursor = current_app.db.connection.cursor(DictCursor)
        cursor.execute("SELECT institute_id FROM teacher_invites WHERE token = %s", (token,))
        invite = cursor.fetchone()
        cursor.close()

        if invite:
            institution_id = invite['institute_id']
            session['institution_id'] = institution_id
        else:
            flash("Invalid or expired invitation token.", "danger")
            return redirect(url_for('auth.get_started'))
    else:
        institution_id = session.get('institution_id')

    if request.method == 'POST':
        teacher_name = request.form.get('teacher_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        dob = request.form.get('dob')
        gender = request.form.get('gender')
        city = request.form.get('city')
        state = request.form.get('state')
        address = request.form.get('address')
        subject_expertise1 = request.form.get('subject_expertise1')
        subject_expertise2 = request.form.get('subject_expertise2')
        years_experience = request.form.get('years_experience')
        highest_qualification = request.form.get('highest_qualification')
        specialization = request.form.get('specialization')
        teacher_id = request.form.get('teacher_id')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return redirect(url_for('auth.teacher_signup', token=token))

        if not institution_id:
            flash("Institution not found. Please try again.", "danger")
            return redirect(url_for('auth.teacher_signup', token=token))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        profile_pic_file = request.files.get('profile_pic')
        profile_pic_filename = None
        if profile_pic_file and profile_pic_file.filename:
            profile_pic_filename = secure_filename(profile_pic_file.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            profile_pic_file.save(os.path.join(upload_folder, profile_pic_filename))
        
        resume_file = request.files.get('resume')
        resume_filename = None
        if resume_file and resume_file.filename:
            resume_filename = secure_filename(resume_file.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            resume_file.save(os.path.join(upload_folder, resume_filename))

        try:
            cursor = current_app.db.connection.cursor()
            sql_auth = "INSERT INTO auth_users (email, password, role) VALUES (%s, %s, %s)"
            cursor.execute(sql_auth, (email, hashed_password, 'teacher'))
            auth_user_id = cursor.lastrowid

            sql_teacher = """
                INSERT INTO teachers (
                    auth_user_id, teacher_name, phone, dob, gender, city, state, address, 
                    subject_expertise1, subject_expertise2, years_experience, highest_qualification, 
                    specialization, teacher_id, username, institution_id, profile_pic, resume, invite_token
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql_teacher, (
                auth_user_id, teacher_name, phone, dob, gender, city, state, address,
                subject_expertise1, subject_expertise2, years_experience, highest_qualification,
                specialization, teacher_id, username, institution_id, profile_pic_filename, resume_filename,
                token  # Store the invite token here.
            ))

            current_app.db.connection.commit()
            # After successful registration in teacher_signup...
            cursor.execute("UPDATE teacher_invites SET teacher_email = %s WHERE token = %s", (email, token))
            current_app.db.connection.commit()
            cursor.close()

            flash("Teacher signup successful! Please log in.", "success")
            return redirect(url_for('auth.login'))
        except Exception as e:
            current_app.db.connection.rollback()
            cursor.close()
            flash("Signup failed: " + str(e), "danger")
            return redirect(url_for('auth.teacher_signup', token=token))

    return render_template('singup/teachers_signup.html', token=token)

@auth_bp.route('/student_signup', methods=['GET', 'POST'])
def student_signup():
    token = request.args.get('token')
    
    # Retrieve invite details
    try:
        cursor = current_app.db.connection.cursor(DictCursor)
        cursor.execute("SELECT teacher_id, institute_id FROM student_invites WHERE token = %s", (token,))
        invite_details = cursor.fetchone()
        if not invite_details:
            flash("Invalid or expired invite token.", "danger")
            return redirect(url_for('auth.get_started'))
        teacher_id = invite_details['teacher_id']
        institute_id = invite_details['institute_id']
    except Exception as e:
        flash("Error retrieving invite details: " + str(e), "danger")
        return redirect(url_for('auth.get_started'))
    
    if request.method == 'POST':
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
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Check if passwords match
        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect(url_for('auth.student_signup', token=token))

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        profile_pic_file = request.files.get('profile_pic')
        profile_pic_filename = None
        if profile_pic_file and profile_pic_file.filename:
            profile_pic_filename = secure_filename(profile_pic_file.filename)
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            profile_pic_file.save(os.path.join(upload_folder, profile_pic_filename))

        try:
            cursor = current_app.db.connection.cursor()
            
            # Insert into auth_users for authentication
            sql_auth = "INSERT INTO auth_users (email, password, role) VALUES (%s, %s, %s)"
            cursor.execute(sql_auth, (email, hashed_password, 'student'))
            auth_user_id = cursor.lastrowid  # Get the inserted user ID

            # Updated student insert query including teacher_id and institute_id
            sql_student = """
                INSERT INTO students (
                    auth_user_id, student_name, phone, dob, gender, city, state, address,
                    enroll_number, course, profile_pic, guardian_name, guardian_phone, username,
                    invite_token, teacher_id, institute_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql_student, (
                auth_user_id, student_name, phone, dob, gender, city, state, address,
                enroll_number, course, profile_pic_filename, guardian_name, guardian_phone, username,
                token, teacher_id, institute_id
            ))

            current_app.db.connection.commit()
            
            # Clear the invite record (if needed)
            cursor.execute("UPDATE student_invites SET student_email = %s WHERE token = %s", (email, token))
            current_app.db.connection.commit()
            
            flash("Student signup successful! Please log in.", "success")
            return redirect(url_for('auth.login'))

        except Exception as e:
            current_app.db.connection.rollback()
            flash("Signup failed: " + str(e), "danger")
            return redirect(url_for('auth.student_signup', token=token))

    return render_template('singup/student_signup.html', token=token)

@auth_bp.route('/get_started')
def get_started():
    return render_template("singup/get_started.html")

@auth_bp.route('/terms')
def terms():
    return render_template('singup/terms.html')

# ____________________________________________
@auth_bp.route('/institution_status')
def institution_status():
    # Get the logged-in institute's ID from the session
    institute_id = session.get('user_id')
    if not institute_id:
        flash("No institute logged in", "danger")
        return redirect(url_for('auth.login'))
    
    # Get the status from the query parameter
    status = request.args.get('status')

    if status == 'approved':
        # Use a DictCursor to query the institution record
        cursor = current_app.db.connection.cursor(DictCursor)
        cursor.execute("SELECT status_shown FROM institutions WHERE auth_user_id = %s", (institute_id,))
        result = cursor.fetchone()
        
        # If popup already shown, redirect to the dashboard
        if result and result.get('status_shown'):
            return redirect(url_for('institute.dashboard'))
        
        # Otherwise, mark the approved status page as shown in the DB
        cursor.execute("UPDATE institutions SET status_shown = TRUE WHERE auth_user_id = %s", (institute_id,))
        current_app.db.connection.commit()

    # Render the status page if it's pending or rejected, or after showing for the first time
    return render_template('singup/institution_status.html', status=status)

@auth_bp.route('/join_link', methods=['POST'])
def join_link():
    join_link = request.form.get('join_link')
    if not join_link:
        flash("Please enter a valid link.", "danger")
        return redirect(url_for('auth.get_started'))

    # Parse token from URL
    parsed_url = urlparse.urlparse(join_link)
    query_params = urlparse.parse_qs(parsed_url.query)
    token = query_params.get('token', [None])[0]

    if not token:
        flash("Invalid link. Token not found.", "danger")
        return redirect(url_for('auth.get_started'))

    token = token.strip().strip('"').strip("'")
    print("Token after cleaning:", repr(token))  # Debug

    conn = current_app.db.connection
    cursor = conn.cursor(DictCursor)

    # Check if a teacher account exists that used this token
    cursor.execute("SELECT * FROM teachers WHERE invite_token = %s", (token,))
    teacher_record = cursor.fetchone()
    if teacher_record:
        session['logged_in'] = True
        session['user_type'] = 'teacher'
        session['user_id'] = teacher_record['auth_user_id']  # or adjust based on your schema
        flash("Registration complete. Redirecting to teacher dashboard...", "success")
        return redirect(url_for('teacher.dashboard'))


    # Check if a student account exists that used this token
    cursor.execute("SELECT * FROM students WHERE invite_token = %s", (token,))
    student_record = cursor.fetchone()
    if student_record:
        session['logged_in'] = True
        session['user_type'] = 'student'
        session['user_id'] = student_record['auth_user_id']  # or adjust accordingly
        flash("Registration complete. Redirecting to student dashboard...", "success")
        return redirect(url_for('student.dashboard'))

    # If invite exists but no account is found, registration is incomplete.
    # Check teacher_invites first.
    cursor.execute("SELECT * FROM teacher_invites WHERE token = %s", (token,))
    teacher_invite = cursor.fetchone()
    if teacher_invite:
        flash("Please complete your teacher registration.", "info")
        return redirect(url_for('auth.teacher_signup', token=token))

    # Then check student_invites.
    cursor.execute("SELECT * FROM student_invites WHERE token = %s", (token,))
    student_invite = cursor.fetchone()
    if student_invite:
        flash("Please complete your student registration.", "info")
        return redirect(url_for('auth.student_signup', token=token))

    flash("Invalid or expired token.", "danger")
    return redirect(url_for('auth.get_started'))
