import json
import tempfile
import unittest
from pathlib import Path

from workbench.repository import Repository


class StatisticsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="acwing-statistics-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.problem = self.root / "题库/测试题"
        self.problem.mkdir(parents=True)
        (self.problem / "题目.md").write_text("# 测试题", encoding="utf-8")
        self.repo = Repository(self.root)
        self.sequence = 0

    def add_run(self, mode, status):
        self.sequence += 1
        run_id = f"20261031T120000{self.sequence:06}Z-1234abcd"
        directory = self.problem / "runs" / run_id
        directory.mkdir(parents=True)
        data = {"id": run_id, "created_at": "2026-10-31T12:00:00+00:00", "mode": mode,
                "status": status, "attempt": "001.cpp", "passed": 30 if status == "PASS" else 0, "total": 30}
        (directory / "result.json").write_text(json.dumps(data), encoding="utf-8")
        return directory

    def test_empty_and_new_round_counts(self):
        expected = {"practice_count": 0, "passed_count": 0, "failed_count": 0}
        self.assertEqual(self.repo.detail("测试题")["stats"], expected)
        first = self.repo.create_attempt("测试题")
        self.repo.create_attempt("测试题")
        self.repo.save_attempt("测试题", first["id"], "// another edit", first["revision"])
        expected["practice_count"] = 2
        self.assertEqual(self.repo.detail("测试题")["stats"], expected)
        self.assertEqual(self.repo.list_problems()[0]["stats"], expected)

    def test_only_completed_full_checks_count_once_each(self):
        self.repo.create_attempt("测试题")
        for status in ("PASS", "PASS", "WA", "CE", "RE", "TLE", "OLE", "ERROR", "RUNNING"):
            self.add_run("check", status)
        for mode in ("sample", "manual"):
            for status in ("PASS", "OK", "WA", "CE", "RE", "TLE", "OLE"):
                self.add_run(mode, status)
        expected = {"practice_count": 1, "passed_count": 2, "failed_count": 5}
        self.assertEqual(self.repo.detail("测试题")["stats"], expected)
        self.assertEqual(self.repo.list_problems()[0]["stats"], expected)

    def test_counts_include_history_older_than_display_limit_and_survive_restart(self):
        self.repo.create_attempt("测试题")
        self.add_run("check", "PASS")
        last_check = self.add_run("check", "WA").name
        for _ in range(105):
            self.add_run("sample", "PASS")
        reloaded = Repository(self.root)
        detail = reloaded.detail("测试题")
        self.assertEqual(len(detail["runs"]), 100)
        self.assertEqual(detail["stats"], {"practice_count": 1, "passed_count": 1, "failed_count": 1})
        self.assertEqual(reloaded.list_problems()[0]["last_check"]["id"], last_check)

    def test_incomplete_or_malformed_logs_do_not_inflate_counts(self):
        self.add_run("check", "PASS")
        for malformed in ("not json", "[]", '{"mode":"check","status":"PASS"}'):
            directory = self.add_run("check", "WA")
            (directory / "result.json").write_text(malformed, encoding="utf-8")
        directory = self.add_run("check", "WA")
        (directory / "result.json").unlink()
        self.assertEqual(self.repo.detail("测试题")["stats"], {"practice_count": 0, "passed_count": 1, "failed_count": 0})


if __name__ == "__main__":
    unittest.main()
