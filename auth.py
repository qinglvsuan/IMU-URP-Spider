"""
auth.py — IMU 教务系统登录模块
支持清华 URP 综合教务系统（如内蒙古大学所使用的版本）
"""

import requests
import logging
import hashlib
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://jwxt.imu.edu.cn"
LOGIN_URL = f"{BASE_URL}/login"
LOGIN_ACTION = f"{BASE_URL}/j_spring_security_check"
CAPTCHA_URL = f"{BASE_URL}/img/captcha.jpg"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

def _urp_encrypt_password(password: str) -> str:
    """
    清华 URP 系统的密码加密逻辑。
    对应 JS: hex_md5(hex_md5(pwd), '1.8') + '*' + hex_md5(hex_md5(pwd, '1.8'), '1.8')
    - 缺省 ver 时，附加 "{Urp602019}"
    - ver 为 '1.8' 时，不附加后缀
    """
    def md5(s: str) -> str:
        return hashlib.md5(s.encode('utf-8')).hexdigest()
    
    # 左半部分: MD5( MD5(password + "{Urp602019}") )
    part1 = md5(md5(password + "{Urp602019}"))
    
    # 右半部分: MD5( MD5(password) )
    part2 = md5(md5(password))
    
    return f"{part1}*{part2}"


def create_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    return s


def login(username: str, password: str) -> requests.Session:
    """
    登录清华 URP 系统。
    流程：
    1. GET /login 获取页面 tokenValue
    2. GET /img/captcha.jpg 获取验证码并用 ddddocr 识别
    3. POST /j_spring_security_check 进行登录
    """
    session = create_session()

    # ── Step 1: 获取登录页，提取 CSRF (tokenValue) ──────────────
    try:
        logger.info(f"访问登录页: {LOGIN_URL}")
        resp = session.get(LOGIN_URL, timeout=15)
        resp.raise_for_status()
    except Exception as ex:
        raise RuntimeError(f"无法访问教务系统登录页面: {ex}")

    soup = BeautifulSoup(resp.text, "lxml")
    
    token_input = soup.find("input", id="tokenValue")
    token_value = token_input.get("value", "") if token_input else ""
    if not token_value:
        logger.warning("未能在页面上找到 tokenValue，可能会登录失败")

    # ── Step 2: 获取并识别验证码 ─────────────────────────────────
    captcha_code = ""
    try:
        logger.info(f"获取验证码: {CAPTCHA_URL}")
        # 加入时间戳防止缓存
        import time
        c_url = f"{CAPTCHA_URL}?_={int(time.time()*1000)}"
        c_resp = session.get(c_url, timeout=10, headers={"Referer": LOGIN_URL})
        
        if c_resp.status_code == 200 and len(c_resp.content) > 100:
            import ddddocr
            import gc
            ocr = ddddocr.DdddOcr(show_ad=False)
            captcha_code = ocr.classification(c_resp.content)
            logger.info(f"✅ 验证码识别结果: {captcha_code}")
            # 显式释放 ONNX 模型占用的内存
            del ocr
            gc.collect()
        else:
            logger.warning("验证码图片获取失败或为空")
    except Exception as ex:
        logger.error(f"验证码处理异常: {ex}")

    # ── Step 3: 加密密码并提交表单 ───────────────────────────────
    encrypted_pwd = _urp_encrypt_password(password)
    
    form_data = {
        "j_username": username,
        "j_password": encrypted_pwd,
        "j_captcha": captcha_code,
        "tokenValue": token_value,
        "lang": "zh"
    }

    logger.info("提交登录表单...")
    try:
        login_resp = session.post(
            LOGIN_ACTION,
            data=form_data,
            headers={
                "Referer": LOGIN_URL,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=True, # URP 成功后通常 302 重定向到 index
            timeout=20,
        )
    except Exception as ex:
        raise RuntimeError(f"登录请求失败: {ex}")

    # ── Step 4: 判断登录结果 ─────────────────────────────────────
    resp_text = login_resp.text
    
    # 检查URL或页面内容
    if "errorCode=badCaptcha" in login_resp.url or "验证码错误" in resp_text:
        raise RuntimeError("验证码错误")
    if "errorCode=badCredentials" in login_resp.url or "密码错误" in resp_text or "用户名或密码" in resp_text:
        raise RuntimeError("账号或密码错误")
    
    # 成功后通常会跳转到带有注销/欢迎信息的页面，或者直接就是后台框架页
    if "j_username" not in resp_text and "j_password" not in resp_text:
        logger.info("✅ 登录成功！")
        return session

    raise RuntimeError("登录失败，请检查账号密码或教务系统状态。")


def test_session_valid(session: requests.Session) -> bool:
    """检测 Session 是否有效。"""
    try:
        # 使用随意一个需登录的后台接口进行探测
        test_url = f"{BASE_URL}/student/rollManagement/rollInfo/index"
        resp = session.get(test_url, timeout=10, allow_redirects=False)
        if resp.status_code in (301, 302):
            location = resp.headers.get("Location", "")
            if "login" in location.lower():
                return False
        if resp.status_code == 200 and "j_username" not in resp.text:
            return True
        return False
    except Exception:
        return False


def get_cookies_dict(session: requests.Session) -> dict:
    return dict(session.cookies)

