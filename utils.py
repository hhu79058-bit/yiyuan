from flask import session


def require_login():
    """
    简单登录校验，未登录返回 False。
    """
    if not session.get('role'):
        return False
    return True


def require_doctor():
    """
    医生/后台权限校验（doctor 或 admin）。
    """
    if session.get('role') not in ('doctor', 'admin'):
        return False
    return True


def require_admin():
    """
    管理员权限校验（admin）。
    """
    if session.get('role') != 'admin':
        return False
    return True
