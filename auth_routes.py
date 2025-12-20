from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from db import (
    get_db_connection,
    DEFAULT_ADMIN_PHONE,
    DEFAULT_ADMIN_PASSWORD,
    generate_medical_record_no,
)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # 已登录用户无需重复登录，直接跳转到对应首页
    role = session.get('role')
    if role == 'doctor':
        return redirect(url_for('doctor.dashboard'))
    if role == 'admin':
        return redirect(url_for('doctor.admin_home'))
    if role == 'patient':
        return redirect(url_for('registration.patient_home'))

    error = None
    if request.method == 'POST':
        role = request.form.get('role')
        phone = request.form.get('phone')
        password = request.form.get('password')

        conn = get_db_connection()
        user = None
        try:
            with conn.cursor() as cursor:
                if role == 'doctor':
                    sql = "SELECT * FROM doctor WHERE phone = %s AND password = %s"
                    cursor.execute(sql, (phone, password))
                    user = cursor.fetchone()
                    if user:
                        session['role'] = 'doctor'
                        session['user_id'] = user['doctor_id']
                        session['user_name'] = user['name']
                        return redirect(url_for('doctor.dashboard'))
                elif role == 'patient':
                    sql = "SELECT * FROM patient WHERE phone = %s AND password = %s"
                    cursor.execute(sql, (phone, password))
                    user = cursor.fetchone()
                    if user:
                        session['role'] = 'patient'
                        session['user_id'] = user['patient_id']
                        session['user_name'] = user['name']
                        return redirect(url_for('registration.patient_home'))
                elif role == 'admin':
                    sql = "SELECT * FROM admin_user WHERE phone = %s AND password = %s"
                    cursor.execute(sql, (phone, password))
                    user = cursor.fetchone()
                    if user:
                        session['role'] = 'admin'
                        session['user_id'] = user['admin_id']
                        session['user_name'] = user['name']
                        return redirect(url_for('doctor.admin_home'))
            if not user:
                error = '登录失败：账号或密码错误'
        except Exception as e:
            error = f"系统错误: {e}"
        finally:
            conn.close()
    return render_template(
        'login.html',
        error=error,
        admin_phone=DEFAULT_ADMIN_PHONE,
        admin_password=DEFAULT_ADMIN_PASSWORD,
    )


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        gender = request.form.get('gender')
        age = request.form.get('age')
        phone = request.form.get('phone')
        password = request.form.get('password')
        allergy = request.form.get('allergy') or ''

        if not name or not gender or not age or not phone or not password:
            flash('请完整填写注册信息。', 'error')
            return render_template('register.html')

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM patient WHERE phone=%s LIMIT 1", (phone,))
                if cursor.fetchone():
                    flash('该手机号已注册，请直接登录。', 'error')
                    return render_template('register.html')

                mr_no = generate_medical_record_no(conn)
                cursor.execute("""
                    INSERT INTO patient (name, gender, age, phone, allergy, medical_record_no, password)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (name, gender, age, phone, allergy, mr_no, password))
            conn.commit()
            flash('注册成功，请登录。', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            conn.rollback()
            flash(f'注册失败：{e}', 'error')
        finally:
            conn.close()

    return render_template('register.html')
