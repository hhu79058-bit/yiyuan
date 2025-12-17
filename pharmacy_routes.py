from flask import Blueprint, render_template, request, redirect, url_for, flash
from db import get_db_connection
from utils import require_login

pharmacy_bp = Blueprint('pharmacy', __name__)


@pharmacy_bp.route('/pharmacy')
def pharmacy_manage():
    if not require_login():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    medicines = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT med_id, med_name, price, stock
                FROM medicine
                ORDER BY med_id DESC
            """)
            medicines = cursor.fetchall()
    finally:
        conn.close()

    return render_template('pharmacy_manage.html', medicines=medicines)


@pharmacy_bp.route('/pharmacy/add', methods=['POST'])
def pharmacy_add():
    if not require_login():
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
    if not require_login():
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
    if not require_login():
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
