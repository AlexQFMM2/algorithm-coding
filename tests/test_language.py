import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from workbench.language import LanguageService, find_clangd
from workbench.repository import AppError, Repository
from workbench.server import Server


class LanguageTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="acwing-language-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "题库/题目").mkdir(parents=True)
        (self.root / "题库/题目/题目.md").write_text("# 临时题目", encoding="utf-8")
        self.repo = Repository(self.root)
        self.attempt = self.repo.create_attempt("题目", "int main() {}\n")
        self.language = LanguageService(self.repo)
        self.addCleanup(self.language.close)
        self.version = 0

    def payload(self, source="int main() {}\n", action="diagnostics", **extra):
        self.version += 1
        return {"problem": "题目", "attempt": self.attempt["id"],
                "session": "test-window-00000001", "source": source,
                "version": self.version, "action": action, **extra}


class LanguageValidationTest(LanguageTestCase):
    def test_unavailable_service_leaves_saves_and_runs_independent(self):
        with patch("workbench.language.find_clangd", return_value=None):
            self.assertFalse(self.language.status()["available"])
            with self.assertRaises(AppError) as caught:
                self.language.handle(self.payload())
            self.assertEqual(caught.exception.status, 503)
            self.assertIn("setup-editor.py", str(caught.exception))
        self.assertEqual(self.repo.read_attempt("题目", self.attempt["id"])["source"], "int main() {}\n")

    def test_invalid_paths_positions_and_actions_do_not_start_a_process(self):
        for invalid in ({"problem": "../题目"}, {"attempt": "../main.cpp"},
                        {"session": "../../somewhere"}, {"version": True},
                        {"source": None}, {"action": "workspace/executeCommand"},
                        {"action": "completion", "position": {"line": 500, "character": 0}}):
            with self.subTest(invalid=invalid), self.assertRaises(AppError):
                self.language.handle(self.payload(**invalid))
        self.assertIsNone(self.language.client)

    def test_language_http_uses_existing_host_origin_and_token_checks(self):
        server = Server(self.root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        payload = json.dumps(self.payload()).encode()
        headers = {"Content-Type": "application/json", "X-Workbench-Token": server.token}
        try:
            for invalid in ({"X-Workbench-Token": "wrong"}, {"Origin": "https://example.com"}, {"Host": "example.com"}):
                with self.subTest(invalid=invalid), self.assertRaises(HTTPError) as caught:
                    urlopen(Request(base + "/api/language", data=payload, headers={**headers, **invalid}))
                self.assertEqual(caught.exception.code, 403)
            with patch("workbench.language.find_clangd", return_value=None):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(base + "/api/language", data=payload, headers=headers))
                self.assertEqual(caught.exception.code, 503)
            self.assertIsNone(server.language.client)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


@unittest.skipUnless(find_clangd(), "Install clangd to exercise the real language server")
class LanguageIntegrationTest(LanguageTestCase):
    def test_unsaved_diagnostics_clear_after_fix_without_touching_files(self):
        source = '#include <bits/stdc++.h>\nint main() { std::vector<int> values; return missing; }\n'
        result = self.language.handle(self.payload(source))["result"]
        self.assertTrue(any("missing" in diagnostic["message"] and diagnostic["severity"] == 1 for diagnostic in result), result)
        self.assertFalse(any("file not found" in diagnostic["message"] for diagnostic in result), result)
        result = self.language.handle(self.payload(source.replace("missing", "0")))["result"]
        self.assertFalse(any(diagnostic["severity"] == 1 for diagnostic in result), result)
        source = 'int main() { int unused = 1; }\n'
        result = self.language.handle(self.payload(source))["result"]
        self.assertTrue(any(diagnostic["severity"] == 2 and "unused" in diagnostic["message"] for diagnostic in result), result)
        self.assertEqual(self.repo.read_attempt("题目", self.attempt["id"])["source"], "int main() {}\n")
        self.assertFalse(list(self.root.rglob(".workbench-*.cpp")))
        self.assertFalse(list(self.root.rglob("runs")))
        self.assertTrue((self.root / ".workbench/language.log").is_file())

    def test_completions_understand_local_symbols_and_standard_library_members(self):
        source = '#include <vector>\nint main() { std::vector<int> values; values.pu }\n'
        response = self.language.handle(self.payload(source, "completion", position={
            "line": 1, "character": source.splitlines()[1].index("values.pu") + len("values.pu")}))["result"]
        items = response.get("items", []) if isinstance(response, dict) else response
        self.assertTrue(any("push_back" in item["label"] for item in items), items)
        source = 'int main() { int local_count = 3; return local_c; }\n'
        response = self.language.handle(self.payload(source, "completion", position={
            "line": 0, "character": source.index("return local_c") + len("return local_c")}))["result"]
        items = response.get("items", []) if isinstance(response, dict) else response
        self.assertTrue(any("local_count" in item["label"] for item in items), items)

    def test_signature_hover_and_utf16_positions(self):
        source = 'int merge_sum(int left, int right) { return left + right; }\nint main() { /* 😀中文 */ return merge_sum(1, ); }\n'
        line = source.splitlines()[1]
        cursor = line[:line.index("1, ") + 3]
        result = self.language.handle(self.payload(source, "signature", position={
            "line": 1, "character": len(cursor.encode("utf-16-le")) // 2}))["result"]
        self.assertTrue(result["signatures"], result)
        self.assertIn("right", result["signatures"][0]["label"])
        self.assertEqual(result["activeParameter"], 1)
        result = self.language.handle(self.payload(source, "hover", position={
            "line": 0, "character": 6}))["result"]
        self.assertIn("merge_sum", str(result))

    def test_tabs_versions_and_service_restart(self):
        older = self.payload("int main() { return first_missing; }\n")
        first = self.language.handle(older)
        other = self.payload("int main() {}\n", session="test-window-00000002")
        self.assertFalse(any(d["severity"] == 1 for d in self.language.handle(other)["result"]))
        self.assertEqual(first["result"], self.language.handle(older)["result"])
        latest = self.payload("int main() {}\n")
        self.assertFalse(any(d["severity"] == 1 for d in self.language.handle(latest)["result"]))
        self.assertTrue(self.language.handle(older)["stale"])
        with self.assertRaises(AppError):
            self.language.handle({**latest, "source": "int main(){return different;}"})
        process = self.language.client.process
        process.kill()
        process.wait(timeout=5)
        self.assertFalse(any(d["severity"] == 1 for d in self.language.handle(latest)["result"]))
        restarted = self.language.client.process
        self.assertNotEqual(process.pid, restarted.pid)
        self.language.close()
        self.assertIsNotNone(restarted.poll())


if __name__ == "__main__":
    unittest.main()
