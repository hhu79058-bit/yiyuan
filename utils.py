from flask import session


def require_login():
    """
    简单登录校验，未登录返回 False。
    """
    if not session.get('role'):
        return False
    return True
