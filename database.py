"""
database.py — SQLite 数据持久化模块
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "spider.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构。"""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scores (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                course_code TEXT,
                course_name TEXT NOT NULL,
                credit      REAL DEFAULT 0,
                score       REAL,
                score_raw   TEXT,
                grade_point REAL DEFAULT 0,
                term        TEXT,
                exam_type   TEXT,
                course_nature TEXT,
                created_at  TEXT DEFAULT (datetime('now', 'localtime')),
                UNIQUE(course_code, term)
            );

            CREATE TABLE IF NOT EXISTS schedule (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                semester   TEXT,
                data_json  TEXT,
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS student_info (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                data_json  TEXT,
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                level      TEXT NOT NULL,
                message    TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
    logger.info("数据库初始化完成")


# ── 成绩 ──────────────────────────────────────────────────────

def upsert_scores(scores: list) -> list:
    """
    插入/更新成绩，返回本次新增的成绩列表。
    """
    new_scores = []
    with get_conn() as conn:
        for s in scores:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO scores
                        (course_code, course_name, credit, score, score_raw,
                         grade_point, term, exam_type, course_nature)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        s.get("course_code", ""),
                        s.get("course_name", ""),
                        s.get("credit", 0),
                        s.get("score"),
                        s.get("score_raw", ""),
                        s.get("grade_point", 0),
                        s.get("term", ""),
                        s.get("exam_type", ""),
                        s.get("course_nature", ""),
                    ),
                )
                if cursor.lastrowid:
                    new_scores.append(s)
            except sqlite3.IntegrityError:
                # 记录已存在，跳过
                pass
    return new_scores


def get_all_scores() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scores ORDER BY term DESC, course_name"
        ).fetchall()
        return [dict(r) for r in rows]


def get_score_count() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]


# ── 课表 ──────────────────────────────────────────────────────

def save_schedule(semester: str, courses: list):
    with get_conn() as conn:
        conn.execute("DELETE FROM schedule")
        conn.execute(
            "INSERT INTO schedule (semester, data_json) VALUES (?, ?)",
            (semester, json.dumps(courses, ensure_ascii=False)),
        )


def get_schedule() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM schedule ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            return {
                "semester": row["semester"],
                "courses": json.loads(row["data_json"]),
                "updated_at": row["updated_at"],
            }
        return {"semester": "", "courses": [], "updated_at": ""}


# ── 学生信息 ──────────────────────────────────────────────────

def save_student_info(info: dict):
    with get_conn() as conn:
        conn.execute("DELETE FROM student_info")
        conn.execute(
            "INSERT INTO student_info (data_json) VALUES (?)",
            (json.dumps(info, ensure_ascii=False),),
        )


def get_student_info() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM student_info ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            return json.loads(row["data_json"])
        return {}


# ── 日志 ──────────────────────────────────────────────────────

def add_log(level: str, message: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (level, message) VALUES (?, ?)",
            (level, message),
        )
        # 保留最近500条
        conn.execute(
            "DELETE FROM logs WHERE id NOT IN "
            "(SELECT id FROM logs ORDER BY id DESC LIMIT 500)"
        )


def get_logs(limit: int = 100) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ── 配置 ──────────────────────────────────────────────────────

def get_config(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_config(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
