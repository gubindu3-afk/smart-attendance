from flask import Flask, request, jsonify
from flask_mysqldb import MySQL
from flask_cors import CORS
from datetime import date, datetime

app = Flask(__name__)
CORS(app)

app.config['MYSQL_HOST']        = 'junction.proxy.rlwy.net'
app.config['MYSQL_USER']        = 'root'
app.config['MYSQL_PASSWORD']    = 'adviWiOOhiMHKGeXoLIDpabzFJiXnxMV'
app.config['MYSQL_DB']          = 'railway'
app.config['MYSQL_PORT']        = 44293
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

LATE_CUTOFF = datetime.strptime("10:30:00", "%H:%M:%S").time()

def get_punctuality(time_str):
    if not time_str:
        return None
    try:
        t = datetime.strptime(str(time_str), "%H:%M:%S").time()
        return 'Late' if t > LATE_CUTOFF else 'On-time'
    except:
        return None

def get_admin_password():
    cur = mysql.connection.cursor()
    cur.execute("SELECT value FROM admin_settings WHERE setting_key='admin_password'")
    row = cur.fetchone()
    cur.close()
    return row['value'] if row else '1234'


# ══════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════

@app.route('/api/login', methods=['POST'])
def login():
    data     = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    # Admin
    if username == 'admin' and password == get_admin_password():
        return jsonify({'success': True, 'role': 'admin'})

    # Teacher (email + password)
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM teachers WHERE email=%s AND password=%s", (username, password))
    teacher = cur.fetchone()
    if teacher:
        cur.close()
        return jsonify({'success': True, 'role': 'teacher', 'teacher': teacher})

    # Parent (student_id + phone)
    cur.execute("SELECT * FROM students WHERE id=%s AND phone=%s", (username, password))
    student = cur.fetchone()
    cur.close()
    if student:
        return jsonify({'success': True, 'role': 'parent', 'student': student})

    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401


# ══════════════════════════════════════════════════════════════
# ADMIN SETTINGS
# ══════════════════════════════════════════════════════════════

@app.route('/api/settings/change-password', methods=['POST'])
def change_password():
    data        = request.json
    old_pass    = data.get('old_password', '')
    new_pass    = data.get('new_password', '')
    if old_pass != get_admin_password():
        return jsonify({'error': 'Current password is incorrect'}), 400
    if not new_pass or len(new_pass) < 4:
        return jsonify({'error': 'New password must be at least 4 characters'}), 400
    cur = mysql.connection.cursor()
    cur.execute("UPDATE admin_settings SET value=%s WHERE setting_key='admin_password'", (new_pass,))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True, 'message': 'Password changed successfully'})


# ══════════════════════════════════════════════════════════════
# STUDENTS
# ══════════════════════════════════════════════════════════════

@app.route('/api/students', methods=['GET'])
def get_students():
    dept   = request.args.get('dept')
    year   = request.args.get('year')
    search = request.args.get('search', '').strip()
    cur    = mysql.connection.cursor()
    query  = "SELECT * FROM students WHERE 1=1"
    params = []
    if dept:
        query += " AND dept=%s"; params.append(dept)
    if year:
        query += " AND year=%s"; params.append(year)
    if search:
        query += " AND (name LIKE %s OR id LIKE %s)"
        params += [f'%{search}%', f'%{search}%']
    query += " ORDER BY name"
    cur.execute(query, params)
    students = cur.fetchall()
    cur.close()
    return jsonify(students)

@app.route('/api/students', methods=['POST'])
def add_student():
    data = request.json
    if not data.get('id') or not data.get('name'):
        return jsonify({'error': 'ID and Name required'}), 400
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO students (id,name,email,phone,dept,year) VALUES (%s,%s,%s,%s,%s,%s)",
            (data['id'], data['name'], data.get('email',''), data.get('phone',''), data['dept'], data['year'])
        )
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/students/<student_id>', methods=['PUT'])
def update_student(student_id):
    data = request.json
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "UPDATE students SET name=%s,email=%s,phone=%s,dept=%s,year=%s WHERE id=%s",
            (data['name'], data.get('email',''), data.get('phone',''), data['dept'], data['year'], student_id)
        )
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/students/<student_id>', methods=['DELETE'])
def delete_student(student_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM students WHERE id=%s", (student_id,))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/students/<student_id>/report', methods=['GET'])
def student_individual_report(student_id):
    """Individual student full report for admin"""
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM students WHERE id=%s", (student_id,))
    student = cur.fetchone()
    if not student:
        return jsonify({'error': 'Not found'}), 404
    cur.execute(
        "SELECT date,status,time_in,punctuality FROM attendance WHERE student_id=%s ORDER BY date DESC",
        (student_id,)
    )
    records = cur.fetchall()
    cur.close()
    total   = len(records)
    present = sum(1 for r in records if r['status'] == 'Present')
    late    = sum(1 for r in records if r['punctuality'] == 'Late')
    percent = round((present/total)*100) if total > 0 else 100
    serialized = [{'date':str(r['date']),'status':r['status'],'time_in':str(r['time_in']) if r['time_in'] else None,'punctuality':r['punctuality']} for r in records]
    return jsonify({'student':student,'total':total,'present':present,'absent':total-present,'late':late,'percent':percent,'records':serialized})


# ══════════════════════════════════════════════════════════════
# TEACHERS
# ══════════════════════════════════════════════════════════════

@app.route('/api/teachers', methods=['GET'])
def get_teachers():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id,name,email,dept,subject,year FROM teachers ORDER BY name")
    teachers = cur.fetchall()
    cur.close()
    return jsonify(teachers)

@app.route('/api/teachers', methods=['POST'])
def add_teacher():
    data = request.json
    if not data.get('name') or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Name, email and password required'}), 400
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO teachers (name,email,password,dept,subject,year) VALUES (%s,%s,%s,%s,%s,%s)",
            (data['name'],data['email'],data['password'],data['dept'],data['subject'],data['year'])
        )
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/teachers/<int:tid>', methods=['PUT'])
def update_teacher(tid):
    data = request.json
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "UPDATE teachers SET name=%s,email=%s,dept=%s,subject=%s,year=%s WHERE id=%s",
            (data['name'],data['email'],data['dept'],data['subject'],data['year'],tid)
        )
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/teachers/<int:tid>', methods=['DELETE'])
def delete_teacher(tid):
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM teachers WHERE id=%s", (tid,))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ══════════════════════════════════════════════════════════════
# ATTENDANCE
# ══════════════════════════════════════════════════════════════

@app.route('/api/attendance/<att_date>', methods=['GET'])
def get_attendance(att_date):
    dept = request.args.get('dept')
    year = request.args.get('year')
    cur  = mysql.connection.cursor()
    if dept and year:
        cur.execute("SELECT id FROM students WHERE dept=%s AND year=%s", (dept, year))
    else:
        cur.execute("SELECT id FROM students")
    all_students = cur.fetchall()
    cur.execute("SELECT student_id,status,time_in,punctuality FROM attendance WHERE date=%s", (att_date,))
    records = {r['student_id']:{'status':r['status'],'time_in':str(r['time_in']) if r['time_in'] else None,'punctuality':r['punctuality']} for r in cur.fetchall()}
    cur.close()
    result = {}
    for s in all_students:
        result[s['id']] = records.get(s['id'], {'status':'Present','time_in':None,'punctuality':None})
    return jsonify(result)


@app.route('/api/attendance', methods=['POST'])
def save_attendance():
    data     = request.json
    att_date = data.get('date')
    records  = data.get('records', {})
    if not att_date or not records:
        return jsonify({'error': 'date and records required'}), 400
    try:
        cur = mysql.connection.cursor()
        for student_id, info in records.items():
            status  = info.get('status', 'Present')
            time_in = info.get('time_in')
            punctuality = get_punctuality(time_in) if status == 'Present' and time_in else None
            if status == 'Absent':
                time_in = None

            cur.execute(
                """INSERT INTO attendance (student_id,date,status,time_in,punctuality)
                   VALUES (%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE status=%s,time_in=%s,punctuality=%s""",
                (student_id,att_date,status,time_in,punctuality,status,time_in,punctuality)
            )

            # ── Auto-create notifications ─────────────────────
            if status == 'Absent':
                cur.execute("SELECT name FROM students WHERE id=%s", (student_id,))
                s = cur.fetchone()
                if s:
                    msg = f"{s['name']} was absent on {att_date}"
                    cur.execute(
                        """INSERT INTO notifications (student_id,date,type,message)
                           VALUES (%s,%s,'Absent',%s)
                           ON DUPLICATE KEY UPDATE message=%s""",
                        (student_id, att_date, msg, msg)
                    )
            elif punctuality == 'Late':
                cur.execute("SELECT name FROM students WHERE id=%s", (student_id,))
                s = cur.fetchone()
                if s:
                    msg = f"{s['name']} arrived late ({time_in}) on {att_date}"
                    cur.execute(
                        """INSERT INTO notifications (student_id,date,type,message)
                           VALUES (%s,%s,'Late',%s)
                           ON DUPLICATE KEY UPDATE message=%s""",
                        (student_id, att_date, msg, msg)
                    )

        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True, 'message': f'Attendance saved for {att_date}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ══════════════════════════════════════════════════════════════
# PARENT — student attendance summary + notifications
# ══════════════════════════════════════════════════════════════

@app.route('/api/attendance/student/<student_id>', methods=['GET'])
def get_student_attendance(student_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM students WHERE id=%s", (student_id,))
    student = cur.fetchone()
    if not student:
        return jsonify({'error': 'Student not found'}), 404

    cur.execute(
        "SELECT date,status,time_in,punctuality FROM attendance WHERE student_id=%s ORDER BY date DESC",
        (student_id,)
    )
    records = cur.fetchall()

    # Notifications
    cur.execute(
        "SELECT type,message,date,is_read FROM notifications WHERE student_id=%s ORDER BY created_at DESC LIMIT 10",
        (student_id,)
    )
    notifications = cur.fetchall()
    cur.close()

    total   = len(records)
    present = sum(1 for r in records if r['status'] == 'Present')
    late    = sum(1 for r in records if r['punctuality'] == 'Late')
    percent = round((present/total)*100) if total > 0 else 100

    serialized = [{'date':str(r['date']),'status':r['status'],'time_in':str(r['time_in']) if r['time_in'] else None,'punctuality':r['punctuality']} for r in records]
    chart_data = [{'date':str(r['date']),'status':r['status']} for r in reversed(records[:7])]
    notif_list = [{'type':n['type'],'message':n['message'],'date':str(n['date']),'is_read':n['is_read']} for n in notifications]

    return jsonify({
        'student':student,'total':total,'present':present,
        'absent':total-present,'late':late,'percent':percent,
        'records':serialized,'chart_data':chart_data,
        'notifications':notif_list
    })

@app.route('/api/attendance/student/<student_id>/datewise', methods=['GET'])
def parent_datewise(student_id):
    """Parent reads attendance for a specific date — read only"""
    att_date = request.args.get('date', date.today().isoformat())
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT date,status,time_in,punctuality FROM attendance WHERE student_id=%s AND date=%s",
        (student_id, att_date)
    )
    row = cur.fetchone()
    cur.close()
    if row:
        return jsonify({'date':str(row['date']),'status':row['status'],'time_in':str(row['time_in']) if row['time_in'] else None,'punctuality':row['punctuality']})
    return jsonify({'date':att_date,'status':'No record','time_in':None,'punctuality':None})


# ══════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    today = date.today().isoformat()
    cur   = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) as c FROM students"); total_students = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM teachers"); total_teachers = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM attendance WHERE date=%s AND status='Present'", (today,)); today_present = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM attendance WHERE date=%s AND status='Absent'",  (today,)); today_absent  = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM attendance WHERE date=%s AND punctuality='Late'", (today,)); today_late = cur.fetchone()['c']
    cur.execute("SELECT COUNT(DISTINCT date) as c FROM attendance"); total_days = cur.fetchone()['c']

    cur.execute("SELECT id FROM students")
    all_ids = [r['id'] for r in cur.fetchall()]
    total_pct = 0; low_count = 0
    for sid in all_ids:
        cur.execute("SELECT COUNT(*) as t, SUM(status='Present') as p FROM attendance WHERE student_id=%s", (sid,))
        row = cur.fetchone(); t,p = row['t'], row['p'] or 0
        pct = (p/t*100) if t>0 else 100
        total_pct += pct
        if pct < 75: low_count += 1
    avg_rate = round(total_pct/len(all_ids)) if all_ids else 0
    cur.close()

    return jsonify({
        'total_students':total_students,'total_teachers':total_teachers,
        'today_present':today_present,'today_absent':today_absent,
        'today_late':today_late,'avg_rate':avg_rate,
        'low_count':low_count,'total_classes':total_days
    })


# ══════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════

@app.route('/api/report', methods=['GET'])
def report():
    dept  = request.args.get('dept', 'All Departments')
    year  = request.args.get('year', 'All Years')
    month = request.args.get('month', '')   # YYYY-MM format, optional
    cur   = mysql.connection.cursor()
    query = "SELECT * FROM students WHERE 1=1"; params = []
    if dept != 'All Departments': query += " AND dept=%s"; params.append(dept)
    if year != 'All Years':       query += " AND year=%s"; params.append(year)
    cur.execute(query, params)
    students = cur.fetchall()
    result = []
    for s in students:
        if month:
            cur.execute("SELECT COUNT(*) as t, SUM(status='Present') as p, SUM(punctuality='Late') as l FROM attendance WHERE student_id=%s AND DATE_FORMAT(date,'%%Y-%%m')=%s", (s['id'], month))
        else:
            cur.execute("SELECT COUNT(*) as t, SUM(status='Present') as p, SUM(punctuality='Late') as l FROM attendance WHERE student_id=%s", (s['id'],))
        row = cur.fetchone(); t,p,l = row['t'], row['p'] or 0, row['l'] or 0
        pct = round((p/t)*100) if t>0 else 100
        result.append({**s,'percent':pct,'late_count':int(l),'total_classes':t,'present_days':int(p),'is_low':pct<75})
    cur.close()
    return jsonify(result)

@app.route('/api/report/low', methods=['GET'])
def low_attendance_list():
    """Only students below 75%"""
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM students ORDER BY name")
    students = cur.fetchall()
    result = []
    for s in students:
        cur.execute("SELECT COUNT(*) as t, SUM(status='Present') as p FROM attendance WHERE student_id=%s", (s['id'],))
        row = cur.fetchone(); t,p = row['t'], row['p'] or 0
        pct = round((p/t)*100) if t>0 else 100
        if pct < 75:
            result.append({**s,'percent':pct,'classes_needed':max(0,int((0.75*(t+1)-p)/(1-0.75)) if (t+p)>0 else 0)})
    cur.close()
    return jsonify(result)


# ══════════════════════════════════════════════════════════════
# CLASSES
# ══════════════════════════════════════════════════════════════

@app.route('/api/classes', methods=['GET'])
def get_classes():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM classes ORDER BY dept,year,semester")
    classes = cur.fetchall()
    cur.close()
    return jsonify(classes)

@app.route('/api/classes', methods=['POST'])
def add_class():
    data = request.json
    try:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO classes (dept,year,semester,subject) VALUES (%s,%s,%s,%s)",
                    (data['dept'],data['year'],data['semester'],data['subject']))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/classes/<int:cid>', methods=['DELETE'])
def delete_class(cid):
    try:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM classes WHERE id=%s", (cid,))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# ══════════════════════════════════════════════════════════════
# TEACHER SUMMARY (for teacher dashboard)
# ══════════════════════════════════════════════════════════════

@app.route('/api/teacher/summary', methods=['GET'])
def teacher_summary():
    """Today's attendance summary for teacher's class"""
    dept      = request.args.get('dept', '')
    year      = request.args.get('year', '')
    att_date  = request.args.get('date', date.today().isoformat())
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) as total FROM students WHERE dept=%s AND year=%s", (dept, year))
    total = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) as c FROM attendance a JOIN students s ON a.student_id=s.id WHERE s.dept=%s AND s.year=%s AND a.date=%s AND a.status='Present'", (dept,year,att_date))
    present = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM attendance a JOIN students s ON a.student_id=s.id WHERE s.dept=%s AND s.year=%s AND a.date=%s AND a.status='Absent'", (dept,year,att_date))
    absent = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM attendance a JOIN students s ON a.student_id=s.id WHERE s.dept=%s AND s.year=%s AND a.date=%s AND a.punctuality='Late'", (dept,year,att_date))
    late = cur.fetchone()['c']
    cur.close()
    pct = round((present/total)*100) if total>0 else 0
    return jsonify({'total':total,'present':present,'absent':absent,'late':late,'percent':pct})


# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
