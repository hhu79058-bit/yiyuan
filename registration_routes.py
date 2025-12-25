from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import (
    get_db_connection,
    fetch_departments_and_doctors,
    create_registration_record,
    generate_medical_record_no,
    update_schedule_booked,
    column_exists,
    log_operation,
)
from utils import require_admin

reg_bp = Blueprint('registration', __name__)

# 按小时分段的时间段，可按需调整
TIME_SLOTS = [f"{str(h).zfill(2)}:00-{str(h + 1).zfill(2)}:00" for h in range(8, 18)]


def _guess_shift(time_slot: str) -> str:
    """根据时间段推断班次，兼容旧逻辑。"""
    try:
        hour = int(time_slot.split(':')[0])
        if hour < 12:
            return '上午'
        elif hour < 18:
            return '下午'
        return '夜间'
    except Exception:
        return '全天'


@reg_bp.route('/patient_home')
def patient_home():
    if session.get('role') != 'patient':
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    doctors = []
    departments = []
    doctors_by_dept = []
    my_regs = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                  SELECT d.doctor_id, d.name, d.title, d.reg_fee, dept.dept_name, d.status
                  FROM doctor d
                           JOIN department dept ON d.dept_id = dept.dept_id
                  WHERE d.status = '正常'
                  ORDER BY dept.dept_name, d.name
                  """)
            doctors = cursor.fetchall()

            my_sql = """
                     SELECT r.reg_id, r.queue_num, r.visit_status, r.reg_time,
                            r.visit_date, r.shift, r.time_slot, r.fee_status,
                            d.name as doctor_name
                     FROM registration r
                              JOIN doctor d ON r.doctor_id = d.doctor_id
                     WHERE r.patient_id = %s
                     ORDER BY r.reg_time DESC
                     """
            cursor.execute(my_sql, (session['user_id'],))
            my_regs = cursor.fetchall()
            cursor.execute("SELECT dept_name FROM department ORDER BY dept_name")
            departments = cursor.fetchall()
    finally:
        conn.close()

    dept_map = {}
    for doc in doctors:
        dept_map.setdefault(doc['dept_name'], []).append(doc)
    for dept in departments:
        name = dept['dept_name']
        if name in dept_map:
            doctors_by_dept.append({'dept_name': name, 'doctors': dept_map[name]})
    for name, dept_docs in dept_map.items():
        if not any(d['dept_name'] == name for d in departments):
            doctors_by_dept.append({'dept_name': name, 'doctors': dept_docs})

    return render_template(
        'patient_home.html',
        patient_name=session['user_name'],
        doctors=doctors,
        departments=departments,
        doctors_by_dept=doctors_by_dept,
        my_regs=my_regs,
        time_slots=TIME_SLOTS,
        today=date.today().isoformat()
    )


@reg_bp.route('/book_appointment/<int:doctor_id>', methods=['POST', 'GET'])
def book_appointment(doctor_id):
    if session.get('role') != 'patient':
        return redirect(url_for('auth.login'))

    patient_id = session['user_id']
    visit_date = request.form.get('visit_date') or date.today().isoformat()
    time_slot = request.form.get('time_slot') or TIME_SLOTS[0]
    shift = request.form.get('shift') or _guess_shift(time_slot)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT dept_id, reg_fee FROM doctor WHERE doctor_id=%s", (doctor_id,))
            doc_info = cursor.fetchone()
            if not doc_info:
                flash("医生不存在", 'error')
                return redirect(url_for('registration.patient_home'))

        create_registration_record(
            conn,
            patient_id=patient_id,
            doctor_id=doctor_id,
            dept_id=doc_info['dept_id'],
            visit_date=visit_date,
            shift=shift,
            time_slot=time_slot,
            fee_status='未支付'
        )
        flash("挂号成功，请按时就诊", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"挂号失败：{e}", 'error')
    finally:
        conn.close()

    return redirect(url_for('registration.patient_home'))


@reg_bp.route('/registration/manage')
def registration_manage():
    if not require_admin():
        return redirect(url_for('auth.login'))

    selected_date = request.args.get('date') or date.today().isoformat()

    conn = get_db_connection()
    departments = []
    doctors = []
    today_regs = []
    dept_stats = []
    totals = {}
    schedules = []
    dept_doctors = []
    try:
        departments, doctors = fetch_departments_and_doctors(conn)
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.reg_id, r.queue_num, r.visit_status, r.visit_date, r.shift, r.time_slot, r.fee_status,
                       p.name AS patient_name, p.medical_record_no,
                       d.name AS doctor_name, dept.dept_name
                FROM registration r
                         JOIN patient p ON r.patient_id = p.patient_id
                         JOIN doctor d ON r.doctor_id = d.doctor_id
                         JOIN department dept ON r.dept_id = dept.dept_id
                WHERE r.visit_date = %s
                ORDER BY r.time_slot, r.queue_num
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
            has_work_date = column_exists(conn, 'doctor_schedule', 'work_date')
            has_shift = column_exists(conn, 'doctor_schedule', 'shift')
            has_time_slot = column_exists(conn, 'doctor_schedule', 'time_slot')
            has_max = column_exists(conn, 'doctor_schedule', 'max_slots')
            has_booked = column_exists(conn, 'doctor_schedule', 'booked_slots')
            has_status = column_exists(conn, 'doctor_schedule', 'status')

            if has_date:
                col_date = "s.schedule_date"
            elif has_work_date:
                col_date = "s.work_date AS schedule_date"
            else:
                col_date = "NULL AS schedule_date"
            col_shift = "s.shift" if has_shift else "'全天' AS shift"
            col_slot = "s.time_slot" if has_time_slot else "'09:00-10:00' AS time_slot"
            col_max = "s.max_slots" if has_max else "0 AS max_slots"
            col_booked = "s.booked_slots" if has_booked else "0 AS booked_slots"
            col_status = "s.status" if has_status else "'可用' AS status"

            schedule_sql = f"""
                SELECT s.schedule_id, {col_date}, {col_shift}, {col_slot}, {col_max}, {col_booked}, {col_status},
                       d.name AS doctor_name, dept.dept_name
                FROM doctor_schedule s
                         JOIN doctor d ON s.doctor_id = d.doctor_id
                         JOIN department dept ON d.dept_id = dept.dept_id
            """
            if has_date:
                schedule_sql += " WHERE s.schedule_date >= CURDATE()"
                schedule_sql += " ORDER BY doctor_name, s.schedule_date"
            elif has_work_date:
                schedule_sql += " WHERE s.work_date >= CURDATE()"
                schedule_sql += " ORDER BY doctor_name, s.work_date"
            else:
                schedule_sql += " ORDER BY doctor_name"

            cursor.execute(schedule_sql)
            schedules = cursor.fetchall()

            cursor.execute("""
                SELECT dept.dept_name, COUNT(d.doctor_id) AS doctor_count
                FROM department dept
                         LEFT JOIN doctor d ON d.dept_id = dept.dept_id
                GROUP BY dept.dept_name
                ORDER BY dept.dept_name
            """)
            dept_doctors = cursor.fetchall()
    finally:
        conn.close()

    return render_template(
        'registration_manage.html',
        selected_date=selected_date,
        departments=departments,
        doctors=doctors,
        today_regs=today_regs,
        dept_stats=dept_stats,
        totals=totals,
        schedules=schedules,
        dept_doctors=dept_doctors,
        time_slots=TIME_SLOTS
    )


@reg_bp.route('/registration/new', methods=['POST'])
def registration_new_patient():
    if not require_admin():
        return redirect(url_for('auth.login'))

    name = request.form.get('name')
    gender = request.form.get('gender')
    age = request.form.get('age')
    phone = request.form.get('phone')
    allergy = request.form.get('allergy')
    dept_id = request.form.get('dept_id')
    doctor_id = request.form.get('doctor_id')
    visit_date = request.form.get('visit_date')
    shift = request.form.get('shift') or '全天'
    time_slot = request.form.get('time_slot') or TIME_SLOTS[0]

    conn = get_db_connection()
    try:
        mr_no = generate_medical_record_no(conn)
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO patient (name, gender, age, phone, allergy, medical_record_no, password)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (name, gender, age, phone, allergy, mr_no, '123456'))
            patient_id = cursor.lastrowid

        create_registration_record(conn, patient_id, doctor_id, dept_id, visit_date, shift, time_slot, fee_status='未支付')
        flash(f"新患者挂号成功，病历号：{mr_no}", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"挂号失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('registration.registration_manage', date=visit_date))


@reg_bp.route('/registration/quick', methods=['POST'])
def registration_quick():
    if not require_admin():
        return redirect(url_for('auth.login'))

    keyword = request.form.get('keyword')
    dept_id = request.form.get('dept_id')
    doctor_id = request.form.get('doctor_id')
    visit_date = request.form.get('visit_date')
    shift = request.form.get('shift') or '全天'
    time_slot = request.form.get('time_slot') or TIME_SLOTS[0]

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

        create_registration_record(conn, patient['patient_id'], doctor_id, dept_id, visit_date, shift, time_slot, fee_status='未支付')
        flash(f"患者 {patient['name']} 挂号成功", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"挂号失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('registration.registration_manage', date=visit_date))


@reg_bp.route('/registration/cancel/<int:reg_id>')
def registration_cancel(reg_id):
    if not require_admin():
        return redirect(url_for('auth.login'))

    visit_date = None
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.visit_status, r.schedule_id, r.visit_date, p.name as patient_name
                FROM registration r
                JOIN patient p ON r.patient_id = p.patient_id
                WHERE r.reg_id=%s
            """, (reg_id,))
            reg = cursor.fetchone()
            if not reg:
                flash("挂号记录不存在", 'error')
                return redirect(url_for('registration.registration_manage'))
            
            visit_date = reg['visit_date']
            if reg['visit_status'] == '已取消':
                flash("该记录已取消，无需重复操作", 'info')
                return redirect(url_for('registration.registration_manage', date=visit_date))
            
            if reg['visit_status'] in ('已就诊', '就诊中'):
                flash(f"患者当前状态为【{reg['visit_status']}】，不可退号", 'error')
                return redirect(url_for('registration.registration_manage', date=visit_date))

            # 检查是否已产生处方且未作废
            cursor.execute("SELECT COUNT(*) as cnt FROM prescription WHERE reg_id=%s", (reg_id,))
            presc_count = cursor.fetchone()['cnt']
            if presc_count > 0:
                flash("该挂号已产生处方记录，请先联系医生或药房处理处方后再退号", 'error')
                return redirect(url_for('registration.registration_manage', date=visit_date))

            # 1. 更新订单状态
            if reg['visit_status'] == '未就诊':
                # 如果已支付，则标记为已退款（或由财务流程处理，这里演示标记为已退款）
                cursor.execute("""
                    UPDATE registration 
                    SET visit_status='已取消', 
                        fee_status = CASE WHEN fee_status='已支付' THEN '已退款' ELSE fee_status END
                    WHERE reg_id=%s
                """, (reg_id,))
            else:
                cursor.execute("UPDATE registration SET visit_status='已取消' WHERE reg_id=%s", (reg_id,))
            
            # 2. 释放号源
            update_schedule_booked(conn, reg['schedule_id'], -1)
            
            # 3. 记录操作日志
            log_operation(
                conn,
                operator_id=session.get('user_id'),
                operator_name=session.get('user_name'),
                operator_role=session.get('role'),
                op_type='退号',
                target_id=reg_id,
                detail=f"管理员退号：患者 {reg['patient_name']}，挂号ID {reg_id}。原状态：{reg['visit_status']}"
            )
            
        conn.commit()
        flash("已成功退号，号源已释放", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"操作失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('registration.registration_manage', date=visit_date or date.today().isoformat()))


@reg_bp.route('/registration/restore/<int:reg_id>')
def registration_restore(reg_id):
    if not require_admin():
        return redirect(url_for('auth.login'))

    visit_date = None
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.visit_status, r.schedule_id, r.visit_date, p.name as patient_name
                FROM registration r
                JOIN patient p ON r.patient_id = p.patient_id
                WHERE r.reg_id=%s
            """, (reg_id,))
            reg = cursor.fetchone()
            if not reg:
                flash("挂号记录不存在", 'error')
                return redirect(url_for('registration.registration_manage'))
            visit_date = reg['visit_date']
            if reg['visit_status'] != '已取消':
                flash("当前状态不可恢复", 'info')
                return redirect(url_for('registration.registration_manage', date=visit_date))

            cursor.execute("UPDATE registration SET visit_status='未就诊' WHERE reg_id=%s", (reg_id,))
            
            # 记录日志
            log_operation(
                conn,
                operator_id=session.get('user_id'),
                operator_name=session.get('user_name'),
                operator_role=session.get('role'),
                op_type='恢复挂号',
                target_id=reg_id,
                detail=f"管理员恢复挂号：患者 {reg['patient_name']}，挂号ID {reg_id}"
            )
            
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
    if not require_admin():
        return redirect(url_for('auth.login'))

    doctor_id = request.form.get('doctor_id')
    schedule_date = request.form.get('schedule_date')
    shift = request.form.get('shift') or '全天'
    time_slot = request.form.get('time_slot') or TIME_SLOTS[0]
    max_slots = request.form.get('max_slots')
    status = request.form.get('status')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            date_cols = []
            if column_exists(conn, 'doctor_schedule', 'schedule_date'):
                date_cols.append('schedule_date')
            if column_exists(conn, 'doctor_schedule', 'work_date'):
                date_cols.append('work_date')
            if not date_cols:
                date_cols.append('schedule_date')

            columns = ['doctor_id'] + date_cols + ['shift', 'time_slot', 'max_slots', 'booked_slots', 'status']
            placeholders = ', '.join(['%s'] * len(columns))
            col_list = ', '.join(columns)
            cursor.execute(
                f"""
                INSERT INTO doctor_schedule ({col_list})
                VALUES ({placeholders})
                ON DUPLICATE KEY UPDATE max_slots=VALUES(max_slots), status=VALUES(status), time_slot=VALUES(time_slot)
                """,
                [doctor_id] + [schedule_date] * len(date_cols) + [shift, time_slot, max_slots, 0, status]
            )
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
    if not require_admin():
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
