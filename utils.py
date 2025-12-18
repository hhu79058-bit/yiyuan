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
    医生/后台权限校验（当前项目用 doctor 充当前台/管理员）。
    """
    if session.get('role') != 'doctor':
        return False
    return True
