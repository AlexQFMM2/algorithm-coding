import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from workbench.judge import Judge
from tools.array_cases import generated_cases
from support import copy_problem
from workbench.repository import AppError, Repository
from workbench.server import Server

ROOT = Path(__file__).resolve().parent.parent
ECHO = '#include <iostream>\nint main(){long long x; while(std::cin >> x) std::cout << x << " ";}\n'


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="acwing-test-")
        self.root = Path(self.temporary.name)
        for name in ("快速排序", "归并排序", "第k个数"):
            copy_problem(self.root, name)
        self.repo = Repository(self.root)
        self.judge = Judge(self.repo)

    def tearDown(self):
        self.temporary.cleanup()

    def run_source(self, source, mode="manual", user_input="", name="快速排序"):
        attempt = self.repo.create_attempt(name, source)
        return self.judge.run(name, attempt["id"], attempt["revision"], mode, user_input)

    def test_synthetic_reference_solutions_pass_all_checks(self):
        for name in ("快速排序", "归并排序", "第k个数"):
            with self.subTest(name=name):
                source = (self.root / "题库" / name / "main.cpp").read_text()
                result = self.run_source(source, "check", name=name)
                self.assertEqual(result["status"], "PASS", result)
                self.assertEqual(result["passed"], result["total"])
                self.assertGreater(result["total"], 20)

    def test_manual_input_is_not_marked_as_correct_and_snapshot_is_preserved(self):
        result = self.run_source(ECHO, user_input="7 42\n")
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["cases"][0]["stdout"], "7 42 ")
        self.assertIsNone(result["cases"][0]["expected"])
        log = self.root / result["log_path"]
        self.assertEqual((log / "source.cpp").read_text(), ECHO)
        self.assertEqual((log / "case-001.in").read_text(), "7 42\n")
        self.assertEqual(json.loads((log / "result.json").read_text())["status"], "OK")
        attempt = self.repo.read_attempt("快速排序", result["attempt"])
        self.repo.save_attempt("快速排序", attempt["id"], "// changed", attempt["revision"])
        self.assertEqual((log / "source.cpp").read_text(), ECHO)

    def test_failures_are_classified_and_logged(self):
        sources = {
            "WA": '#include <iostream>\nint main(){std::cout << 999;}\n',
            "CE": 'int answer(int n){if(n) return 1;} int main(){}\n',
            "RE": '#include <cstdlib>\nint main(){std::abort();}\n',
            "TLE": 'int main(){while(true){}}\n',
            "OLE": '#include <cstdio>\nint main(){while(true) std::puts("012345678901234567890123456789");}\n',
        }
        for expected, source in sources.items():
            with self.subTest(expected=expected):
                result = self.run_source(source, mode="sample")
                self.assertEqual(result["status"], expected, result)
                self.assertEqual(result["passed"], 0)
                self.assertTrue((self.root / result["log_path"] / "compile.stderr.txt").exists())
                self.assertEqual((self.root / result["log_path"] / "case-001.in").read_text(), "5\n3 1 2 4 5\n")

    def test_new_round_and_conflict_never_overwrite_existing_files(self):
        original = (self.root / "题库/快速排序/main.cpp").read_text()
        first = self.repo.create_attempt("快速排序", ECHO)
        second = self.repo.create_attempt("快速排序")
        self.assertNotEqual(first["id"], second["id"])
        self.repo.save_attempt("快速排序", first["id"], "// external edit", first["revision"])
        with self.assertRaises(AppError) as caught:
            self.repo.save_attempt("快速排序", first["id"], "// stale edit", first["revision"])
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.repo.read_attempt("快速排序", first["id"])["source"], "// external edit")
        self.assertEqual((self.root / "题库/快速排序/main.cpp").read_text(), original)
        with self.assertRaises(AppError):
            self.judge.run("快速排序", first["id"], first["revision"], "sample")

    def test_paths_and_external_symlinks_are_rejected(self):
        for name in ("../快速排序", "/tmp", ".."):
            with self.assertRaises(AppError):
                self.repo.problem(name)
        with self.assertRaises(AppError):
            self.repo.document("../../etc/passwd")
        (self.root / "题库/快速排序/attempts").symlink_to("/tmp")
        with self.assertRaises(AppError):
            self.repo.create_attempt("快速排序")

    def test_random_cases_are_reproducible_and_respect_constraints(self):
        first = generated_cases("kth", 123)
        self.assertEqual(first, generated_cases("kth", 123))
        for case in first:
            lines = case["input"].splitlines()
            n, k = map(int, lines[0].split())
            numbers = list(map(int, lines[1].split()))
            self.assertEqual(n, len(numbers))
            self.assertTrue(1 <= k <= n <= 100_000)
            self.assertTrue(all(1 <= number <= 10**9 for number in numbers))
            self.assertEqual(int(case["output"]), sorted(numbers)[k - 1])

    def test_missing_test_files_cannot_silently_pass_only_samples(self):
        shutil.rmtree(self.root / "题库/快速排序/tests")
        attempt = self.repo.create_attempt("快速排序", (self.root / "题库/快速排序/main.cpp").read_text())
        with self.assertRaises(AppError) as caught:
            self.judge.run("快速排序", attempt["id"], attempt["revision"], "check")
        self.assertIn("尚未准备", str(caught.exception))
        self.assertEqual(self.repo.runs("快速排序"), [])
        self.assertEqual(self.judge.run("快速排序", attempt["id"], attempt["revision"], "sample")["status"], "PASS")
        self.assertFalse(self.repo.detail("快速排序")["test_suite"]["ready"])

    def test_http_round_trip_and_cross_origin_protection(self):
        server = Server(self.root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/api/state") as response:
                state = json.load(response)
            self.assertEqual(len(state["problems"]), 3)
            data = json.dumps({"problem": "快速排序"}).encode()
            headers = {"Content-Type": "application/json", "X-Workbench-Token": state["token"]}
            with urlopen(Request(base + "/api/attempt/new", data=data, headers=headers)) as response:
                attempt = json.load(response)
            self.assertEqual(attempt["id"], "001.cpp")
            for changes in ({"X-Workbench-Token": "incorrect"}, {"Origin": "https://example.com"}, {"Host": "attacker.example"}):
                with self.subTest(changes=changes), self.assertRaises(HTTPError) as caught:
                    urlopen(Request(base + "/api/attempt/new", data=data, headers={**headers, **changes}))
                self.assertEqual(caught.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
