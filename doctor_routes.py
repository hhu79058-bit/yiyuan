from flask import Blueprint, render_template, redirect, url_for, session, request, flash
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
                  SELECT r.reg_id, r.patient_id, p.name AS patient_name, p.gender, p.age,
                         p.medical_record_no, p.allergy, p.past_illness,
                         r.visit_status, r.queue_num, r.visit_date, r.shift,
                         r.called_time, r.call_times
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


@doctor_bp.route('/call_patient/<int:reg_id>')
def call_patient(reg_id):
    """
    叫号：记录叫号次数与时间，不改变就诊状态。
    """
    if session.get('role') != 'doctor':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 限定只能叫自己名下的号
            cursor.execute("SELECT doctor_id FROM registration WHERE reg_id=%s", (reg_id,))
            row = cursor.fetchone()
            if not row or row['doctor_id'] != session.get('user_id'):
                flash("无权叫号该患者", 'error')
                return redirect(url_for('doctor.dashboard'))

            cursor.execute("""
                UPDATE registration
                SET called_time = NOW(), call_times = call_times + 1
                WHERE reg_id = %s
            """, (reg_id,))
        conn.commit()
        flash("已叫号", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"叫号失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('doctor.dashboard'))


@doctor_bp.route('/doctor/patient/<int:patient_id>')
def doctor_patient_detail(patient_id):
    """
    医生快速查看患者基本信息与历史记录。
    """
    if session.get('role') != 'doctor':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    patient = None
    regs = []
    med_records = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT patient_id, name, gender, age, phone, allergy, past_illness, medical_record_no
                FROM patient WHERE patient_id=%s
            """, (patient_id,))
            patient = cursor.fetchone()

            cursor.execute("""
                SELECT r.reg_time, r.visit_date, r.shift, r.visit_status, r.queue_num, r.reg_fee,
                       d.name AS doctor_name, dept.dept_name
                FROM registration r
                         JOIN doctor d ON r.doctor_id = d.doctor_id
                         JOIN department dept ON r.dept_id = dept.dept_id
                WHERE r.patient_id=%s
                ORDER BY r.reg_time DESC
                LIMIT 50
            """, (patient_id,))
            regs = cursor.fetchall()

            cursor.execute("""
                SELECT mr.main_complaint, mr.diagnosis, mr.create_time,
                       d.name AS doctor_name
                FROM medical_record mr
                         JOIN registration r ON mr.reg_id = r.reg_id
                         JOIN doctor d ON r.doctor_id = d.doctor_id
                WHERE r.patient_id=%s
                ORDER BY mr.create_time DESC
                LIMIT 50
            """, (patient_id,))
            med_records = cursor.fetchall()
    finally:
        conn.close()

    return render_template('doctor_patient_detail.html',
                           patient=patient,
                           regs=regs,
                           med_records=med_records)


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
                          SELECT r.reg_id, p.name, p.gender, p.age, p.allergy, p.past_illness
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
            # 处方库存校验：如库存不足则整单回滚
            for i in range(len(med_ids)):
                if med_ids[i] and quantities[i]:
                    cursor.execute("SELECT stock, med_name FROM medicine WHERE med_id=%s", (med_ids[i],))
                    m = cursor.fetchone()
                    if not m:
                        flash("处方包含不存在的药品，已取消提交", 'error')
                        conn.rollback()
                        return redirect(url_for('doctor.consultation_page', reg_id=reg_id))
                    if int(m['stock']) < int(quantities[i]):
                        flash(f"库存不足：{m['med_name']}（库存 {m['stock']}），请调整数量", 'error')
                        conn.rollback()
                        return redirect(url_for('doctor.consultation_page', reg_id=reg_id))

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
