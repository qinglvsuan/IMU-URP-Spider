"""
spider.py — IMU 教务系统数据抓取模块
"""

import logging
import re
import json
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://jwxt.imu.edu.cn"

# ── API 端点 ─────────────────────────────────────────────────
URLS = {
    "academic_info": f"{BASE_URL}/main/academicInfo",
    "student_info": f"{BASE_URL}/student/rollManagement/rollInfo/index",
    "scores_page": f"{BASE_URL}/student/integratedQuery/scoreQuery/allPassingScores/index",
    "schedule": f"{BASE_URL}/student/courseSelect/thisSemesterCurriculum/ajaxStudentSchedule/callback",
    "current_scores": f"{BASE_URL}/student/integratedQuery/scoreQuery/thisTermScores/index",
}

JSON_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


def fetch_student_info(session) -> dict:
    """
    获取学生基本信息：姓名、学号、专业、班级等。
    返回 dict。
    """
    try:
        resp = session.get(URLS["student_info"], timeout=15)
        resp.raise_for_status()

        # 尝试 JSON
        try:
            data = resp.json()
            if isinstance(data, dict):
                return {
                    "name": data.get("xm", data.get("name", "")),
                    "student_id": data.get("xh", data.get("studentId", "")),
                    "major": data.get("zymc", data.get("major", "")),
                    "class_name": data.get("bjmc", data.get("className", "")),
                    "college": data.get("xymc", data.get("college", "")),
                    "grade": data.get("njdm_id", data.get("grade", "")),
                }
        except Exception:
            pass

        # HTML 解析 (适配 URP 的页面结构)
        soup = BeautifulSoup(resp.text, "lxml")
        info = {}
        
        # 尝试从 span 提取（如：欢迎您，张三）
        for span in soup.find_all("span"):
            text = span.get_text(strip=True)
            if "欢迎您，" in text:
                info["name"] = text.replace("欢迎您，", "").strip()
            elif "学号：" in text:
                info["student_id"] = text.replace("学号：", "").strip()
            elif "院系：" in text:
                info["college"] = text.replace("院系：", "").strip()
                if not info.get("major"):
                    info["major"] = info["college"]
            elif "专业：" in text:
                info["major"] = text.replace("专业：", "").strip()
            elif "班级：" in text:
                info["class_name"] = text.replace("班级：", "").strip()

        # 如果通过 span 没找到名字，再尝试传统的 .name 类名
        if not info.get("name"):
            name_tag = soup.find(class_="name")
            if name_tag:
                info["name"] = name_tag.get_text(strip=True)
        return info

    except Exception as ex:
        logger.error(f"获取学生信息失败: {ex}")
        return {}


def fetch_gpa(session) -> dict:
    """
    获取学业信息（GPA、学分等）。
    返回 dict: {gpa, credits_earned, credits_required}
    """
    try:
        resp = session.post(
            URLS["academic_info"],
            data={},
            headers=JSON_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            item = data[0]
        elif isinstance(data, dict):
            item = data
        else:
            return {}

        return {
            "gpa": float(item.get("gpa", item.get("jd", 0)) or 0),
            "credits_earned": float(item.get("yxf", item.get("creditsEarned", 0)) or 0),
            "credits_required": float(item.get("bxyxf", item.get("creditsRequired", 0)) or 0),
        }
    except Exception as ex:
        logger.error(f"获取GPA失败: {ex}")
        return {}


def fetch_all_scores(session) -> list:
    """
    获取所有已通过成绩。
    返回 list of dict:
      [{course_name, course_code, credit, score, grade_point, term, exam_type}, ...]
    """
    try:
        # 先访问成绩页面，从中提取真实数据接口 URL
        resp = session.get(URLS["scores_page"], timeout=15)
        resp.raise_for_status()

        # 方式1: 从 HTML 中提取 var url 变量（NiuHK 项目方式）
        url_match = re.search(r'var\s+url\s*=\s*["\']([^"\']+)["\']', resp.text)
        if url_match:
            score_api_url = BASE_URL + url_match.group(1)
            logger.info(f"成绩API URL: {score_api_url}")
            
            # 清华 URP 的 callback 接口一般使用 GET
            if "callback" in score_api_url:
                api_resp = session.get(score_api_url, headers=JSON_HEADERS, timeout=15)
            else:
                api_resp = session.post(score_api_url, data={}, headers=JSON_HEADERS, timeout=15)
                
            api_resp.raise_for_status()
            return _parse_scores_json(api_resp.json())

        # 方式2: 直接尝试标准成绩接口
        for path in [
            "/jwglxt/cjcx/cjcxDgxqcjList_dcxDgxqcjList.html",
            "/student/integratedQuery/scoreQuery/allPassingScores/data",
        ]:
            try:
                r = session.post(
                    BASE_URL + path,
                    data={"_search": "false", "nd": "", "queryModel.showCount": "1000",
                          "queryModel.currentPage": "1", "queryModel.sortName": "",
                          "queryModel.sortOrder": "asc"},
                    headers=JSON_HEADERS,
                    timeout=15,
                )
                if r.status_code == 200:
                    return _parse_scores_json(r.json())
            except Exception:
                continue

        # 方式3: 从 HTML 表格中解析
        return _parse_scores_html(resp.text)

    except Exception as ex:
        logger.error(f"获取成绩失败: {ex}")
        return []


def _parse_scores_json(data) -> list:
    """解析成绩 JSON 响应。"""
    scores = []
    items = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # 常见的分页格式
        for key in ["items", "rows", "list", "data", "datas"]:
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
                
        # 针对清华 URP 的历年成绩 lnList (学期列表 -> cjList 课程列表)
        if not items and "lnList" in data and isinstance(data["lnList"], list):
            items = []
            for term_data in data["lnList"]:
                if isinstance(term_data, dict):
                    for k, v in term_data.items():
                        if isinstance(v, list):
                            items.extend(v)

        if not items and "datas" in data:
            datas = data["datas"]
            if isinstance(datas, dict):
                for v in datas.values():
                    if isinstance(v, list):
                        items = v
                        break
        
        if not items:
            logger.error(f"未能解析成绩 JSON，原始数据键: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            # 强行打印整个结构以便分析
            logger.error(f"完整 JSON 结构: {json.dumps(data, ensure_ascii=False)[:2000]}")

    for item in items:
        if not isinstance(item, dict):
            continue
        score_val = item.get("cj", item.get("score", item.get("courseScore", item.get("zcj", ""))))
        try:
            score_float = float(score_val) if score_val not in ("", None) else None
        except (ValueError, TypeError):
            score_float = None

        # 清华 URP 系统的 courseCode 和 term 都在 id 里面
        item_id = item.get("id", {})
        course_code = item.get("kch", item.get("courseCode", item_id.get("courseNumber", item.get("kch_id", ""))))
        term = item.get("xnxq", item.get("term", item_id.get("executiveEducationPlanNumber", item.get("xnxqdm", ""))))
        
        # 去掉学期数字最后一个没有意义的数字，仅当存在 3 个连字符时进行，例如 "2024-2025-1-2" -> "2024-2025-1"
        if term and term.count('-') == 3:
            term = term.rsplit('-', 1)[0]
            
        # 映射考核方式
        exam_type_code = item.get("examTypeCode", item.get("ksxz", item.get("examType", "")))
        exam_type_map = {"01": "考试", "02": "考查", "03": "免修", "04": "缓考", "05": "补考", "06": "重修"}
        exam_type = exam_type_map.get(exam_type_code, exam_type_code)

        scores.append({
            "course_name": item.get("kcmc", item.get("courseName", item.get("kcm", ""))),
            "course_code": course_code,
            "credit": float(item.get("xf", item.get("credit", 0)) or 0),
            "score": score_float,
            "score_raw": str(score_val),
            "grade_point": float(item.get("jd", item.get("gradePointScore", item.get("gradePoint", 0))) or 0),
            "term": term,
            "exam_type": exam_type,
            "course_nature": item.get("kcxzmc", item.get("courseAttributeName", item.get("courseNature", ""))),
        })

    logger.info(f"解析到 {len(scores)} 条成绩记录")
    return scores


def _parse_scores_html(html: str) -> list:
    """从 HTML 表格中解析成绩（备用方案）。"""
    soup = BeautifulSoup(html, "lxml")
    scores = []
    table = soup.find("table")
    if not table:
        return scores

    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    for row in table.find_all("tr")[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if not cells:
            continue
        row_dict = dict(zip(headers, cells))

        score_val = row_dict.get("成绩", "")
        try:
            score_float = float(score_val)
        except (ValueError, TypeError):
            score_float = None

        scores.append({
            "course_name": row_dict.get("课程名称", ""),
            "course_code": row_dict.get("课程代码", ""),
            "credit": float(row_dict.get("学分", 0) or 0),
            "score": score_float,
            "score_raw": score_val,
            "grade_point": float(row_dict.get("绩点", 0) or 0),
            "term": row_dict.get("学年学期", ""),
            "exam_type": row_dict.get("考核方式", ""),
            "course_nature": row_dict.get("课程性质", ""),
        })
    return scores


def fetch_schedule(session) -> dict:
    """
    获取本学期课表。
    返回 dict: {
      semester: "2024-2025第二学期",
      courses: [{name, teacher, location, weeks, weekday, periods}]
    }
    """
    try:
        resp = session.get(
            URLS["schedule"],
            headers=JSON_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        result = {"semester": "", "courses": []}

        # 提取学期信息
        if isinstance(data, dict):
            # 清华 URP 的课表 JSON 结构
            xkxx = data.get("xkxx", [])
            if xkxx:
                for course_dict in xkxx:
                    for key, item in course_dict.items():
                        if not isinstance(item, dict): continue
                        
                        # 解析时间和地点（URP 中在 timeAndPlaceList 内）
                        time_place = item.get("timeAndPlaceList", [{}])
                        tp = time_place[0] if time_place else {}
                        
                        start_period = tp.get("classSessions", "")
                        duration = tp.get("continuingSession", 1)
                        try:
                            start_p = int(start_period)
                            dur = int(duration)
                            if dur > 1:
                                periods_str = f"{start_p}-{start_p + dur - 1}节"
                            else:
                                periods_str = f"{start_p}节"
                        except (ValueError, TypeError):
                            periods_str = f"{start_period}节"

                        result["courses"].append({
                            "name": item.get("courseName", ""),
                            "teacher": item.get("attendClassTeacher", "").replace("*", "").strip(),
                            "location": tp.get("teachingBuildingName", "") + tp.get("classroomName", ""),
                            "weeks": tp.get("classWeek", ""),
                            "weekday": int(tp.get("classDay", 0) or 0),
                            "periods": periods_str,
                            "credit": float(item.get("unit", 0) or 0),
                        })

            # 如果不是清华 URP，走原有正方逻辑
            date_list = data.get("dateList", [{}])
            if date_list and not xkxx:
                first = date_list[0] if isinstance(date_list, list) else {}
                result["semester"] = first.get("programPlanName", first.get("xqmc", ""))

                kbList = data.get("kbList", data.get("courseList", data.get("list", [])))
                for item in kbList:
                    if not isinstance(item, dict):
                        continue
                    result["courses"].append({
                        "name": item.get("kcmc", item.get("name", "")),
                        "teacher": item.get("xm", item.get("teacher", "")),
                        "location": item.get("cdmc", item.get("location", "")),
                        "weeks": item.get("zcd", item.get("weeks", "")),
                        "weekday": int(item.get("xqj", item.get("weekday", 0)) or 0),
                        "periods": item.get("jcdm", item.get("periods", "")),
                        "credit": float(item.get("xf", 0) or 0),
                    })

        logger.info(f"获取课表成功，共 {len(result['courses'])} 门课")
        return result

    except Exception as ex:
        logger.error(f"获取课表失败: {ex}")
        return {"semester": "", "courses": []}


def fetch_current_term_scores(session) -> list:
    """获取本学期成绩（用于检测新成绩）。"""
    try:
        resp = session.get(URLS["current_scores"], timeout=15)
        resp.raise_for_status()

        url_match = re.search(r'var\s+url\s*=\s*["\']([^"\']+)["\']', resp.text)
        if url_match:
            api_url = BASE_URL + url_match.group(1)
            if "callback" in api_url:
                r = session.get(api_url, headers=JSON_HEADERS, timeout=15)
            else:
                r = session.post(api_url, data={}, headers=JSON_HEADERS, timeout=15)
            r.raise_for_status()
            return _parse_scores_json(r.json())

        # fallback: use all scores but filter current term
        return []
    except Exception as ex:
        logger.error(f"获取本学期成绩失败: {ex}")
        return []
