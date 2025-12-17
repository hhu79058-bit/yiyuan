from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import get_db_connection, fetch_departments_and_doctors, create_registration_record, \
    generate_medical_record_no, update_schedule_booked, column_exists
from utils import require_login

reg_bp = Blueprint('registration', __name__)


@reg_bp.route('/patient_home')
def patient_home():
    if session.get('role') != 'patient':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                  SELECT d.doctor_id, d.name, d.title, d.reg_fee, dept.dept_name
                  FROM doctor d
                           JOIN department dept ON d.dept_id = dept.dept_id
                  WHERE d.status = '正常'
                  """)
            doctors = cursor.fetchall()

            my_sql = """
                     SELECT r.reg_id, r.queue_num, d.name as doctor_name, r.visit_status, r.reg_time, r.visit_date, r.shift,
                            r.fee_status
                     FROM registration r
                              JOIN doctor d ON r.doctor_id = d.doctor_id
                     WHERE r.patient_id = %s
                     ORDER BY r.reg_time DESC
                     """
            cursor.execute(my_sql, (session['user_id'],))
            my_regs = cursor.fetchall()

    finally:
        conn.close()

    return render_template('patient_home.html',
                           patient_name=session['user_name'],
                           doctors=doctors,
                           my_regs=my_regs)


@reg_bp.route('/book_appointment/<int:doctor_id>')
def book_appointment(doctor_id):
    if session.get('role') != 'patient':
        return redirect(url_for('auth.login'))

    patient_id = session['user_id']

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT dept_id, reg_fee FROM doctor WHERE doctor_id=%s", (doctor_id,))
            doc_info = cursor.fetchone()

            count_sql = """
                        SELECT COUNT(*) as cnt
                        FROM registration
                        WHERE doctor_id=%s AND visit_date = CURDATE() AND shift = '全天' AND visit_status != '已取消'
                        """
            cursor.execute(count_sql, (doctor_id,))
            count_res = cursor.fetchone()
            new_queue_num = count_res['cnt'] + 1

            insert_sql = """
                         INSERT INTO registration (patient_id, doctor_id, dept_id, reg_fee, visit_status, queue_num,
                                                   reg_time, visit_date, shift, fee_status)
                         VALUES (%s, %s, %s, %s, '未就诊', %s, NOW(), CURDATE(), '全天', '未支付')
                         """
            cursor.execute(insert_sql, (patient_id, doctor_id, doc_info['dept_id'], doc_info['reg_fee'], new_queue_num))
            conn.commit()

    except Exception as e:
        print(f"挂号失败: {e}")
    finally:
        conn.close()

    return redirect(url_for('registration.patient_home'))


@reg_bp.route('/registration/manage')
def registration_manage():
    if not require_login():
        return redirect(url_for('auth.login'))

    selected_date = request.args.get('date') or date.today().isoformat()

    conn = get_db_connection()
    try:
        departments, doctors = fetch_departments_and_doctors(conn)
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.reg_id, r.queue_num, r.visit_status, r.visit_date, r.shift, r.fee_status,
                       p.name AS patient_name, p.medical_record_no,
                       d.name AS doctor_name, dept.dept_name
                FROM registration r
                         JOIN patient p ON r.patient_id = p.patient_id
                         JOIN doctor d ON r.doctor_id = d.doctor_id
                         JOIN department dept ON r.dept_id = dept.dept_id
                WHERE r.visit_date = %s
                ORDER BY r.shift, r.queue_num
            """, (selected_date,))
            today_regs = cursor.fetchall()

            cursor.execute("""
                SELECT dept.dept_name, COUNT(*) AS cnt
                FROM registration r
                         JOIN department dept ON r.dept_id = dept.dept_id
                WHERE r.visit_date = %s AND r.visit_status != '已取消'
                GROUP BY dept.dept_name
            """, (selected_date,))
            dept_stats = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*) AS total_cnt,
                       SUM(reg_fee) AS total_fee
                FROM registration
                WHERE visit_date = %s AND visit_status != '已取消'
            """, (selected_date,))
            totals = cursor.fetchone()

            has_date = column_exists(conn, 'doctor_schedule', 'schedule_date')
            has_shift = column_exists(conn, 'doctor_schedule', 'shift')
            has_max = column_exists(conn, 'doctor_schedule', 'max_slots')
            has_booked = column_exists(conn, 'doctor_schedule', 'booked_slots')
            has_status = column_exists(conn, 'doctor_schedule', 'status')

            col_date = "s.schedule_date" if has_date else "NULL AS schedule_date"
            col_shift = "s.shift" if has_shift else "'全天' AS shift"
            col_max = "s.max_slots" if has_max else "0 AS max_slots"
            col_booked = "s.booked_slots" if has_booked else "0 AS booked_slots"
            col_status = "s.status" if has_status else "'可用' AS status"

            schedule_sql = f"""
                SELECT s.schedule_id, {col_date}, {col_shift}, {col_max}, {col_booked}, {col_status},
                       d.name AS doctor_name, dept.dept_name
                FROM doctor_schedule s
                         JOIN doctor d ON s.doctor_id = d.doctor_id
                         JOIN department dept ON d.dept_id = dept.dept_id
            """
            if has_date:
                schedule_sql += " WHERE s.schedule_date >= CURDATE()"
            schedule_sql += " ORDER BY doctor_name"

            cursor.execute(schedule_sql)
            schedules = cursor.fetchall()
    finally:
        conn.close()

    return render_template('registration_manage.html',
                           selected_date=selected_date,
                           departments=departments,
                           doctors=doctors,
                           today_regs=today_regs,
                           dept_stats=dept_stats,
                           totals=totals,
                           schedules=schedules)


@reg_bp.route('/registration/new', methods=['POST'])
def registration_new_patient():
    if not require_login():
        return redirect(url_for('auth.login'))

    name = request.form.get('name')
    gender = request.form.get('gender')
    age = request.form.get('age')
    phone = request.form.get('phone')
    allergy = request.form.get('allergy')
    dept_id = request.form.get('dept_id')
    doctor_id = request.form.get('doctor_id')
    visit_date = request.form.get('visit_date')
    shift = request.form.get('shift')

    conn = get_db_connection()
    try:
        mr_no = generate_medical_record_no(conn)
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO patient (name, gender, age, phone, allergy, medical_record_no, password)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (name, gender, age, phone, allergy, mr_no, '123456'))
            patient_id = cursor.lastrowid

        create_registration_record(conn, patient_id, doctor_id, dept_id, visit_date, shift, fee_status='未支付')
        flash(f"新患者挂号成功，病历号：{mr_no}", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"挂号失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('registration.registration_manage', date=visit_date))


@reg_bp.route('/registration/quick', methods=['POST'])
def registration_quick():
    if not require_login():
        return redirect(url_for('auth.login'))

    keyword = request.form.get('keyword')
    dept_id = request.form.get('dept_id')
    doctor_id = request.form.get('doctor_id')
    visit_date = request.form.get('visit_date')
    shift = request.form.get('shift')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT patient_id, medical_record_no, name
                FROM patient
                WHERE medical_record_no = %s OR name = %s
                LIMIT 1
            """, (keyword, keyword))
            patient = cursor.fetchone()

        if not patient:
            flash("未找到对应患者，请核对病历号或姓名。", 'error')
            return redirect(url_for('registration.registration_manage', date=visit_date))

        create_registration_record(conn, patient['patient_id'], doctor_id, dept_id, visit_date, shift, fee_status='未支付')
        flash(f"患者 {patient['name']} 挂号成功。", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"挂号失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('registration.registration_manage', date=visit_date))


@reg_bp.route('/registration/cancel/<int:reg_id>')
def registration_cancel(reg_id):
    if not require_login():
        return redirect(url_for('auth.login'))

    visit_date = None
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT visit_status, schedule_id, visit_date FROM registration WHERE reg_id=%s", (reg_id,))
            reg = cursor.fetchone()
            if not reg:
                flash("挂号记录不存在", 'error')
                return redirect(url_for('registration.registration_manage'))
            visit_date = reg['visit_date']
            if reg['visit_status'] == '已取消':
                flash("该记录已取消", 'info')
                return redirect(url_for('registration.registration_manage', date=visit_date))

            cursor.execute("UPDATE registration SET visit_status='已取消' WHERE reg_id=%s", (reg_id,))
        update_schedule_booked(conn, reg['schedule_id'], -1)
        flash("已成功退号", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"操作失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('registration.registration_manage', date=visit_date or date.today().isoformat()))


@reg_bp.route('/registration/restore/<int:reg_id>')
def registration_restore(reg_id):
    if not require_login():
        return redirect(url_for('auth.login'))

    visit_date = None
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT visit_status, schedule_id, visit_date FROM registration WHERE reg_id=%s", (reg_id,))
            reg = cursor.fetchone()
            if not reg:
                flash("挂号记录不存在", 'error')
                return redirect(url_for('registration.registration_manage'))
            visit_date = reg['visit_date']
            if reg['visit_status'] != '已取消':
                flash("当前状态不可恢复", 'info')
                return redirect(url_for('registration.registration_manage', date=visit_date))

            cursor.execute("UPDATE registration SET visit_status='未就诊' WHERE reg_id=%s", (reg_id,))
        update_schedule_booked(conn, reg['schedule_id'], 1)
        flash("已恢复挂号", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"操作失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('registration.registration_manage', date=visit_date or date.today().isoformat()))


@reg_bp.route('/schedule/save', methods=['POST'])
def schedule_save():
    if not require_login():
        return redirect(url_for('auth.login'))

    doctor_id = request.form.get('doctor_id')
    schedule_date = request.form.get('schedule_date')
    shift = request.form.get('shift')
    max_slots = request.form.get('max_slots')
    status = request.form.get('status')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO doctor_schedule (doctor_id, schedule_date, shift, max_slots, booked_slots, status)
                VALUES (%s, %s, %s, %s, 0, %s)
                ON DUPLICATE KEY UPDATE max_slots=VALUES(max_slots), status=VALUES(status)
            """, (doctor_id, schedule_date, shift, max_slots, status))
        conn.commit()
        flash("排班已保存", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"排班保存失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('registration.registration_manage', date=schedule_date))


@reg_bp.route('/schedule/status/<int:schedule_id>/<string:new_status>')
def schedule_status(schedule_id, new_status):
    if not require_login():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE doctor_schedule SET status=%s WHERE schedule_id=%s", (new_status, schedule_id))
        conn.commit()
        flash("排班状态已更新", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"更新失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('registration.registration_manage'))
