from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import bcrypt
import uuid
from datetime import datetime
from config import Config
from db import init_db, get_db_connection

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config.from_object(Config)

try:
    init_db()
except Exception as e:
    print("Database init warning:", e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        roll_no = request.form.get('roll_no')
        name = request.form.get('name')
        email = request.form.get('email')
        branch = request.form.get('branch')
        year = request.form.get('year')
        password = request.form.get('password')
        
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (roll_no, name, email, branch, year, password_hash) VALUES (%s, %s, %s, %s, %s, %s)",
                (roll_no, name, email, branch, year, hashed_pw)
            )
            cursor.close()
            conn.close()
            return redirect(url_for('student_login'))
        except Exception as e:
            return render_template('student_register.html', error="Roll No. or Email already exists!")
            
    return render_template('student_register.html')

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        roll_no = request.form.get('roll_no')
        password = request.form.get('password')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE roll_no = %s", (roll_no,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            session['user_id'] = user['id']
            session['roll_no'] = user['roll_no']
            session['name'] = user['name']
            session['branch'] = user['branch']
            session['year'] = user['year']
            return redirect(url_for('student_dashboard'))
        else:
            return render_template('student_login.html', error="Invalid Roll No. or Password")
            
    return render_template('student_login.html')

@app.route('/student/dashboard')
def student_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('student_login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exams WHERE branch = %s AND year = %s AND is_active = TRUE", (session['branch'], session['year']))
    exams = cursor.fetchall()
    
    cursor.execute("SELECT exam_id FROM attempts WHERE user_id = %s", (session['user_id'],))
    attempted = [row['exam_id'] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    return render_template('student_dashboard.html', exams=exams, attempted=attempted)

@app.route('/exam/<unique_link>', methods=['GET', 'POST'])
def take_exam(unique_link):
    if 'user_id' not in session:
        return redirect(url_for('student_login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exams WHERE unique_link = %s", (unique_link,))
    exam = cursor.fetchone()
    
    if not exam:
        cursor.close()
        conn.close()
        return "Exam not found", 404
        
    cursor.execute("SELECT * FROM attempts WHERE user_id = %s AND exam_id = %s", (session['user_id'], exam['id']))
    existing_attempt = cursor.fetchone()
    
    if existing_attempt:
        cursor.close()
        conn.close()
        return render_template('error.html', message="Aap yeh exam pehle hi de chuke hain. Dubara attempt nahi kiya ja sakta!")

    if request.method == 'POST':
        cursor.execute("SELECT * FROM questions WHERE exam_id = %s", (exam['id'],))
        questions = cursor.fetchall()
        
        score = 0
        total = len(questions)
        
        for q in questions:
            selected_option = request.form.get(f"q_{q['id']}")
            if selected_option and selected_option == q['correct_option']:
                score += 1
                
        cursor.execute(
            "INSERT INTO attempts (user_id, exam_id, start_time, submit_time, score, total_questions, status) VALUES (%s, %s, NOW(), NOW(), %s, %s, 'COMPLETED')",
            (session['user_id'], exam['id'], score, total)
        )
        cursor.close()
        conn.close()
        return redirect(url_for('exam_submitted'))

    cursor.execute("SELECT * FROM questions WHERE exam_id = %s", (exam['id'],))
    questions = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return render_template('exam_room.html', exam=exam, questions=questions)

@app.route('/exam/submitted')
def exam_submitted():
    if 'user_id' not in session:
        return redirect(url_for('student_login'))
    return render_template('exam_submitted.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admins WHERE username = %s", (username,))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if admin and bcrypt.checkpw(password.encode('utf-8'), admin['password_hash'].encode('utf-8')):
            session['admin_logged'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error="Invalid Admin Credentials")
            
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged'):
        return redirect(url_for('admin_login'))
    return render_template('admin_dashboard.html')

@app.route('/admin/students')
def admin_students():
    if not session.get('admin_logged'):
        return redirect(url_for('admin_login'))
        
    branch_filter = request.args.get('branch', '')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if branch_filter:
        cursor.execute("SELECT * FROM users WHERE branch = %s", (branch_filter,))
    else:
        cursor.execute("SELECT * FROM users")
    students = cursor.fetchall()
    
    cursor.execute("SELECT DISTINCT branch FROM users")
    branches = [row['branch'] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    return render_template('admin_students.html', students=students, branches=branches, selected_branch=branch_filter)

@app.route('/admin/exams', methods=['GET', 'POST'])
def admin_exams():
    if not session.get('admin_logged'):
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exams")
    exams = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_exams.html', exams=exams)

@app.route('/admin/add-exam', methods=['GET', 'POST'])
def add_exam():
    if not session.get('admin_logged'):
        return redirect(url_for('admin_login'))
        
    if request.method == 'POST':
        title = request.form.get('title')
        branch = request.form.get('branch')
        year = request.form.get('year')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')
        duration = request.form.get('duration_minutes')
        
        # Automatically unique link generate hoga (jaise cse-exam-<random_string>)
        unique_link = f"exam-{uuid.uuid4().hex[:8]}"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO exams (title, unique_link, branch, year, start_time, end_time, duration_minutes) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (title, unique_link, branch, year, start_time, end_time, duration)
        )
        exam_id = cursor.lastrowid
        
        # Dynamic Questions handle karna (Jitne bhi questions add kiye honge)
        question_texts = request.form.getlist('question_text[]')
        opt_as = request.form.getlist('opt_a[]')
        opt_bs = request.form.getlist('opt_b[]')
        opt_cs = request.form.getlist('opt_c[]')
        opt_ds = request.form.getlist('opt_d[]')
        corrects = request.form.getlist('correct[]')
        
        for i in range(len(question_texts)):
            if question_texts[i].strip():
                cursor.execute(
                    "INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_option) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (exam_id, question_texts[i], opt_as[i], opt_bs[i], opt_cs[i], opt_ds[i], corrects[i].upper())
                )
            
        cursor.close()
        conn.close()
        return redirect(url_for('admin_exams'))
        
    return render_template('add_exam.html')

@app.route('/admin/results')
def admin_results():
    if not session.get('admin_logged'):
        return redirect(url_for('admin_login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT attempts.*, users.name, users.roll_no, users.branch, exams.title 
        FROM attempts 
        JOIN users ON attempts.user_id = users.id 
        JOIN exams ON attempts.exam_id = exams.id
    """)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin_results.html', results=results)

@app.route('/admin/change-password', methods=['GET', 'POST'])
def change_password():
    if not session.get('admin_logged'):
        return redirect(url_for('admin_login'))
        
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE admins SET password_hash = %s WHERE username = 'admin'", (hashed_pw,))
        cursor.close()
        conn.close()
        return render_template('admin_change_password.html', success="Admin password successfully updated!")
        
    return render_template('admin_change_password.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)