"""
test_audit.py — 全面系统检修与安全审计测试套件
用于对核心模块、数据库并发、API 认证安全防护及数据转化机制进行自动化校验。
"""

import sys
import unittest
import json
import sqlite3
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

import database as db
import config_manager as cfg
import app as flask_app_module


class TestAuditAndSecurity(unittest.TestCase):

    def setUp(self):
        db.init_db()
        self.app = flask_app_module.app
        self.client = self.app.test_client()

    def test_database_wal_mode(self):
        """测试 1: 校验 SQLite 数据库是否成功开启 WAL 模式及连接配置。"""
        with db.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            mode = cursor.fetchone()[0].upper()
            self.assertEqual(mode, "WAL", f"Expected WAL journal mode, got {mode}")

    def test_config_security_and_masking(self):
        """测试 2: 校验 /api/config/all 接口在不同认证状态下的掩码与防御逻辑。"""
        # 情况 A: 当面板未设置密码时，访问接口能放行，但敏感字段必须强制施加掩码
        cfg.save({
            "panel_password": "",
            "imu_password": "SuperSecretPassword123"
        })
        res = self.client.get("/api/config/all")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("imu_password"), "••••••••", "Secrets must be masked when unauthenticated")

        # 情况 B: 当面板设置了密码，未带 Token 的请求应被拦截 401
        cfg.save({
            "panel_username": "admin",
            "panel_password": "MyPanelPassword888",
            "imu_password": "SuperSecretPassword123"
        })
        res_no_auth = self.client.get("/api/config/all")
        self.assertEqual(res_no_auth.status_code, 401)

        # 情况 C: 带正确 Token 的请求放行并可解密明文
        res_auth = self.client.get(
            "/api/config/all",
            headers={"X-Panel-Token": "MyPanelPassword888", "X-Panel-User": "admin"}
        )
        self.assertEqual(res_auth.status_code, 200)
        data_auth = res_auth.get_json()
        self.assertEqual(data_auth.get("imu_password"), "SuperSecretPassword123")

    def test_score_upsert_and_change_detection(self):
        """测试 3: 校验 upsert_scores 新增与分数修改更正（is_changed）识别。"""
        initial_score = [{
            "course_code": "TEST101",
            "course_name": "软件安全测试",
            "credit": 3.0,
            "score": 80.0,
            "score_raw": "80.0",
            "grade_point": 3.0,
            "term": "2025-2026-1",
            "exam_type": "考试",
            "course_nature": "专业必修课"
        }]

        # 首次插入，应判定为新成绩
        new1 = db.upsert_scores(initial_score)
        self.assertEqual(len(new1), 1)

        # 再次插入相同数据，无变化
        new2 = db.upsert_scores(initial_score)
        self.assertEqual(len(new2), 0)

        # 模拟分数更新修正为 92.0
        updated_score = [{
            "course_code": "TEST101",
            "course_name": "软件安全测试",
            "credit": 3.0,
            "score": 92.0,
            "score_raw": "92.0",
            "grade_point": 4.0,
            "term": "2025-2026-1",
            "exam_type": "考试",
            "course_nature": "专业必修课"
        }]
        new3 = db.upsert_scores(updated_score)
        self.assertEqual(len(new3), 1, "Expected score modification to be detected and returned in new_scores")

    def test_gpa_endpoint(self):
        """测试 4: 校验 /api/gpa 接口能够准确返回学分及 GPA 信息。"""
        cfg.save({"panel_password": ""}) # 清除面板密码限制以方便测试
        db.save_student_info({"name": "测试学生", "gpa": 3.85, "credits_required": 165.0})
        res = self.client.get("/api/gpa")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get("gpa"), 3.85)
        self.assertEqual(data.get("credits_required"), 165.0)

    def test_security_ignore_files(self):
        """测试 5: 校验 .gitignore 与 .dockerignore 排除规则。"""
        gitignore_path = Path(__file__).parent / ".gitignore"
        dockerignore_path = Path(__file__).parent / ".dockerignore"
        
        self.assertTrue(gitignore_path.exists(), ".gitignore file must exist")
        self.assertTrue(dockerignore_path.exists(), ".dockerignore file must exist")
        
        git_content = gitignore_path.read_text(encoding="utf-8")
        docker_content = dockerignore_path.read_text(encoding="utf-8")
        
        for secret_pattern in [".env", "data/"]:
            self.assertIn(secret_pattern, git_content, f"{secret_pattern} missing in .gitignore")
            self.assertIn(secret_pattern, docker_content, f"{secret_pattern} missing in .dockerignore")


if __name__ == "__main__":
    unittest.main()
