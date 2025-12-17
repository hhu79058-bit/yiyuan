from flask import Blueprint, render_template, request, redirect, url_for, session
from db import get_db_connection

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
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
            if not user:
                error = '登录失败：账号或密码错误'
        except Exception as e:
            error = f"系统错误: {e}"
        finally:
            conn.close()
    return render_template('login.html', error=error)


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
