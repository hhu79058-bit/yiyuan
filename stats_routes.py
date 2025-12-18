from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, session
from db import get_db_connection
from utils import require_doctor

stats_bp = Blueprint('stats', __name__)


def _date_condition(field_visit_date, field_reg_time):
    """
    兼容旧数据：visit_date 为空时用 reg_time 的日期。
    返回 SQL 片段（带 2 个占位符）：
        (visit_date = %s OR (visit_date IS NULL AND DATE(reg_time) = %s))
    """
    return f"({field_visit_date} = %s OR ({field_visit_date} IS NULL AND DATE({field_reg_time}) = %s))"


@stats_bp.route('/stats')
def daily_stats():
    if not require_doctor():
        return redirect(url_for('auth.login'))

    selected_date = request.args.get('date') or date.today().isoformat()

    conn = get_db_connection()
    summary = {}
    dept_rows = []
    doctor_rows = []
    medicine_rows = []
    try:
        with conn.cursor() as cursor:
            cond = _date_condition("r.visit_date", "r.reg_time")

            # 1) 总挂号 / 取消 / 已支付 / 未支付
            cursor.execute(f"""
                SELECT
                    COUNT(*) AS reg_total,
                    SUM(CASE WHEN r.visit_status = '已取消' THEN 1 ELSE 0 END) AS reg_cancelled,
                    SUM(CASE WHEN r.fee_status = '已支付' THEN 1 ELSE 0 END) AS reg_paid,
                    SUM(CASE WHEN r.fee_status != '已支付' OR r.fee_status IS NULL THEN 1 ELSE 0 END) AS reg_unpaid,
                    SUM(CASE WHEN r.visit_status = '就诊中' THEN 1 ELSE 0 END) AS visiting,
                    SUM(CASE WHEN r.visit_status = '已就诊' THEN 1 ELSE 0 END) AS visited
                FROM registration r
                WHERE {cond}
            """, (selected_date, selected_date))
            summary = cursor.fetchone() or {}

            # 2) 收入汇总：挂号费/检查费/药费/总额（按已支付统计更合理）
            cursor.execute(f"""
                SELECT
                    SUM(r.reg_fee) AS reg_fee_sum,
                    SUM(IFNULL(r.check_fee, 0)) AS check_fee_sum,
                    SUM(IFNULL(pf.med_fee, 0)) AS med_fee_sum,
                    SUM(r.reg_fee + IFNULL(r.check_fee, 0) + IFNULL(pf.med_fee, 0)) AS total_fee_sum
                FROM registration r
                LEFT JOIN (
                    SELECT reg_id, SUM(total_amount) AS med_fee
                    FROM prescription
                    GROUP BY reg_id
                ) pf ON pf.reg_id = r.reg_id
                WHERE {cond} AND r.fee_status = '已支付' AND r.visit_status != '已取消'
            """, (selected_date, selected_date))
            paid_fee = cursor.fetchone() or {}
            summary.update({
                'paid_reg_fee_sum': paid_fee.get('reg_fee_sum') or 0,
                'paid_check_fee_sum': paid_fee.get('check_fee_sum') or 0,
                'paid_med_fee_sum': paid_fee.get('med_fee_sum') or 0,
                'paid_total_fee_sum': paid_fee.get('total_fee_sum') or 0,
            })

            # 3) 今日病历数（反映接诊完成度）
            cursor.execute("""
                SELECT COUNT(*) AS mr_count
                FROM medical_record mr
                         JOIN registration r ON mr.reg_id = r.reg_id
                WHERE (r.visit_date = %s OR (r.visit_date IS NULL AND DATE(r.reg_time) = %s))
            """, (selected_date, selected_date))
            summary['mr_count'] = (cursor.fetchone() or {}).get('mr_count') or 0

            # 4) 科室挂号分布（不含取消）
            cursor.execute(f"""
                SELECT dept.dept_name,
                       COUNT(*) AS cnt
                FROM registration r
                         JOIN department dept ON r.dept_id = dept.dept_id
                WHERE {cond} AND r.visit_status != '已取消'
                GROUP BY dept.dept_name
                ORDER BY cnt DESC
            """, (selected_date, selected_date))
            dept_rows = cursor.fetchall() or []

            total_active = sum(int(x['cnt']) for x in dept_rows) if dept_rows else 0
            for row in dept_rows:
                row['ratio'] = (float(row['cnt']) / total_active * 100) if total_active else 0

            # 5) 医生接诊/挂号分布
            cursor.execute(f"""
                SELECT d.name AS doctor_name,
                       COUNT(*) AS reg_cnt,
                       SUM(CASE WHEN r.visit_status = '已就诊' THEN 1 ELSE 0 END) AS done_cnt
                FROM registration r
                         JOIN doctor d ON r.doctor_id = d.doctor_id
                WHERE {cond} AND r.visit_status != '已取消'
                GROUP BY d.name
                ORDER BY reg_cnt DESC
            """, (selected_date, selected_date))
            doctor_rows = cursor.fetchall() or []

            # 6) 今日已发药药品 TOP（按已发药处方数量累计）
            cursor.execute(f"""
                SELECT m.med_name,
                       SUM(pr.total_quantity) AS qty_sum
                FROM prescription pr
                         JOIN registration r ON pr.reg_id = r.reg_id
                         JOIN medicine m ON pr.med_id = m.med_id
                WHERE {cond} AND pr.dispense_status = '已发药'
                GROUP BY m.med_name
                ORDER BY qty_sum DESC
                LIMIT 10
            """, (selected_date, selected_date))
            medicine_rows = cursor.fetchall() or []
    finally:
        conn.close()

    return render_template('stats_daily.html',
                           selected_date=selected_date,
                           summary=summary,
                           dept_rows=dept_rows,
                           doctor_rows=doctor_rows,
                           medicine_rows=medicine_rows)
