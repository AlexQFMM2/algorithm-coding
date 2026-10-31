"""Problem discovery and lossless practice-file storage."""
import hashlib
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path


TEMPLATE = """#include <iostream>
#include <algorithm>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    // 从这里开始，试着独立完成。

    return 0;
}
"""


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def revision(source):
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def atomic_write(path, content):
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, data):
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def practice_statistics(attempts, runs):
    """Count saved rounds and completed full checks, using existing files only."""
    checks = [run for run in runs if run["mode"] == "check"]
    failures = {"WA", "CE", "RE", "TLE", "OLE"}
    return {"practice_count": len(attempts),
            "passed_count": sum(run["status"] == "PASS" for run in checks),
            "failed_count": sum(run["status"] in failures for run in checks)}


class Repository:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()

    @property
    def bank(self):
        return self.contained(self.root / "题库")

    def contained(self, path):
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise AppError("文件必须位于当前仓库中。", 403)
        return resolved

    def problem(self, name):
        if not isinstance(name, str) or not name or Path(name).name != name or name.startswith("."):
            raise AppError("无效的题目名称。", 404)
        path = self.contained(self.bank / name)
        if not path.is_relative_to(self.bank):
            raise AppError("题目必须位于题库目录内。", 403)
        if not path.is_dir() or not (path / "题目.md").is_file():
            raise AppError("题目不存在。", 404)
        return path

    def config(self, path):
        config_file = self.contained(path / "practice.json")
        if not config_file.exists():
            return {"title": path.name, "topic": "自定义题目", "samples": []}
        try:
            config = json.loads(config_file.read_text(encoding="utf-8"))
            if not isinstance(config, dict) or not isinstance(config.get("samples", []), list):
                raise ValueError("题目配置格式错误")
            for sample in config.get("samples", []):
                if not isinstance(sample, dict) or not all(isinstance(sample.get(key), str) for key in ("input", "output")):
                    raise ValueError("每个样例都需要字符串 input 和 output")
            return config
        except (ValueError, OSError) as error:
            raise AppError(f"无法读取 {path.name}/practice.json：{error}") from error

    def list_problems(self):
        items = []
        if not self.bank.exists():
            return items
        for path in sorted(self.bank.iterdir()):
            if path.name.startswith(".") or not path.is_dir() or not (path / "题目.md").is_file():
                continue
            self.problem(path.name)
            config = self.config(path)
            attempts = self.attempts(path.name)
            runs = self.runs(path.name, limit=None)
            latest_check = next((run for run in runs if run["mode"] == "check"), None)
            items.append({"id": path.name, "title": config.get("title", path.name),
                          "topic": config.get("topic", "算法练习"), "attempt_count": len(attempts),
                          "stats": practice_statistics(attempts, runs),
                          "last_check": latest_check, "order": config.get("order", 100)})
        return sorted(items, key=lambda item: (item["order"], item["id"]))

    def attempts(self, name):
        path = self.contained(self.problem(name) / "attempts")
        if not path.exists():
            return []
        return [{"id": p.name, "modified": datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat()}
                for p in sorted(path.glob("*.cpp"), reverse=True)
                if re.fullmatch(r"\d{3,}\.cpp", p.name) and self.contained(p).is_file()]

    def attempt_path(self, name, attempt):
        if not isinstance(attempt, str) or not re.fullmatch(r"\d{3,}\.cpp", attempt):
            raise AppError("无效的练习文件。", 404)
        path = self.contained(self.problem(name) / "attempts" / attempt)
        if not path.is_file():
            raise AppError("练习文件不存在。", 404)
        return path

    def read_attempt(self, name, attempt):
        path = self.attempt_path(name, attempt)
        source = path.read_text(encoding="utf-8")
        return {"id": attempt, "source": source, "revision": revision(source),
                "path": str(path.relative_to(self.root))}

    def test_cases(self, name):
        """Load a coherent snapshot of the extra tests; never silently skip a pair."""
        problem = self.problem(name)
        directory = problem / "tests"
        try:
            if directory.is_symlink():
                raise AppError("测试目录不能使用符号链接。", 403)
            directory = self.contained(directory)
            if not directory.is_dir():
                raise AppError("尚未准备 tests/ 测试数据，请使用“运行样例”或补齐测试文件。")
            before = directory.stat()
            files = {path.name: path for path in directory.iterdir() if path.suffix in (".in", ".out")}
            if not files:
                raise AppError("tests/ 测试目录为空，不能执行“检查全部”。")
            versions = {}
            for filename, path in files.items():
                if path.is_symlink() or not self.contained(path).is_relative_to(directory) or not path.is_file():
                    raise AppError(f"测试文件 {filename} 不是题目内的普通文件。", 403)
                counterpart = path.stem + (".out" if path.suffix == ".in" else ".in")
                if counterpart not in files:
                    raise AppError(f"测试文件 {filename} 缺少对应的 {counterpart}，已停止完整检查。")
                stat = path.stat()
                limit = 2_000_000 if path.suffix == ".in" else 4 * 1024 * 1024
                if stat.st_size > limit:
                    raise AppError(f"测试文件 {filename} 过大，输入上限 2 MB、答案上限 4 MB。", 413)
                versions[filename] = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
            cases = []
            for filename in sorted(files):
                incoming = files[filename]
                if incoming.suffix != ".in":
                    continue
                expected = files[incoming.stem + ".out"]
                cases.append({"name": incoming.stem, "input": incoming.read_text(encoding="utf-8"),
                              "output": expected.read_text(encoding="utf-8"),
                              "source": {"kind": "file", "input": str(incoming.relative_to(self.root)),
                                         "output": str(expected.relative_to(self.root))}})
            after = directory.stat()
            if (before.st_ino, before.st_mtime_ns) != (after.st_ino, after.st_mtime_ns):
                raise AppError("测试数据正在更新，请稍后重新检查。", 409)
            for filename, path in files.items():
                stat = path.stat()
                if versions[filename] != (stat.st_ino, stat.st_size, stat.st_mtime_ns) or path.is_symlink():
                    raise AppError("测试数据正在更新，请稍后重新检查。", 409)
            return cases
        except (OSError, UnicodeError) as error:
            raise AppError(f"无法读取测试数据：{error}。请检查文件权限、UTF-8 编码和文件是否正在更新。") from error

    def test_suite(self, name, sample_count):
        try:
            count = len(self.test_cases(name))
            return {"sample_count": sample_count, "file_count": count,
                    "total_count": sample_count + count, "ready": True, "error": None}
        except AppError as error:
            return {"sample_count": sample_count, "file_count": 0,
                    "total_count": None, "ready": False, "error": str(error)}

    def create_attempt(self, name, source=None):
        with self.lock:
            directory = self.contained(self.problem(name) / "attempts")
            directory.mkdir(exist_ok=True)
            existing = self.attempts(name)
            number = max((int(item["id"].split(".")[0]) for item in existing), default=0) + 1
            filename = f"{number:03}.cpp"
            # Exclusive creation also protects against another app process.
            with (directory / filename).open("x", encoding="utf-8") as stream:
                stream.write(TEMPLATE if source is None else source)
            return self.read_attempt(name, filename)

    def save_attempt(self, name, attempt, source, expected_revision):
        if not isinstance(source, str) or len(source.encode("utf-8")) > 256_000:
            raise AppError("代码不能为空类型或超过 256 KB。")
        with self.lock:
            path = self.attempt_path(name, attempt)
            if revision(path.read_text(encoding="utf-8")) != expected_revision:
                raise AppError("文件已在其他窗口或编辑器中修改。请先下载当前草稿，再重新载入，避免覆盖。", 409)
            atomic_write(path, source)
            return {"revision": revision(source)}

    def detail(self, name):
        with self.lock:
            path = self.problem(name)
            config = self.config(path)
            attempts = self.attempts(name)
            runs = self.runs(name, limit=None)
            documents = [{"name": p.name, "path": str(p.relative_to(self.root))}
                         for p in sorted(path.iterdir()) if p.suffix in (".md", ".cpp") and p.is_file()]
            return {"id": name, "path": str(path.relative_to(self.root)), "title": config.get("title", name),
                    "topic": config.get("topic", "算法练习"), "samples": config.get("samples", []),
                    "test_suite": self.test_suite(name, len(config.get("samples", []))), "documents": documents,
                    "attempts": attempts,
                    "stats": practice_statistics(attempts, runs),
                    "attempt": self.read_attempt(name, attempts[0]["id"]) if attempts else None,
                    "runs": runs[:100]}

    def document(self, relative):
        path = self.contained(self.root / relative)
        if path.suffix not in (".md", ".cpp") or not path.is_file():
            raise AppError("文档不存在。", 404)
        return {"path": str(path.relative_to(self.root)), "content": path.read_text(encoding="utf-8"),
                "code": path.suffix == ".cpp"}

    def run_path(self, name, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"\d{8}T\d{12}Z-[a-f0-9]{8}", run_id):
            raise AppError("无效的日志编号。", 404)
        return self.contained(self.problem(name) / "runs" / run_id)

    def runs(self, name, limit=100):
        directory = self.contained(self.problem(name) / "runs")
        records = []
        for path in sorted(directory.glob("*/result.json"), reverse=True):
            try:
                data = json.loads(self.contained(path).read_text(encoding="utf-8"))
                if not isinstance(data, dict) or not all(isinstance(data.get(key), str)
                                                        for key in ("id", "created_at", "mode", "status", "attempt")):
                    continue
                records.append({key: data.get(key) for key in ("id", "created_at", "mode", "status", "attempt", "passed", "total")})
                if limit is not None and len(records) >= limit:
                    break
            except (OSError, ValueError):
                continue
        return records

    def read_run(self, name, run_id):
        path = self.contained(self.run_path(name, run_id) / "result.json")
        if not path.is_file():
            raise AppError("运行日志不存在。", 404)
        result = json.loads(path.read_text(encoding="utf-8"))
        # Historical snapshots remain byte-for-byte unchanged after moving the bank.
        result["log_path"] = str(path.parent.relative_to(self.root))
        return result
