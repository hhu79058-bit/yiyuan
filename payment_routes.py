from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection, column_exists
from utils import require_admin

payment_bp = Blueprint('cashier', __name__)


@payment_bp.route('/cashier')
def cashier_page():
    if session.get('role') == 'patient':
        return redirect(url_for('cashier.patient_payments'))
    if not require_admin():
        return redirect(url_for('auth.login'))

    selected_date = request.args.get('date') or date.today().isoformat()
    status_filter = request.args.get('status', 'all')

    conn = get_db_connection()
    rows = []
    totals = {'count': 0, 'amount': 0}
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT r.reg_id, r.reg_fee, IFNULL(r.check_fee, 0) AS check_fee,
                       r.fee_status, r.visit_status, r.visit_date, r.shift, r.paid_time,
                       p.name AS patient_name, p.medical_record_no,
                       d.name AS doctor_name,
                       IFNULL((
                            SELECT SUM(pr.total_amount) FROM prescription pr WHERE pr.reg_id = r.reg_id
                       ), 0) AS med_fee
                FROM registration r
                    JOIN patient p ON r.patient_id = p.patient_id
                    JOIN doctor d ON r.doctor_id = d.doctor_id
                WHERE r.visit_date = %s
            """
            params = [selected_date]
            if status_filter == 'unpaid':
                sql += " AND r.fee_status = '未支付'"
            elif status_filter == 'paid':
                sql += " AND r.fee_status = '已支付'"
            sql += " ORDER BY r.visit_date DESC, r.reg_id DESC"

            cursor.execute(sql, params)
            rows = cursor.fetchall()

        # 计算合计
        for r in rows:
            total_fee = float(r['reg_fee']) + float(r['check_fee']) + float(r['med_fee'])
            r['total_fee'] = total_fee
            totals['count'] += 1
            totals['amount'] += total_fee
    finally:
        conn.close()

    return render_template('cash_register.html',
                           rows=rows,
                           selected_date=selected_date,
                           status_filter=status_filter,
                           totals=totals)


@payment_bp.route('/cashier/pay/<int:reg_id>', methods=['POST'])
def cashier_pay(reg_id):
    if not require_admin():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 允许重复提交时保持已支付状态
            cursor.execute("""
                UPDATE registration
                SET fee_status='已支付', paid_time=NOW()
                WHERE reg_id=%s
            """, (reg_id,))
        conn.commit()
        flash("支付状态已更新为已支付", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"支付更新失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('cashier.cashier_page'))


# ============ 患者自助支付 ============ #


@payment_bp.route('/patient/payments')
def patient_payments():
    if session.get('role') != 'patient':
        return redirect(url_for('auth.login'))

    patient_id = session.get('user_id')
    conn = get_db_connection()
    rows = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.reg_id, r.reg_time, r.visit_date, r.shift, r.fee_status,
                       r.reg_fee, IFNULL(r.check_fee, 0) AS check_fee,
                       d.name AS doctor_name,
                       IFNULL((SELECT SUM(pr.total_amount) FROM prescription pr WHERE pr.reg_id = r.reg_id), 0) AS med_fee
                FROM registration r
                         JOIN doctor d ON r.doctor_id = d.doctor_id
                WHERE r.patient_id = %s
                ORDER BY r.reg_time DESC
            """, (patient_id,))
            rows = cursor.fetchall()

        for r in rows:
            r['total_fee'] = float(r['reg_fee']) + float(r['check_fee']) + float(r['med_fee'])
    finally:
        conn.close()

    return render_template('patient_payments.html', rows=rows)


@payment_bp.route('/patient/pay/<int:reg_id>', methods=['POST'])
def patient_pay(reg_id):
    if session.get('role') != 'patient':
        return redirect(url_for('auth.login'))

    patient_id = session.get('user_id')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 确认该挂号属于当前患者
            cursor.execute("SELECT patient_id FROM registration WHERE reg_id=%s", (reg_id,))
            reg = cursor.fetchone()
            if not reg or reg['patient_id'] != patient_id:
                flash("无权操作该订单", 'error')
                return redirect(url_for('cashier.patient_payments'))

            cursor.execute("""
                UPDATE registration
                SET fee_status='已支付', paid_time=NOW()
                WHERE reg_id=%s
            """, (reg_id,))
        conn.commit()
        flash("支付成功", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"支付失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('cashier.patient_payments'))
