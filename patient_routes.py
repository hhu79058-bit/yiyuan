from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection, generate_medical_record_no, table_exists
from utils import require_login

patients_bp = Blueprint('patients', __name__)


@patients_bp.route('/patients')
def patient_manage():
    if not require_login():
        return redirect(url_for('auth.login'))

    keyword = request.args.get('q', '').strip()
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if keyword:
                like_kw = f"%{keyword}%"
                cursor.execute("""
                    SELECT patient_id, name, gender, age, phone, allergy, medical_record_no
                    FROM patient
                    WHERE name LIKE %s OR medical_record_no LIKE %s
                    ORDER BY patient_id DESC
                    LIMIT 200
                """, (like_kw, like_kw))
            else:
                cursor.execute("""
                    SELECT patient_id, name, gender, age, phone, allergy, medical_record_no
                    FROM patient
                    ORDER BY patient_id DESC
                    LIMIT 200
                """)
            patients = cursor.fetchall()
    finally:
        conn.close()

    return render_template('patient_manage.html', patients=patients, keyword=keyword)


@patients_bp.route('/patients/create', methods=['POST'])
def patient_create():
    if not require_login():
        return redirect(url_for('auth.login'))

    name = request.form.get('name')
    gender = request.form.get('gender')
    age = request.form.get('age')
    phone = request.form.get('phone')
    allergy = request.form.get('allergy')
    med_no = request.form.get('medical_record_no')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            if med_no:
                cursor.execute("SELECT 1 FROM patient WHERE medical_record_no=%s LIMIT 1", (med_no,))
                if cursor.fetchone():
                    flash("病历号已存在，请更换或留空自动生成。", 'error')
                    return redirect(url_for('patients.patient_manage'))
            else:
                med_no = generate_medical_record_no(conn)

            cursor.execute("""
                INSERT INTO patient (name, gender, age, phone, allergy, medical_record_no, password)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (name, gender, age, phone, allergy, med_no, '123456'))
        conn.commit()
        flash(f"已创建患者，病历号：{med_no}", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"创建失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('patients.patient_manage'))


@patients_bp.route('/patients/update', methods=['POST'])
def patient_update():
    if not require_login():
        return redirect(url_for('auth.login'))

    patient_id = request.form.get('patient_id')
    name = request.form.get('name')
    gender = request.form.get('gender')
    age = request.form.get('age')
    phone = request.form.get('phone')
    allergy = request.form.get('allergy')
    med_no = request.form.get('medical_record_no')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT patient_id FROM patient
                WHERE medical_record_no=%s AND patient_id != %s
                LIMIT 1
            """, (med_no, patient_id))
            exists = cursor.fetchone()
            if exists:
                flash("病历号已被其他患者使用。", 'error')
                return redirect(url_for('patients.patient_manage'))

            cursor.execute("""
                UPDATE patient
                SET name=%s, gender=%s, age=%s, phone=%s, allergy=%s, medical_record_no=%s
                WHERE patient_id=%s
            """, (name, gender, age, phone, allergy, med_no, patient_id))
        conn.commit()
        flash("信息已更新", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"更新失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('patients.patient_manage'))


@patients_bp.route('/patients/<int:patient_id>')
def patient_detail(patient_id):
    if not require_login():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    patient = None
    regs = []
    med_records = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT patient_id, name, gender, age, phone, allergy, medical_record_no
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
            """, (patient_id,))
            regs = cursor.fetchall()

            if table_exists(conn, 'medical_record'):
                cursor.execute("""
                    SELECT mr.main_complaint, mr.diagnosis, mr.create_time,
                           d.name AS doctor_name
                    FROM medical_record mr
                             JOIN registration r ON mr.reg_id = r.reg_id
                             JOIN doctor d ON r.doctor_id = d.doctor_id
                    WHERE r.patient_id=%s
                    ORDER BY mr.create_time DESC
                """, (patient_id,))
                med_records = cursor.fetchall()
    finally:
        conn.close()

    return render_template('patient_detail.html',
                           patient=patient,
                           regs=regs,
                           med_records=med_records)


@patients_bp.route('/patient/profile', methods=['GET', 'POST'])
def patient_profile():
    """
    患者个人中心：患者自行维护过敏史、既往病史。
    """
    if session.get('role') != 'patient':
        return redirect(url_for('auth.login'))

    patient_id = session.get('user_id')
    conn = get_db_connection()
    patient = None
    try:
        if request.method == 'POST':
            allergy = request.form.get('allergy')
            past_illness = request.form.get('past_illness')
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE patient SET allergy=%s, past_illness=%s
                    WHERE patient_id=%s
                """, (allergy, past_illness, patient_id))
            conn.commit()
            flash("档案已更新", 'success')

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT name, gender, age, phone, allergy, past_illness, medical_record_no
                FROM patient WHERE patient_id=%s
            """, (patient_id,))
            patient = cursor.fetchone()
    finally:
        conn.close()

    return render_template('patient_profile.html', patient=patient)
