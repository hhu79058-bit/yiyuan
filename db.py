import pymysql
from datetime import datetime

DB_NAME = 'clinic_system'


def get_db_connection():
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='123456',  # 请根据实际密码修改
        database=DB_NAME,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    ensure_schema(conn)
    return conn


def table_exists(conn, table_name):
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema=%s AND table_name=%s
            LIMIT 1
        """, (DB_NAME, table_name))
        return cursor.fetchone() is not None


def column_exists(conn, table_name, column_name):
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s AND column_name=%s
            LIMIT 1
        """, (DB_NAME, table_name, column_name))
        return cursor.fetchone() is not None


def ensure_schema(conn):
    """
    兜底创建/补充挂号所需的表字段，避免列缺失导致运行错误。
    """
    try:
        with conn.cursor() as cursor:
            if not table_exists(conn, 'doctor_schedule'):
                cursor.execute("""
                    CREATE TABLE doctor_schedule (
                        schedule_id INT AUTO_INCREMENT PRIMARY KEY,
                        doctor_id INT NOT NULL,
                        schedule_date DATE NOT NULL,
                        shift VARCHAR(10) NOT NULL,
                        max_slots INT NOT NULL DEFAULT 20,
                        booked_slots INT NOT NULL DEFAULT 0,
                        status VARCHAR(10) NOT NULL DEFAULT '可用',
                        UNIQUE KEY uniq_doctor_date_shift (doctor_id, schedule_date, shift)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            else:
                # 针对已有表补全缺失列
                if not column_exists(conn, 'doctor_schedule', 'schedule_date'):
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN schedule_date DATE NOT NULL DEFAULT CURDATE();")
                if not column_exists(conn, 'doctor_schedule', 'shift'):
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN shift VARCHAR(10) NOT NULL DEFAULT '上午';")
                if not column_exists(conn, 'doctor_schedule', 'max_slots'):
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN max_slots INT NOT NULL DEFAULT 20;")
                if not column_exists(conn, 'doctor_schedule', 'booked_slots'):
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN booked_slots INT NOT NULL DEFAULT 0;")
                if not column_exists(conn, 'doctor_schedule', 'status'):
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN status VARCHAR(10) NOT NULL DEFAULT '可用';")
            if not column_exists(conn, 'registration', 'visit_date'):
                cursor.execute("ALTER TABLE registration ADD COLUMN visit_date DATE NULL AFTER reg_time;")
            if not column_exists(conn, 'registration', 'shift'):
                cursor.execute("ALTER TABLE registration ADD COLUMN shift VARCHAR(10) NOT NULL DEFAULT '全天' AFTER visit_date;")
            if not column_exists(conn, 'registration', 'fee_status'):
                cursor.execute("ALTER TABLE registration ADD COLUMN fee_status VARCHAR(20) NOT NULL DEFAULT '未支付' AFTER reg_fee;")
            if not column_exists(conn, 'registration', 'schedule_id'):
                cursor.execute("ALTER TABLE registration ADD COLUMN schedule_id INT NULL AFTER shift;")
            if not column_exists(conn, 'patient', 'medical_record_no'):
                cursor.execute("ALTER TABLE patient ADD COLUMN medical_record_no VARCHAR(32) NULL AFTER age;")
            if not column_exists(conn, 'patient', 'past_illness'):
                cursor.execute("ALTER TABLE patient ADD COLUMN past_illness VARCHAR(255) NULL AFTER allergy;")
            if not column_exists(conn, 'registration', 'check_fee'):
                cursor.execute("ALTER TABLE registration ADD COLUMN check_fee DECIMAL(10,2) NOT NULL DEFAULT 0 AFTER reg_fee;")
            if not column_exists(conn, 'registration', 'paid_time'):
                cursor.execute("ALTER TABLE registration ADD COLUMN paid_time DATETIME NULL AFTER fee_status;")
        conn.commit()
    except Exception as e:
        # 记录但不中断主流程
        print(f"[schema] ensure failed: {e}")


def generate_medical_record_no(conn):
    """
    生成唯一的病历号：MR + yyyyMMdd + 自增编号
    """
    today_str = datetime.now().strftime('%Y%m%d')
    with conn.cursor() as cursor:
        cursor.execute("SELECT IFNULL(MAX(patient_id),0) AS max_id FROM patient")
        max_id = cursor.fetchone()['max_id'] + 1
    return f"MR{today_str}{str(max_id).zfill(4)}"


def fetch_departments_and_doctors(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT dept_id, dept_name FROM department ORDER BY dept_name")
        departments = cursor.fetchall()

        cursor.execute("""
            SELECT d.doctor_id, d.name, d.title, d.reg_fee, d.dept_id, dept.dept_name
            FROM doctor d
                     JOIN department dept ON d.dept_id = dept.dept_id
            WHERE d.status = '正常'
            ORDER BY dept.dept_name, d.name
        """)
        doctors = cursor.fetchall()
    return departments, doctors


def create_registration_record(conn, patient_id, doctor_id, dept_id, visit_date, shift, fee_status='未支付'):
    """
    创建挂号记录，校验排班与号源，返回排队号。
    """
    with conn.cursor() as cursor:
        cursor.execute("SELECT reg_fee FROM doctor WHERE doctor_id=%s", (doctor_id,))
        doc = cursor.fetchone()
        if not doc:
            raise ValueError("医生不存在")

        cursor.execute("""
            SELECT schedule_id, max_slots, booked_slots, status
            FROM doctor_schedule
            WHERE doctor_id=%s AND schedule_date=%s AND shift=%s
            LIMIT 1
        """, (doctor_id, visit_date, shift))
        schedule = cursor.fetchone()
        if schedule:
            if schedule['status'] == '停诊':
                raise ValueError("该医生本班次停诊")
            if schedule['booked_slots'] >= schedule['max_slots']:
                raise ValueError("该班次号源已满")

        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM registration
            WHERE doctor_id=%s AND visit_date=%s AND shift=%s AND visit_status != '已取消'
        """, (doctor_id, visit_date, shift))
        count_res = cursor.fetchone()
        new_queue_num = count_res['cnt'] + 1

        cursor.execute("""
            INSERT INTO registration (patient_id, doctor_id, dept_id, reg_fee, visit_status, queue_num, reg_time,
                                      visit_date, shift, fee_status, schedule_id)
            VALUES (%s, %s, %s, %s, '未就诊', %s, NOW(), %s, %s, %s, %s)
        """, (patient_id, doctor_id, dept_id, doc['reg_fee'], new_queue_num, visit_date, shift, fee_status,
              schedule['schedule_id'] if schedule else None))

        if schedule:
            cursor.execute(
                "UPDATE doctor_schedule SET booked_slots = booked_slots + 1 WHERE schedule_id=%s",
                (schedule['schedule_id'],)
            )

        conn.commit()
        return new_queue_num


def update_schedule_booked(conn, schedule_id, delta):
    if not schedule_id:
        return
    with conn.cursor() as cursor:
        cursor.execute("""
            UPDATE doctor_schedule
            SET booked_slots = GREATEST(0, LEAST(max_slots, booked_slots + %s))
            WHERE schedule_id=%s
        """, (delta, schedule_id))
    conn.commit()
