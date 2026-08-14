"""
notifier.py — 通知发送模块
支持：邮件(SMTP)、Server酱(微信)、Telegram Bot
"""

import smtplib
import logging
import requests as _requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
import config_manager as cfg

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 邮件通知
# ═══════════════════════════════════════════════════════════════

def send_email(subject: str, body_html: str) -> bool:
    """发送邮件通知。"""
    smtp_host = cfg.get("email_smtp_host")
    port_str = cfg.get("email_smtp_port", "465")
    smtp_port = int(port_str) if port_str else 465
    use_ssl = cfg.get("email_smtp_ssl", "true").lower() == "true"
    from_addr = cfg.get("email_from")
    password = cfg.get("email_password")
    to_addr = cfg.get("email_to")

    if not all([smtp_host, from_addr, password, to_addr]):
        logger.debug("邮件未配置，跳过")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.starttls()

        server.login(from_addr, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
        logger.info(f"✅ 邮件发送成功 → {to_addr}")
        return True

    except Exception as ex:
        logger.error(f"❌ 邮件发送失败: {ex}")
        return False


# ═══════════════════════════════════════════════════════════════
# Server酱（微信推送）
# ═══════════════════════════════════════════════════════════════

def send_serverchan(title: str, content: str) -> bool:
    """Server酱推送。"""
    key = cfg.get("serverchan_key")
    if not key:
        logger.debug("Server酱未配置，跳过")
        return False

    try:
        url = f"https://sctapi.ftqq.com/{key}.send"
        resp = _requests.post(
            url,
            data={"title": title, "desp": content},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") == 0 or data.get("errno") == 0:
            logger.info("✅ Server酱推送成功")
            return True
        else:
            logger.warning(f"Server酱推送异常: {data}")
            return False
    except Exception as ex:
        logger.error(f"❌ Server酱推送失败: {ex}")
        return False


# ═══════════════════════════════════════════════════════════════
# Telegram Bot
# ═══════════════════════════════════════════════════════════════

def send_telegram(message: str) -> bool:
    """Telegram Bot 推送。"""
    token = cfg.get("telegram_bot_token")
    chat_id = cfg.get("telegram_chat_id")
    if not token or not chat_id:
        logger.debug("Telegram 未配置，跳过")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = _requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=15,
        )
        data = resp.json()
        if data.get("ok"):
            logger.info("✅ Telegram 推送成功")
            return True
        else:
            logger.warning(f"Telegram 推送异常: {data}")
            return False
    except Exception as ex:
        logger.error(f"❌ Telegram 推送失败: {ex}")
        return False


# ═══════════════════════════════════════════════════════════════
# 统一推送（同时发送所有已配置的通知）
# ═══════════════════════════════════════════════════════════════

def notify_new_scores(new_scores: list, student_name: str = ""):
    """
    有新成绩时，通过所有已配置的渠道发送通知。
    """
    if cfg.get("push_enabled", "true").lower() == "false":
        logger.info("⏸️ 推送服务已关闭，跳过所有外部消息通知")
        return {}

    if not new_scores:
        return

    count = len(new_scores)
    name_tag = f"（{student_name}）" if student_name else ""

    # ── 构造消息内容 ─────────────────────────────────────────
    score_lines = []
    for s in new_scores:
        course_name = s.get("course_name", "")
        score_val = s.get("score_raw") or s.get("score", "")
        gp = s.get("grade_point")
        
        line = f"• {course_name}: {score_val}"
        if gp:
            line += f"（绩点 {gp}）"
            
        avg = s.get("avg_score")
        max_s = s.get("max_score")
        min_s = s.get("min_score")
        if avg is not None:
            line += f"\n  └─ 全班平均: {avg} | 最高分: {max_s} | 最低分: {min_s}"
            
        score_lines.append(line)

    plain_body = f"📊 新增 {count} 门成绩{name_tag}：\n\n" + "\n".join(score_lines)
    telegram_body = f"📊 *新增成绩提醒*{name_tag}\n\n" + "\n".join(score_lines)

    # ── HTML 邮件模板 ─────────────────────────────────────────
    rows_html = ""
    for s in new_scores:
        extra_html = ""
        if s.get("avg_score") is not None:
            extra_html = f"""
            <tr style="background-color:#161b22;border-bottom:1px solid #2d2d2d;">
              <td colspan="5" style="padding:4px 12px 12px;font-size:12px;color:#8b949e;text-align:left;">
                └─ 全班平均: <strong style="color:#c9d1d9;">{s.get('avg_score')}</strong> &nbsp;|&nbsp; 
                最高分: <strong style="color:#c9d1d9;">{s.get('max_score')}</strong> &nbsp;|&nbsp; 
                最低分: <strong style="color:#c9d1d9;">{s.get('min_score')}</strong>
              </td>
            </tr>
            """
        
        rows_html += f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;">{s.get('course_name','')}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;font-weight:bold;color:#7ee787;">
            {s.get('score_raw') or s.get('score','')}
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;">
            {s.get('grade_point','')}
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;">
            {s.get('credit','')}
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #2d2d2d;text-align:center;color:#8b949e;">
            {s.get('term','')}
          </td>
        </tr>
        {extra_html}
        """

    email_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',Arial,sans-serif;margin:0;padding:20px;">
      <div style="max-width:600px;margin:0 auto;background:#161b22;border-radius:12px;
                  border:1px solid #30363d;overflow:hidden;">
        <div style="background:linear-gradient(135deg,#1f6feb,#58a6ff);padding:24px 28px;">
          <h2 style="margin:0;color:#fff;font-size:20px;">📊 内蒙古大学成绩更新提醒</h2>
          <p style="margin:6px 0 0;color:rgba(255,255,255,0.8);font-size:14px;">
            新增 {count} 门成绩{name_tag}
          </p>
        </div>
        <div style="padding:24px 28px;">
          <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <thead>
              <tr style="color:#8b949e;font-size:12px;text-transform:uppercase;">
                <th style="padding:8px 12px;text-align:left;border-bottom:1px solid #30363d;">课程</th>
                <th style="padding:8px 12px;border-bottom:1px solid #30363d;">成绩</th>
                <th style="padding:8px 12px;border-bottom:1px solid #30363d;">绩点</th>
                <th style="padding:8px 12px;border-bottom:1px solid #30363d;">学分</th>
                <th style="padding:8px 12px;border-bottom:1px solid #30363d;">学期</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        <div style="padding:16px 28px;background:#0d1117;font-size:12px;color:#6e7681;text-align:center;">
          IMU JWXT Spider — 自动监控 · 实时提醒
        </div>
      </div>
    </body>
    </html>
    """

    # ── 发送 ──────────────────────────────────────────────────
    subject = f"📊 新成绩提醒{name_tag}：{count} 门成绩已发布"
    email_sent = send_email(subject, email_html)
    sc_sent = send_serverchan(subject, plain_body)
    tg_sent = send_telegram(telegram_body)

    results = {"email": email_sent, "serverchan": sc_sent, "telegram": tg_sent}
    logger.info(f"通知结果: {results}")
    return results


def notify_login_error(error_msg: str):
    """登录失败时发送告警。"""
    if cfg.get("push_enabled", "true").lower() == "false":
        logger.info("⏸️ 推送服务已关闭，跳过登录错误通知")
        return

    title = "⚠️ IMU Spider 登录失败"
    body = f"教务系统登录失败，请检查账号密码或网络。\n\n错误信息：{error_msg}"
    send_serverchan(title, body)
    send_telegram(f"⚠️ *登录失败*\n{error_msg}")
    send_email(title, f"<p>{body.replace(chr(10), '<br>')}</p>")
