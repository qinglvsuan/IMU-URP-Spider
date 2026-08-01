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
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
    except Exception:
        pass
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
                avg_score   REAL,
                max_score   REAL,
                min_score   REAL,
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
        # 自动迁移检查：补全旧版本 SQLite 缺失的列
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(scores)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        for col, col_type in [("avg_score", "REAL"), ("max_score", "REAL"), ("min_score", "REAL")]:
            if col not in existing_cols:
                try:
                    conn.execute(f"ALTER TABLE scores ADD COLUMN {col} {col_type}")
                    logger.info(f"✅ 数据库迁移：为 scores 表新增 {col} 字段")
                except Exception as e:
                    logger.error(f"迁移 {col} 字段失败: {e}")

    logger.info("数据库初始化完成")


# ── 成绩 ──────────────────────────────────────────────────────

def upsert_scores(scores: list) -> list:
    """
    插入/更新成绩，返回本次新增的成绩列表。
    """
    new_scores = []
    with get_conn() as conn:
        for s in scores:
            course_code = s.get("course_code", "")
            term = s.get("term", "")
            
            # 检查是否是新成绩或改分更正
            row = conn.execute(
                "SELECT id, score, score_raw FROM scores WHERE course_code = ? AND term = ?",
                (course_code, term)
            ).fetchone()
            is_new = (row is None)
            is_changed = False
            if not is_new and row:
                old_raw = str(row["score_raw"]) if row["score_raw"] is not None else ""
                new_raw = str(s.get("score_raw", "")) if s.get("score_raw") is not None else ""
                if new_raw and old_raw != new_raw and old_raw not in ("None", ""):
                    is_changed = True

            try:
                conn.execute(
                    """
                    INSERT INTO scores
                        (course_code, course_name, credit, score, score_raw,
                         grade_point, term, exam_type, course_nature, avg_score, max_score, min_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(course_code, term) DO UPDATE SET
                        course_name = COALESCE(excluded.course_name, course_name),
                        credit = COALESCE(excluded.credit, credit),
                        score = COALESCE(excluded.score, score),
                        score_raw = COALESCE(excluded.score_raw, score_raw),
                        grade_point = COALESCE(excluded.grade_point, grade_point),
                        exam_type = COALESCE(excluded.exam_type, exam_type),
                        course_nature = COALESCE(excluded.course_nature, course_nature),
                        avg_score = COALESCE(excluded.avg_score, avg_score),
                        max_score = COALESCE(excluded.max_score, max_score),
                        min_score = COALESCE(excluded.min_score, min_score)
                    """,
                    (
                        course_code,
                        s.get("course_name", ""),
                        s.get("credit", 0),
                        s.get("score"),
                        s.get("score_raw", ""),
                        s.get("grade_point", 0),
                        term,
                        s.get("exam_type", ""),
                        s.get("course_nature", ""),
                        s.get("avg_score"),
                        s.get("max_score"),
                        s.get("min_score"),
                    ),
                )
                if is_new or is_changed:
                    new_scores.append(s)
            except sqlite3.Error as e:
                logger.error(f"Failed to upsert score: {e}")
                
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
