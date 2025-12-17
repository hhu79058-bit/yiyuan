from flask import Blueprint, render_template, redirect, url_for, session, request
from db import get_db_connection

doctor_bp = Blueprint('doctor', __name__)


@doctor_bp.route('/doctor_dashboard')
def dashboard():
    if session.get('role') != 'doctor':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                  SELECT r.reg_id, p.name AS patient_name, p.gender, p.age, r.visit_status, r.queue_num,
                         r.visit_date, r.shift
                  FROM registration r
                           JOIN patient p ON r.patient_id = p.patient_id
                  WHERE r.doctor_id = %s \
                    AND (r.visit_date = CURDATE() OR (r.visit_date IS NULL AND DATE(r.reg_time) = CURDATE())) \
                    AND r.visit_status IN ('未就诊', '就诊中')
                  ORDER BY r.visit_status DESC, r.queue_num ASC
                  """
            cursor.execute(sql, (session['user_id'],))
            patients = cursor.fetchall()
    finally:
        conn.close()

    return render_template('dashboard.html',
                           doctor_name=session['user_name'],
                           patients=patients)


@doctor_bp.route('/start_consult/<int:reg_id>')
def start_consult(reg_id):
    if session.get('role') != 'doctor':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "UPDATE registration SET visit_status = '就诊中' WHERE reg_id = %s"
            cursor.execute(sql, (reg_id,))
            conn.commit()
    finally:
        conn.close()
        return redirect(url_for('doctor.consultation_page', reg_id=reg_id))


@doctor_bp.route('/consultation/<int:reg_id>')
def consultation_page(reg_id):
    if session.get('role') != 'doctor':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql_patient = """
                          SELECT r.reg_id, p.name, p.gender, p.age, p.allergy
                          FROM registration r
                                   JOIN patient p ON r.patient_id = p.patient_id
                          WHERE r.reg_id = %s
                          """
            cursor.execute(sql_patient, (reg_id,))
            patient = cursor.fetchone()

            cursor.execute("SELECT * FROM medicine WHERE stock > 0")
            medicines = cursor.fetchall()

    finally:
        conn.close()

    return render_template('consultation.html',
                           patient=patient,
                           medicines=medicines,
                           doctor_name=session['user_name'])


@doctor_bp.route('/submit_consultation', methods=['POST'])
def submit_consultation():
    if session.get('role') != 'doctor':
        return redirect(url_for('auth.login'))

    reg_id = request.form.get('reg_id')
    main_complaint = request.form.get('main_complaint')
    diagnosis = request.form.get('diagnosis')
    med_ids = request.form.getlist('med_id[]')
    quantities = request.form.getlist('quantity[]')
    usages = request.form.getlist('usage[]')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql_record = """
                         INSERT INTO medical_record (reg_id, doctor_id, main_complaint, diagnosis, create_time)
                         VALUES (%s, %s, %s, %s, NOW())
                         """
            cursor.execute(sql_record, (reg_id, session['user_id'], main_complaint, diagnosis))

            for i in range(len(med_ids)):
                if med_ids[i] and quantities[i]:
                    cursor.execute("SELECT price FROM medicine WHERE med_id=%s", (med_ids[i],))
                    med_info = cursor.fetchone()
                    total_amt = float(med_info['price']) * int(quantities[i])

                    sql_presc = """
                                INSERT INTO prescription (reg_id, med_id, dosage, med_usage, total_quantity, total_amount)
                                VALUES (%s, %s, '标准剂量', %s, %s, %s)
                                """
                    cursor.execute(sql_presc, (reg_id, med_ids[i], usages[i], quantities[i], total_amt))

            cursor.execute("UPDATE registration SET visit_status = '已就诊' WHERE reg_id = %s", (reg_id,))

            conn.commit()
    except Exception as e:
        print(f"保存失败: {e}")
        conn.rollback()
    finally:
        conn.close()

    return redirect(url_for('doctor.dashboard'))
