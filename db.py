import pymysql
from datetime import datetime

DB_NAME = 'clinic_system'
DEFAULT_ADMIN_NAME = '管理员'
DEFAULT_ADMIN_PHONE = 'admin'
DEFAULT_ADMIN_PASSWORD = '123456'
_SCHEMA_READY = False


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


def get_schedule_date_column(conn):
    if column_exists(conn, 'doctor_schedule', 'schedule_date'):
        return 'schedule_date'
    if column_exists(conn, 'doctor_schedule', 'work_date'):
        return 'work_date'
    return 'schedule_date'


def ensure_schema(conn):
    """
    兜底创建/补充挂号所需的表字段，避免列缺失导致运行错误。
    """
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    try:
        with conn.cursor() as cursor:
            if not table_exists(conn, 'doctor_schedule'):
                cursor.execute("""
                    CREATE TABLE doctor_schedule (
                        schedule_id INT AUTO_INCREMENT PRIMARY KEY,
                        doctor_id INT NOT NULL,
                        schedule_date DATE NOT NULL,
                        shift VARCHAR(10) NOT NULL,
                        time_slot VARCHAR(20) NOT NULL DEFAULT '09:00-10:00',
                        max_slots INT NOT NULL DEFAULT 20,
                        booked_slots INT NOT NULL DEFAULT 0,
                        status VARCHAR(10) NOT NULL DEFAULT '可用',
                        UNIQUE KEY uniq_doctor_date_slot (doctor_id, schedule_date, time_slot),
                        KEY idx_doctor_date_slot (doctor_id, schedule_date, time_slot)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            else:
                # 针对已有表补全缺失列
                if not column_exists(conn, 'doctor_schedule', 'schedule_date'):
                    # 避免在部分 MySQL 版本上使用函数作为默认值导致失败
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN schedule_date DATE NULL;")
                if not column_exists(conn, 'doctor_schedule', 'shift'):
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN shift VARCHAR(10) NOT NULL DEFAULT '上午';")
                if not column_exists(conn, 'doctor_schedule', 'time_slot'):
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN time_slot VARCHAR(20) NOT NULL DEFAULT '09:00-10:00' AFTER shift;")
                if not column_exists(conn, 'doctor_schedule', 'max_slots'):
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN max_slots INT NOT NULL DEFAULT 20;")
                if not column_exists(conn, 'doctor_schedule', 'booked_slots'):
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN booked_slots INT NOT NULL DEFAULT 0;")
                if not column_exists(conn, 'doctor_schedule', 'status'):
                    cursor.execute("ALTER TABLE doctor_schedule ADD COLUMN status VARCHAR(10) NOT NULL DEFAULT '可用';")
                # 调整唯一索引，支持同一医生同一天多个时间段
                cursor.execute("SHOW INDEX FROM doctor_schedule WHERE Key_name='uniq_doctor_date_shift'")
                if cursor.fetchone():
                    try:
                        cursor.execute("ALTER TABLE doctor_schedule DROP INDEX uniq_doctor_date_shift")
                    except Exception:
                        pass
                cursor.execute("SHOW INDEX FROM doctor_schedule WHERE Key_name='uniq_doctor_date_slot'")
                if not cursor.fetchone():
                    try:
                        cursor.execute(
                            "ALTER TABLE doctor_schedule ADD UNIQUE KEY uniq_doctor_date_slot (doctor_id, schedule_date, time_slot)"
                        )
                    except Exception:
                        pass
                if column_exists(conn, 'doctor_schedule', 'work_date') and column_exists(conn, 'doctor_schedule', 'schedule_date'):
                    cursor.execute("""
                        UPDATE doctor_schedule
                        SET schedule_date = work_date
                        WHERE schedule_date IS NULL AND work_date IS NOT NULL
                    """)

            # 确保 prescription 表存在（药房发药/收费依赖）
            if not table_exists(conn, 'prescription'):
                cursor.execute("""
                    CREATE TABLE prescription (
                        presc_id INT AUTO_INCREMENT PRIMARY KEY,
                        reg_id INT NOT NULL,
                        med_id INT NOT NULL,
                        dosage VARCHAR(50) NULL,
                        med_usage VARCHAR(255) NULL,
                        total_quantity INT NOT NULL DEFAULT 0,
                        total_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
                        dispense_status VARCHAR(20) NOT NULL DEFAULT '未发药',
                        dispense_time DATETIME NULL,
                        KEY idx_reg (reg_id),
                        KEY idx_med (med_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            if not column_exists(conn, 'registration', 'visit_date'):
                cursor.execute("ALTER TABLE registration ADD COLUMN visit_date DATE NULL AFTER reg_time;")
            if not column_exists(conn, 'registration', 'shift'):
                cursor.execute("ALTER TABLE registration ADD COLUMN shift VARCHAR(10) NOT NULL DEFAULT '全天' AFTER visit_date;")
            if not column_exists(conn, 'registration', 'time_slot'):
                cursor.execute("ALTER TABLE registration ADD COLUMN time_slot VARCHAR(20) NOT NULL DEFAULT '09:00-10:00' AFTER shift;")
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
            if not column_exists(conn, 'prescription', 'dispense_status'):
                cursor.execute("ALTER TABLE prescription ADD COLUMN dispense_status VARCHAR(20) NOT NULL DEFAULT '未发药';")
            if not column_exists(conn, 'prescription', 'dispense_time'):
                cursor.execute("ALTER TABLE prescription ADD COLUMN dispense_time DATETIME NULL;")
            # 医生叫号记录
            if not column_exists(conn, 'registration', 'called_time'):
                cursor.execute("ALTER TABLE registration ADD COLUMN called_time DATETIME NULL;")
            if not column_exists(conn, 'registration', 'call_times'):
                cursor.execute("ALTER TABLE registration ADD COLUMN call_times INT NOT NULL DEFAULT 0;")

            # ===== 数据回填：避免页面出现 None =====
            # 1) 病历号为空的患者：用 patient_id 生成稳定且唯一的病历号
            if column_exists(conn, 'patient', 'medical_record_no'):
                cursor.execute("""
                    UPDATE patient
                    SET medical_record_no = CONCAT('MR', LPAD(patient_id, 8, '0'))
                    WHERE medical_record_no IS NULL OR medical_record_no = ''
                """)

            # 2) 就诊日期为空的挂号：默认使用 reg_time 的日期
            if column_exists(conn, 'registration', 'visit_date'):
                cursor.execute("""
                    UPDATE registration
                    SET visit_date = DATE(reg_time)
                    WHERE visit_date IS NULL AND reg_time IS NOT NULL
                """)
            # 3) 班次为空：给默认值，避免展示 None
            if column_exists(conn, 'registration', 'shift'):
                cursor.execute("""
                    UPDATE registration
                    SET shift = '全天'
                    WHERE shift IS NULL OR shift = ''
                """)
            # 3.1) 时间段为空：给默认值
            if column_exists(conn, 'registration', 'time_slot'):
                cursor.execute("""
                    UPDATE registration
                    SET time_slot = '09:00-10:00'
                    WHERE time_slot IS NULL OR time_slot = ''
                """)

            # 4) 排班日期为空：给默认值，避免列表展示 None
            if column_exists(conn, 'doctor_schedule', 'schedule_date'):
                cursor.execute("""
                    UPDATE doctor_schedule
                    SET schedule_date = CURDATE()
                    WHERE schedule_date IS NULL
                """)
            if column_exists(conn, 'doctor_schedule', 'time_slot'):
                cursor.execute("""
                    UPDATE doctor_schedule
                    SET time_slot = '09:00-10:00'
                    WHERE time_slot IS NULL OR time_slot = ''
                """)

            # 管理员账号：单独表，避免依赖 doctor/department 结构
            if not table_exists(conn, 'admin_user'):
                cursor.execute("""
                    CREATE TABLE admin_user (
                        admin_id INT AUTO_INCREMENT PRIMARY KEY,
                        name VARCHAR(50) NOT NULL,
                        phone VARCHAR(32) NOT NULL UNIQUE,
                        password VARCHAR(64) NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
            # 确保默认管理员账号存在
            cursor.execute("SELECT 1 FROM admin_user WHERE phone=%s LIMIT 1", (DEFAULT_ADMIN_PHONE,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO admin_user (name, phone, password) VALUES (%s, %s, %s)",
                    (DEFAULT_ADMIN_NAME, DEFAULT_ADMIN_PHONE, DEFAULT_ADMIN_PASSWORD)
                )
        conn.commit()
        _SCHEMA_READY = True
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


def create_registration_record(conn, patient_id, doctor_id, dept_id, visit_date, shift, time_slot, fee_status='未支付'):
    """
    创建挂号记录，校验排班与号源，返回排队号。
    """
    with conn.cursor() as cursor:
        cursor.execute("SELECT reg_fee FROM doctor WHERE doctor_id=%s", (doctor_id,))
        doc = cursor.fetchone()
        if not doc:
            raise ValueError("医生不存在")

        date_col = get_schedule_date_column(conn)
        schedule = None
        if date_col:
            cursor.execute(f"""
                SELECT 1
                FROM doctor_schedule
                WHERE doctor_id=%s AND {date_col}=%s AND shift='全天' AND status='停诊'
                LIMIT 1
            """, (doctor_id, visit_date))
            if cursor.fetchone():
                raise ValueError("该医生当天停诊")

            cursor.execute(f"""
                SELECT schedule_id, max_slots, booked_slots, status
                FROM doctor_schedule
                WHERE doctor_id=%s AND {date_col}=%s AND time_slot=%s AND shift IN (%s, '全天')
                LIMIT 1
            """, (doctor_id, visit_date, time_slot, shift))
            schedule = cursor.fetchone()
        if schedule:
            if schedule['status'] == '停诊':
                raise ValueError("该医生本时段停诊")
            if schedule['booked_slots'] >= schedule['max_slots']:
                raise ValueError("该班次号源已满")

        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM registration
            WHERE doctor_id=%s AND visit_date=%s AND shift=%s AND time_slot=%s AND visit_status != '已取消'
        """, (doctor_id, visit_date, shift, time_slot))
        count_res = cursor.fetchone()
        new_queue_num = count_res['cnt'] + 1

        cursor.execute("""
            INSERT INTO registration (patient_id, doctor_id, dept_id, reg_fee, visit_status, queue_num, reg_time,
                                      visit_date, shift, time_slot, fee_status, schedule_id)
            VALUES (%s, %s, %s, %s, '未就诊', %s, NOW(), %s, %s, %s, %s, %s)
        """, (patient_id, doctor_id, dept_id, doc['reg_fee'], new_queue_num, visit_date, shift, time_slot, fee_status,
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
