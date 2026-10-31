import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from workbench.repository import AppError, Repository
from workbench.server import Server
from workbench.visualization import VisualizationRunner, list_visualizations, read_visualization
from workbench.visualization_protocol import MAX_COMMANDS, MAX_STEPS, validate_trace

SOURCE = '''#include "visualization.hpp"
#include <iostream>
int main() {
    int n; if (!(std::cin >> n)) { std::cerr << "需要整数"; return 2; }
    wbviz::Recorder r;
    r.array("a", "数组", {n, 1}); r.log("note", "解释"); r.layout({"a", "note"});
    r.step(__LINE__, "开始");
    r.select("a", 0, 1); r.set("note", "<b>plain text</b>");
    r.step(__LINE__, "增加计数", {{"kind", "count"}, {"before", 0}, {"after", 1}, {"pairs", wbviz::Json::array({wbviz::Json::array({n, 1})})}});
    r.finish(); std::cout << 1;
}
'''


class VisualizationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="algorithm-viz-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.problem = self.root / "题库/demo"
        self.problem.mkdir(parents=True)
        (self.problem / "题目.md").write_text("# Original demonstration fixture")
        self.config = {"samples": [{"input": "2\n", "output": "1\n"}], "visualization": {"source": "visualize.cpp"}}
        self.save_config()
        (self.problem / "visualize.cpp").write_text(SOURCE, encoding="utf-8")
        self.repo = Repository(self.root)
        self.runner = VisualizationRunner(self.repo, threading.Lock())

    def save_config(self):
        (self.problem / "practice.json").write_text(json.dumps(self.config), encoding="utf-8")

    def test_dynamic_discovery_and_unsafe_sources(self):
        self.assertTrue(self.repo.detail("demo")["visualization"]["available"])
        (self.problem / "visualize.cpp").unlink()
        self.assertFalse(self.repo.detail("demo")["visualization"]["available"])
        self.assertIsNotNone(self.repo.detail("demo")["visualization"]["error"])
        for name in ("../outside.cpp", "/tmp/code.cpp", ".secret.cpp"):
            self.config["visualization"]["source"] = name
            self.save_config()
            self.assertFalse(self.repo.detail("demo")["visualization"]["available"])
        self.config["visualization"]["source"] = "visualize.cpp"
        self.save_config()
        outside = self.root / "outside.cpp"
        outside.write_text(SOURCE)
        (self.problem / "visualize.cpp").symlink_to(outside)
        self.assertFalse(self.repo.detail("demo")["visualization"]["available"])

    def test_snapshot_replay_survives_source_changes_without_statistical_side_effects(self):
        before = self.repo.list_problems()[0]["stats"]
        result = self.runner.run("demo")
        self.assertEqual(result["status"], "READY", result)
        self.assertEqual(result["steps"], 2)
        self.assertEqual(result["input"], "2\n")
        self.assertEqual(result["source"], SOURCE)
        self.assertEqual(result["trace"]["commands"][-1]["args"][1]["pairs"], [[2, 1]])
        self.assertEqual(before, self.repo.list_problems()[0]["stats"])
        self.assertFalse((self.problem / "attempts").exists())
        self.assertFalse((self.problem / "runs").exists())
        (self.problem / "visualize.cpp").write_text("int main(){}")
        read = read_visualization(self.repo, "demo", result["id"])
        self.assertEqual(read["trace"], result["trace"])
        self.assertEqual(read["source"], SOURCE)
        self.assertEqual(len(list_visualizations(self.repo, "demo")), 1)
        record_dir = self.root / result["log_path"]
        for file in ("input.txt", "source.cpp", "compile.stdout.txt", "compile.stderr.txt", "stdout.txt", "stderr.txt", "visualization.json"):
            self.assertTrue((record_dir / file).is_file(), file)
        (record_dir / "visualization.json").write_text('{}')
        with self.assertRaisesRegex(AppError, "损坏"):
            read_visualization(self.repo, "demo", result["id"])

    def test_error_statuses_do_not_create_judge_records(self):
        sources = {
            "CE": 'int main( {',
            "INPUT_ERROR": '#include <iostream>\nint main(){std::cerr<<"bad input";return 2;}',
            "RE": '#include <cstdlib>\nint main(){std::abort();}',
            "TLE": 'int main(){for(;;){}}',
            "OLE": '#include <cstdio>\nint main(){for(;;)std::puts("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");}',
            "ERROR": '#include <fstream>\nint main(){std::ofstream("visualization.json")<<"{}";}',
        }
        for status, source in sources.items():
            with self.subTest(status=status):
                (self.problem / "visualize.cpp").write_text(source)
                result = self.runner.run("demo")
                self.assertEqual(result["status"], status, result)
                self.assertNotIn("trace", result)
                self.assertIsNotNone(result["error"])
                record_dir = self.root / result["log_path"]
                for filename in ("compile.stdout.txt", "compile.stderr.txt", "stdout.txt", "stderr.txt"):
                    self.assertTrue((record_dir / filename).is_file(), filename)
                if status == "ERROR":
                    self.assertEqual((record_dir / "visualization.partial.json").read_text(), "{}")
        self.assertEqual(self.repo.list_problems()[0]["stats"], {"practice_count": 0, "passed_count": 0, "failed_count": 0})

    def test_input_limits_paths_and_execution_lock(self):
        with self.assertRaises(AppError):
            self.runner.run("demo", "manual", "1" * 16001)
        with self.assertRaises(AppError):
            self.runner.run("demo", sample=20)
        with self.assertRaises(AppError):
            read_visualization(self.repo, "demo", "../elsewhere")
        with self.runner.lock:
            with self.assertRaisesRegex(AppError, "已有程序"):
                self.runner.run("demo")
        (self.problem / "visualizations").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(AppError):
            self.runner.run("demo")

    def test_protocol_rejects_bounds_unsupported_actions_and_incomplete_steps(self):
        commands = [
            {"key": "a", "method": "Array1DTracer", "args": ["数组"]},
            {"key": "a", "method": "set", "args": [[2, 1]]},
            {"key": None, "method": "setRoot", "args": ["a"]},
            {"key": None, "method": "delay", "args": [1, {"message": "start"}]},
        ]
        trace = {"version": 1, "complete": True, "commands": commands}
        self.assertEqual(validate_trace(trace, 10), 1)
        for bad in [
            {"key": "a", "method": "patch", "args": [2]},
            {"key": "a", "method": "select", "args": [-1, 1]},
            {"key": "a", "method": "__proto__", "args": []},
            {"key": None, "method": "delay", "args": [11]},
            {"key": None, "method": "delay", "args": [1, {"message": {}}]},
        ]:
            with self.subTest(command=bad), self.assertRaises(AppError):
                validate_trace({**trace, "commands": commands[:-1] + [bad, commands[-1]]}, 10)
        with self.assertRaises(AppError):
            validate_trace({**trace, "complete": False}, 10)
        with self.assertRaises(AppError):
            validate_trace({**trace, "commands": commands[:-1]}, 10)
        with self.assertRaisesRegex(AppError, "4000 步"):
            validate_trace({**trace, "commands": commands[:3] + [commands[-1]] * (MAX_STEPS + 1)}, 10)
        with self.assertRaisesRegex(AppError, "命令数量超限"):
            validate_trace({**trace, "commands": [commands[-1]] * (MAX_COMMANDS + 1)}, 10)
        with self.assertRaisesRegex(AppError, "数组值"):
            validate_trace({**trace, "commands": commands[:1] + [{"key": "a", "method": "set", "args": [[10 ** 1000]]}]}, 10)

    def test_http_discovery_record_and_mutation_security(self):
        visualization = self.config.pop("visualization")
        self.save_config()
        server = Server(self.root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        opener = build_opener(ProxyHandler({}))
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with opener.open(base + "/api/problem?id=demo") as response:
                self.assertFalse(json.load(response)["visualization"]["configured"])
            self.config["visualization"] = visualization
            self.save_config()
            with opener.open(base + "/api/problem?id=demo") as response:
                self.assertTrue(json.load(response)["visualization"]["available"])
            data = json.dumps({"problem": "demo", "input_mode": "sample"}).encode()
            request = Request(base + "/api/visualizations", data=data, headers={"Content-Type": "application/json", "X-Workbench-Token": server.token})
            with opener.open(request, timeout=25) as response:
                result = json.load(response)
            self.assertEqual(result["status"], "READY", result)
            with opener.open(base + "/api/visualizations?problem=demo") as response:
                self.assertEqual(len(json.load(response)["runs"]), 1)
            with opener.open(base + f"/api/visualization?problem=demo&run={result['id']}") as response:
                self.assertEqual(json.load(response)["trace"], result["trace"])
            request.remove_header("X-workbench-token")
            from urllib.error import HTTPError
            with self.assertRaises(HTTPError) as error:
                opener.open(request)
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
