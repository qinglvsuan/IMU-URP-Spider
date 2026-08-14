"""
scheduler.py — 定时任务模块（基于 APScheduler）
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

import auth
import spider
import database as db
import notifier
import config_manager as cfg

logger = logging.getLogger(__name__)

# 全局 Session（登录态）
_session = None
_student_name = ""
_consecutive_failures = 0

def _ensure_session():
    """确保 Session 有效，必要时重新登录。"""
    global _session, _login_locked, _consecutive_failures
    username = cfg.get("imu_username")
    password = cfg.get("imu_password")

    if _session and auth.test_session_valid(_session):
        _consecutive_failures = 0
        return _session

    if _login_locked:
        logger.warning("因账号或密码错误，自动登录已锁定。请在设置中修改密码。")
        return None

    logger.info("Session 无效，重新登录...")
    try:
        _session = auth.login(username, password)
        _consecutive_failures = 0
        db.add_log("INFO", "✅ 登录成功")
        return _session
    except Exception as ex:
        err_msg = str(ex)
        _consecutive_failures += 1

        if "账号或密码错误" in err_msg:
            _login_locked = True
            logger.error("账号或密码错误，为防止账号被锁定，已暂停自动重试。请在设置中修改密码。")
            db.add_log("ERROR", "❌ 账号或密码错误，已暂停自动登录，请重设密码。")
            notifier.notify_login_error(err_msg)
        else:
            logger.error(f"登录失败 (连续{_consecutive_failures}次): {ex}")
            db.add_log("ERROR", f"❌ 登录失败: {ex}")
            # 只有当偶然失败（如验证码误判、网络超时）连续失败 >= 3 次时，才触发外部推送通知，避免偶发单次识别误判骚扰用户
            if _consecutive_failures >= 3:
                notifier.notify_login_error(f"连续{_consecutive_failures}次登录失败: {err_msg}")
        
        return None


def check_scores():
    """检查成绩更新（定时任务主逻辑）。"""
    global _student_name
    logger.info("▶ 开始检查成绩...")
    db.add_log("INFO", "开始检查成绩")

    session = _ensure_session()
    if not session:
        return

    import gc
    try:
        # 获取最新成绩
        scores = spider.fetch_all_scores(session)
        if not scores:
            logger.warning("未获取到成绩数据")
            db.add_log("WARN", "未获取到成绩数据")
            return

        # 与数据库对比，找出新成绩
        new_scores = db.upsert_scores(scores)

        if new_scores:
            logger.info(f"🎉 发现 {len(new_scores)} 门新成绩！")
            db.add_log("INFO", f"发现 {len(new_scores)} 门新成绩: " +
                       ", ".join(s.get("course_name", "") for s in new_scores))
            
            # 成绩变化时，同步更新本地缓存的 GPA
            try:
                gpa_data = spider.fetch_gpa(session)
                info = db.get_student_info()
                if info:
                    info["gpa"] = gpa_data.get("gpa", 0.0)
                    db.save_student_info(info)
            except Exception as e:
                logger.error(f"同步更新 GPA 失败: {e}")
                
            notifier.notify_new_scores(new_scores, _student_name)
        else:
            total = db.get_score_count()
            logger.info(f"✅ 成绩检查完毕，无更新（共 {total} 条）")
            db.add_log("INFO", f"成绩无更新，共 {total} 条")

    except Exception as ex:
        logger.error(f"成绩检查出错: {ex}")
        db.add_log("ERROR", f"成绩检查出错: {ex}")
    finally:
        gc.collect()


def refresh_all_data():
    """刷新所有数据（成绩+课表+学生信息），每次启动时执行一次。"""
    global _student_name
    session = _ensure_session()
    if not session:
        return

    try:
        # 学生信息与 GPA
        info = spider.fetch_student_info(session)
        if info:
            try:
                gpa_data = spider.fetch_gpa(session)
                info["gpa"] = gpa_data.get("gpa", 0.0)
            except Exception as e:
                logger.error(f"获取 GPA 失败: {e}")
                
            db.save_student_info(info)
            _student_name = info.get("name", "")
            logger.info(f"学生信息已更新: {info.get('name')}")

        # 成绩（首次全量导入，不触发通知）
        scores = spider.fetch_all_scores(session)
        if scores:
            db.upsert_scores(scores)  # 第一次运行时全部当作"已知"

        # 课表
        schedule = spider.fetch_schedule(session)
        if schedule and schedule.get("courses"):
            db.save_schedule(schedule["semester"], schedule["courses"])
            logger.info(f"课表已更新: {schedule['semester']}")

        db.add_log("INFO", "数据全量刷新完成")
    except Exception as ex:
        logger.error(f"数据刷新失败: {ex}")
        db.add_log("ERROR", f"数据刷新失败: {ex}")


def get_fresh_session():
    """供 Flask 路由调用，获取当前有效 Session。"""
    return _ensure_session()


def start(interval_minutes: int = 10) -> BackgroundScheduler:
    """启动定时任务调度器。"""
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    # 成绩检查（每N分钟）
    scheduler.add_job(
        check_scores,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="check_scores",
        name="成绩检查",
        misfire_grace_time=300,
        replace_existing=True,
    )

    scheduler.start()
    logger.info(f"⏰ 定时任务已启动，每 {interval_minutes} 分钟检查一次成绩")
    return scheduler
