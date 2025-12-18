from flask import Blueprint, render_template, request, redirect, url_for, flash
from db import get_db_connection
from utils import require_doctor

pharmacy_bp = Blueprint('pharmacy', __name__)


@pharmacy_bp.route('/pharmacy')
def pharmacy_manage():
    if not require_doctor():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    medicines = []
    pending_items = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT med_id, med_name, price, stock
                FROM medicine
                ORDER BY med_id DESC
            """)
            medicines = cursor.fetchall()

            # 待发药清单：已支付的处方，且未发药
            cursor.execute("""
                SELECT r.reg_id, p.name AS patient_name, p.medical_record_no,
                       d.name AS doctor_name, r.visit_date, r.shift,
                       pr.med_id, m.med_name, pr.total_quantity, pr.total_amount,
                       pr.dispense_status
                FROM prescription pr
                         JOIN registration r ON pr.reg_id = r.reg_id
                         JOIN patient p ON r.patient_id = p.patient_id
                         JOIN doctor d ON r.doctor_id = d.doctor_id
                         JOIN medicine m ON pr.med_id = m.med_id
                WHERE r.fee_status = '已支付'
                  AND IFNULL(pr.dispense_status, '未发药') != '已发药'
                ORDER BY r.reg_time DESC
            """)
            pending_items = cursor.fetchall()
    finally:
        conn.close()

    return render_template('pharmacy_manage.html', medicines=medicines, pending_items=pending_items)


@pharmacy_bp.route('/pharmacy/add', methods=['POST'])
def pharmacy_add():
    if not require_doctor():
        return redirect(url_for('auth.login'))

    med_name = request.form.get('med_name')
    price = request.form.get('price')
    stock = request.form.get('stock')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO medicine (med_name, price, stock)
                VALUES (%s, %s, %s)
            """, (med_name, price, stock))
        conn.commit()
        flash("已添加新药品", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"添加失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('pharmacy.pharmacy_manage'))


@pharmacy_bp.route('/pharmacy/update', methods=['POST'])
def pharmacy_update():
    if not require_doctor():
        return redirect(url_for('auth.login'))

    med_id = request.form.get('med_id')
    price = request.form.get('price')
    stock = request.form.get('stock')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE medicine SET price=%s, stock=%s WHERE med_id=%s
            """, (price, stock, med_id))
        conn.commit()
        flash("药品信息已更新", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"更新失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('pharmacy.pharmacy_manage'))


@pharmacy_bp.route('/pharmacy/delete/<int:med_id>')
def pharmacy_delete(med_id):
    if not require_doctor():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM medicine WHERE med_id=%s", (med_id,))
        conn.commit()
        flash("药品已下架", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"删除失败：{e}", 'error')
    finally:
        conn.close()
    return redirect(url_for('pharmacy.pharmacy_manage'))


@pharmacy_bp.route('/pharmacy/dispense', methods=['POST'])
def pharmacy_dispense():
    """
    发药：按 reg_id + med_id 对单条处方发药并扣减库存。
    """
    if not require_doctor():
        return redirect(url_for('auth.login'))

    reg_id = request.form.get('reg_id')
    med_id = request.form.get('med_id')

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 校验是否已支付
            cursor.execute("SELECT fee_status FROM registration WHERE reg_id=%s", (reg_id,))
            reg = cursor.fetchone()
            if not reg or reg['fee_status'] != '已支付':
                flash("未支付订单不可发药", 'error')
                return redirect(url_for('pharmacy.pharmacy_manage'))

            # 锁定处方行，避免并发重复发药
            cursor.execute("""
                SELECT total_quantity, dispense_status
                FROM prescription
                WHERE reg_id=%s AND med_id=%s
                LIMIT 1
                FOR UPDATE
            """, (reg_id, med_id))
            presc = cursor.fetchone()
            if not presc:
                flash("未找到对应处方", 'error')
                return redirect(url_for('pharmacy.pharmacy_manage'))
            if presc.get('dispense_status') == '已发药':
                flash("该药已发药，无需重复操作", 'info')
                return redirect(url_for('pharmacy.pharmacy_manage'))

            try:
                qty = int(presc['total_quantity'])
            except Exception:
                flash("处方数量异常，无法发药", 'error')
                conn.rollback()
                return redirect(url_for('pharmacy.pharmacy_manage'))
            if qty <= 0:
                flash("处方数量异常，无法发药", 'error')
                conn.rollback()
                return redirect(url_for('pharmacy.pharmacy_manage'))

            # 锁定库存行，避免并发超卖
            cursor.execute("SELECT stock FROM medicine WHERE med_id=%s FOR UPDATE", (med_id,))
            med = cursor.fetchone()
            if not med:
                flash("药品不存在", 'error')
                conn.rollback()
                return redirect(url_for('pharmacy.pharmacy_manage'))
            if int(med['stock']) < qty:
                flash("库存不足，无法发药", 'error')
                conn.rollback()
                return redirect(url_for('pharmacy.pharmacy_manage'))

            cursor.execute("UPDATE medicine SET stock = stock - %s WHERE med_id=%s", (qty, med_id))
            # 状态原子变更：只允许从“未发药”->“已发药”
            cursor.execute("""
                UPDATE prescription
                SET dispense_status='已发药', dispense_time=NOW()
                WHERE reg_id=%s AND med_id=%s AND dispense_status != '已发药'
            """, (reg_id, med_id))
            if cursor.rowcount != 1:
                flash("处方状态已变化，已取消本次发药", 'error')
                conn.rollback()
                return redirect(url_for('pharmacy.pharmacy_manage'))

        conn.commit()
        flash("发药成功，库存已扣减", 'success')
    except Exception as e:
        conn.rollback()
        flash(f"发药失败：{e}", 'error')
    finally:
        conn.close()

    return redirect(url_for('pharmacy.pharmacy_manage'))
