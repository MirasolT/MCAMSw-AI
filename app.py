import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
import mysql.connector
from werkzeug.utils import secure_filename
import os
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
import re
import io
try:
    from openai import OpenAI
    openai_available = True
except ImportError:
    openai_available = False

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Flask-Mail configuration (use your Gmail/app password)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = 'your.@gmail.com'  # Your Gmail
app.config['MAIL_PASSWORD'] = 'your.password'       # Your App Password
app.config['MAIL_DEFAULT_SENDER'] = ('Academy Medical Clinic', 'your.@gmail.com')

mail = Mail(app)

def send_notification_email(recipient, subject, message, sender_name=None, sender_email=None):
    msg = Message(subject, recipients=[recipient])
    if sender_name and sender_email:
        msg.reply_to = (sender_email, sender_name)
    msg.html = f"""
        <h3>New Message From Notification System</h3>
        <p><strong>From:</strong> {sender_name or 'System'} &lt;{sender_email or app.config['MAIL_DEFAULT_SENDER'][1]}&gt;</p>
        <p><strong>Subject:</strong> {subject}</p>
        <p><strong>Message:</strong><br>{message.replace(chr(10), '<br>')}</p>
    """
    msg.body = f"""From: {sender_name or 'System'} <{sender_email or app.config['MAIL_DEFAULT_SENDER'][1]}>
Subject: {subject}
Message:
{message}"""
    try:
        mail.send(msg)
    except Exception as e:
        print(f"Email send error: {e}")
        try:
            from flask import flash
            flash(f"Email send error: {e}", "danger")
        except:
            pass

@app.route('/test_email')
def test_email():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    try:
        send_notification_email(
            recipient=app.config['MAIL_USERNAME'],
            subject='Test Email from Medical Clinic System',
            message='This is a test email to verify your Flask-Mail configuration.',
            sender_name='System Test',
            sender_email=app.config['MAIL_DEFAULT_SENDER'][1]
        )
        flash('Test email sent successfully! Check your inbox.', 'success')
    except Exception as e:
        flash(f'Failed to send test email: {e}', 'danger')
    return redirect(url_for('admin_dashboard'))

# Connect to MySQL (XAMPP)
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='school_clinic_system',
         port=3306
    )

def notify_and_email(recipient_id, sender_id, message_type, subject, message, delivery_method, is_read=False, appointment_id=None, related_record_id=None):
    # Insert notification into the database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO notifications (recipient_id, sender_id, message_type, subject, message, delivery_method, is_read, appointment_id, related_record_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (recipient_id, sender_id, message_type, subject, message, delivery_method, is_read, appointment_id, related_record_id))
    conn.commit()
    cursor.close()
    conn.close()
    # If delivery_method is Email, send an email
    if delivery_method == 'Email':
        # Get recipient email and name
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT email, first_name, last_name FROM users WHERE user_id = %s', (recipient_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user and user['email']:
            try:
                send_notification_email(
                    recipient=user['email'],
                    subject=subject,
                    message=message,
                    sender_name='Medical Clinic Academy',
                    sender_email=app.config['MAIL_DEFAULT_SENDER'][1]
                )
            except Exception as e:
                # Optionally log or flash email errors
                pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Database connection
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Ensure proper querying for active users with matching credentials
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s AND is_active = TRUE", (username, password))
        user = cursor.fetchone()

        if user:
            # Set session variables based on the logged-in user's info
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['role'] = user['role']

            flash("Login successful", "success")

            # Role-based redirection
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'student':
                return redirect(url_for('student_dashboard'))
            elif user['role'] == 'parent':
                return redirect(url_for('parent_dashboard'))
            elif user['role'] == 'staff':
                return redirect(url_for('staff_dashboard'))

        else:
            flash("Invalid credentials or inactive user", "danger")

        cursor.close()
        conn.close()

    return render_template('login.html')


@app.route('/register/<role>', methods=['GET', 'POST'])
def register(role):
    if role not in ['student', 'parent']:
        return "Invalid role", 400

    if request.method == 'POST':
        try:
            # Extract form data
            guardian_id = request.form.get('guardian_id')
            student_ref_id = request.form.get('student_ref_id')
            age = int(request.form['age'])

            # Age restriction: Block registration for underage users
            if age < 16:
                flash("You must be 16 or older to register.", "danger")
                return redirect(url_for('login'))

            # Handle profile photo upload
            profile_photo_file = request.files.get('profile_photo')
            profile_photo_path = ''
            if profile_photo_file and profile_photo_file.filename != '':
                filename = secure_filename(profile_photo_file.filename)
                # Ensure upload folder exists
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                profile_photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                profile_photo_file.save(profile_photo_path)

            data = (
                request.form['username'],
                request.form['password'],  # ⚠️ No hashing as per instruction
                request.form['email'],
                request.form['first_name'],
                request.form['last_name'],
                request.form['birthdate'],
                age,
                request.form['gender'],
                request.form['address'],
                request.form['phone_number'],
                role,
                int(guardian_id) if guardian_id else None,
                int(student_ref_id) if student_ref_id else None,
                profile_photo_path,
                request.form['emergency_contact_name'],
                request.form['emergency_contact_phone'],
                request.form['school_id']
            )

            # Insert into database
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (
                    username, password, email, first_name, last_name, birthdate, age, gender, address,
                    phone_number, role, guardian_id, student_ref_id, profile_photo,
                    emergency_contact_name, emergency_contact_phone, school_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, data)

            conn.commit()
            cursor.close()
            conn.close()

            # Send professional welcome notification/email to the new user
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT user_id, first_name, last_name, email FROM users WHERE username = %s', (request.form['username'],))
            new_user = cursor.fetchone()
            sender_id = session['user_id'] if 'user_id' in session else None
            parent_name = session.get('username', 'Your Parent')
            if new_user:
                # Notify the child (Email & In-App)
                for method in ['Email', 'In-App']:
                    notify_and_email(
                        recipient_id=new_user['user_id'],
                        sender_id=sender_id,
                        message_type='Welcome',
                        subject='Welcome to Medical Clinic Academy',
                        message=f"Your account has been created and linked to your parent {parent_name}. You can now access your health records and appointments.",
                        delivery_method=method,
                        is_read=False
                    )
                # Notify the parent (Email & In-App)
                for method in ['Email', 'In-App']:
                    notify_and_email(
                        recipient_id=sender_id,
                        sender_id=sender_id,
                        message_type='ChildRegistered',
                        subject='Child Registered Successfully',
                        message=f"You have successfully registered {new_user['first_name']} {new_user['last_name']} as your child in the system.",
                        delivery_method=method,
                        is_read=False
                    )
            cursor.close()
            conn.close()

            flash(f"{role.capitalize()} registered successfully!", "success")
            return redirect(url_for('login'))

        except Exception as e:
            flash(f"Error: {str(e)}", "danger")

    return render_template('register.html', role=role)

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin':
        flash("Access denied", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Show all users, including admins
    cursor.execute("SELECT * FROM users WHERE is_active = TRUE")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_dashboard.html', users=users)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'role' not in session or session['role'] != 'admin':
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        # You can process settings form here
        flash("Settings saved successfully!", "success")
        return redirect(url_for('settings'))

    return render_template('admin_settings.html')

@app.route('/manage_encryption', methods=['GET', 'POST'])
def manage_encryption():
    if 'role' not in session or session['role'] != 'admin':
        flash("Access denied", "danger")
        return redirect(url_for('login'))

    # Add your encryption management logic here (e.g., enable/disable encryption, settings)
    if request.method == 'POST':
        encryption_enabled = request.form.get('encryption_enabled') == 'on'

        # Example: Save encryption settings to database or config file
        # This could be saving a flag to the database indicating encryption state
        # For simplicity, we'll just print it here
        flash(f"Encryption {'enabled' if encryption_enabled else 'disabled'}", 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('manage_encryption.html')


@app.route('/view_system_logs')
def view_system_logs():
    if 'role' not in session or session['role'] != 'admin':
        flash("Access denied", "danger")
        return redirect(url_for('login'))

    # Example: Retrieve system logs from a log file or database
    # Here, we'll just simulate some log entries
    logs = [
        {"timestamp": "2025-05-01 10:00:00", "message": "User logged in"},
        {"timestamp": "2025-05-01 10:30:00", "message": "User registered"},
        {"timestamp": "2025-05-01 11:00:00", "message": "System backup started"},
    ]

    return render_template('view_system_logs.html', logs=logs)


@app.route('/generate_health_report', methods=['GET', 'POST'])
def generate_health_report():
    if 'role' not in session or session['role'] != 'admin':
        flash("Access denied", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        export_format = request.form.get('export_format')
        if export_format in ['txt', 'ini']:
            # Fetch all data
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT * FROM users')
            users = cursor.fetchall()
            cursor.execute('SELECT * FROM health_records')
            health_records = cursor.fetchall()
            cursor.execute('SELECT * FROM appointments')
            appointments = cursor.fetchall()
            cursor.execute('SELECT * FROM vaccinations')
            vaccinations = cursor.fetchall()
            cursor.execute('SELECT * FROM notifications')
            notifications = cursor.fetchall()
            cursor.close()
            conn.close()

            # Professional sentence-based report
            def user_sentence(u):
                return f"User {u['user_id']}: {u['first_name']} {u['last_name']} (Username: {u['username']}, Role: {u['role']}, Email: {u['email']}, Age: {u['age']}, Gender: {u['gender']}, Active: {u['is_active']})"
            def health_sentence(r):
                return f"Health Record {r['record_id']}: Student ID {r['student_id']}, Height: {r['height_cm']} cm, Weight: {r['weight_kg']} kg, Blood Type: {r['blood_type']}, Conditions: {r['medical_conditions']}, Visit Date: {r['visit_date']}, Status: {r['status']}"
            def appointment_sentence(a):
                return f"Appointment {a['appointment_id']}: Student ID {a['student_id']}, Date: {a['appointment_date']} {a['appointment_time']}, Type: {a['appointment_type']}, Status: {a['status']}, Reason: {a['reason']}"
            def vaccination_sentence(v):
                return f"Vaccination {v['vaccination_id']}: Student ID {v['student_id']}, Vaccine: {v['vaccine_name']} ({v['vaccine_type']}), Date: {v['date_administered']}, Status: {v['status']}"
            def notification_sentence(n):
                return f"Notification {n['notification_id']}: To User {n['recipient_id']}, Type: {n['message_type']}, Subject: {n['subject']}, Sent: {n['sent_at']}, Read: {n['is_read']}"

            report = io.StringIO()
            if export_format == 'ini':
                report.write('[Users]\n')
                for u in users:
                    report.write(user_sentence(u) + '\n')
                report.write('\n[HealthRecords]\n')
                for r in health_records:
                    report.write(health_sentence(r) + '\n')
                report.write('\n[Appointments]\n')
                for a in appointments:
                    report.write(appointment_sentence(a) + '\n')
                report.write('\n[Vaccinations]\n')
                for v in vaccinations:
                    report.write(vaccination_sentence(v) + '\n')
                report.write('\n[Notifications]\n')
                for n in notifications:
                    report.write(notification_sentence(n) + '\n')
            else:
                report.write('--- Users ---\n')
                for u in users:
                    report.write(user_sentence(u) + '\n')
                report.write('\n--- Health Records ---\n')
                for r in health_records:
                    report.write(health_sentence(r) + '\n')
                report.write('\n--- Appointments ---\n')
                for a in appointments:
                    report.write(appointment_sentence(a) + '\n')
                report.write('\n--- Vaccinations ---\n')
                for v in vaccinations:
                    report.write(vaccination_sentence(v) + '\n')
                report.write('\n--- Notifications ---\n')
                for n in notifications:
                    report.write(notification_sentence(n) + '\n')
            report.seek(0)
            filename = f"health_report.{export_format}"
            return send_file(io.BytesIO(report.getvalue().encode('utf-8')), as_attachment=True, download_name=filename, mimetype='text/plain')
        else:
            flash("Invalid export format.", "danger")
            return redirect(url_for('generate_health_report'))

    # GET: Show all data and summary for charts
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    cursor.execute('SELECT * FROM health_records')
    health_records = cursor.fetchall()
    cursor.execute('SELECT * FROM appointments')
    appointments = cursor.fetchall()
    cursor.execute('SELECT * FROM vaccinations')
    vaccinations = cursor.fetchall()
    cursor.execute('SELECT * FROM notifications')
    notifications = cursor.fetchall()
    # Summary for charts
    # Users per role
    cursor.execute('SELECT role, COUNT(*) as count FROM users GROUP BY role')
    users_per_role = cursor.fetchall()
    # Appointments per day
    cursor.execute('SELECT appointment_date, COUNT(*) as count FROM appointments GROUP BY appointment_date ORDER BY appointment_date')
    appt_per_day = cursor.fetchall()
    # Vaccinations per month
    cursor.execute("SELECT DATE_FORMAT(date_administered, '%Y-%m') as month, COUNT(*) as count FROM vaccinations GROUP BY month ORDER BY month")
    vax_per_month = cursor.fetchall()
    # Health records per status
    cursor.execute('SELECT status, COUNT(*) as count FROM health_records GROUP BY status')
    health_per_status = cursor.fetchall()
    cursor.close()
    conn.close()
    # Build unique years for global filter
    years = set()
    for a in appt_per_day:
        if a['appointment_date']:
            years.add(str(a['appointment_date'])[:4])
    for v in vax_per_month:
        if v['month']:
            years.add(str(v['month'])[:4])
    years = sorted(years)
    # Convert all data to be JSON serializable (dates, datetimes, timedeltas to str)
    import datetime
    def make_serializable(obj):
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serializable(i) for i in obj]
        elif isinstance(obj, (datetime.datetime, datetime.date, datetime.timedelta)):
            return str(obj)
        else:
            return obj
    users = make_serializable(users)
    health_records = make_serializable(health_records)
    appointments = make_serializable(appointments)
    vaccinations = make_serializable(vaccinations)
    notifications = make_serializable(notifications)
    appt_per_day = make_serializable(appt_per_day)
    vax_per_month = make_serializable(vax_per_month)
    health_per_status = make_serializable(health_per_status)
    return render_template('generate_health_report.html',
        users=users,
        health_records=health_records,
        appointments=appointments,
        vaccinations=vaccinations,
        notifications=notifications,
        users_per_role=users_per_role,
        appt_per_day=appt_per_day,
        vax_per_month=vax_per_month,
        health_per_status=health_per_status,
        years=years
    )


@app.route('/create_user', methods=['GET', 'POST'])
def create_user():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    # Fetch students under 16 for the dropdown
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_id, first_name, last_name, age, profile_photo FROM users WHERE role = 'student' AND age < 16 AND is_active = TRUE")
    under16_students = cursor.fetchall()
    cursor.close()
    conn.close()

    if request.method == 'POST':
        try:
            age = int(request.form['age'])
            role = request.form['role']
            profile_photo_file = request.files.get('profile_photo')
            profile_photo_path = ''
            if profile_photo_file and profile_photo_file.filename != '':
                filename = secure_filename(profile_photo_file.filename)
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                profile_photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                profile_photo_file.save(profile_photo_path)
            # Set guardian_id and student_ref_id to None for staff/admin
            guardian_id = request.form.get('guardian_id') or None
            student_ref_id = request.form.get('student_ref_id') or None
            if role in ['staff', 'admin']:
                guardian_id = None
                student_ref_id = None
            data = (
                request.form['username'],
                request.form['password'],
                request.form['email'],
                request.form['first_name'],
                request.form['last_name'],
                request.form['birthdate'],
                age,
                request.form['gender'],
                request.form['address'],
                request.form['phone_number'],
                role,
                guardian_id,
                student_ref_id,
                profile_photo_path,
                request.form['emergency_contact_name'],
                request.form['emergency_contact_phone'],
                request.form['school_id']
            )
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (
                    username, password, email, first_name, last_name, birthdate, age, gender, address,
                    phone_number, role, guardian_id, student_ref_id, profile_photo,
                    emergency_contact_name, emergency_contact_phone, school_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, data)
            conn.commit()
            cursor.close()
            conn.close()

            # Notify the admin (self) about the creation
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT user_id, first_name, last_name, email, role FROM users WHERE username = %s', (request.form['username'],))
            new_user = cursor.fetchone()
            # Notify the admin (self) about the creation
            if new_user:
                notify_and_email(
                    recipient_id=session['user_id'],
                    sender_id=session['user_id'],
                    message_type='Account',
                    subject='User Created',
                    message=f"Hi Admin, you successfully created {new_user['role'].capitalize()} {new_user['first_name']} {new_user['last_name']}.",
                    delivery_method='Email',
                    is_read=False
                )
                # Notify the new user (welcome)
                notify_and_email(
                    recipient_id=new_user['user_id'],
                    sender_id=session['user_id'],
                    message_type='Welcome',
                    subject='Welcome to Medical Clinic Academy',
                    message=f"Welcome, {new_user['first_name']} {new_user['last_name']}. Your account has been created at Medical Clinic Academy. We look forward to supporting your health and wellness.",
                    delivery_method='Email',
                    is_read=False
                )
            cursor.close()
            conn.close()

            flash("User created successfully!", "success")
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
    return render_template('create_user.html', under16_students=under16_students)


@app.route('/update_user/<int:user_id>', methods=['GET', 'POST'])
def update_user(user_id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    # Fetch students under 16 for the dropdown
    cursor.execute("SELECT user_id, first_name, last_name, age, profile_photo FROM users WHERE role = 'student' AND age < 16 AND is_active = TRUE")
    under16_students = cursor.fetchall()
    if request.method == 'POST':
        update_data = (
            request.form['password'],
            request.form['role'],
            user_id
        )
        cursor.execute("UPDATE users SET password = %s, role = %s WHERE user_id = %s", update_data)
        conn.commit()
        # Fetch updated user info for notifications
        cursor.execute("SELECT user_id, first_name, last_name, role, email FROM users WHERE user_id = %s", (user_id,))
        updated_user = cursor.fetchone()
        # Notify the admin (self)
        if updated_user:
            notify_and_email(
                recipient_id=session['user_id'],
                sender_id=session['user_id'],
                message_type='Account',
                subject='User Updated',
                message=f"Hi Admin, you successfully updated {updated_user['role'].capitalize()} {updated_user['first_name']} {updated_user['last_name']}.",
                delivery_method='Email',
                is_read=False
            )
            # Notify the updated user
            notify_and_email(
                recipient_id=updated_user['user_id'],
                sender_id=session['user_id'],
                message_type='Account',
                subject='Account Updated',
                message=f"Hi {updated_user['first_name']}, your account information has been updated by the admin.",
                delivery_method='Email',
                is_read=False
            )
        flash("User updated successfully!", "success")
        return redirect(url_for('admin_dashboard'))
    cursor.close()
    conn.close()
    return render_template('update_user.html', user=user, under16_students=under16_students)

@app.route('/deactivate_user/<int:user_id>')
def deactivate_user(user_id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = FALSE WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("User deactivated", "info")
    # Notify the deactivated user
    notify_and_email(
        recipient_id=user_id,
        sender_id=session['user_id'],
        message_type='Account',
        subject='Account Deactivated',
        message='Your account has been deactivated by the administrator. If you believe this is a mistake, please contact the Medical Clinic.',
        delivery_method='Email',
        is_read=False
    )
    # Notify the admin (self)
    notify_and_email(
        recipient_id=session['user_id'],
        sender_id=session['user_id'],
        message_type='Account',
        subject='User Account Deactivated',
        message=f'You have deactivated the account of user ID {user_id}.',
        delivery_method='Email',
        is_read=False
    )
    return redirect(url_for('admin_dashboard'))



@app.route('/student_dashboard')
def student_dashboard():
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT first_name, last_name, age FROM users WHERE user_id = %s", (session['user_id'],))
    user = cursor.fetchone()

    # Ensure every appointment has a notification for this student
    cursor.execute('SELECT appointment_id, appointment_date, appointment_time, appointment_type, status FROM appointments WHERE student_id = %s', (session['user_id'],))
    all_appts = cursor.fetchall()
    for appt in all_appts:
        with conn.cursor(dictionary=True) as check_cursor:
            check_cursor.execute('SELECT 1 FROM notifications WHERE recipient_id = %s AND appointment_id = %s', (session['user_id'], appt['appointment_id']))
            exists = check_cursor.fetchone()
            check_cursor.fetchall()  # Clear any remaining results
        if not exists:
            notify_and_email(
                recipient_id=session['user_id'],
                sender_id=session['user_id'],
                message_type='Alert',
                subject='Appointment',
                message=f"Appointment ({appt['appointment_type']}) on {appt['appointment_date']} {appt['appointment_time']} - Status: {appt['status']}",
                delivery_method='Email',
                is_read=False,
                appointment_id=appt['appointment_id']
            )
    # Ensure every vaccination has a notification for this student
    cursor.execute('SELECT vaccination_id, vaccine_name, date_administered, status FROM vaccinations WHERE student_id = %s', (session['user_id'],))
    all_vax = cursor.fetchall()
    for vax in all_vax:
        with conn.cursor(dictionary=True) as check_cursor:
            check_cursor.execute('SELECT 1 FROM notifications WHERE recipient_id = %s AND related_record_id = %s AND message_type = %s', (session['user_id'], vax['vaccination_id'], 'Vaccination'))
            exists = check_cursor.fetchone()
            check_cursor.fetchall()
        if not exists:
            notify_and_email(
                recipient_id=session['user_id'],
                sender_id=session['user_id'],
                message_type='Vaccination',
                subject='Vaccination',
                message=f"{vax['vaccine_name']} administered on {vax['date_administered']} - Status: {vax['status']}",
                delivery_method='Email',
                is_read=False,
                related_record_id=vax['vaccination_id']
            )
    # Ensure every health record has a notification for this student
    cursor.execute('SELECT record_id, visit_date, status FROM health_records WHERE student_id = %s', (session['user_id'],))
    all_recs = cursor.fetchall()
    for rec in all_recs:
        with conn.cursor(dictionary=True) as check_cursor:
            check_cursor.execute('SELECT 1 FROM notifications WHERE recipient_id = %s AND related_record_id = %s AND message_type = %s', (session['user_id'], rec['record_id'], 'HealthRecord'))
            exists = check_cursor.fetchone()
            check_cursor.fetchall()
        if not exists:
            notify_and_email(
                recipient_id=session['user_id'],
                sender_id=session['user_id'],
                message_type='HealthRecord',
                subject='Health Record',
                message=f"Health record updated on {rec['visit_date']} - Status: {rec['status']}",
                delivery_method='Email',
                is_read=False,
                related_record_id=rec['record_id']
            )
    conn.commit()

    # Fetch upcoming appointments (today or future, not cancelled, only Pending)
    cursor.execute('''SELECT DATE_FORMAT(appointment_date, '%Y-%m-%d') as appointment_date,
                             TIME_FORMAT(appointment_time, '%H:%i') as appointment_time,
                             appointment_type, status, reason
                      FROM appointments
                      WHERE student_id = %s AND appointment_date >= CURDATE() AND status = 'Pending'
                      ORDER BY appointment_date ASC, appointment_time ASC
                      LIMIT 5''', (session['user_id'],))
    upcoming_appointments = cursor.fetchall()

    # Fetch all notifications for the student (appointments, vaccinations, health_records, etc.)
    cursor.execute('''SELECT * FROM notifications WHERE recipient_id = %s ORDER BY sent_at DESC''', (session['user_id'],))
    notifications = cursor.fetchall()

    # Fetch 3 most recent unread health reminders
    cursor.execute('''SELECT * FROM notifications WHERE recipient_id = %s AND message_type = 'Reminder' ORDER BY is_read ASC, sent_at DESC LIMIT 3''', (session['user_id'],))
    health_reminders = cursor.fetchall()

    # Fetch 3 most recent health records
    cursor.execute('''SELECT visit_date, next_follow_up FROM health_records WHERE student_id = %s AND status != 'Archived' ORDER BY visit_date DESC, next_follow_up DESC LIMIT 3''', (session['user_id'],))
    recent_health_records = cursor.fetchall()

    cursor.close()
    conn.close()

    # Pass the data to the template
    return render_template('student_dashboard.html', username=f"{user['first_name']} {user['last_name']}", age=user['age'], upcoming_appointments=upcoming_appointments, notifications=notifications, health_reminders=health_reminders, recent_health_records=recent_health_records)

@app.route('/view_profile')
def view_profile():
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    # Fetch profile details from the database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (session['user_id'],))
    user = cursor.fetchone()
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()

    return render_template('view_profile.html', user=user)

@app.route('/update_profile', methods=['GET', 'POST'])
def update_profile():
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Get updated data from the form
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        phone_number = request.form['phone_number']

        # Update user profile in the database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''UPDATE users SET first_name = %s, last_name = %s, email = %s, phone_number = %s 
                          WHERE user_id = %s''', (first_name, last_name, email, phone_number, session['user_id']))
        conn.commit()
        cursor.close()
        conn.close()

        # Notify the user about their profile update
        notify_and_email(
            recipient_id=session['user_id'],
            sender_id=session['user_id'],
            message_type='Profile',
            subject='Profile Updated',
            message='Your profile has been updated successfully.',
            delivery_method='Email',
            is_read=False
        )

        flash("Profile updated successfully!", "success")
        return redirect(url_for('view_profile'))

    # Fetch the current profile data
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (session['user_id'],))
    user = cursor.fetchone()
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()

    return render_template('update_profile.html', user=user)

@app.route('/view_health_records')
def view_health_records():
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    # Fetch health records for the student
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''SELECT * FROM health_records WHERE student_id = %s AND status != 'Archived' ORDER BY visit_date DESC''', 
                   (session['user_id'],))
    records = cursor.fetchall()
    # Fetch user info for sidebar
    cursor.execute('SELECT first_name, last_name, age FROM users WHERE user_id = %s', (session['user_id'],))
    user = cursor.fetchone()
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()

    username = f"{user['first_name']} {user['last_name']}" if user else ''
    age = user['age'] if user else ''

    return render_template('view_health_records.html', records=records, username=username, age=age)

@app.route('/schedule_appointment', methods=['GET', 'POST'])
def schedule_appointment():
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    # Fetch the student's age from the database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT age FROM users WHERE user_id = %s", (session['user_id'],))
    user = cursor.fetchone()
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()

    if not user or user['age'] is None or user['age'] < 16:
        flash("You must be at least 16 years old to schedule an appointment.", "danger")
        return redirect(url_for('student_dashboard'))

    if request.method == 'POST':
        appointment_date = request.form['appointment_date']
        appointment_time = request.form['appointment_time']
        appointment_type = request.form['appointment_type']
        reason = request.form['reason']

        # Schedule an appointment
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO appointments (student_id, booked_by, appointment_date, appointment_time, 
                          appointment_type, reason, status) VALUES (%s, %s, %s, %s, %s, %s, 'Pending')''',
                       (session['user_id'], session['user_id'], appointment_date, appointment_time, appointment_type, reason))
        conn.commit()
        # Fetch student name
        cursor.execute('SELECT first_name, last_name FROM users WHERE user_id = %s', (session['user_id'],))
        student = cursor.fetchone()
        student_name = f"{student[0]} {student[1]}"
        # Notify all staff and all admins
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id FROM users WHERE role = 'staff'")
        staff_users = cursor.fetchall()
        cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchall()
        cursor.fetchall()  # Clear unread results
        cursor.close()
        conn.close()
        for staff in staff_users:
            notify_and_email(
                recipient_id=staff['user_id'],
                sender_id=session['user_id'] if 'user_id' in session else None,
                message_type='Appointment',
                subject='New Appointment Booked',
                message=f"A new appointment has been booked by {student_name} for {appointment_date} at {appointment_time}. Please review and take action (approve, reschedule, or cancel) as needed. Status: Pending.",
                delivery_method='Email',
                is_read=False
            )
        for admin in admin_users:
            notify_and_email(
                recipient_id=admin['user_id'],
                sender_id=session['user_id'] if 'user_id' in session else None,
                message_type='Appointment',
                subject='New Appointment Booked',
                message=f"A new appointment has been booked by {student_name} for {appointment_date} at {appointment_time}. Please review and take action (approve, reschedule, or cancel) as needed. Status: Pending.",
                delivery_method='Email',
                is_read=False
            )
        cursor.close()
        conn.close()
        # Notify the student (self) about their appointment
        notify_and_email(
            recipient_id=session['user_id'],
            sender_id=session['user_id'],
            message_type='Appointment',
            subject='Appointment Booked',
            message=f"Welcome, {student_name}. You have successfully booked an appointment. If this appointment is not cancelled, please proceed to the Medical Clinic for your consultation.",
            delivery_method='Email',
            is_read=False
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Appointment scheduled successfully!", "success")
        return redirect(url_for('student_dashboard'))

    return render_template('schedule_appointment.html')

@app.route('/student_view_appointments')
def student_view_appointments():
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    # Fetch appointments for the student
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''SELECT * FROM appointments WHERE student_id = %s ORDER BY appointment_date DESC''', 
                   (session['user_id'],))
    appointments = cursor.fetchall()
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()

    return render_template('student_view_appointments.html', appointments=appointments)

@app.route('/student_view_notifications')
def student_view_notifications():
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    # Fetch notifications for the student
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''SELECT * FROM notifications WHERE recipient_id = %s ORDER BY sent_at DESC''', 
                   (session['user_id'],))
    notifications = cursor.fetchall()
    # Fetch user info for sidebar
    cursor.execute('SELECT first_name, last_name, age FROM users WHERE user_id = %s', (session['user_id'],))
    user = cursor.fetchone()
    cursor.fetchall()  # Clear unread results
    # Count unread notifications
    cursor.execute('SELECT COUNT(*) as unread_count FROM notifications WHERE recipient_id = %s AND is_read = FALSE', (session['user_id'],))
    unread_count = cursor.fetchone()['unread_count']
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()

    username = f"{user['first_name']} {user['last_name']}" if user else ''
    age = user['age'] if user else ''

    return render_template('student_view_notifications.html', notifications=notifications, username=username, age=age, unread_count=unread_count)

@app.route('/parent_dashboard')
def parent_dashboard():
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))

    # Fetch health records from the database for the parent
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM health_records WHERE student_id IN (SELECT student_ref_id FROM users WHERE guardian_id = %s)", (session['user_id'],))
    health_records = cursor.fetchall()
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()

    return render_template('parent_dashboard.html', username=session['username'], health_records=health_records)

@app.route('/parent_view_student_profile')
def parent_view_student_profile():
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE guardian_id = %s", (session['user_id'],))
    students = cursor.fetchall()
    # Fetch students under 16 not linked to any parent
    cursor.execute("SELECT user_id, first_name, last_name, age FROM users WHERE role = 'student' AND age < 16 AND guardian_id IS NULL")
    linkable_students = cursor.fetchall()
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()
    return render_template('parent_view_student_profile.html', students=students, username=session['username'])

@app.route('/parent_update_student_profile/<int:student_id>', methods=['GET', 'POST'])
def parent_update_student_profile(student_id):
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch student profile based on guardian_id and student_id
    cursor.execute("SELECT * FROM users WHERE guardian_id = %s AND user_id = %s", (session['user_id'], student_id))
    student = cursor.fetchone()

    if not student:
        cursor.close()
        conn.close()
        flash("Student not found or not linked to your account.", "danger")
        return redirect(url_for('parent_view_student_profile'))

    if request.method == 'POST':
        # Get form data and update student profile
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        address = request.form['address']
        phone_number = request.form['phone_number']

        cursor.execute('''UPDATE users SET first_name=%s, last_name=%s, address=%s, phone_number=%s WHERE user_id=%s''',
                       (first_name, last_name, address, phone_number, student['user_id']))
        conn.commit()
        cursor.close()
        conn.close()

        # Notify the child about their profile update
        notify_and_email(
            recipient_id=student['user_id'],
            sender_id=session['user_id'],
            message_type='Profile',
            subject='Profile Updated',
            message='Your profile has been updated by your parent/guardian.',
            delivery_method='Email',
            is_read=False
        )
        # Notify the parent about the update
        notify_and_email(
            recipient_id=session['user_id'],
            sender_id=session['user_id'],
            message_type='Profile',
            subject='Child Profile Updated',
            message=f"You have updated the profile of {first_name} {last_name}.",
            delivery_method='Email',
            is_read=False
        )

        flash("Student profile updated successfully!", "success")
        return redirect(url_for('parent_view_student_profile'))

    cursor.close()
    conn.close()

    return render_template('parent_update_student_profile.html', student=student, student_id=student_id)

@app.route('/parent_register_child', methods=['GET', 'POST'])
def parent_register_child():
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            # Validate form data
            username = request.form['username']
            password = request.form['password']
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            birthdate = request.form['birthdate']
            gender = request.form['gender']
            address = request.form['address']
            phone_number = request.form['phone_number']
            school_id = request.form['school_id']

            # Validate password strength
            if len(password) < 8 or not any(char.isdigit() for char in password):
                flash("Password must be at least 8 characters with at least one number", "danger")
                return redirect(url_for('parent_register_child'))

            # Validate username format
            if not username.isalnum():
                flash("Username can only contain letters and numbers", "danger")
                return redirect(url_for('parent_register_child'))

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO users (username, password, email, first_name, last_name, birthdate, age, gender, address, phone_number, role, guardian_id, school_id) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'student', %s, %s)''',
                       (username, password, request.form['email'], first_name, last_name, birthdate, int(request.form['age']), gender, address, phone_number, session['user_id'], school_id))
            conn.commit()
            cursor.close()
            conn.close()

            flash("Child registered successfully!", "success")
            return redirect(url_for('parent_dashboard'))

        except Exception as e:
            flash(f"Error registering child: {str(e)}", "danger")

    return render_template('parent_register_child.html', username=session.get('username'))

@app.route('/parent_add_vaccination', methods=['GET', 'POST'])
def parent_add_vaccination():
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))

    # Get the parent's children from the database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT user_id, first_name, last_name 
                      FROM users 
                      WHERE guardian_id = %s AND role = 'student' 
                      ORDER BY first_name''', (session['user_id'],))
    students = cursor.fetchall()
    cursor.close()
    conn.close()

    if request.method == 'POST':
        try:
            # Get form data
            student_id = request.form['student_id']
            vaccine_name = request.form['vaccine_name']
            vaccine_type = request.form['vaccine_type']
            date_administered = request.form['date_administered']
            next_dose_date = request.form.get('next_dose_date') or None
            notes = request.form.get('notes') or None
            administered_by = session['user_id']

            # Validate date is not in the future
            if date_administered > datetime.now().strftime('%Y-%m-%d'):
                flash("Vaccination date cannot be in the future", "danger")
                return redirect(url_for('parent_add_vaccination'))

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO vaccinations 
                              (student_id, vaccine_name, vaccine_type, date_administered, 
                               next_dose_date, notes, administered_by)
                              VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                           (student_id, vaccine_name, vaccine_type, date_administered, 
                            next_dose_date, notes, administered_by))
            conn.commit()
            cursor.close()
            conn.close()

            # Notify the student about new vaccination record
            notify_and_email(
                recipient_id=student_id,
                sender_id=session['user_id'],
                message_type='Vaccination',
                subject='New Vaccination Record',
                message='A new vaccination record has been added for you. Please check your vaccination records in the system.',
                delivery_method='Email',
                is_read=False
            )
            # Notify the parent if student is under 18
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT age, guardian_id FROM users WHERE user_id = %s', (student_id,))
            user = cursor.fetchone()
            if user and user['age'] < 18 and user['guardian_id']:
                notify_and_email(
                    recipient_id=user['guardian_id'],
                    sender_id=session['user_id'],
                    message_type='Vaccination',
                    subject='New Vaccination Record for Your Child',
                    message='A new vaccination record has been added for your child. Please check their vaccination records in the system.',
                    delivery_method='Email',
                    is_read=False
                )
            # Notify all admins
            cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
            admin_users = cursor.fetchall()
            for admin in admin_users:
                notify_and_email(
                    recipient_id=admin[0],
                    sender_id=session['user_id'],
                    message_type='Vaccination',
                    subject='New Vaccination Record Added',
                    message=f"A new vaccination record has been added for student ID {student_id}.",
                    delivery_method='Email',
                    is_read=False
                )
            cursor.close()
            conn.close()

            flash("Vaccination record added successfully!", "success")
            return redirect(url_for('parent_view_health_records'))

        except Exception as e:
            flash(f"Error adding vaccination record: {str(e)}", "danger")

    return render_template('parent_add_vaccination.html', 
                         username=session.get('username'),
                         students=students)

@app.route('/parent_add_medical_record', methods=['GET', 'POST'])
def parent_add_medical_record():
    # Disable for parents
    flash('Parents are not allowed to add medical records. Please contact the clinic staff.', 'danger')
    return redirect(url_for('parent_view_health_records'))

@app.route('/parent_view_health_records')
def parent_view_health_records():
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get health records with student names
    cursor.execute('''SELECT hr.*, CONCAT(u.first_name, ' ', u.last_name) as student_name 
                      FROM health_records hr
                      JOIN users u ON hr.student_id = u.user_id
                      WHERE hr.student_id IN 
                          (SELECT student_ref_id FROM users WHERE guardian_id = %s)
                      ORDER BY hr.last_updated DESC''', 
                   (session['user_id'],))
    health_records = cursor.fetchall()
    
    cursor.close()
    conn.close()

    return render_template('parent_view_health_records.html', 
                         health_records=health_records,
                         username=session.get('username'))

@app.route('/parent_update_health_record/<int:record_id>', methods=['GET', 'POST'])
def parent_update_health_record(record_id):
    # Disable for parents
    flash('Parents are not allowed to update health records. Please contact the clinic staff.', 'danger')
    return redirect(url_for('parent_view_health_records'))

@app.route('/parent_update_vaccination/<int:vaccination_id>', methods=['GET', 'POST'])
def parent_update_vaccination(vaccination_id):
    # Disable for parents
    flash('Parents are not allowed to update vaccination records. Please contact the clinic staff.', 'danger')
    return redirect(url_for('parent_view_vaccinations'))

@app.route('/parent_book_appointment', methods=['GET', 'POST'])
def parent_book_appointment():
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))

    # Fetch the parent's students for the dropdown
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''SELECT user_id, first_name, last_name FROM users WHERE guardian_id = %s AND role = 'student' ORDER BY first_name''', (session['user_id'],))
    students = cursor.fetchall()
    cursor.close()
    conn.close()

    if request.method == 'POST':
        # Get form data for booking an appointment
        student_id = request.form['student_id']
        appointment_date = request.form['appointment_date']
        reason = request.form['reason']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO appointments (student_id, appointment_date, reason, booked_by)
                          VALUES (%s, %s, %s, %s)''',
                       (student_id, appointment_date, reason, session['user_id']))
        conn.commit()
        cursor.close()
        conn.close()

        # Fetch student and parent names
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT first_name, last_name, guardian_id FROM users WHERE user_id = %s', (student_id,))
        student = cursor.fetchone()
        student_name = f"{student['first_name']} {student['last_name']}" if student else ''
        parent_id = session['user_id']
        cursor.execute('SELECT first_name, last_name FROM users WHERE user_id = %s', (parent_id,))
        parent = cursor.fetchone()
        parent_name = f"{parent['first_name']} {parent['last_name']}" if parent else ''
        cursor.close()
        conn.close()

        # Notify the student (Email & In-App)
        for method in ['Email', 'In-App']:
            notify_and_email(
                recipient_id=student_id,
                sender_id=parent_id,
                message_type='Appointment',
                subject='Appointment Booked',
                message=f"Hi {student_name}, you have successfully booked an appointment. If this appointment is not cancelled, please proceed to the Medical Clinic for your consultation at the scheduled time.",
                delivery_method=method,
                is_read=False
            )
        # Notify the parent (Email & In-App)
        for method in ['Email', 'In-App']:
            notify_and_email(
                recipient_id=parent_id,
                sender_id=parent_id,
                message_type='Appointment',
                subject='Appointment Booked for Your Child',
                message=f"Hi {parent_name}, you have successfully booked an appointment for {student_name}. If this appointment is not cancelled, please ensure your child attends the clinic at the scheduled time.",
                delivery_method=method,
                is_read=False
            )

        flash("Appointment booked successfully!", "success")
        return redirect(url_for('parent_view_appointments'))

    return render_template('parent_book_appointment.html', students=students)

@app.route('/parent_view_appointments')
def parent_view_appointments():
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))

    # Fetch appointments for the parent's children, including student names
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT a.*, u.first_name, u.last_name
        FROM appointments a
        JOIN users u ON a.student_id = u.user_id
        WHERE u.guardian_id = %s
        ORDER BY a.appointment_date DESC, a.appointment_id DESC
    ''', (session['user_id'],))
    appointments = cursor.fetchall()
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()

    return render_template('parent_view_appointments.html', appointments=appointments)

@app.route('/parent_update_appointment/<int:appointment_id>', methods=['GET', 'POST'])
def parent_update_appointment(appointment_id):
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM appointments WHERE appointment_id = %s AND student_id IN (SELECT student_ref_id FROM users WHERE guardian_id = %s)", (appointment_id, session['user_id']))
    appointment = cursor.fetchone()

    if not appointment:
        flash("Appointment not found or you don't have permission to update it", "danger")
        return redirect(url_for('parent_view_appointments'))

    if request.method == 'POST':
        # Get form data for updating the appointment
        appointment_date = request.form['appointment_date']
        reason = request.form['reason']

        cursor.execute('''UPDATE appointments SET appointment_date=%s, reason=%s WHERE appointment_id=%s''',
                       (appointment_date, reason, appointment_id))
        conn.commit()
        cursor.close()
        conn.close()

        flash("Appointment updated successfully!", "success")
        return redirect(url_for('parent_view_appointments'))

    cursor.close()
    conn.close()

    return render_template('parent_update_appointment.html', appointment=appointment)

@app.route('/parent_view_notifications')
def parent_view_notifications():
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))

    # Fetch notifications for the logged-in parent
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM notifications WHERE recipient_id = %s", (session['user_id'],))
    notifications = cursor.fetchall()
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()

    return render_template('parent_view_notifications.html', notifications=notifications)


@app.route('/staff_dashboard')
def staff_dashboard():
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Ensure every appointment has a notification for this staff
    cursor.execute('SELECT appointment_id, student_id, appointment_date, appointment_time FROM appointments WHERE status != "Cancelled"')
    all_appointments = cursor.fetchall()
    for appt in all_appointments:
        # Check notification existence with a context manager
        with conn.cursor(dictionary=True) as check_cursor:
            check_cursor.execute('SELECT 1 FROM notifications WHERE recipient_id = %s AND appointment_id = %s', (session['user_id'], appt['appointment_id']))
            exists = check_cursor.fetchone()
            check_cursor.fetchall()  # Clear any remaining results
        if not exists:
            # Get student name with a context manager
            with conn.cursor(dictionary=True) as student_cursor:
                student_cursor.execute('SELECT first_name, last_name FROM users WHERE user_id = %s', (appt['student_id'],))
                student = student_cursor.fetchone()
                student_cursor.fetchall()  # Clear any remaining results
                student_name = f"{student['first_name']} {student['last_name']}"
            notify_and_email(
                recipient_id=session['user_id'],
                sender_id=session['user_id'],
                message_type='Alert',
                subject='Appointment',
                message=f"Appointment by {student_name} at {appt['appointment_date']} {appt['appointment_time']}",
                delivery_method='Email',
                is_read=False,
                appointment_id=appt['appointment_id']
            )
    conn.commit()
    # Fetch today's appointments with formatted time
    cursor.execute('''
        SELECT a.*, u.first_name, u.last_name, TIME_FORMAT(a.appointment_time, '%H:%i') as formatted_time
        FROM appointments a
        JOIN users u ON a.student_id = u.user_id
        WHERE a.appointment_date = CURDATE() AND a.status = 'Pending'
        ORDER BY a.appointment_time ASC
    ''')
    todays_appointments = cursor.fetchall()
    # Fetch unread notifications
    cursor.execute('''SELECT * FROM notifications WHERE recipient_id = %s AND is_read = FALSE ORDER BY sent_at DESC''', (session['user_id'],))
    unread_notifications = cursor.fetchall()
    cursor.fetchall()  # Clear unread results
    cursor.close()
    conn.close()
    return render_template('staff_dashboard.html', username=session['username'], todays_appointments=todays_appointments, unread_notifications=unread_notifications)

@app.route('/create_medical_record', methods=['GET', 'POST'])
def create_medical_record():
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Get form data
        student_id = request.form['student_id']
        recorded_by = session['user_id']
        height_cm = request.form['height_cm']
        weight_kg = request.form['weight_kg']
        blood_type = request.form['blood_type']
        allergies = request.form['allergies']
        medical_conditions = request.form['medical_conditions']
        current_medications = request.form['current_medications']
        immunization_status = request.form['immunization_status']
        vision_test_result = request.form['vision_test_result']
        hearing_test_result = request.form['hearing_test_result']
        general_diagnosis = request.form['general_diagnosis']
        treatment_plan = request.form['treatment_plan']
        doctor_notes = request.form['doctor_notes']
        visit_date = request.form['visit_date']
        next_follow_up = request.form['next_follow_up']

        # Insert into health_records table
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO health_records (student_id, recorded_by, height_cm, weight_kg, blood_type, allergies, 
            medical_conditions, current_medications, immunization_status, vision_test_result, hearing_test_result, 
            general_diagnosis, treatment_plan, doctor_notes, visit_date, next_follow_up, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (student_id, recorded_by, height_cm, weight_kg, blood_type, allergies, medical_conditions, current_medications,
             immunization_status, vision_test_result, hearing_test_result, general_diagnosis, treatment_plan, doctor_notes,
             visit_date, next_follow_up, 'Active')
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Notify the student about new medical record
        notify_and_email(
            recipient_id=student_id,
            sender_id=session['user_id'],
            message_type='HealthRecord',
            subject='New Medical Record',
            message='A new medical record has been created for you. Please check your health records in the system.',
            delivery_method='Email',
            is_read=False
        )
        # Notify the parent if student is under 18
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT age, guardian_id FROM users WHERE user_id = %s', (student_id,))
        user = cursor.fetchone()
        if user and user['age'] < 18 and user['guardian_id']:
            notify_and_email(
                recipient_id=user['guardian_id'],
                sender_id=session['user_id'],
                message_type='HealthRecord',
                subject='New Medical Record for Your Child',
                message='A new medical record has been created for your child. Please check their health records in the system.',
                delivery_method='Email',
                is_read=False
            )
        # Notify all admins
        cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchall()
        student_id = student_id
        for admin in admin_users:
            notify_and_email(
                recipient_id=admin['user_id'],
                sender_id=session['user_id'],
                message_type='HealthRecord',
                subject='New Medical Record Created',
                message=f'A new medical record has been created for student ID {student_id}.',
                delivery_method='Email',
                is_read=False
            )
        cursor.close()
        conn.close()

        flash("Medical record created successfully!", "success")
        return redirect(url_for('staff_dashboard'))

    # GET: Fetch students and distinct dropdown values
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_id, first_name, last_name FROM users WHERE role = 'student' AND is_active = TRUE ORDER BY first_name, last_name")
    students = cursor.fetchall()
    cursor.execute("SELECT DISTINCT medical_conditions FROM health_records WHERE medical_conditions IS NOT NULL AND medical_conditions != ''")
    medical_conditions = [row['medical_conditions'] for row in cursor.fetchall() if row['medical_conditions']]
    cursor.execute("SELECT DISTINCT current_medications FROM health_records WHERE current_medications IS NOT NULL AND current_medications != ''")
    current_medications = [row['current_medications'] for row in cursor.fetchall() if row['current_medications']]
    cursor.execute("SELECT DISTINCT immunization_status FROM health_records WHERE immunization_status IS NOT NULL AND immunization_status != ''")
    immunization_statuses = [row['immunization_status'] for row in cursor.fetchall() if row['immunization_status']]
    cursor.close()
    conn.close()
    return render_template('create_medical_record.html', students=students, medical_conditions=medical_conditions, current_medications=current_medications, immunization_statuses=immunization_statuses)


@app.route('/view_medical_records')
def view_medical_records():
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM health_records")
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('view_medical_records.html', records=records)


@app.route('/update_medical_record/<int:record_id>', methods=['GET', 'POST'])
def update_medical_record(record_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch the old record before updating
    cursor.execute("SELECT * FROM health_records WHERE record_id = %s", (record_id,))
    old_record = cursor.fetchone()

    if request.method == 'POST':
        # Update logic
        height_cm = request.form['height_cm']
        weight_kg = request.form['weight_kg']
        blood_type = request.form['blood_type']
        allergies = request.form['allergies']
        medical_conditions = request.form['medical_conditions']
        current_medications = request.form['current_medications']
        immunization_status = request.form['immunization_status']
        vision_test_result = request.form['vision_test_result']
        hearing_test_result = request.form['hearing_test_result']
        general_diagnosis = request.form['general_diagnosis']
        treatment_plan = request.form['treatment_plan']
        doctor_notes = request.form['doctor_notes']
        visit_date = request.form['visit_date']
        next_follow_up = request.form['next_follow_up']

        # Update query
        cursor.execute(
            '''UPDATE health_records SET height_cm=%s, weight_kg=%s, blood_type=%s, allergies=%s, 
            medical_conditions=%s, current_medications=%s, immunization_status=%s, vision_test_result=%s,
            hearing_test_result=%s, general_diagnosis=%s, treatment_plan=%s, doctor_notes=%s, visit_date=%s, 
            next_follow_up=%s WHERE record_id=%s''',
            (height_cm, weight_kg, blood_type, allergies, medical_conditions, current_medications, immunization_status, 
             vision_test_result, hearing_test_result, general_diagnosis, treatment_plan, doctor_notes, visit_date, 
             next_follow_up, record_id)
        )
        conn.commit()
        # Fetch the updated record for notifications
        cursor.execute("SELECT * FROM health_records WHERE record_id = %s", (record_id,))
        record = cursor.fetchone()
        student_id = record['student_id']
        staff_id = session['user_id']

        # Notify the student about updated medical record (generic)
        notify_and_email(
            recipient_id=student_id,
            sender_id=staff_id,
            message_type='HealthRecord',
            subject='Medical Record Updated',
            message='Your medical record has been updated. Please check your health records in the system.',
            delivery_method='Email',
            is_read=False
        )
        # Notify the parent if student is under 18
        cursor.execute('SELECT age, guardian_id, first_name, last_name FROM users WHERE user_id = %s', (student_id,))
        user = cursor.fetchone()
        student_name = f"{user['first_name']} {user['last_name']}" if user else 'the patient'
        if user and user['age'] < 18 and user['guardian_id']:
            notify_and_email(
                recipient_id=user['guardian_id'],
                sender_id=staff_id,
                message_type='HealthRecord',
                subject='Medical Record Updated for Your Child',
                message='Your child\'s medical record has been updated. Please check their health records in the system.',
                delivery_method='Email',
                is_read=False
            )
        # Notify all admins
        cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchall()
        for admin in admin_users:
            notify_and_email(
                recipient_id=admin['user_id'],
                sender_id=staff_id,
                message_type='HealthRecord',
                subject='Medical Record Updated',
                message=f"A medical record has been updated for student ID {student_id}.",
                delivery_method='Email',
                is_read=False
            )
        # --- New: Notify if Visit Date or Next Follow-up Date changed ---
        if old_record:
            # Visit Date
            if str(old_record.get('visit_date')) != str(visit_date) and visit_date:
                # Student
                visit_msg = f"Dear {student_name}, your Visit Date is set to {visit_date}. Please be on time for your appointment. If you have any questions, feel free to contact the clinic."
                notify_and_email(
                    recipient_id=student_id,
                    sender_id=staff_id,
                    message_type='Reminder',
                    subject='Visit Date Set',
                    message=visit_msg,
                    delivery_method='Email',
                    is_read=False
                )
                notify_and_email(
                    recipient_id=student_id,
                    sender_id=staff_id,
                    message_type='Reminder',
                    subject='Visit Date Set',
                    message=visit_msg,
                    delivery_method='In-App',
                    is_read=False
                )
                # Parent
                if user and user['age'] < 18 and user['guardian_id']:
                    parent_msg = f"Dear Parent/Guardian, your child's Visit Date is set to {visit_date}. Please ensure they arrive on time for their appointment."
                    notify_and_email(
                        recipient_id=user['guardian_id'],
                        sender_id=staff_id,
                        message_type='Reminder',
                        subject="Child's Visit Date Set",
                        message=parent_msg,
                        delivery_method='Email',
                        is_read=False
                    )
                    notify_and_email(
                        recipient_id=user['guardian_id'],
                        sender_id=staff_id,
                        message_type='Reminder',
                        subject="Child's Visit Date Set",
                        message=parent_msg,
                        delivery_method='In-App',
                        is_read=False
                    )
                # Staff/Doctor (self)
                staff_msg = f"You have set the Visit Date for {student_name} to {visit_date}. A reminder has been sent to the patient and their parent/guardian if applicable."
                notify_and_email(
                    recipient_id=staff_id,
                    sender_id=staff_id,
                    message_type='Reminder',
                    subject='Visit Date Set for Patient',
                    message=staff_msg,
                    delivery_method='In-App',
                    is_read=False
                )
            # Next Follow-up Date
            if str(old_record.get('next_follow_up')) != str(next_follow_up) and next_follow_up:
                followup_msg = f"Dear {student_name}, your Next Follow-up Date is set to {next_follow_up}. Please be on time for your follow-up appointment. If you have any questions, feel free to contact the clinic."
                notify_and_email(
                    recipient_id=student_id,
                    sender_id=staff_id,
                    message_type='Reminder',
                    subject='Next Follow-up Date Set',
                    message=followup_msg,
                    delivery_method='Email',
                    is_read=False
                )
                notify_and_email(
                    recipient_id=student_id,
                    sender_id=staff_id,
                    message_type='Reminder',
                    subject='Next Follow-up Date Set',
                    message=followup_msg,
                    delivery_method='In-App',
                    is_read=False
                )
                if user and user['age'] < 18 and user['guardian_id']:
                    parent_msg = f"Dear Parent/Guardian, your child's Next Follow-up Date is set to {next_follow_up}. Please ensure they attend as scheduled."
                    notify_and_email(
                        recipient_id=user['guardian_id'],
                        sender_id=staff_id,
                        message_type='Reminder',
                        subject="Child's Next Follow-up Date Set",
                        message=parent_msg,
                        delivery_method='Email',
                        is_read=False
                    )
                    notify_and_email(
                        recipient_id=user['guardian_id'],
                        sender_id=staff_id,
                        message_type='Reminder',
                        subject="Child's Next Follow-up Date Set",
                        message=parent_msg,
                        delivery_method='In-App',
                        is_read=False
                    )
                staff_msg = f"You have set the Next Follow-up Date for {student_name} to {next_follow_up}. A reminder has been sent to the patient and their parent/guardian if applicable."
                notify_and_email(
                    recipient_id=staff_id,
                    sender_id=staff_id,
                    message_type='Reminder',
                    subject='Next Follow-up Date Set for Patient',
                    message=staff_msg,
                    delivery_method='In-App',
                    is_read=False
                )
        cursor.close()
        conn.close()

        flash("Medical record updated successfully!", "success")
        return redirect(url_for('view_medical_records'))

    # GET: fetch record
    cursor.execute("SELECT * FROM health_records WHERE record_id = %s", (record_id,))
    record = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('update_medical_record.html', record=record)


@app.route('/delete_medical_record/<int:record_id>', methods=['GET', 'POST'])
def delete_medical_record(record_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Fetch the record before deleting to get student_id
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT student_id FROM health_records WHERE record_id = %s', (record_id,))
        record = cursor.fetchone()
        student_id = record['student_id'] if record else None
        cursor.close()
        conn.close()
        # Delete record from the database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM health_records WHERE record_id = %s", (record_id,))
        conn.commit()
        cursor.close()
        conn.close()
        # Notify the student about deleted medical record
        if student_id:
            notify_and_email(
                recipient_id=student_id,
                sender_id=session['user_id'],
                message_type='HealthRecord',
                subject='Medical Record Deleted',
                message='A medical record has been deleted from your health records in the system.',
                delivery_method='Email',
                is_read=False
            )
            # Notify the parent if student is under 18
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT age, guardian_id FROM users WHERE user_id = %s', (student_id,))
            user = cursor.fetchone()
            if user and user['age'] < 18 and user['guardian_id']:
                notify_and_email(
                    recipient_id=user['guardian_id'],
                    sender_id=session['user_id'],
                    message_type='HealthRecord',
                    subject='Medical Record Deleted for Your Child',
                    message='A medical record has been deleted from your child\'s health records in the system.',
                    delivery_method='Email',
                    is_read=False
                )
            # Notify all admins
            cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
            admin_users = cursor.fetchall()
            for admin in admin_users:
                notify_and_email(
                    recipient_id=admin['user_id'],
                    sender_id=session['user_id'],
                    message_type='HealthRecord',
                    subject='Medical Record Deleted',
                    message=f"A medical record has been deleted for student ID {student_id}.",
                    delivery_method='Email',
                    is_read=False
                )
            cursor.close()
            conn.close()

        flash("Medical record deleted successfully!", "success")
        return redirect(url_for('view_medical_records'))

    # If the request is GET, show the confirmation page
    return render_template('delete_medical_record.html', record_id=record_id)


@app.route('/view_appointments')
def view_appointments():
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM appointments')
    appointments = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('view_appointments.html', appointments=appointments)

@app.route('/mark_appointment_completed/<int:appointment_id>', methods=['POST'])
def mark_appointment_completed(appointment_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE appointments SET status='Completed' WHERE appointment_id=%s", (appointment_id,)
    )
    conn.commit()
    cursor.close()
    conn.close()

    # After marking as completed, notify the student, parent, staff, and admin
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT student_id, appointment_date, appointment_time FROM appointments WHERE appointment_id = %s', (appointment_id,))
    appt = cursor.fetchone()
    if appt:
        cursor.execute('SELECT first_name, last_name, age, guardian_id FROM users WHERE user_id = %s', (appt['student_id'],))
        student = cursor.fetchone()
        student_name = f"{student['first_name']} {student['last_name']}" if student else ''
        # Notify student
        notify_and_email(
            recipient_id=appt['student_id'],
            sender_id=session['user_id'],
            message_type='Appointment',
            subject='Appointment Completed',
            message=f"Your appointment on {appt['appointment_date']} at {appt['appointment_time']} has been marked as completed. Thank you for attending.",
            delivery_method='Email',
            is_read=False,
            appointment_id=appointment_id
        )
        # Notify parent if student is under 18 and has a guardian
        if student and student.get('age', 18) < 18 and student.get('guardian_id'):
            notify_and_email(
                recipient_id=student['guardian_id'],
                sender_id=session['user_id'],
                message_type='Appointment',
                subject="Your Child's Appointment Completed",
                message=f"The appointment for your child {student_name} on {appt['appointment_date']} at {appt['appointment_time']} has been marked as completed.",
                delivery_method='Email',
                is_read=False,
                appointment_id=appointment_id
            )
        cursor.execute("SELECT user_id FROM users WHERE role = 'staff'")
        staff_users = cursor.fetchall()
        cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchall()
        cursor.close()
        conn.close()
        for staff in staff_users:
            notify_and_email(
                recipient_id=staff['user_id'],
                sender_id=session['user_id'],
                message_type='Appointment',
                subject='Appointment Completed',
                message=f"The appointment for {student_name} on {appt['appointment_date']} at {appt['appointment_time']} has been marked as completed.",
                delivery_method='Email',
                is_read=False,
                appointment_id=appointment_id
            )
        for admin in admin_users:
            notify_and_email(
                recipient_id=admin['user_id'],
                sender_id=session['user_id'],
                message_type='Appointment',
                subject='Appointment Completed',
                message=f"The appointment for {student_name} on {appt['appointment_date']} at {appt['appointment_time']} has been marked as completed.",
                delivery_method='Email',
                is_read=False,
                appointment_id=appointment_id
            )
    flash("Appointment marked as completed!", "success")
    return redirect(url_for('view_appointments'))

@app.route('/reschedule_appointment/<int:appointment_id>', methods=['GET', 'POST'])
def reschedule_appointment(appointment_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM appointments WHERE appointment_id = %s', (appointment_id,))
    appointment = cursor.fetchone()
    if not appointment:
        cursor.close()
        conn.close()
        flash('Appointment not found.', 'danger')
        return redirect(url_for('view_appointments'))

    # Fetch student info
    student_name = ''
    profile_photo = ''
    if appointment.get('student_id'):
        cursor.execute('SELECT first_name, last_name, profile_photo FROM users WHERE user_id = %s', (appointment['student_id'],))
        student = cursor.fetchone()
        if student:
            student_name = f"{student['first_name']} {student['last_name']}"
            profile_photo = student['profile_photo']

    # For GET: pass current date/time to template (format time as 12-hour AM/PM)
    if request.method == 'GET':
        appointment_date = appointment['appointment_date']
        try:
            appt_time_obj = datetime.datetime.strptime(str(appointment['appointment_time']), '%H:%M:%S')
            appointment_time = appt_time_obj.strftime('%I:%M %p')
        except Exception:
            appointment_time = str(appointment['appointment_time'])
        cursor.close()
        conn.close()
        return render_template('reschedule_appointment.html', appointment_id=appointment_id, appointment_date=appointment_date, appointment_time=appointment_time, student_name=student_name, profile_photo=profile_photo)

    # For POST: update and notify
    new_date = request.form['appointment_date']
    new_time = request.form['appointment_time']
    cursor.execute(
        "UPDATE appointments SET appointment_date=%s, appointment_time=%s, status='Pending' WHERE appointment_id=%s",
        (new_date, new_time, appointment_id)
    )
    conn.commit()
    # Fetch student info again for notifications
    cursor.execute('SELECT student_id FROM appointments WHERE appointment_id = %s', (appointment_id,))
    appt = cursor.fetchone()
    student_id = appt['student_id'] if appt else None
    student_name = ''
    if student_id:
        cursor.execute('SELECT first_name, last_name FROM users WHERE user_id = %s', (student_id,))
        student = cursor.fetchone()
        student_name = f"{student['first_name']} {student['last_name']}" if student else ''
    # Notify student
    if student_id:
        notify_and_email(
            recipient_id=student_id,
            sender_id=session['user_id'],
            message_type='Appointment',
            subject='Appointment Rescheduled',
            message=f"Your appointment has been rescheduled to {new_date} at {new_time}.",
            delivery_method='Email',
            is_read=False,
            appointment_id=appointment_id
        )
    # Notify all staff
    cursor.execute("SELECT user_id FROM users WHERE role = 'staff'")
    staff_users = cursor.fetchall()
    for staff in staff_users:
        notify_and_email(
            recipient_id=staff['user_id'],
            sender_id=session['user_id'],
            message_type='Appointment',
            subject='Appointment Rescheduled',
            message=f"The appointment for {student_name} has been rescheduled to {new_date} at {new_time}. Please review and take action as needed. Status: Pending.",
            delivery_method='Email',
            is_read=False,
            appointment_id=appointment_id
        )
    # Notify all admins
    cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
    admin_users = cursor.fetchall()
    for admin in admin_users:
        notify_and_email(
            recipient_id=admin['user_id'],
            sender_id=session['user_id'],
            message_type='Appointment',
            subject='Appointment Rescheduled',
            message=f"The appointment for {student_name} has been rescheduled to {new_date} at {new_time}. Please review and take action as needed. Status: Pending.",
            delivery_method='Email',
            is_read=False,
            appointment_id=appointment_id
        )
    cursor.close()
    conn.close()
    flash("Appointment rescheduled successfully!", "success")
    return redirect(url_for('view_appointments'))

@app.route('/cancel_appointment/<int:appointment_id>', methods=['POST'])
def cancel_appointment(appointment_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE appointments SET status='Cancelled' WHERE appointment_id=%s", (appointment_id,))
    conn.commit()
    cursor.close()
    conn.close()

    # After cancelling, notify the student, parent, staff, and admin
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT student_id, appointment_date, appointment_time FROM appointments WHERE appointment_id = %s', (appointment_id,))
    appt = cursor.fetchone()
    if appt:
        cursor.execute('SELECT first_name, last_name, age, guardian_id FROM users WHERE user_id = %s', (appt['student_id'],))
        student = cursor.fetchone()
        student_name = f"{student['first_name']} {student['last_name']}" if student else ''
        # Notify student
        notify_and_email(
            recipient_id=appt['student_id'],
            sender_id=session['user_id'],
            message_type='Appointment',
            subject='Appointment Cancelled',
            message=f"Your appointment on {appt['appointment_date']} at {appt['appointment_time']} has been cancelled. Please contact the clinic if you have questions.",
            delivery_method='Email',
            is_read=False,
            appointment_id=appointment_id
        )
        # Notify parent if student is under 18 and has a guardian
        if student and student.get('age', 18) < 18 and student.get('guardian_id'):
            notify_and_email(
                recipient_id=student['guardian_id'],
                sender_id=session['user_id'],
                message_type='Appointment',
                subject="Your Child's Appointment Cancelled",
                message=f"The appointment for your child {student_name} on {appt['appointment_date']} at {appt['appointment_time']} has been cancelled.",
                delivery_method='Email',
                is_read=False,
                appointment_id=appointment_id
            )
        cursor.execute("SELECT user_id FROM users WHERE role = 'staff'")
        staff_users = cursor.fetchall()
        cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchall()
        cursor.close()
        conn.close()
        for staff in staff_users:
            notify_and_email(
                recipient_id=staff['user_id'],
                sender_id=session['user_id'],
                message_type='Appointment',
                subject='Appointment Cancelled',
                message=f"The appointment for {student_name} on {appt['appointment_date']} at {appt['appointment_time']} has been cancelled. No further action is required.",
                delivery_method='Email',
                is_read=False,
                appointment_id=appointment_id
            )
        for admin in admin_users:
            notify_and_email(
                recipient_id=admin['user_id'],
                sender_id=session['user_id'],
                message_type='Appointment',
                subject='Appointment Cancelled',
                message=f"The appointment for {student_name} on {appt['appointment_date']} at {appt['appointment_time']} has been cancelled. No further action is required.",
                delivery_method='Email',
                is_read=False,
                appointment_id=appointment_id
            )
    flash("Appointment cancelled successfully!", "success")
    return redirect(url_for('view_appointments'))


@app.route('/create_vaccination_log', methods=['GET', 'POST'])
def create_vaccination_log():
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    # Fetch all active students for the dropdown
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_id, first_name, last_name FROM users WHERE role = 'student' AND is_active = TRUE ORDER BY first_name, last_name")
    students = cursor.fetchall()
    cursor.close()
    conn.close()

    if request.method == 'POST':
        # Get form data
        student_id = request.form['student_id']
        vaccine_name = request.form['vaccine_name']
        vaccine_type = request.form['vaccine_type']
        manufacturer = request.form['manufacturer']
        batch_number = request.form['batch_number']
        dose_number = request.form['dose_number']
        total_doses = request.form['total_doses']
        date_administered = request.form['date_administered']
        next_due_date = request.form['next_due_date']
        administered_by = session['user_id']
        site_of_injection = request.form['site_of_injection']
        side_effects = request.form['side_effects']
        status = 'Completed'

        # Insert into vaccinations table
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO vaccinations (student_id, vaccine_name, vaccine_type, manufacturer, batch_number, 
            dose_number, total_doses, date_administered, next_due_date, administered_by, site_of_injection, 
            side_effects, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (student_id, vaccine_name, vaccine_type, manufacturer, batch_number, dose_number, total_doses,
             date_administered, next_due_date, administered_by, site_of_injection, side_effects, status)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Notify the student about new vaccination record (Email & In-App)
        for method in ['Email', 'In-App']:
            notify_and_email(
                recipient_id=student_id,
                sender_id=session['user_id'],
                message_type='Vaccination',
                subject='New Vaccination Record',
                message='A new vaccination record has been added for you. Please check your vaccination records in the system.',
                delivery_method=method,
                is_read=False
            )
        # Notify the parent if student is under 18 (Email & In-App)
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT age, guardian_id FROM users WHERE user_id = %s', (student_id,))
        user = cursor.fetchone()
        if user and user['age'] < 18 and user['guardian_id']:
            for method in ['Email', 'In-App']:
                notify_and_email(
                    recipient_id=user['guardian_id'],
                    sender_id=session['user_id'],
                    message_type='Vaccination',
                    subject='New Vaccination Record for Your Child',
                    message='A new vaccination record has been added for your child. Please check their vaccination records in the system.',
                    delivery_method=method,
                    is_read=False
                )
        # Notify all admins (Email & In-App)
        cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchall()
        for admin in admin_users:
            for method in ['Email', 'In-App']:
                notify_and_email(
                    recipient_id=admin['user_id'] if isinstance(admin, dict) else admin[0],
                    sender_id=session['user_id'],
                    message_type='Vaccination',
                    subject='New Vaccination Record Added',
                    message=f"A new vaccination record has been added for student ID {student_id}.",
                    delivery_method=method,
                    is_read=False
                )
        cursor.close()
        conn.close()

        flash("Vaccination log created successfully!", "success")
        return redirect(url_for('staff_dashboard'))

    return render_template('create_vaccination_log.html', students=students)

@app.route('/view_vaccination_data')
def view_vaccination_data():
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT v.*, u.first_name, u.last_name, u.role as student_role
        FROM vaccinations v
        LEFT JOIN users u ON v.student_id = u.user_id
    """)
    vaccinations = cursor.fetchall()
    for v in vaccinations:
        if v.get('first_name') and v.get('last_name'):
            v['student_name'] = f"{v['first_name']} {v['last_name']}"
            v['student_role'] = v.get('student_role', '')
        else:
            v['student_name'] = 'Unknown'
            v['student_role'] = 'Unknown'
    cursor.close()
    conn.close()

    return render_template('view_vaccination_data.html', vaccinations=vaccinations)

@app.route('/edit_vaccination_data/<int:vaccination_id>', methods=['GET', 'POST'])
def edit_vaccination_data(vaccination_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Get form data to update the vaccination record
        vaccine_name = request.form['vaccine_name']
        vaccine_type = request.form['vaccine_type']
        manufacturer = request.form['manufacturer']
        batch_number = request.form['batch_number']
        dose_number = request.form['dose_number']
        total_doses = request.form['total_doses']
        date_administered = request.form['date_administered']
        next_due_date = request.form['next_due_date']
        site_of_injection = request.form['site_of_injection']
        side_effects = request.form['side_effects']

        # Update vaccination record
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''UPDATE vaccinations SET vaccine_name=%s, vaccine_type=%s, manufacturer=%s, batch_number=%s,
            dose_number=%s, total_doses=%s, date_administered=%s, next_due_date=%s, site_of_injection=%s, 
            side_effects=%s WHERE vaccination_id=%s''',
            (vaccine_name, vaccine_type, manufacturer, batch_number, dose_number, total_doses,
             date_administered, next_due_date, site_of_injection, side_effects, vaccination_id)
        )
        conn.commit()
        cursor.close()
        conn.close()

        flash("Vaccination data updated successfully!", "success")
        return redirect(url_for('view_vaccination_data'))

    # Fetch the vaccination data for the given ID
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM vaccinations WHERE vaccination_id=%s", (vaccination_id,))
    vaccination = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('edit_vaccination_data.html', vaccination=vaccination)

@app.route('/delete_vaccination_data/<int:vaccination_id>', methods=['POST'])
def delete_vaccination_data(vaccination_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    # Fetch the vaccination record before deleting to get student_id
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT student_id FROM vaccinations WHERE vaccination_id = %s', (vaccination_id,))
    record = cursor.fetchone()
    student_id = record['student_id'] if record else None
    cursor.close()
    conn.close()
    # Delete record from the database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vaccinations WHERE vaccination_id = %s", (vaccination_id,))
    conn.commit()
    cursor.close()
    conn.close()
    # Notify the student about deleted vaccination record
    if student_id:
        notify_and_email(
            recipient_id=student_id,
            sender_id=session['user_id'],
            message_type='Vaccination',
            subject='Vaccination Record Deleted',
            message='A vaccination record has been deleted from your vaccination records in the system.',
            delivery_method='Email',
            is_read=False
        )
        # Notify the parent if student is under 18
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT age, guardian_id FROM users WHERE user_id = %s', (student_id,))
        user = cursor.fetchone()
        if user and user['age'] < 18 and user['guardian_id']:
            notify_and_email(
                recipient_id=user['guardian_id'],
                sender_id=session['user_id'],
                message_type='Vaccination',
                subject='Vaccination Record Deleted for Your Child',
                message='A vaccination record has been deleted from your child\'s vaccination records in the system.',
                delivery_method='Email',
                is_read=False
            )
        # Notify all admins
        cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchall()
        for admin in admin_users:
            notify_and_email(
                recipient_id=admin[0],
                sender_id=session['user_id'],
                message_type='Vaccination',
                subject='Vaccination Record Deleted',
                message=f"A vaccination record has been deleted for student ID {student_id}.",
                delivery_method='Email',
                is_read=False
            )
        cursor.close()
        conn.close()

    flash("Vaccination data deleted successfully!", "success")
    return redirect(url_for('view_vaccination_data'))


@app.route('/send_health_alert', methods=['GET', 'POST'])
def send_health_alert():
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    if request.method == 'POST':
        recipient_id = request.form['recipient_id']
        subject = request.form['subject']
        message = request.form['message']
        delivery_method = request.form['delivery_method']
        sender_id = session['user_id']
        message_type = 'Alert'

        # Ensure subject starts with 'Academy Medical Clinic: '
        subject_prefix = 'Academy Medical Clinic: '
        if not subject.startswith(subject_prefix):
            subject = subject_prefix + subject

        # Always send in-app notification
        notify_and_email(
            recipient_id=recipient_id,
            sender_id=sender_id,
            message_type=message_type,
            subject=subject,
            message=message,
            delivery_method='In-App',
            is_read=False
        )
        # If Email is selected, also send email
        if delivery_method == 'Email':
            notify_and_email(
                recipient_id=recipient_id,
                sender_id=sender_id,
                message_type=message_type,
                subject=subject,
                message=message,
                delivery_method='Email',
                is_read=False
            )
        flash("Health alert sent successfully!", "success")
        return redirect(url_for('staff_dashboard'))

    # GET: Build recipients list (students and parents)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_id, first_name, last_name, role FROM users WHERE role IN ('student', 'parent') AND is_active = TRUE ORDER BY role, first_name, last_name")
    recipients = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('send_health_alert.html', recipients=recipients)

@app.route('/view_sent_alerts')
def view_sent_alerts():
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT n.*, u.first_name, u.last_name, u.role as recipient_role
        FROM notifications n
        LEFT JOIN users u ON n.recipient_id = u.user_id
        WHERE n.sender_id = %s
        ORDER BY n.sent_at DESC
    """, (session['user_id'],))
    alerts = cursor.fetchall()
    # Add recipient_name and recipient_role for template
    for alert in alerts:
        if alert.get('first_name') and alert.get('last_name'):
            alert['recipient_name'] = f"{alert['first_name']} {alert['last_name']}"
            alert['recipient_role'] = alert.get('recipient_role', '')
        else:
            alert['recipient_name'] = 'Unknown'
            alert['recipient_role'] = 'Unknown'
    cursor.close()
    conn.close()

    return render_template('view_sent_alerts.html', alerts=alerts)

@app.route('/edit_health_alert/<int:notification_id>', methods=['GET', 'POST'])
def edit_health_alert(notification_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Get updated health alert data
        subject = request.form['subject']
        message = request.form['message']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''UPDATE notifications SET subject=%s, message=%s WHERE notification_id=%s''',
            (subject, message, notification_id)
        )
        conn.commit()
        cursor.close()
        conn.close()

        flash("Health alert updated successfully!", "success")
        return redirect(url_for('view_sent_alerts'))

    # Fetch the alert details for editing
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM notifications WHERE notification_id = %s", (notification_id,))
    alert = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('edit_health_alert.html', alert=alert)


@app.route('/delete_health_alert/<int:notification_id>', methods=['POST'])
def delete_health_alert(notification_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notifications WHERE notification_id = %s", (notification_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Health alert deleted successfully!", "success")
    return redirect(url_for('view_sent_alerts'))

@app.route('/mark_notification_read/<int:notification_id>', methods=['POST'])
def mark_notification_read(notification_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE notifications SET is_read = TRUE WHERE notification_id = %s AND recipient_id = %s', (notification_id, session['user_id']))
    conn.commit()
    cursor.close()
    conn.close()
    return ('', 204)

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('index'))

@app.route('/admin_view_notifications')
def admin_view_notifications():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM notifications WHERE recipient_id = %s ORDER BY sent_at DESC', (session['user_id'],))
    notifications = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_view_notifications.html', notifications=notifications)

def send_visit_and_followup_reminders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    # Visit Date reminders for tomorrow (already implemented)
    cursor.execute("SELECT * FROM health_records WHERE visit_date = %s AND status = 'Active'", (tomorrow,))
    visit_records = cursor.fetchall()
    for record in visit_records:
        student_id = record['student_id']
        recorded_by = record.get('recorded_by')
        cursor.execute('SELECT first_name, last_name, age, guardian_id FROM users WHERE user_id = %s', (student_id,))
        student = cursor.fetchone()
        student_name = f"{student['first_name']} {student['last_name']}" if student else 'the patient'
        message = f"Dear {student_name}, this is a friendly reminder of your scheduled clinic visit on {tomorrow}. Please arrive on time and bring any necessary documents. If you have questions, contact the clinic."
        notify_and_email(
            recipient_id=student_id,
            sender_id=recorded_by,
            message_type='Reminder',
            subject='Clinic Visit Reminder',
            message=message,
            delivery_method='Email',
            is_read=False
        )
        notify_and_email(
            recipient_id=student_id,
            sender_id=recorded_by,
            message_type='Reminder',
            subject='Clinic Visit Reminder',
            message=message,
            delivery_method='In-App',
            is_read=False
        )
        if student and student['age'] < 18 and student['guardian_id']:
            parent_message = f"Dear Parent/Guardian, this is a reminder that your child {student_name} has a scheduled clinic visit on {tomorrow}. Please ensure they are prepared and arrive on time."
            notify_and_email(
                recipient_id=student['guardian_id'],
                sender_id=recorded_by,
                message_type='Reminder',
                subject="Child's Clinic Visit Reminder",
                message=parent_message,
                delivery_method='Email',
                is_read=False
            )
            notify_and_email(
                recipient_id=student['guardian_id'],
                sender_id=recorded_by,
                message_type='Reminder',
                subject="Child's Clinic Visit Reminder",
                message=parent_message,
                delivery_method='In-App',
                is_read=False
            )
        # Staff/Doctor
        if recorded_by:
            staff_msg = f"Reminder: The Visit Date for {student_name} is scheduled for {tomorrow}."
            notify_and_email(
                recipient_id=recorded_by,
                sender_id=None,
                message_type='Reminder',
                subject='Patient Visit Date Reminder',
                message=staff_msg,
                delivery_method='In-App',
                is_read=False
            )
    # Next Follow-up reminders for tomorrow (already implemented)
    cursor.execute("SELECT * FROM health_records WHERE next_follow_up = %s AND status = 'Active'", (tomorrow,))
    followup_records = cursor.fetchall()
    for record in followup_records:
        student_id = record['student_id']
        recorded_by = record.get('recorded_by')
        cursor.execute('SELECT first_name, last_name, age, guardian_id FROM users WHERE user_id = %s', (student_id,))
        student = cursor.fetchone()
        student_name = f"{student['first_name']} {student['last_name']}" if student else 'the patient'
        message = f"Dear {student_name}, this is a reminder of your upcoming follow-up appointment scheduled for {tomorrow}. Please attend as advised by your healthcare provider."
        notify_and_email(
            recipient_id=student_id,
            sender_id=recorded_by,
            message_type='Reminder',
            subject='Follow-up Appointment Reminder',
            message=message,
            delivery_method='Email',
            is_read=False
        )
        notify_and_email(
            recipient_id=student_id,
            sender_id=recorded_by,
            message_type='Reminder',
            subject='Follow-up Appointment Reminder',
            message=message,
            delivery_method='In-App',
            is_read=False
        )
        if student and student['age'] < 18 and student['guardian_id']:
            parent_message = f"Dear Parent/Guardian, this is a reminder that your child {student_name} has a follow-up appointment scheduled for {tomorrow}. Please ensure they attend as advised."
            notify_and_email(
                recipient_id=student['guardian_id'],
                sender_id=recorded_by,
                message_type='Reminder',
                subject="Child's Follow-up Appointment Reminder",
                message=parent_message,
                delivery_method='Email',
                is_read=False
            )
            notify_and_email(
                recipient_id=student['guardian_id'],
                sender_id=recorded_by,
                message_type='Reminder',
                subject="Child's Follow-up Appointment Reminder",
                message=parent_message,
                delivery_method='In-App',
                is_read=False
            )
        # Staff/Doctor
        if recorded_by:
            staff_msg = f"Reminder: The Next Follow-up Date for {student_name} is scheduled for {tomorrow}."
            notify_and_email(
                recipient_id=recorded_by,
                sender_id=None,
                message_type='Reminder',
                subject='Patient Follow-up Date Reminder',
                message=staff_msg,
                delivery_method='In-App',
                is_read=False
            )
    # --- New: Today is your Visit Date/Follow-up Date ---
    # Visit Date today
    cursor.execute("SELECT * FROM health_records WHERE visit_date = %s AND status = 'Active'", (today,))
    today_visit_records = cursor.fetchall()
    for record in today_visit_records:
        student_id = record['student_id']
        recorded_by = record.get('recorded_by')
        cursor.execute('SELECT first_name, last_name, age, guardian_id FROM users WHERE user_id = %s', (student_id,))
        student = cursor.fetchone()
        student_name = f"{student['first_name']} {student['last_name']}" if student else 'the patient'
        message = f"Dear {student_name}, today is your Visit Date ({today}). Please be on time for your appointment."
        notify_and_email(
            recipient_id=student_id,
            sender_id=recorded_by,
            message_type='Reminder',
            subject='Today is Your Visit Date',
            message=message,
            delivery_method='Email',
            is_read=False
        )
        notify_and_email(
            recipient_id=student_id,
            sender_id=recorded_by,
            message_type='Reminder',
            subject='Today is Your Visit Date',
            message=message,
            delivery_method='In-App',
            is_read=False
        )
        if student and student['age'] < 18 and student['guardian_id']:
            parent_message = f"Dear Parent/Guardian, today is your child's Visit Date ({today}). Please ensure they arrive on time for their appointment."
            notify_and_email(
                recipient_id=student['guardian_id'],
                sender_id=recorded_by,
                message_type='Reminder',
                subject="Today is Your Child's Visit Date",
                message=parent_message,
                delivery_method='Email',
                is_read=False
            )
            notify_and_email(
                recipient_id=student['guardian_id'],
                sender_id=recorded_by,
                message_type='Reminder',
                subject="Today is Your Child's Visit Date",
                message=parent_message,
                delivery_method='In-App',
                is_read=False
            )
        if recorded_by:
            staff_msg = f"Today is the Visit Date for {student_name} ({today})."
            notify_and_email(
                recipient_id=recorded_by,
                sender_id=None,
                message_type='Reminder',
                subject='Today is Patient Visit Date',
                message=staff_msg,
                delivery_method='In-App',
                is_read=False
            )
    # Next Follow-up Date today
    cursor.execute("SELECT * FROM health_records WHERE next_follow_up = %s AND status = 'Active'", (today,))
    today_followup_records = cursor.fetchall()
    for record in today_followup_records:
        student_id = record['student_id']
        recorded_by = record.get('recorded_by')
        cursor.execute('SELECT first_name, last_name, age, guardian_id FROM users WHERE user_id = %s', (student_id,))
        student = cursor.fetchone()
        student_name = f"{student['first_name']} {student['last_name']}" if student else 'the patient'
        message = f"Dear {student_name}, today is your Next Follow-up Date ({today}). Please be on time for your follow-up appointment."
        notify_and_email(
            recipient_id=student_id,
            sender_id=recorded_by,
            message_type='Reminder',
            subject='Today is Your Next Follow-up Date',
            message=message,
            delivery_method='Email',
            is_read=False
        )
        notify_and_email(
            recipient_id=student_id,
            sender_id=recorded_by,
            message_type='Reminder',
            subject='Today is Your Next Follow-up Date',
            message=message,
            delivery_method='In-App',
            is_read=False
        )
        if student and student['age'] < 18 and student['guardian_id']:
            parent_message = f"Dear Parent/Guardian, today is your child's Next Follow-up Date ({today}). Please ensure they attend as scheduled."
            notify_and_email(
                recipient_id=student['guardian_id'],
                sender_id=recorded_by,
                message_type='Reminder',
                subject="Today is Your Child's Next Follow-up Date",
                message=parent_message,
                delivery_method='Email',
                is_read=False
            )
            notify_and_email(
                recipient_id=student['guardian_id'],
                sender_id=recorded_by,
                message_type='Reminder',
                subject="Today is Your Child's Next Follow-up Date",
                message=parent_message,
                delivery_method='In-App',
                is_read=False
            )
        if recorded_by:
            staff_msg = f"Today is the Next Follow-up Date for {student_name} ({today})."
            notify_and_email(
                recipient_id=recorded_by,
                sender_id=None,
                message_type='Reminder',
                subject='Today is Patient Next Follow-up Date',
                message=staff_msg,
                delivery_method='In-App',
                is_read=False
            )
    cursor.close()
    conn.close()

# Start the scheduler when the app starts
scheduler = BackgroundScheduler()
scheduler.add_job(send_visit_and_followup_reminders, 'cron', hour=7, minute=0)  # Runs every day at 7:00 AM
scheduler.start()

@app.route('/student_view_vaccinations')
def student_view_vaccinations():
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM vaccinations WHERE student_id = %s ORDER BY date_administered DESC', (session['user_id'],))
    vaccinations = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('student_view_vaccinations.html', vaccinations=vaccinations)

@app.route('/parent_view_vaccinations')
def parent_view_vaccinations():
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''SELECT v.*, u.first_name, u.last_name FROM vaccinations v JOIN users u ON v.student_id = u.user_id WHERE v.student_id IN (SELECT user_id FROM users WHERE guardian_id = %s) ORDER BY v.date_administered DESC''', (session['user_id'],))
    vaccinations = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('parent_view_vaccinations.html', vaccinations=vaccinations)

@app.route('/update_vaccination_log/<int:vaccination_id>', methods=['GET', 'POST'])
def update_vaccination_log(vaccination_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM vaccinations WHERE vaccination_id = %s', (vaccination_id,))
    vaccination = cursor.fetchone()
    cursor.execute("SELECT user_id, first_name, last_name FROM users WHERE role = 'student' AND is_active = TRUE ORDER BY first_name, last_name")
    students = cursor.fetchall()
    if request.method == 'POST':
        student_id = request.form['student_id']
        vaccine_name = request.form['vaccine_name']
        vaccine_type = request.form['vaccine_type']
        manufacturer = request.form['manufacturer']
        batch_number = request.form['batch_number']
        dose_number = request.form['dose_number']
        total_doses = request.form['total_doses']
        date_administered = request.form['date_administered']
        next_due_date = request.form['next_due_date']
        site_of_injection = request.form['site_of_injection']
        side_effects = request.form['side_effects']
        status = request.form.get('status', 'Completed')
        cursor.execute('''UPDATE vaccinations SET student_id=%s, vaccine_name=%s, vaccine_type=%s, manufacturer=%s, batch_number=%s, dose_number=%s, total_doses=%s, date_administered=%s, next_due_date=%s, site_of_injection=%s, side_effects=%s, status=%s WHERE vaccination_id=%s''',
            (student_id, vaccine_name, vaccine_type, manufacturer, batch_number, dose_number, total_doses, date_administered, next_due_date, site_of_injection, side_effects, status, vaccination_id))
        conn.commit()
        # Notify student, parent (if under 18), and all admins (Email & In-App)
        for method in ['Email', 'In-App']:
            notify_and_email(
                recipient_id=student_id,
                sender_id=session['user_id'],
                message_type='Vaccination',
                subject='Vaccination Record Updated',
                message='A vaccination record has been updated for you. Please check your vaccination records in the system.',
                delivery_method=method,
                is_read=False
            )
        cursor.execute('SELECT age, guardian_id FROM users WHERE user_id = %s', (student_id,))
        user = cursor.fetchone()
        if user and user['age'] < 18 and user['guardian_id']:
            for method in ['Email', 'In-App']:
                notify_and_email(
                    recipient_id=user['guardian_id'],
                    sender_id=session['user_id'],
                    message_type='Vaccination',
                    subject='Vaccination Record Updated for Your Child',
                    message='A vaccination record has been updated for your child. Please check their vaccination records in the system.',
                    delivery_method=method,
                    is_read=False
                )
        cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchall()
        for admin in admin_users:
            for method in ['Email', 'In-App']:
                notify_and_email(
                    recipient_id=admin['user_id'] if isinstance(admin, dict) else admin[0],
                    sender_id=session['user_id'],
                    message_type='Vaccination',
                    subject='Vaccination Record Updated',
                    message=f"A vaccination record has been updated for student ID {student_id}.",
                    delivery_method=method,
                    is_read=False
                )
        cursor.close()
        conn.close()
        flash("Vaccination log updated successfully!", "success")
        return redirect(url_for('view_vaccination_data'))
    cursor.close()
    conn.close()
    return render_template('update_vaccination_log.html', vaccination=vaccination, students=students)

@app.route('/delete_vaccination_log/<int:vaccination_id>', methods=['GET', 'POST'])
def delete_vaccination_log(vaccination_id):
    if 'role' not in session or session['role'] != 'staff':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM vaccinations WHERE vaccination_id = %s', (vaccination_id,))
    vaccination = cursor.fetchone()
    if request.method == 'POST':
        student_id = vaccination['student_id']
        cursor.execute('DELETE FROM vaccinations WHERE vaccination_id = %s', (vaccination_id,))
        conn.commit()
        # Notify student, parent (if under 18), and all admins (Email & In-App)
        for method in ['Email', 'In-App']:
            notify_and_email(
                recipient_id=student_id,
                sender_id=session['user_id'],
                message_type='Vaccination',
                subject='Vaccination Record Deleted',
                message='A vaccination record has been deleted from your vaccination records in the system.',
                delivery_method=method,
                is_read=False
            )
        cursor.execute('SELECT age, guardian_id FROM users WHERE user_id = %s', (student_id,))
        user = cursor.fetchone()
        if user and user['age'] < 18 and user['guardian_id']:
            for method in ['Email', 'In-App']:
                notify_and_email(
                    recipient_id=user['guardian_id'],
                    sender_id=session['user_id'],
                    message_type='Vaccination',
                    subject='Vaccination Record Deleted for Your Child',
                    message='A vaccination record has been deleted from your child\'s vaccination records in the system.',
                    delivery_method=method,
                    is_read=False
                )
        cursor.execute("SELECT user_id FROM users WHERE role = 'admin'")
        admin_users = cursor.fetchall()
        for admin in admin_users:
            for method in ['Email', 'In-App']:
                notify_and_email(
                    recipient_id=admin['user_id'] if isinstance(admin, dict) else admin[0],
                    sender_id=session['user_id'],
                    message_type='Vaccination',
                    subject='Vaccination Record Deleted',
                    message=f"A vaccination record has been deleted for student ID {student_id}.",
                    delivery_method=method,
                    is_read=False
                )
        cursor.close()
        conn.close()
        flash("Vaccination log deleted successfully!", "success")
        return redirect(url_for('view_vaccination_data'))
    cursor.close()
    conn.close()
    return render_template('delete_vaccination_log.html', vaccination=vaccination)

@app.route('/student_view_reminders')
def student_view_reminders():
    if 'role' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''SELECT * FROM notifications WHERE recipient_id = %s AND message_type = 'Reminder' ORDER BY is_read ASC, sent_at DESC''', (session['user_id'],))
    reminders = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('student_view_reminders.html', reminders=reminders)

@app.route('/student_ai_chat', methods=['POST'])
def student_ai_chat():
    import re
    data = request.get_json()
    user_message = data.get('message', '').strip()

    # Try OpenAI GPT-4o first
    if openai_available:
        try:
            client = OpenAI(api_key="Change Your Own API KEY IN HERE!!!!!!!!!!")
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": (
                        "You are a professional, friendly, and empathetic virtual doctor for a school clinic. "
                        "Give clear, concise, and medically sound advice. If the user's question is urgent or life-threatening, "
                        "tell them to seek emergency care immediately. If the user is under 16, remind them to involve a parent for appointments."
                    )},
                    {"role": "user", "content": user_message}
                ]
            )
            ai_response = completion.choices[0].message.content.strip()
            return jsonify({'response': ai_response})
        except Exception as e:
            pass  # Fallback to programmed responses below

    # --- Existing programmed responses below (regex/intent matching) ---
    user_message_lower = user_message.lower()
    responses = [
        # --- Concern, complexity, and emergency prompts ---
        (r'(i have a concern|i am concerned|i\'m worried|i feel unwell|i don\'t feel well|i have a problem|i\'m not sure what\'s wrong)',
         "Thank you for sharing your concern. Can you describe your symptoms in more detail? When did they start, and have they changed over time? I'm here to help you understand your health and guide you on what to do next."),
        (r'(multiple symptoms|many symptoms|symptoms getting worse|worse|not improving)',
         "If your symptoms are getting worse or not improving, it's important to seek medical attention. Can you list all the symptoms you're experiencing? If you feel very unwell, please visit the clinic or emergency room."),
        (r'(family history|my family has|worried about.*disease|risk of.*disease)',
         "Family history can increase your risk for certain conditions. If you're worried about a specific disease, let me know which one, and I can provide information or recommend screening options."),
        (r'(chronic condition|rare disease|long-term illness|lifelong condition)',
         "Managing a chronic or rare condition can be challenging. It's important to follow your treatment plan and keep regular appointments with your healthcare provider. If you have specific questions, I'm here to help."),
        (r'(is this normal|should i be worried|what should i do|do i need to see a doctor)',
         "Some symptoms can be normal, but others may need medical attention. Can you tell me more about what you're experiencing? If you're unsure, it's always safest to consult a healthcare professional."),
        (r'(urgent|emergency|help now|can\'t breathe|chest pain|severe pain|fainting|unconscious)',
         "If you are experiencing severe symptoms such as difficulty breathing, chest pain, severe pain, fainting, or loss of consciousness, please seek emergency medical care immediately or call emergency services."),
        # --- Conversational/Doctor-style prompts ---
        (r'(hi|hello|good morning|good afternoon|good evening)', "Hello! I'm your virtual clinic assistant. How can I help you with your health today?"),
        (r'(worried|scared|afraid|nervous)', "It's normal to feel that way. If you're worried about your health, I'm here to help. Can you tell me more about your symptoms or concerns?"),
        (r'(thank you|salamat|thanks)', "You're very welcome! If you have any more questions or need support, just let me know."),
        (r'(pain|hurt|ache)', "I'm sorry to hear you're in pain. Can you describe where it hurts and how severe it is? This will help me guide you better."),
        (r'(medicine|medication|drug)', "Are you currently taking any medications? If so, please let me know which ones, so I can provide more tailored advice."),
        (r'(is it serious|should i worry|dangerous)', "I understand your concern. Some symptoms can be mild, but others may need prompt attention. If you feel very unwell, or if your symptoms are severe or worsening, please visit the clinic or contact a healthcare provider immediately."),
        (r'(checkup|annual physical|routine exam)', "Regular checkups are important for maintaining good health. If you haven't had a checkup recently, consider scheduling one with the clinic."),
        (r'(how to stay healthy|prevent illness|wellness)', "To stay healthy, eat a balanced diet, exercise regularly, get enough sleep, manage stress, and keep up with your vaccinations and checkups."),
        # --- Doctor-style for common symptoms ---
        (r'(fever|temperature)', "As your virtual clinic assistant, I recommend you rest, stay hydrated, and monitor your temperature closely. If your fever is high or persistent, or if you feel very unwell, please consult a healthcare professional promptly. May I ask if you have any other symptoms?"),
        (r'(cough|coughing)', "A cough can have many causes. Is your cough dry or productive? If you're experiencing difficulty breathing, chest pain, or if the cough lasts more than a week, please seek medical attention."),
        (r'(headache|migraine)', "Headaches are common and often improve with rest and hydration. However, if your headache is severe, sudden, or associated with vision changes or fever, please see a doctor as soon as possible."),
        # --- Advanced health-related prompts (previously added) ---
        (r'(cold|flu|runny nose|sneezing)', "Colds and flu are caused by viruses. Rest, drink plenty of fluids, and monitor your symptoms. If you have a high fever or trouble breathing, consult a doctor."),
        (r'(sore eyes|conjunctivitis|pink eye)', "Sore eyes or conjunctivitis can be caused by infection or allergies. Avoid touching your eyes, wash your hands often, and see a doctor if symptoms persist."),
        (r'(rash|skin problem|itchy skin|hives)', "Skin rashes can have many causes. If you have a new rash, try to avoid scratching. If it spreads, is painful, or you have a fever, consult a healthcare provider."),
        (r'(vomit|vomiting|diarrhea|loose bowel)', "Vomiting and diarrhea can lead to dehydration. Drink small sips of water or oral rehydration solution. If symptoms are severe or persistent, seek medical attention."),
        (r'(high blood pressure|hypertension)', "High blood pressure often has no symptoms. It's important to have regular checkups. Maintain a healthy diet, exercise, and take medications as prescribed."),
        (r'(diabetes|high blood sugar)', "Diabetes requires regular monitoring of blood sugar, a healthy diet, and sometimes medication. If you feel dizzy, weak, or confused, seek help immediately."),
        (r'(asthma attack|difficulty breathing)', "If you are having an asthma attack, use your inhaler as prescribed. If you do not feel better or have severe difficulty breathing, seek emergency care."),
        (r'(allergic reaction|anaphylaxis|swelling|difficulty swallowing)', "Severe allergic reactions can be life-threatening. If you have swelling of the face, lips, or trouble breathing, call emergency services immediately."),
        (r'(mental health|stress|anxiety|depression|sad)', "Mental health is important. If you feel stressed, anxious, or sad, talk to someone you trust or a counselor. The clinic can help connect you to support."),
        (r'(healthy eating|nutrition|diet|food)', "A balanced diet includes fruits, vegetables, whole grains, and lean proteins. Drink water and limit sugary or fatty foods for better health."),
        (r'(exercise|physical activity|workout|sports)', "Regular exercise helps keep your body and mind healthy. Aim for at least 30 minutes of activity most days of the week."),
        (r'(sleep|insomnia|can\'t sleep|rest)', "Good sleep is important for health. Try to keep a regular sleep schedule, avoid screens before bed, and relax before sleeping."),
        (r'(first aid|wound|cut|bleeding|burn)', "For minor wounds, wash with clean water and cover with a bandage. For burns, cool with running water. If bleeding is severe or the wound is deep, seek medical help."),
        (r'(child.*fever|baby.*fever|toddler.*fever)', "If a child has a fever, keep them hydrated and monitor for other symptoms. If the child is very young, has a high fever, or seems very ill, see a doctor promptly."),
        (r'(covid.*prevent|corona.*prevent|how.*avoid.*covid)', "To prevent COVID-19, wash your hands often, wear a mask in crowded places, and get vaccinated if eligible."),
        # --- Existing prompts below ---
        # Health records
        (r'(what.*health record|health record.*mean|define health record)', "A health record contains your medical history, visit dates, diagnoses, and treatment plans recorded by clinic staff."),
        (r'(visit date)', "Visit date is the day you visited the clinic for a checkup or consultation."),
        (r'(next follow[- ]?up)', "Next follow-up is the recommended date for your next clinic visit, if needed."),
        (r'(how.*update.*health record|edit.*health record)', "Health records are updated by clinic staff after your visit. If you notice an error, please contact the clinic."),
        # Appointments
        (r'(appointment status.*pending|what.*pending appointment)', "Pending means your appointment is scheduled but not yet completed or cancelled."),
        (r'(how.*reschedule.*appointment)', "You can reschedule by clicking on your appointment and selecting a new date and time, if allowed."),
        (r'(cancel.*appointment)', "To cancel an appointment, go to your appointments list and select the cancel option for the appointment you wish to cancel."),
        (r'(completed appointment)', "A completed appointment means you have already attended and finished your clinic visit."),
        # Vaccinations
        (r'(dose number)', "Dose number refers to which shot in a vaccine series you have received (e.g., 1st dose, 2nd dose)."),
        (r'(batch number)', "Batch number identifies the specific batch of vaccine you received, for safety and tracking."),
        (r'(parent consent)', "Parent consent is required for students under 18 before receiving certain vaccinations."),
        (r'(side effect[s]?)', "Side effects are possible reactions after vaccination, such as mild fever or soreness. If you have severe side effects, contact the clinic."),
        (r'(site of injection)', "Site of injection is the part of your body where the vaccine was administered, such as your arm or thigh."),
        # Notifications
        (r'(urgent notification|urgent alert)', "Urgent notifications are marked as important and may require immediate attention."),
        (r'(attachment.*notification|notification.*attachment)', "Some notifications may include attachments, such as reports or forms, for you to download."),
        (r'(notification type|types of notification)', "Notifications can be alerts, reminders, reports, or general information sent by the clinic."),
        # User roles
        (r'(what.*staff.*do|staff role)', "Staff can manage appointments, health records, and send notifications."),
        (r'(what.*parent.*do|parent role)', "Parents can register children, view their records, and book appointments for them."),
        (r'(what.*admin.*do|admin role)', "Admins manage users, oversee system settings, and have full access to clinic records."),
        (r'(what.*student.*do|student role)', "Students can view their health records, book appointments (if 16+), and receive notifications."),
        # General system features
        (r'(update.*emergency contact|change.*emergency contact)', "You can update your emergency contact information in your profile settings."),
        (r'(profile photo|change.*profile photo)', "You can upload or change your profile photo in your profile settings."),
        (r'(how.*register.*parent|parent registration)', "Parents can register in the system to manage their children's health records and appointments."),
        # Health symptoms
        (r'(fever|temperature)', "If you have a fever, rest, stay hydrated, and monitor your temperature. If it's high or persistent, please consult a healthcare professional. Do you have any other symptoms?"),
        (r'(cough|coughing)', "A cough can be caused by many things. Is it dry or productive? If it's persistent, severe, or with other symptoms, please consult the clinic."),
        (r'(headache|migraine)', "For headaches, rest and hydration can help. Is your headache severe or accompanied by other symptoms? If so, please seek medical advice."),
        (r'(sore throat)', "A sore throat can be caused by infection or irritation. Gargling with warm salt water may help. If it persists, consult the clinic."),
        (r'(stomach ache|abdominal pain|tummy ache)', "Stomach aches can have many causes. Is it severe, or do you have other symptoms like vomiting or fever? If so, please consult a doctor."),
        (r'(covid|corona|virus)', "If you suspect COVID-19, please isolate and contact the clinic for further instructions. Testing may be recommended. Do you have a fever, cough, or loss of taste/smell?"),
        (r'(vaccination|vaccine|immunization)', "Vaccinations are important for your health. You can view your vaccination records in the system or ask the clinic staff for your schedule."),
        (r'(allergy|allergies)', "If you have allergies, try to avoid known triggers. If you have trouble breathing or severe symptoms, seek medical help immediately."),
        (r'(asthma)', "If you have asthma, use your inhaler as prescribed. If you have trouble breathing, seek help immediately."),
        # System use
        (r'(how.*use|help|guide|tutorial|paano|instructions)', "You can use the dashboard to view your health records, book appointments, and check notifications. Is there a specific feature you need help with?"),
        (r'(appointment|book|schedule)', "To book an appointment, use the 'New Appointment' card on your dashboard if you are 16 or older. If you are under 16, please ask your parent to register and book for you."),
        (r'(health record|medical record|history)', "You can view your health records by clicking the 'Health Records' card on your dashboard."),
        (r'(vaccination record|vaccine record)', "You can view your vaccination records by clicking the 'My Vaccinations' card on your dashboard."),
        (r'(notification|alert|reminder)', "Notifications and reminders appear in the bell icon at the top of your dashboard. Click it to view unread messages."),
        (r'(profile|update info|change info)', "You can update your profile by clicking the 'My Profile' card on your dashboard."),
        # General
        (r'(thank you|salamat|thanks)', "You're welcome! If you have more questions, just ask."),
        (r'(hi|hello|good morning|good afternoon|good evening)', "Hello! How can I help you today?")
    ]
    for pattern, answer in responses:
        if re.search(pattern, user_message_lower):
            session['ai_unclear_count'] = 0
            return jsonify({'response': answer})
    unclear_count = session.get('ai_unclear_count', 0)
    if unclear_count < 1:
        session['ai_unclear_count'] = unclear_count + 1
        return jsonify({'response': "I'm not sure I understand. Can you tell me more about your concern or rephrase your question?"})
    age = session.get('age')
    if not age:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT age FROM users WHERE user_id = %s', (session['user_id'],))
        user = cursor.fetchone()
        age = user['age'] if user else None
        cursor.close()
        conn.close()
        session['age'] = age
    session['ai_unclear_count'] = 0
    if age is not None and age >= 16:
        response = ("I'm unable to answer your question directly. I recommend making an appointment at the Academy Medical Clinic System. "
                    "On your dashboard, you'll find a card labeled 'New Appointment' where you can book. Please note, you must be 16+ years old to book an appointment yourself.")
    else:
        response = ("I'm unable to answer your question directly. If you are under 16, please ask your parent or guardian to register in the system and book the appointment for you.")
    return jsonify({'response': response})

@app.route('/mark_all_notifications_read', methods=['POST'])
def mark_all_notifications_read():
    if 'user_id' not in session:
        return '', 401
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE notifications SET is_read = TRUE WHERE recipient_id = %s AND is_read = FALSE', (session['user_id'],))
    conn.commit()
    cursor.close()
    conn.close()
    return '', 204

@app.route('/update_health_record_status/<int:record_id>', methods=['POST'])
def update_health_record_status(record_id):
    if 'role' not in session or session['role'] != 'staff':
        return '', 401
    data = request.get_json()
    new_status = data.get('status')
    if new_status not in ['Active', 'Resolved', 'Archived']:
        return '', 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE health_records SET status = %s WHERE record_id = %s', (new_status, record_id))
    conn.commit()
    cursor.close()
    conn.close()
    return '', 204

@app.route('/api/user-ages')
def api_user_ages():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT username, age FROM users WHERE is_active = TRUE")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(users)

@app.route('/api/appointments-per-day')
def api_appointments_per_day():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT appointment_date AS date, COUNT(*) AS count
        FROM appointments
        GROUP BY appointment_date
        ORDER BY appointment_date
    """)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route('/api/users-per-role')
def api_users_per_role():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT role, COUNT(*) AS count
        FROM users
        WHERE is_active = TRUE
        GROUP BY role
    """)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route('/api/vaccinations-per-month')
def api_vaccinations_per_month():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT DATE_FORMAT(date_administered, '%Y-%m') AS month, COUNT(*) AS count
        FROM vaccinations
        GROUP BY month
        ORDER BY month
    """)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route('/api/medical-records-per-status')
def api_medical_records_per_status():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT status, COUNT(*) AS count
        FROM health_records
        GROUP BY status
    """)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route('/api/notifications-per-type')
def api_notifications_per_type():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT message_type, COUNT(*) AS count
        FROM notifications
        GROUP BY message_type
    """)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route('/parent_link_student', methods=['POST'])
def parent_link_student():
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))
    student_id = request.form.get('student_id')
    if not student_id:
        flash('No student selected.', 'danger')
        return redirect(url_for('parent_view_student_profile'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE user_id = %s AND role = 'student'", (student_id,))
    student = cursor.fetchone()
    if not student:
        cursor.close()
        conn.close()
        flash('Student not found.', 'danger')
        return redirect(url_for('parent_view_student_profile'))
    if student['age'] >= 16:
        cursor.close()
        conn.close()
        flash('Only students under 16 can be linked.', 'danger')
        return redirect(url_for('parent_view_student_profile'))
    if student['guardian_id']:
        cursor.close()
        conn.close()
        flash('This student is already linked to a parent.', 'danger')
        return redirect(url_for('parent_view_student_profile'))
    cursor.execute('UPDATE users SET guardian_id = %s WHERE user_id = %s', (session['user_id'], student_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Student successfully linked to your account.', 'success')
    return redirect(url_for('parent_view_student_profile'))

@app.route('/parent_unlink_student/<int:student_id>', methods=['POST'])
def parent_unlink_student(student_id):
    if 'role' not in session or session['role'] != 'parent':
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM users WHERE user_id = %s AND guardian_id = %s', (student_id, session['user_id']))
    student = cursor.fetchone()
    if not student:
        cursor.close()
        conn.close()
        flash('Student not linked to your account.', 'danger')
        return redirect(url_for('parent_view_student_profile'))
    cursor.execute('UPDATE users SET guardian_id = NULL WHERE user_id = %s', (student_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Student successfully unlinked from your account.', 'success')
    return redirect(url_for('parent_view_student_profile'))

@app.route('/parent_ai_chat', methods=['POST'])
def parent_ai_chat():
    import re
    if 'role' not in session or session['role'] != 'parent':
        return '', 403
    data = request.get_json()
    user_message = data.get('message', '').strip()

    # Try OpenAI GPT-4o firstapi
    if openai_available:
        try:
            client = OpenAI(api_key="Change your own OPENAI API KEY in HERE 2!!!!!!!!!!!!!!")
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": (
                        "You are a professional, friendly, and empathetic virtual health assistant for parents in a school clinic. "
                        "Give clear, concise, and supportive advice. If the question is about a child's health, remind the parent to consult the clinic for urgent issues."
                    )},
                    {"role": "user", "content": user_message}
                ]
            )
            ai_response = completion.choices[0].message.content.strip()
            return jsonify({'response': ai_response})
        except Exception as e:
            pass  # Fallback to programmed responses below

    user_message_lower = user_message.lower()
    responses = [
        (r'(urgent|emergency|help now|can\'t breathe|chest pain|severe pain|fainting|unconscious)',
         "If your child is experiencing severe symptoms such as difficulty breathing, chest  ain, severe pain, fainting, or loss of consciousness, please seek emergency medical care immediately or call emergency services."),
        (r'(hi|hello|good morning|good afternoon|good evening)', "Hello! I'm your virtual clinic assistant for parents. How can I help you with your child's health today?"),
        (r'(thank you|salamat|thanks)', "You're very welcome! If you have more questions or need support, just let me know."),
        (r'(appointment|book|schedule)', "To book an appointment for your child, use the 'Book Appointment' card on your dashboard. If you need help, let me know!"),
        (r'(health record|medical record|history)', "You can view your child's health records by clicking the 'Health Records' card on your dashboard."),
        (r'(vaccination|vaccine|immunization)', "You can view your child's vaccination records by clicking the 'Vaccination Logs' card on your dashboard."),
        (r'(notification|alert|reminder)', "Notifications and reminders appear in the bell icon at the top of your dashboard. Click it to view unread messages."),
        (r'(profile|update info|change info)', "You can update your child's profile by clicking the 'Student Profile' card on your dashboard."),
        (r'(how.*use|help|guide|tutorial|paano|instructions)', "You can use the dashboard to view your child's health records, book appointments, and check notifications. Is there a specific feature you need help with?"),
        (r'(parent role|what.*parent.*do)', "Parents can register children, view their records, and book appointments for them. If you have questions about your child's health, I'm here to help."),
        (r'(child.*fever|baby.*fever|toddler.*fever)', "If your child has a fever, keep them hydrated and monitor for other symptoms. If the child is very young, has a high fever, or seems very ill, see a doctor promptly."),
        (r'(mental health|stress|anxiety|depression|sad)', "If you are concerned about your child's mental health, talk to them and consider reaching out to a counselor or the clinic for support."),
        (r'(covid|corona|virus)', "To prevent COVID-19, ensure your child washes hands often, wears a mask in crowded places, and is vaccinated if eligible."),
        (r'(thank you|salamat|thanks)', "You're welcome! If you have more questions, just ask."),
        (r'(hi|hello|good morning|good afternoon|good evening)', "Hello! How can I help you today?")
    ]
    for pattern, answer in responses:
        if re.search(pattern, user_message_lower):
            return jsonify({'response': answer})
    return jsonify({'response': "I'm not sure I understand. Can you tell me more about your concern or rephrase your question?"})

if __name__ == '__main__':
    app.run(debug=True)
