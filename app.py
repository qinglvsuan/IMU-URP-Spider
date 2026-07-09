"""
app.py — Flask 主程序入口
"""

import os
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template

# 加载环境变量（.env 文件），作为 DB 配置的初始种子
load_dotenv(Path(__file__).parent / ".env")

import database as db
import spider
import notifier
import scheduler as sch
import config_manager as cfg

# ── 日志配置 ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Flask ─────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.urandom(24)


def get_panel_password():
    """面板密码从 DB 读取（支持运行时修改）。"""
    return cfg.get("panel_password", "")


# ── 简单密码保护中间件 ────────────────────────────────────────
@app.before_request
def check_auth():
    pw = get_panel_password()
    if not pw:
        return  # 未设置密码，跳过
    # 设置页本身（GET /api/config/all）即使未授权也可访问，
    # 防止配置了密码后前端完全无法工作
    if request.path in ("/api/config/all", "/"):
        return
    if request.path.startswith("/api/") or request.path.startswith("/static/"):
        token = request.headers.get("X-Panel-Token", "") or request.args.get("token", "")
        if token != pw:
            return jsonify({"error": "Unauthorized"}), 401


# ══════════════════════════════════════════════════════════════
# 前端页面
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ══════════════════════════════════════════════════════════════
# API 路由
# ══════════════════════════════════════════════════════════════

@app.route("/api/status")
def api_status():
    """系统状态。"""
    session = sch._session
    student = db.get_student_info()
    score_count = db.get_score_count()
    schedule = db.get_schedule()
    return jsonify({
        "logged_in": session is not None,
        "student": student,
        "score_count": score_count,
        "schedule_semester": schedule.get("semester", ""),
        "schedule_updated_at": schedule.get("updated_at", ""),
        "check_interval": cfg.get("check_interval", "10"),
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/api/login", methods=["POST"])
def api_login():
    """手动触发重新登录。"""
    try:
        import auth
        username = cfg.get("imu_username")
        password = cfg.get("imu_password")
        if not username or not password:
            return jsonify({"success": False, "message": "请先在设置中填写教务系统账号和密码"}), 400
        
        sch._login_locked = False
        session = auth.login(username, password)
        sch._session = session
        sch.refresh_all_data()
        db.add_log("INFO", "手动触发登录成功")
        return jsonify({"success": True, "message": "登录成功"})
    except Exception as ex:
        db.add_log("ERROR", f"手动登录失败: {ex}")
        return jsonify({"success": False, "message": str(ex)}), 500


@app.route("/api/scores")
def api_scores():
    """获取所有成绩。"""
    scores = db.get_all_scores()
    return jsonify({"scores": scores, "total": len(scores)})


@app.route("/api/scores/refresh", methods=["POST"])
def api_scores_refresh():
    """手动刷新成绩。"""
    session = sch.get_fresh_session()
    if not session:
        return jsonify({"success": False, "message": "未登录，请先在设置中填写账号并登录"}), 401
    try:
        scores = spider.fetch_all_scores(session)
        new_scores = db.upsert_scores(scores)
        if new_scores:
            student = db.get_student_info()
            notifier.notify_new_scores(new_scores, student.get("name", ""))
        db.add_log("INFO", f"手动刷新成绩，新增 {len(new_scores)} 条")
        return jsonify({
            "success": True,
            "total": len(scores),
            "new_count": len(new_scores),
            "new_scores": new_scores,
        })
    except Exception as ex:
        db.add_log("ERROR", f"成绩刷新失败: {ex}")
        return jsonify({"success": False, "message": str(ex)}), 500


@app.route("/api/schedule")
def api_schedule():
    """获取课表。"""
    return jsonify(db.get_schedule())


@app.route("/api/schedule/refresh", methods=["POST"])
def api_schedule_refresh():
    """手动刷新课表。"""
    session = sch.get_fresh_session()
    if not session:
        return jsonify({"success": False, "message": "未登录"}), 401
    try:
        schedule = spider.fetch_schedule(session)
        if schedule:
            db.save_schedule(schedule["semester"], schedule["courses"])
        db.add_log("INFO", "课表已刷新")
        return jsonify({"success": True, **schedule})
    except Exception as ex:
        db.add_log("ERROR", f"课表刷新失败: {ex}")
        return jsonify({"success": False, "message": str(ex)}), 500


@app.route("/api/gpa")
def api_gpa():
    """获取 GPA 和学分。GPA和学分均来自本地数据库缓存（由后台任务更新）。"""
    try:
        info = db.get_student_info()
        real_gpa = info.get("gpa", 0.0)
        
        # 获取本地学分统计
        scores = db.get_all_scores()
        total_credit = 0.0
        for s in scores:
            c = float(s.get("credit") or 0)
            if c > 0:
                total_credit += c
        
        return jsonify({
            "gpa": real_gpa,
            "credits_earned": round(total_credit, 1),
            "credits_required": 160.0  # 普遍的毕业要求学分估算值
        })
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


@app.route("/api/logs")
def api_logs():
    """获取操作日志。"""
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify({"logs": db.get_logs(limit)})


# ── 配置 API（核心新增）─────────────────────────────────────

@app.route("/api/config/all", methods=["GET"])
def api_config_all():
    """
    获取所有配置（密码类字段用掩码返回）。
    该接口无需 token 验证，以便前端在未配置密码时也能读取设置。
    """
    return jsonify(cfg.get_all(mask_secrets=True))


@app.route("/api/config/save", methods=["POST"])
def api_config_save():
    """
    保存配置（接受 JSON body）。
    掩码值 "••••••••" 会被自动跳过，不覆盖原有密钥。
    保存成功后若账号密码发生变化，自动重置 session。
    """
    updates = request.get_json(force=True, silent=True) or {}
    if not updates:
        return jsonify({"success": False, "message": "请求体为空"}), 400

    # 检测账号密码是否变化（变化则需重新登录）
    old_user = cfg.get("imu_username")
    old_pass = cfg.get("imu_password")

    results = cfg.save(updates)
    db.add_log("INFO", f"配置已更新: {list(results.keys())}")

    # 若账号密码变化，清除旧 session 并重置锁定状态
    new_user = cfg.get("imu_username")
    new_pass = cfg.get("imu_password")
    session_reset = False
    if old_user != new_user or old_pass != new_pass:
        sch._session = None
        sch._login_locked = False
        session_reset = True
        db.add_log("INFO", "账号密码已变更，Session 已重置，请重新登录")

    # 若检查间隔有变化，重新调度定时任务
    if "check_interval" in results and results["check_interval"] == "ok":
        try:
            new_interval = int(cfg.get("check_interval", "10"))
            sch._scheduler_ref.reschedule_job(
                "check_scores",
                trigger="interval",
                minutes=new_interval,
            )
            db.add_log("INFO", f"定时任务间隔已更新为 {new_interval} 分钟")
        except Exception:
            pass  # 若 scheduler 还未启动则跳过

    return jsonify({
        "success": True,
        "results": results,
        "session_reset": session_reset,
    })


@app.route("/api/notify/test", methods=["POST"])
def api_notify_test():
    """发送测试通知。"""
    student = db.get_student_info()
    fake_score = [{
        "course_name": "测试课程（高等数学）",
        "score": 95,
        "score_raw": "95",
        "grade_point": 4.0,
        "credit": 4.0,
        "term": "2024-2025-2",
    }]
    result = notifier.notify_new_scores(fake_score, student.get("name", ""))
    db.add_log("INFO", "发送测试通知")
    return jsonify({"success": True, "results": result})


# ══════════════════════════════════════════════════════════════
# 启动
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 初始化数据库
    db.init_db()
    logger.info("数据库初始化完成")

    # 将 .env 中的值作为初始配置写入 DB（不覆盖已有 DB 配置）
    cfg.seed_from_env()

    # 首次全量刷新（异步，不阻塞启动）
    import threading
    t = threading.Thread(target=sch.refresh_all_data, daemon=True)
    t.start()

    # 启动定时任务
    interval_str = cfg.get("check_interval", "10")
    interval = int(interval_str) if interval_str else 10
    _scheduler = sch.start(interval)

    # 把 scheduler 引用存到 sch 模块，供动态修改间隔使用
    sch._scheduler_ref = _scheduler

    # 启动 Flask
    port = int(os.getenv("PORT", "5000"))
    logger.info(f"🚀 IMU Spider 启动，访问 http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
