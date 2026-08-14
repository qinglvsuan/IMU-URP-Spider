"""
config_manager.py — 配置中心
优先级：SQLite DB > .env 环境变量 > 默认值

首次启动时自动将 .env 中的值写入 DB 作为初始配置。
之后通过 WebUI 修改配置时，直接写入 DB，不再依赖 .env。
"""

import os
import logging
import database as db

logger = logging.getLogger(__name__)

# 所有配置项的默认值（用于前端展示与类型推断）
DEFAULTS = {
    "imu_username":       "",
    "imu_password":       "",
    "check_interval":     "10",
    "panel_username":     "",
    "panel_password":     "",
    # 服务开关
    "spider_enabled":     "true",
    "push_enabled":       "true",
    # 邮件
    "email_smtp_host":    "smtp.qq.com",
    "email_smtp_port":    "465",
    "email_smtp_ssl":     "true",
    "email_from":         "",
    "email_password":     "",
    "email_to":           "",
    # Server酱
    "serverchan_key":     "",
    # Telegram
    "telegram_bot_token": "",
    "telegram_chat_id":   "",
}

# .env 中的键名 → DB 键名 映射
ENV_MAPPING = {
    "IMU_USERNAME":        "imu_username",
    "IMU_PASSWORD":        "imu_password",
    "CHECK_INTERVAL":      "check_interval",
    "PANEL_USERNAME":      "panel_username",
    "PANEL_PASSWORD":      "panel_password",
    "SPIDER_ENABLED":      "spider_enabled",
    "PUSH_ENABLED":        "push_enabled",
    "EMAIL_SMTP_HOST":     "email_smtp_host",
    "EMAIL_SMTP_PORT":     "email_smtp_port",
    "EMAIL_SMTP_SSL":      "email_smtp_ssl",
    "EMAIL_FROM":          "email_from",
    "EMAIL_PASSWORD":      "email_password",
    "EMAIL_TO":            "email_to",
    "SERVERCHAN_KEY":      "serverchan_key",
    "TELEGRAM_BOT_TOKEN":  "telegram_bot_token",
    "TELEGRAM_CHAT_ID":    "telegram_chat_id",
}


def seed_from_env():
    """
    将 .env 中存在的非空值写入 DB（仅在 DB 中该键不存在时写入，不覆盖用户已有设置）。
    """
    seeded = 0
    for env_key, db_key in ENV_MAPPING.items():
        env_val = os.getenv(env_key, "")
        if env_val and db.get_config(db_key) is None:
            db.set_config(db_key, env_val)
            seeded += 1
    if seeded:
        logger.info(f"从 .env 初始化了 {seeded} 项配置到数据库")


def get(key: str, default: str = "") -> str:
    """读取一项配置（DB 优先，其次 DEFAULTS）。"""
    val = db.get_config(key)
    if val is not None:
        return val
    return DEFAULTS.get(key, default)


def get_all(mask_secrets: bool = True) -> dict:
    """
    读取所有配置项。
    mask_secrets=True 时，密码类字段返回掩码字符串（用于前端展示）。
    """
    SECRET_KEYS = {"imu_password", "email_password", "serverchan_key", "telegram_bot_token", "panel_password"}
    result = {}
    for key in DEFAULTS:
        val = get(key)
        if mask_secrets and key in SECRET_KEYS and val:
            result[key] = "••••••••"
        else:
            result[key] = val
    return result


def save(updates: dict) -> dict:
    """
    批量保存配置。
    - 忽略掩码值（不把 "••••••••" 写回 DB）
    - 返回 {key: "ok"|"skipped"} 的结果字典
    """
    MASK = "••••••••"
    results = {}
    for key, val in updates.items():
        if key not in DEFAULTS:
            results[key] = "unknown_key"
            continue
        if val == MASK:
            results[key] = "skipped"
            continue
        db.set_config(key, str(val).strip())
        results[key] = "ok"
    return results
