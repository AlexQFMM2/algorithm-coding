"""Local reference demonstrations, with snapshots independent of judge statistics."""
import hashlib
import json
import re
import secrets
import shutil
import signal
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .judge import TIMEOUT, OUTPUT_LIMIT, execute, preview
from .repository import AppError, revision, write_json
from .visualization_protocol import TRACE_LIMIT, validate_trace

APP_ROOT = Path(__file__).resolve().parent.parent
SOURCE_LIMIT = 256000
INPUT_LIMIT = 16000


def source_path(repo, name):
    problem = repo.problem(name)
    settings = repo.config(problem).get("visualization")
    if not isinstance(settings, dict):
        raise AppError("本题尚未配置参考算法演示。", 404)
    source = settings.get("source")
    if not isinstance(source, str) or not source.endswith(".cpp") or Path(source).name != source or source.startswith("."):
        raise AppError("演示 source 必须是本题目录内的 C++ 文件名。")
    path = problem / source
    if path.is_symlink() or not repo.contained(path).is_relative_to(problem) or not path.is_file():
        raise AppError("演示源码不存在，或路径超出题目目录。")
    if path.stat().st_size > SOURCE_LIMIT:
        raise AppError("演示源码不能超过 256 KB。")
    return path, settings


def describe_visualization(repo, name):
    configured = "visualization" in repo.config(repo.problem(name))
    if not configured:
        return {"configured": False, "available": False, "error": None}
    try:
        path, settings = source_path(repo, name)
        source = path.read_text(encoding="utf-8")
        title = settings.get("title", "参考算法演示")
        hint = settings.get("input_hint", "使用题目标准输入格式；教学演示请使用小规模数据。")
        if not all(isinstance(x, str) for x in (title, hint)):
            raise AppError("演示标题和输入说明必须为文字。")
        return {"configured": True, "available": True, "error": None, "title": title,
                "input_hint": hint, "source_path": str(path.relative_to(repo.root)), "source_revision": revision(source)}
    except (AppError, OSError, UnicodeError) as error:
        return {"configured": True, "available": False, "error": str(error)}


def record_path(repo, name, run_id=None):
    problem = repo.problem(name)
    directory = problem / "visualizations"
    if directory.is_symlink() or not repo.contained(directory).is_relative_to(problem):
        raise AppError("演示记录目录必须位于本题目录中。", 403)
    if run_id is not None:
        if not isinstance(run_id, str) or not re.fullmatch(r"\d{8}T\d{12}Z-[a-f0-9]{8}", run_id):
            raise AppError("无效的演示记录编号。", 404)
        directory = directory / run_id
        if directory.is_symlink() or not repo.contained(directory).is_relative_to(problem):
            raise AppError("演示记录路径越界。", 403)
    return directory


def read_file(directory, name, limit):
    path = directory / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise AppError(f"演示文件 {name} 缺失、不是普通文件或超过限制。")
    return path.read_bytes()


def parse_json(data):
    def invalid(value):
        raise ValueError(f"非有限数值 {value}")
    return json.loads(data, parse_constant=invalid)


def read_visualization(repo, name, run_id):
    directory = record_path(repo, name, run_id)
    try:
        result = parse_json(read_file(directory, "result.json", 128000))
        if not isinstance(result, dict) or result.get("id") != run_id:
            raise AppError("演示记录头损坏。")
        source = read_file(directory, "source.cpp", SOURCE_LIMIT).decode("utf-8")
        incoming = read_file(directory, "input.txt", INPUT_LIMIT).decode("utf-8")
        if revision(source) != result.get("source_revision"):
            raise AppError("演示源码快照已损坏。")
        result.update(source=source, input=incoming, log_path=str(directory.relative_to(repo.root)))
        if result["status"] == "READY":
            data = read_file(directory, "visualization.json", TRACE_LIMIT)
            if hashlib.sha256(data).hexdigest() != result.get("trace_sha256"):
                raise AppError("演示步骤快照已损坏，请重新生成。")
            result["trace"] = parse_json(data)
            validate_trace(result["trace"], len(source.splitlines()))
        return result
    except (ValueError, OSError, UnicodeError, RecursionError, KeyError) as error:
        raise AppError(f"无法读取演示记录：{error}") from error


def list_visualizations(repo, name):
    directory = record_path(repo, name)
    records = []
    for path in sorted(directory.glob("*/result.json"), reverse=True):
        try:
            safe = record_path(repo, name, path.parent.name)
            record = parse_json(read_file(safe, "result.json", 128000))
            if record.get("id") != path.parent.name or not all(isinstance(record.get(k), str) for k in ("status", "created_at")):
                continue
            records.append({k: record.get(k) for k in ("id", "status", "created_at", "steps", "input_mode")})
            if len(records) >= 100:
                break
        except (AppError, OSError, ValueError, RecursionError, AttributeError):
            continue
    return records


class VisualizationRunner:
    def __init__(self, repository, execution_lock):
        self.repo = repository
        self.lock = execution_lock

    def run(self, name, input_mode="sample", user_input="", sample=0):
        if input_mode not in ("sample", "manual"):
            raise AppError("请选择题目样例或手动输入。")
        if not isinstance(user_input, str) or len(user_input.encode("utf-8")) > INPUT_LIMIT:
            raise AppError("演示输入不能超过 16 KB。")
        compiler = shutil.which("g++")
        if not compiler:
            raise AppError("没有找到 g++，请安装后重试。", 503)
        if not self.lock.acquire(blocking=False):
            raise AppError("已有程序正在编译或运行，请稍后重试。", 409)
        try:
            return self._run(name, input_mode, user_input, sample, compiler)
        finally:
            self.lock.release()

    def _run(self, name, input_mode, incoming, sample, compiler):
        repo = self.repo
        with repo.lock:
            description = describe_visualization(repo, name)
            if not description["available"]:
                raise AppError(description["error"] or "本题尚未准备演示。")
            path, _ = source_path(repo, name)
            source = path.read_text(encoding="utf-8")
            if input_mode == "sample":
                samples = repo.config(repo.problem(name)).get("samples", [])
                if type(sample) is not int or not 0 <= sample < len(samples):
                    raise AppError("没有这个题目样例。")
                incoming = samples[sample]["input"]
            if len(incoming.encode("utf-8")) > INPUT_LIMIT:
                raise AppError("演示输入不能超过 16 KB。")
        now = datetime.now(timezone.utc)
        run_id = now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + secrets.token_hex(4)
        directory = record_path(repo, name, run_id)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "source.cpp").write_text(source, encoding="utf-8")
        (directory / "input.txt").write_text(incoming, encoding="utf-8")
        (directory / "compile-input.txt").write_text("", encoding="utf-8")
        for filename in ("compile.stdout.txt", "compile.stderr.txt", "stdout.txt", "stderr.txt"):
            (directory / filename).write_text("", encoding="utf-8")
        result = {"id": run_id, "problem": name, "title": description["title"], "status": "RUNNING", "created_at": now.isoformat(),
                  "input_mode": input_mode, "sample": sample if input_mode == "sample" else None,
                  "source_path": str(path.relative_to(repo.root)), "source_revision": revision(source), "steps": 0,
                  "compiler": "", "stdout": "", "stderr": "", "duration_ms": 0, "error": None,
                  "protocol_version": 1, "recorder_sha256": hashlib.sha256((APP_ROOT / "workbench/include/visualization.hpp").read_bytes()).hexdigest()}
        write_json(directory / "result.json", result)
        start = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="algorithm-visualization-") as temp:
                working = Path(temp)
                binary = working / "demo"
                command = [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror=return-type",
                           "-I" + str(APP_ROOT / "workbench/include"), "-I" + str(APP_ROOT / "vendor"),
                           str(directory / "source.cpp"), "-o", str(binary)]
                result["compile_command"] = command
                result["compile"] = execute(command, working, directory / "compile-input.txt", directory / "compile.stdout.txt", directory / "compile.stderr.txt", 20)
                result["compiler"] = preview(directory / "compile.stderr.txt")
                if result["compile"]["timed_out"] or result["compile"]["exit_code"]:
                    result["status"] = "CE"
                    result["error"] = "演示代码编译失败。" if not result["compile"]["timed_out"] else "演示代码编译超过 20 秒。"
                else:
                    result["execution"] = execute([sys.executable, str(APP_ROOT / "workbench/worker.py"), str(binary)], working,
                        directory / "input.txt", directory / "stdout.txt", directory / "stderr.txt", TIMEOUT)
                    result["stdout"], result["stderr"] = preview(directory / "stdout.txt"), preview(directory / "stderr.txt")
                    execution = result["execution"]
                    trace_path = working / "visualization.json"
                    if any((directory / name).stat().st_size >= OUTPUT_LIMIT for name in ("stdout.txt", "stderr.txt")) or execution["exit_code"] == -signal.SIGXFSZ:
                        result.update(status="OLE", error="演示输出超过 4 MiB，请缩小输入。")
                    elif execution["timed_out"] or execution["exit_code"] == -signal.SIGXCPU:
                        result.update(status="TLE", error="演示运行超过 3 秒，已停止。")
                    elif execution["exit_code"]:
                        result.update(status="INPUT_ERROR" if execution["exit_code"] == 2 else "RE",
                                      error="输入不符合演示要求。" if execution["exit_code"] == 2 else "演示程序异常退出。")
                    else:
                        data = read_file(working, "visualization.json", TRACE_LIMIT)
                        (directory / "visualization.partial.json").write_bytes(data)
                        trace = parse_json(data)
                        steps = validate_trace(trace, len(source.splitlines()))
                        (directory / "visualization.json").write_bytes(data)
                        (directory / "visualization.partial.json").unlink()
                        result.update(status="READY", steps=steps, trace_sha256=hashlib.sha256(data).hexdigest())
                    if result["status"] != "READY" and trace_path.is_file() and not trace_path.is_symlink() and trace_path.stat().st_size <= TRACE_LIMIT:
                        shutil.copyfile(trace_path, directory / "visualization.partial.json")
        except Exception as error:
            result.update(status="ERROR", error=f"无法生成完整演示：{error}")
        finally:
            result["duration_ms"] = round((time.monotonic() - start) * 1000)
            write_json(directory / "result.json", result)
        return read_visualization(repo, name, run_id)
