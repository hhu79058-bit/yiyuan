from flask import Flask, redirect, url_for

from auth_routes import auth_bp
from registration_routes import reg_bp
from doctor_routes import doctor_bp
from patient_routes import patients_bp
from pharmacy_routes import pharmacy_bp
from payment_routes import payment_bp

app = Flask(__name__)
app.secret_key = 'clinic_secret_key_2025'

# 注册各业务蓝图
app.register_blueprint(auth_bp)
app.register_blueprint(reg_bp)
app.register_blueprint(doctor_bp)
app.register_blueprint(patients_bp)
app.register_blueprint(pharmacy_bp)
app.register_blueprint(payment_bp)


@app.route('/')
def index():
    return redirect(url_for('auth.login'))


if __name__ == '__main__':
    app.run(debug=True)
