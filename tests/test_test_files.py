import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import ProxyHandler, Request, build_opener

from tools.test_builder import build_suite
from workbench.judge import Judge
from workbench.repository import AppError, Repository
from workbench.server import Server

ECHO = '#include <iostream>\nint main(){long long n; std::cin >> n; std::cout << n;}\n'


class TestFilesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="acwing-file-tests-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.problem = self.root / "题库/临时题"
        self.problem.mkdir(parents=True)
        (self.problem / "题目.md").write_text("# 测试题", encoding="utf-8")
        (self.problem / "main.cpp").write_text(ECHO)
        (self.problem / "practice.json").write_text(json.dumps({"samples": [{"input": "7\n", "output": "7\n"}]}))
        self.tests = self.problem / "tests"
        self.tests.mkdir()
        self.pair("002-较大", "42\n", "42\n")
        self.pair("001-较小", "1\n", "1\n")
        self.repo = Repository(self.root)

    def pair(self, stem, incoming, expected):
        (self.tests / (stem + ".in")).write_text(incoming, encoding="utf-8")
        (self.tests / (stem + ".out")).write_text(expected, encoding="utf-8")

    def test_metadata_paths_order_and_live_changes(self):
        detail = self.repo.detail("临时题")
        self.assertEqual(detail["path"], "题库/临时题")
        self.assertEqual(detail["test_suite"], {"sample_count": 1, "file_count": 2, "total_count": 3, "ready": True, "error": None})
        self.assertTrue(all(d["path"].startswith("题库/临时题/") for d in detail["documents"]))
        self.assertEqual([c["name"] for c in self.repo.test_cases("临时题")], ["001-较小", "002-较大"])
        self.pair("003-新增", "100\n", "100\n")
        self.assertEqual(self.repo.detail("临时题")["test_suite"]["total_count"], 4)

    def test_bad_pairs_encoding_size_and_paths_are_not_skipped(self):
        incoming = self.tests / "003-故障.in"
        outgoing = self.tests / "003-故障.out"
        incoming.write_text("3")
        with self.assertRaisesRegex(AppError, "缺少对应"):
            self.repo.test_cases("临时题")
        incoming.unlink()
        outgoing.write_text("3")
        self.assertFalse(self.repo.detail("临时题")["test_suite"]["ready"])
        incoming.write_bytes(b"\xff")
        with self.assertRaisesRegex(AppError, "UTF-8"):
            self.repo.test_cases("临时题")
        incoming.write_bytes(b"1" * 2_000_001)
        with self.assertRaisesRegex(AppError, "过大"):
            self.repo.test_cases("临时题")
        incoming.unlink()
        incoming.symlink_to(self.root / "elsewhere")
        with self.assertRaises(AppError):
            self.repo.test_cases("临时题")
        incoming.unlink()
        incoming.mkdir()
        with self.assertRaises(AppError):
            self.repo.test_cases("临时题")

    def test_unreadable_file_and_suite_updates_are_reported(self):
        original = Path.read_text
        def unreadable(path, *args, **kwargs):
            if path.suffix == ".out":
                raise PermissionError("fixture denied")
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", unreadable):
            self.assertIn("无法读取", self.repo.detail("临时题")["test_suite"]["error"])
        def change_mid_read(path, *args, **kwargs):
            text = original(path, *args, **kwargs)
            if path.name == "002-较大.out":
                (self.tests / "001-较小.in").write_text("different")
            return text
        with patch.object(Path, "read_text", change_mid_read):
            with self.assertRaisesRegex(AppError, "正在更新"):
                self.repo.test_cases("临时题")

    def test_empty_and_linked_directory_block_full_check_without_records(self):
        attempt = self.repo.create_attempt("临时题", ECHO)
        for path in self.tests.iterdir():
            path.unlink()
        with self.assertRaisesRegex(AppError, "目录为空"):
            Judge(self.repo).run("临时题", attempt["id"], attempt["revision"], "check")
        self.assertFalse((self.problem / "runs").exists())
        self.tests.rmdir()
        external = self.root / "external"
        external.mkdir()
        self.tests.symlink_to(external, target_is_directory=True)
        self.assertIn("符号链接", self.repo.detail("临时题")["test_suite"]["error"])
        with self.assertRaises(AppError):
            Judge(self.repo).run("临时题", attempt["id"], attempt["revision"], "check")
        self.assertFalse((self.problem / "runs").exists())

    def test_fixed_cases_snapshots_and_old_logs_remain_readable(self):
        attempt = self.repo.create_attempt("临时题", ECHO)
        self.assertEqual(attempt["path"], "题库/临时题/attempts/001.cpp")
        # The judge must never execute reference code or a generation script.
        (self.problem / "main.cpp").write_text("invalid reference")
        (self.problem / "generate_tests.py").write_text("raise RuntimeError('must not execute')")
        judge = Judge(self.repo)
        result = judge.run("临时题", attempt["id"], attempt["revision"], "check")
        self.assertEqual((result["status"], result["passed"], result["total"]), ("PASS", 3, 3))
        self.assertNotIn("seed", result)
        self.assertEqual(result["case_plan"][1]["source"]["input"], "题库/临时题/tests/001-较小.in")
        log = self.root / result["log_path"]
        self.pair("001-较小", "1", "2")
        second = judge.run("临时题", attempt["id"], attempt["revision"], "check")
        self.assertEqual((second["status"], second["passed"], second["total"]), ("WA", 1, 3))
        self.assertEqual((log / "case-002.expected").read_text(), "1\n")
        # Emulate a pre-migration JSON without rewriting it during reads.
        result["log_path"] = f"临时题/runs/{result['id']}"
        result["seed"] = 123
        saved = log / "result.json"
        saved.write_text(json.dumps(result))
        digest = hashlib.sha256(saved.read_bytes()).hexdigest()
        read = self.repo.read_run("临时题", result["id"])
        self.assertTrue(read["log_path"].startswith("题库/临时题/runs/"))
        self.assertEqual(read["seed"], 123)
        self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(), digest)

    def test_new_problem_is_available_without_server_restart(self):
        server = Server(self.root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        opener = build_opener(ProxyHandler({}))
        def api(path, data=None):
            request = Request(base + path, data=None if data is None else json.dumps(data).encode(),
                              headers={"Content-Type": "application/json", "X-Workbench-Token": server.token})
            with opener.open(request, timeout=15) as response:
                return json.load(response)
        try:
            self.assertEqual(len(api("/api/state")["problems"]), 1)
            added = self.root / "题库/string-length"
            (added / "tests").mkdir(parents=True)
            (added / "题目.md").write_text("Read a token and print its length.")
            (added / "practice.json").write_text('{"samples": []}')
            (added / "tests/001.in").write_text("hello\n")
            (added / "tests/001.out").write_text("5\n")
            self.assertEqual(len(api("/api/state")["problems"]), 2)
            detail = api("/api/problem?id=string-length")
            self.assertTrue(detail["test_suite"]["ready"])
            attempt = api("/api/attempt/new", {"problem": "string-length"})
            source = '#include <iostream>\n#include <string>\nint main(){std::string s;std::cin>>s;std::cout<<s.size();}'
            saved = api("/api/attempt/save", {"problem": "string-length", "attempt": attempt["id"], "source": source, "revision": attempt["revision"]})
            result = api("/api/run", {"problem": "string-length", "attempt": attempt["id"], "revision": saved["revision"], "mode": "check"})
            self.assertEqual((result["status"], result["total"]), ("PASS", 1))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_builder_is_reproducible_and_failure_keeps_previous_suite(self):
        cases = [{"name": "小输入", "input": "1\n", "output": "1\n"}]
        destination = self.root / "generated"
        build_suite(self.problem, cases, destination, 788)
        before = {p.name: p.read_bytes() for p in destination.iterdir()}
        build_suite(self.problem, cases, destination, 788)
        self.assertEqual(before, {p.name: p.read_bytes() for p in destination.iterdir()})
        (self.problem / "main.cpp").write_text('int main(){}')
        with self.assertRaisesRegex(ValueError, "不一致"):
            build_suite(self.problem, cases, destination, 789)
        self.assertEqual(before, {p.name: p.read_bytes() for p in destination.iterdir()})
        self.assertFalse((self.problem / "attempts").exists())
        self.assertFalse((self.problem / "runs").exists())

    def test_failed_publication_restores_previous_suite(self):
        before = {p.name: p.read_bytes() for p in self.tests.iterdir()}
        rename = Path.rename

        def fail_candidate(path, destination):
            if path.name == "candidate":
                raise OSError("simulated publication failure")
            return rename(path, destination)

        with patch.object(Path, "rename", fail_candidate):
            with self.assertRaisesRegex(OSError, "publication failure"):
                build_suite(self.problem, [{"name": "new", "input": "5", "output": "5"}], self.tests, 788)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.tests.iterdir()})
        self.assertFalse(self.tests.with_name(".tests.previous").exists())
        self.assertFalse(self.tests.with_name(".tests.build.lock").exists())


if __name__ == "__main__":
    unittest.main()
