医学信息学大作业：诊疗通（Clinic System）

本项目是一个基于 Flask + PyMySQL 的小型门诊/挂号系统演示，用于课程大作业。

角色与入口

- 仅两种角色：患者 / 医生
- 患者端顶部导航仅保留“收银台（自助支付）”
- 医生端可进行挂号、接诊、处方、药房、收费、统计、患者档案等操作

 快速开始

1. 安装依赖：
   bash
   pip install flask pymysql
   

2. 配置数据库连接：编辑 `db.py` 中的 `host/user/password/DB_NAME`
3. 确保已创建数据库（默认 `clinic_system`），并已有基础表：`patient`、`doctor`、`department`、`registration`、`medicine`、`medical_record` 等（按你的建表脚本为准）
   - 程序启动时会兜底：自动创建缺失的 `doctor_schedule` / `prescription` 表，并补齐部分缺失字段，减少运行时报列缺失与页面出现 None 的情况
4. 启动项目：

   ```bash
   python app.py
   ```

5. 打开登录页：`http://127.0.0.1:5000/login`

## 主要页面（路由）

- 登录/退出：`/login`、`/logout`
- 患者首页：`/patient_home`
- 患者个人中心（维护过敏史/既往病史）：`/patient/profile`
- 患者自助缴费：`/patient/payments`
- 医生工作台：`/doctor_dashboard`
- 挂号管理（H1-H5）：`/registration/manage`
- 患者档案管理（P1-P3）：`/patients`
- 药房管理（S1-S2）：`/pharmacy`
- 收银台（F1，医生端）：`/cashier`
- 统计报表（T1）：`/stats`

## 已实现功能清单

- 模块一 挂号管理（H1-H5）：新患者挂号、老患者快速挂号、今日挂号列表、统计汇总、医生排班（号源/停诊）
- 支持按小时精确选择就诊时间段，排班与挂号均可按时间段设置
- 模块二 患者信息管理（P1-P3）：医生端患者档案创建/查询/维护；患者端可维护过敏史与既往病史
- 模块三 医生看诊（D1-D3）：候诊列表、叫号、就诊状态流转（待就诊→就诊中→已完成）、快速查看患者信息/历史
- 模块四 病历书写（M1）：电子病历（主诉/现病史/初步诊断）
- 模块五 处方管理（R1-R2）：开具处方、用法用量与金额计算、库存检查提示
- 模块六 药房管理（S1-S2）：药品 CRUD、发药并扣减库存（含并发重复发药保护）
- 模块七 统计报表（T1）：今日挂号/接诊/收费汇总、科室比例、医生统计、已发药 TOP
- 模块八 收费管理（F1）：挂号费+检查费+药费合并展示；支付状态（未支付→已支付），支持患者自助支付

## 代码结构（模块化拆分）

- `app.py`：Flask 应用与蓝图注册
- `db.py`：数据库连接 + 自动建表/补字段/默认值回填
- `auth_routes.py`：登录/退出
- `registration_routes.py`：挂号管理、排班管理、患者首页挂号
- `doctor_routes.py`：医生工作台/接诊/病历/处方
- `patient_routes.py`：患者档案（医生端）+ 患者个人中心
- `pharmacy_routes.py`：药房管理、发药
- `payment_routes.py`：收银台、患者自助支付
- `stats_routes.py`：统计报表
- `templates/`：页面模板（统一继承 `base.html`）
- `static/`：静态资源（`app.css`、登录背景等）

## GitHub 一键更新

在项目根目录执行：

```bash
git add .
git commit -m "update"
git push
```
